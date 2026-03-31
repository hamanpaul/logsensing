"""Serialwrap-based reboot powercycle loop."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TextIO

DEFAULT_SERIALWRAP_BIN = os.environ.get(
    "SERIALWRAP_BIN",
    "/home/paul_chen/.paul_tools/serialwrap",
)

RECOVERABLE_STATUSES = {
    "ATTACHED",
    "ATTACHED_NOT_READY",
    "BRIDGE_DOWN",
    "DEVICE_REBOUND_REQUIRED",
    "LOGIN_REQUIRED",
    "TARGET_UNRESPONSIVE",
    "VTTY_STALE",
}
TRANSIENT_STATUSES = {
    "DEVICE_MISSING",
    "REBOOTING",
    "SESSION_RECOVERING",
}


@dataclass(frozen=True)
class PowerCycleConfig:
    """Runtime config for the powercycle loop."""

    selector: str
    count: int | None
    duration_s: float | None
    reboot_cmd: str
    source: str
    serialwrap_bin: str
    cmd_timeout_s: float
    ready_timeout_s: float
    reboot_detect_timeout_s: float
    recover_timeout_s: float
    poll_interval_s: float


def parse_duration(raw: str) -> float:
    """Parse seconds or compact duration strings like 90s/10m/1h30m."""
    text = raw.strip().lower()
    if not text:
        raise argparse.ArgumentTypeError("duration 不可為空")

    total = 0.0
    index = 0
    units = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}
    while index < len(text):
        start = index
        while index < len(text) and text[index].isdigit():
            index += 1
        if start == index:
            raise argparse.ArgumentTypeError(f"無法解析 duration: {raw}")
        value = int(text[start:index])
        unit = ""
        if index < len(text) and text[index].isalpha():
            unit = text[index]
            index += 1
        if unit not in units:
            raise argparse.ArgumentTypeError(f"不支援的 duration 單位: {unit}")
        total += value * units[unit]

    if total <= 0:
        raise argparse.ArgumentTypeError("duration 必須大於 0")
    return total


def positive_int(raw: str) -> int:
    """Parse a strictly positive integer."""
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("值必須大於 0")
    return value


def positive_float(raw: str) -> float:
    """Parse a strictly positive float."""
    value = float(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("值必須大於 0")
    return value


def _payload_status(payload: dict[str, Any]) -> str | None:
    """Extract a best-effort status string from a serialwrap JSON payload."""
    for key in ("status", "result", "outcome", "error_code"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value.upper()
    session = payload.get("session")
    if isinstance(session, dict):
        value = session.get("state")
        if isinstance(value, str) and value:
            return value.upper()
    return None


def _session_state(session: dict[str, Any] | None) -> str | None:
    """Normalize a session state's text."""
    if session is None:
        return None
    value = session.get("state")
    if isinstance(value, str) and value:
        return value.upper()
    return None


def _match_selector(session: dict[str, Any], selector: str) -> bool:
    """Match selector against COM/session_id/alias."""
    return selector in {
        session.get("com"),
        session.get("session_id"),
        session.get("alias"),
    }


class SerialwrapClient:
    """Thin wrapper around the serialwrap CLI."""

    def __init__(self, binary: str) -> None:
        self.binary = binary

    def _run_json(
        self,
        args: list[str],
        *,
        allow_error: bool = False,
    ) -> dict[str, Any]:
        result = subprocess.run(
            [self.binary, *args],
            capture_output=True,
            text=True,
            check=False,
        )
        payload = _parse_json_output(result.stdout)
        if result.returncode != 0 and not allow_error:
            raise RuntimeError(
                f"serialwrap {' '.join(args)} failed ({result.returncode})\n"
                f"stdout: {result.stdout.strip()}\n"
                f"stderr: {result.stderr.strip()}"
            )
        if result.returncode != 0:
            payload.setdefault("_returncode", result.returncode)
            payload.setdefault("_stderr", result.stderr.strip())
        return payload

    def daemon_status(self) -> dict[str, Any]:
        return self._run_json(["daemon", "status"])

    def list_sessions(self) -> list[dict[str, Any]]:
        payload = self._run_json(["session", "list"])
        sessions = payload.get("sessions", [])
        if not isinstance(sessions, list):
            raise RuntimeError("serialwrap session list 回傳格式不正確")
        return [entry for entry in sessions if isinstance(entry, dict)]

    def find_session(self, selector: str) -> dict[str, Any] | None:
        for session in self.list_sessions():
            if _match_selector(session, selector):
                return session
        return None

    def self_test(self, selector: str) -> dict[str, Any]:
        return self._run_json(
            ["session", "self-test", "--selector", selector],
            allow_error=True,
        )

    def recover(self, selector: str, timeout_s: float) -> dict[str, Any]:
        return self._run_json(
            [
                "session",
                "recover",
                "--selector",
                selector,
                "--timeout",
                str(timeout_s),
            ],
            allow_error=True,
        )

    def submit_command(
        self,
        selector: str,
        cmd: str,
        source: str,
        cmd_timeout_s: float,
    ) -> dict[str, Any]:
        return self._run_json(
            [
                "cmd",
                "submit",
                "--selector",
                selector,
                "--cmd",
                cmd,
                "--source",
                source,
                "--mode",
                "line",
                "--cmd-timeout",
                str(cmd_timeout_s),
            ],
            allow_error=True,
        )


def _parse_json_output(stdout: str) -> dict[str, Any]:
    """Parse CLI stdout as JSON."""
    text = stdout.strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        last_line = text.splitlines()[-1]
        payload = json.loads(last_line)
    if not isinstance(payload, dict):
        raise RuntimeError(f"serialwrap JSON 輸出不是 object: {payload!r}")
    return payload


def check_daemon_health(client: SerialwrapClient) -> None:
    """Ensure serialwrap daemon is up before touching the session."""
    payload = client.daemon_status()
    if payload.get("ok") is not True or payload.get("running") is not True:
        raise RuntimeError("serialwrap daemon 未就緒，請先確認 serialwrapd 已啟動")


def ensure_session_exists(client: SerialwrapClient, selector: str) -> None:
    """Fail early if the selector does not map to a known session."""
    if client.find_session(selector) is None:
        raise RuntimeError(
            f"找不到 selector={selector} 的 serialwrap session；"
            "請先完成 session bind/attach 並確認 session list 可見"
        )


def ensure_session_ready(
    client: SerialwrapClient,
    config: PowerCycleConfig,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Wait until the target session becomes READY."""
    ensure_session_exists(client, config.selector)
    deadline = monotonic() + config.ready_timeout_s
    last_status = "UNKNOWN"
    last_recover_at: float | None = None

    while monotonic() < deadline:
        session = client.find_session(config.selector)
        session_state = _session_state(session)
        if session_state == "READY":
            return

        payload = client.self_test(config.selector)
        observed = _payload_status(payload)
        if observed == "OK":
            return
        if observed:
            last_status = observed
        elif session_state:
            last_status = session_state

        if observed in RECOVERABLE_STATUSES and (
            last_recover_at is None or monotonic() - last_recover_at >= config.poll_interval_s
        ):
            client.recover(config.selector, config.recover_timeout_s)
            last_recover_at = monotonic()

        sleep(config.poll_interval_s)

    raise TimeoutError(
        f"session {config.selector} 在 {config.ready_timeout_s:.0f}s 內未進入 READY "
        f"(last_status={last_status})"
    )


def wait_for_reboot_cycle(
    client: SerialwrapClient,
    config: PowerCycleConfig,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> float:
    """Wait until reboot is observed and the session returns to READY."""
    ensure_session_exists(client, config.selector)
    cycle_start = monotonic()
    detect_deadline = cycle_start + config.reboot_detect_timeout_s
    ready_deadline = cycle_start + config.ready_timeout_s
    saw_not_ready = False
    last_status = "READY"
    last_recover_at: float | None = None

    while monotonic() < ready_deadline:
        session = client.find_session(config.selector)
        session_state = _session_state(session)

        payload = client.self_test(config.selector)
        observed = _payload_status(payload)
        normalized = "READY" if observed == "OK" else observed or session_state or "UNKNOWN"
        last_status = normalized

        if normalized != "READY":
            saw_not_ready = True

        if saw_not_ready and normalized == "READY":
            return monotonic() - cycle_start

        if not saw_not_ready and monotonic() >= detect_deadline:
            raise TimeoutError(
                f"已送出 reboot，但在 {config.reboot_detect_timeout_s:.0f}s 內"
                "未觀察到 session 離開 READY"
            )

        if saw_not_ready and normalized in RECOVERABLE_STATUSES and (
            last_recover_at is None or monotonic() - last_recover_at >= config.poll_interval_s
        ):
            client.recover(config.selector, config.recover_timeout_s)
            last_recover_at = monotonic()

        sleep(config.poll_interval_s)

    raise TimeoutError(
        f"session {config.selector} reboot 後在 {config.ready_timeout_s:.0f}s 內"
        f"未回到 READY (last_status={last_status})"
    )


def run_powercycle(
    client: SerialwrapClient,
    config: PowerCycleConfig,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    stdout: TextIO = sys.stdout,
) -> int:
    """Execute reboot cycles until count or duration limit is reached."""
    check_daemon_health(client)
    ensure_session_ready(client, config, monotonic=monotonic, sleep=sleep)

    started_at = monotonic()
    cycles_completed = 0

    _write_line(
        stdout,
        (
            f"Start powercycle: selector={config.selector}, "
            f"count={config.count or '-'}, duration={_format_duration(config.duration_s)}"
        ),
    )

    while True:
        elapsed = monotonic() - started_at
        if config.count is not None and cycles_completed >= config.count:
            reason = "count"
            break
        if config.duration_s is not None and elapsed >= config.duration_s:
            reason = "duration"
            break

        cycle_no = cycles_completed + 1
        _write_line(stdout, f"[cycle {cycle_no}] submit reboot: {config.reboot_cmd}")
        payload = client.submit_command(
            config.selector,
            config.reboot_cmd,
            config.source,
            config.cmd_timeout_s,
        )
        cmd_id = payload.get("cmd_id")
        if not isinstance(cmd_id, str) or not cmd_id:
            raise RuntimeError(f"serialwrap reboot submit 未回傳 cmd_id: {payload}")

        reboot_elapsed = wait_for_reboot_cycle(
            client,
            config,
            monotonic=monotonic,
            sleep=sleep,
        )
        cycles_completed += 1
        total_elapsed = monotonic() - started_at
        _write_line(
            stdout,
            (
                f"[cycle {cycle_no}] ready again, cmd_id={cmd_id}, "
                f"reboot_elapsed={reboot_elapsed:.1f}s, total_elapsed={total_elapsed:.1f}s"
            ),
        )

    total_elapsed = monotonic() - started_at
    _write_line(
        stdout,
        (
            f"Done: completed_cycles={cycles_completed}, "
            f"reason={reason}, total_elapsed={total_elapsed:.1f}s"
        ),
    )
    return cycles_completed


def _format_duration(duration_s: float | None) -> str:
    if duration_s is None:
        return "-"
    return f"{duration_s:.0f}s"


def _write_line(stdout: TextIO, message: str) -> None:
    stdout.write(message + "\n")
    stdout.flush()


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse CLI parser."""
    parser = argparse.ArgumentParser(
        description="透過 serialwrap 在指定 COM/session 上做 reboot powercycle 模擬",
    )
    parser.add_argument(
        "--selector",
        "--port",
        dest="selector",
        required=True,
        help="serialwrap selector，可用 COMx / session_id / alias",
    )
    parser.add_argument(
        "--count",
        type=positive_int,
        default=None,
        help="測試次數上限",
    )
    parser.add_argument(
        "--duration",
        type=parse_duration,
        default=None,
        help="測試時間上限，支援 3600 / 30s / 10m / 1h30m",
    )
    parser.add_argument(
        "--reboot-cmd",
        default="reboot",
        help="送到 target 的 reboot 指令",
    )
    parser.add_argument(
        "--source",
        default="agent:powercycle",
        help="serialwrap source 欄位",
    )
    parser.add_argument(
        "--serialwrap-bin",
        default=DEFAULT_SERIALWRAP_BIN,
        help="serialwrap CLI 路徑",
    )
    parser.add_argument(
        "--cmd-timeout",
        type=positive_float,
        default=5.0,
        help="reboot 指令的 serialwrap cmd-timeout（秒）",
    )
    parser.add_argument(
        "--ready-timeout",
        type=positive_float,
        default=180.0,
        help="每輪 reboot 後等待 session 回到 READY 的上限秒數",
    )
    parser.add_argument(
        "--reboot-detect-timeout",
        type=positive_float,
        default=20.0,
        help="送出 reboot 後，等待 session 離開 READY 的上限秒數",
    )
    parser.add_argument(
        "--recover-timeout",
        type=positive_float,
        default=30.0,
        help="session recover timeout（秒）",
    )
    parser.add_argument(
        "--poll-interval",
        type=positive_float,
        default=2.0,
        help="輪詢 session/self-test 的間隔秒數",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.count is None and args.duration is None:
        parser.error("至少要指定 --count 或 --duration 其中一個")

    config = PowerCycleConfig(
        selector=args.selector,
        count=args.count,
        duration_s=args.duration,
        reboot_cmd=args.reboot_cmd,
        source=args.source,
        serialwrap_bin=args.serialwrap_bin,
        cmd_timeout_s=args.cmd_timeout,
        ready_timeout_s=args.ready_timeout,
        reboot_detect_timeout_s=args.reboot_detect_timeout,
        recover_timeout_s=args.recover_timeout,
        poll_interval_s=args.poll_interval,
    )
    client = SerialwrapClient(config.serialwrap_bin)
    try:
        run_powercycle(client, config)
    except (RuntimeError, TimeoutError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
