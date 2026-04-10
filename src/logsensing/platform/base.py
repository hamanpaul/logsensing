"""平台抽象基礎模型."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logsensing.analyzer.detector import AnomalyRule


@dataclass(frozen=True)
class MilestoneDef:
    """里程碑定義（平台層級）."""

    name: str
    pattern: str
    is_regex: bool = False
    expected_order: int = 0

    def matches(self, text: str) -> bool:
        """判斷 text 是否命中此里程碑."""
        if self.is_regex:
            return bool(re.search(self.pattern, text))
        return self.pattern in text


@dataclass(frozen=True)
class ChannelDef:
    """Demux channel 定義（平台層級）."""

    name: str
    patterns: list[str] = field(default_factory=list)
    is_regex: bool = False


@dataclass(frozen=True)
class DrainOverride:
    """平台特定 Drain3 參數覆蓋."""

    sim_th: float = 0.4
    depth: int = 4
    max_clusters: int = 1024
    extra_delimiters: list[str] = field(default_factory=lambda: [":", "=", "|"])


@dataclass(frozen=True)
class PlatformProfile:
    """封裝平台所有差異點的 profile."""

    name: str
    display_name: str

    # Boot cycle splitting
    boot_anchors: list[str] = field(default_factory=lambda: ["U-Boot TPL"])
    fallback_anchors: list[str] = field(
        default_factory=lambda: ["Starting kernel", "Booting Linux"]
    )

    # Timestamp extraction
    timestamp_pattern: str | None = None
    timestamp_format: str | None = None
    supports_timing: bool = False

    # Boot milestones (baseline profiler)
    milestones: list[MilestoneDef] = field(default_factory=list)

    # Process/module wake time tracking (reporter)
    processes: list[tuple[str, str]] = field(default_factory=list)

    # Demux channel definitions
    demux_channels: list[ChannelDef] = field(default_factory=list)

    # Platform-specific anomaly rules
    anomaly_rules: list[AnomalyRule] = field(default_factory=list)

    # Drain3 config overrides
    drain_config: DrainOverride = field(default_factory=DrainOverride)

    # Auto-detection fingerprints (patterns scanned in first N lines)
    detect_patterns: list[str] = field(default_factory=list)

    def extract_timestamp(self, line: str) -> datetime | None:
        """從日誌行提取 timestamp，若平台不支援則回傳 None."""
        if not self.timestamp_pattern or not self.timestamp_format:
            return None
        m = re.match(self.timestamp_pattern, line)
        if m:
            return datetime.strptime(m.group(1), self.timestamp_format)
        return None

    def matches_log(self, lines: list[str]) -> int:
        """計算 detect_patterns 在 lines 中的命中數，用於自動偵測."""
        score = 0
        for pat in self.detect_patterns:
            for line in lines:
                if pat in line:
                    score += 1
                    break
        return score
