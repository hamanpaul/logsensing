"""Tests for the serialwrap powercycle script."""

from __future__ import annotations

import io

import pytest

from logsensing.serialwrap_powercycle import (
    PowerCycleConfig,
    ensure_session_ready,
    parse_duration,
    run_powercycle,
    wait_for_reboot_cycle,
)


class FakeClock:
    """Simple monotonic clock for deterministic tests."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class FakeClient:
    """A fake serialwrap client for control-flow tests."""

    def __init__(self) -> None:
        self.submit_calls: list[tuple[str, str, str, float]] = []
        self.recover_calls: int = 0
        self.self_test_statuses: list[str] = []

    def daemon_status(self) -> dict[str, object]:
        return {"ok": True, "running": True}

    def find_session(self, selector: str) -> dict[str, str] | None:
        if self.self_test_statuses and self.self_test_statuses[0] != "OK":
            return {"com": selector, "state": "RECOVERING"}
        return {"com": selector, "state": "READY"}

    def self_test(self, selector: str) -> dict[str, str]:
        if self.self_test_statuses:
            return {"status": self.self_test_statuses.pop(0)}
        return {"status": "OK"}

    def recover(self, selector: str, timeout_s: float) -> dict[str, object]:
        self.recover_calls += 1
        return {"status": "OK", "selector": selector, "timeout": timeout_s}

    def submit_command(
        self,
        selector: str,
        cmd: str,
        source: str,
        cmd_timeout_s: float,
    ) -> dict[str, str]:
        self.submit_calls.append((selector, cmd, source, cmd_timeout_s))
        self.self_test_statuses.extend(["REBOOTING", "OK"])
        return {"cmd_id": f"cmd-{len(self.submit_calls)}"}


def make_config(
    *,
    count: int | None,
    duration_s: float | None,
) -> PowerCycleConfig:
    return PowerCycleConfig(
        selector="COM9",
        count=count,
        duration_s=duration_s,
        reboot_cmd="reboot",
        source="agent:powercycle",
        serialwrap_bin="serialwrap",
        cmd_timeout_s=5.0,
        ready_timeout_s=60.0,
        reboot_detect_timeout_s=10.0,
        recover_timeout_s=10.0,
        poll_interval_s=1.0,
    )


def test_parse_duration_supports_compound_units() -> None:
    assert parse_duration("90") == 90
    assert parse_duration("10m") == 600
    assert parse_duration("1h30m") == 5400


def test_ensure_session_ready_recovers_when_not_ready() -> None:
    client = FakeClient()
    client.self_test_statuses = ["ATTACHED_NOT_READY", "OK"]
    clock = FakeClock()

    ensure_session_ready(
        client,
        make_config(count=1, duration_s=None),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    assert client.recover_calls == 1


def test_wait_for_reboot_cycle_requires_transition() -> None:
    client = FakeClient()
    clock = FakeClock()

    with pytest.raises(TimeoutError):
        wait_for_reboot_cycle(
            client,
            make_config(count=1, duration_s=None),
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )


def test_run_powercycle_stops_on_count_before_duration() -> None:
    client = FakeClient()
    clock = FakeClock()
    stdout = io.StringIO()

    completed = run_powercycle(
        client,
        make_config(count=2, duration_s=100.0),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        stdout=stdout,
    )

    assert completed == 2
    assert len(client.submit_calls) == 2
    assert "reason=count" in stdout.getvalue()


def test_run_powercycle_stops_when_duration_reaches_first() -> None:
    client = FakeClient()
    clock = FakeClock()
    stdout = io.StringIO()

    completed = run_powercycle(
        client,
        make_config(count=99, duration_s=1.5),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        stdout=stdout,
    )

    assert completed == 2
    assert len(client.submit_calls) == 2
    assert "reason=duration" in stdout.getvalue()
