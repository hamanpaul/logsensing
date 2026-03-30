"""Demultiplexer - 將解析後日誌行依模組前綴或 PID 分流至虛擬 channel."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from logsensing.parser.drain import ParsedLine
    from logsensing.platform.base import PlatformProfile


@dataclass
class ChannelDef:
    """Channel 定義，用於分流規則."""

    name: str  # Channel 名稱 (e.g., "wifi", "rpc", "kernel")
    patterns: list[str]  # 模組名稱比對模式 (精確或正規表示式)
    is_regex: bool = False  # 若為 True, patterns 以 regex 比對

    def __post_init__(self) -> None:
        """預編譯 regex patterns 以提升效能."""
        if self.is_regex:
            self._compiled: list[re.Pattern[str]] = [
                re.compile(p, re.IGNORECASE) for p in self.patterns
            ]
        else:
            self._compiled = []


@dataclass
class Channel:
    """虛擬 channel，收集分流後的日誌行."""

    name: str
    lines: list[ParsedLine] = field(default_factory=list)

    @property
    def line_count(self) -> int:
        """回傳 channel 中的行數."""
        return len(self.lines)


class Demultiplexer:
    """將解析後日誌行依 module 前綴分流至虛擬 channel.

    使用方式::

        demuxer = Demultiplexer()
        channels = demuxer.demux(parsed_lines)
        for name, ch in channels.items():
            print(f"{name}: {ch.line_count} lines")
    """

    # 基於 BGW720-300 日誌分析的預設 channel 定義
    DEFAULT_CHANNELS: ClassVar[list[ChannelDef]] = [
        ChannelDef(
            name="wifi",
            patterns=["wl0", "wl1", "wl2", "CFG80211", "acsd"],
            is_regex=False,
        ),
        ChannelDef(
            name="dhd",
            patterns=[r"dhd.*", r"dhdpcie.*"],
            is_regex=True,
        ),
        ChannelDef(
            name="rpc",
            patterns=["RPC", "ARMTF RPC"],
            is_regex=False,
        ),
        ChannelDef(
            name="pcie",
            patterns=[r"bcm-pcie", r"pci\s"],
            is_regex=True,
        ),
        ChannelDef(
            name="network",
            patterns=[r"tc_netdev.*", "br0", "NET", "IPv6", r"e1000e", r"ixgbe"],
            is_regex=True,
        ),
        ChannelDef(
            name="kernel",
            patterns=["SMCOS", "SBF", "printk", "kfence"],
            is_regex=False,
        ),
        ChannelDef(
            name="offload",
            patterns=["dol0", "dol1", "dol2", "fcache"],
            is_regex=False,
        ),
    ]

    def __init__(self, channel_defs: list[ChannelDef] | None = None) -> None:
        """初始化 Demultiplexer.

        Args:
            channel_defs: 自訂 channel 定義，若為 None 則使用 DEFAULT_CHANNELS。
        """
        self._channel_defs = channel_defs if channel_defs is not None else self.DEFAULT_CHANNELS

    @classmethod
    def from_platform(cls, platform: PlatformProfile) -> Demultiplexer:
        """從 PlatformProfile 建立 Demultiplexer."""
        if platform.demux_channels:
            # 轉換 platform ChannelDef → demux ChannelDef
            defs = []
            for pcd in platform.demux_channels:
                defs.append(ChannelDef(
                    name=pcd.name,
                    patterns=list(pcd.patterns),
                    is_regex=pcd.is_regex,
                ))
            return cls(channel_defs=defs)
        return cls()

    @property
    def channel_defs(self) -> list[ChannelDef]:
        """回傳目前使用的 channel 定義."""
        return self._channel_defs

    def demux(self, lines: Iterator[ParsedLine]) -> dict[str, Channel]:
        """將解析後日誌行分流至各 channel.

        Args:
            lines: ParsedLine 的迭代器。

        Returns:
            channel 名稱到 Channel 物件的字典，包含 "other" channel。
        """
        channels: dict[str, Channel] = {
            cd.name: Channel(name=cd.name) for cd in self._channel_defs
        }
        channels["other"] = Channel(name="other")

        for line in lines:
            ch_name = self._match_channel(line.module)
            channels[ch_name].lines.append(line)

        return channels

    def demux_single(self, parsed_line: ParsedLine) -> str:
        """回傳單一 ParsedLine 對應的 channel 名稱.

        Args:
            parsed_line: 解析後的日誌行。

        Returns:
            匹配的 channel 名稱，若無匹配則為 "other"。
        """
        return self._match_channel(parsed_line.module)

    def _match_channel(self, module: str | None) -> str:
        """找出 module 名稱對應的 channel.

        Args:
            module: 日誌行的模組名稱，可為 None。

        Returns:
            匹配的 channel 名稱，若無匹配或 module 為 None 則回傳 "other"。
        """
        if module is None:
            return "other"

        for cd in self._channel_defs:
            if cd.is_regex:
                for compiled in cd._compiled:
                    if compiled.fullmatch(module):
                        return cd.name
            else:
                if module in cd.patterns:
                    return cd.name

        return "other"
