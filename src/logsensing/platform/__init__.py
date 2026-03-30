"""平台抽象模組 — 封裝平台差異點的 profile 機制."""

from logsensing.platform.base import (
    ChannelDef,
    DrainOverride,
    MilestoneDef,
    PlatformProfile,
)
from logsensing.platform.bdk import BDK_PROFILE
from logsensing.platform.prplos import PRPLOS_PROFILE
from logsensing.platform.registry import (
    auto_detect,
    get_platform,
    list_platforms,
    register,
    resolve_platform,
)

__all__ = [
    "BDK_PROFILE",
    "PRPLOS_PROFILE",
    "ChannelDef",
    "DrainOverride",
    "MilestoneDef",
    "PlatformProfile",
    "auto_detect",
    "get_platform",
    "list_platforms",
    "register",
    "resolve_platform",
]
