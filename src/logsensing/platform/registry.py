"""平台註冊與自動偵測."""

from __future__ import annotations

from pathlib import Path

from logsensing.platform.base import PlatformProfile
from logsensing.platform.bdk import BDK_PROFILE
from logsensing.platform.prplos import PRPLOS_PROFILE

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
_REGISTRY: dict[str, PlatformProfile] = {
    BDK_PROFILE.name: BDK_PROFILE,
    PRPLOS_PROFILE.name: PRPLOS_PROFILE,
}


def register(profile: PlatformProfile) -> None:
    """註冊自訂平台 profile."""
    _REGISTRY[profile.name] = profile


def get_platform(name: str) -> PlatformProfile:
    """依名稱取得平台 profile.

    Raises:
        KeyError: 若平台名稱不存在。
    """
    return _REGISTRY[name]


def list_platforms() -> list[str]:
    """列出所有已註冊平台名稱."""
    return list(_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------
_SCAN_LINES = 2000


def auto_detect(
    logfile: Path,
    *,
    scan_lines: int = _SCAN_LINES,
) -> PlatformProfile:
    """掃描日誌前 N 行自動偵測平台.

    若無法判定，預設回傳 BDK profile。
    """
    head: list[str] = []
    with open(logfile, encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            if i >= scan_lines:
                break
            head.append(line)

    best_name = BDK_PROFILE.name
    best_score = 0

    for profile in _REGISTRY.values():
        score = profile.matches_log(head)
        if score > best_score:
            best_score = score
            best_name = profile.name

    return _REGISTRY[best_name]


def resolve_platform(
    platform_name: str | None,
    logfile: Path | None = None,
) -> PlatformProfile:
    """解析平台：明確指定 > auto-detect > 預設 BDK.

    Args:
        platform_name: "auto", 平台名稱, 或 None。
        logfile: 用於 auto-detect 的日誌檔案路徑。
    """
    if platform_name and platform_name != "auto":
        return get_platform(platform_name)

    if logfile and logfile.exists():
        return auto_detect(logfile)

    return BDK_PROFILE
