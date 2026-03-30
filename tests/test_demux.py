"""Demultiplexer 單元測試."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from logsensing.parser.demux import Channel, ChannelDef, Demultiplexer


# ---------------------------------------------------------------------------
# 輕量 ParsedLine mock, 避免依賴完整 drain 模組
# ---------------------------------------------------------------------------
@dataclass
class MockParsedLine:
    """測試用的 ParsedLine 替身."""

    raw: str = ""
    content: str = ""
    template_id: int = 0
    template: str = ""
    params: list[str] | None = None
    timestamp: datetime | None = None
    pid: int | None = None
    module: str | None = None
    line_number: int = 0

    def __post_init__(self) -> None:
        if self.params is None:
            self.params = []


def _make_line(module: str | None, line_number: int = 0) -> MockParsedLine:
    """快速建立測試用 ParsedLine."""
    return MockParsedLine(
        raw=f"[{module}] test log line",
        content="test log line",
        module=module,
        line_number=line_number,
    )


# ---------------------------------------------------------------------------
# 1. 預設 channel 定義
# ---------------------------------------------------------------------------
class TestDefaultChannelDefs:
    """驗證預設 channel 定義完整性."""

    def test_default_channels_exist(self) -> None:
        demuxer = Demultiplexer()
        names = [cd.name for cd in demuxer.channel_defs]
        assert "wifi" in names
        assert "dhd" in names
        assert "rpc" in names
        assert "pcie" in names
        assert "network" in names
        assert "kernel" in names
        assert "offload" in names

    def test_default_channels_count(self) -> None:
        demuxer = Demultiplexer()
        assert len(demuxer.channel_defs) == 7

    def test_uses_default_when_none(self) -> None:
        demuxer = Demultiplexer(channel_defs=None)
        assert demuxer.channel_defs is Demultiplexer.DEFAULT_CHANNELS


# ---------------------------------------------------------------------------
# 2. 精確比對
# ---------------------------------------------------------------------------
class TestExactMatching:
    """驗證精確字串比對."""

    def test_wifi_exact_match(self) -> None:
        demuxer = Demultiplexer()
        assert demuxer._match_channel("wl0") == "wifi"
        assert demuxer._match_channel("wl1") == "wifi"
        assert demuxer._match_channel("wl2") == "wifi"
        assert demuxer._match_channel("CFG80211") == "wifi"
        assert demuxer._match_channel("acsd") == "wifi"

    def test_rpc_exact_match(self) -> None:
        demuxer = Demultiplexer()
        assert demuxer._match_channel("RPC") == "rpc"
        assert demuxer._match_channel("ARMTF RPC") == "rpc"

    def test_kernel_exact_match(self) -> None:
        demuxer = Demultiplexer()
        assert demuxer._match_channel("SMCOS") == "kernel"
        assert demuxer._match_channel("SBF") == "kernel"
        assert demuxer._match_channel("printk") == "kernel"
        assert demuxer._match_channel("kfence") == "kernel"

    def test_offload_exact_match(self) -> None:
        demuxer = Demultiplexer()
        assert demuxer._match_channel("dol0") == "offload"
        assert demuxer._match_channel("fcache") == "offload"

    def test_exact_no_partial(self) -> None:
        """精確比對不應部分匹配."""
        demuxer = Demultiplexer()
        # "wl0_extra" 不等於 "wl0", 應歸入 other
        assert demuxer._match_channel("wl0_extra") == "other"


# ---------------------------------------------------------------------------
# 3. Regex 比對
# ---------------------------------------------------------------------------
class TestRegexMatching:
    """驗證正規表示式比對."""

    def test_dhd_regex(self) -> None:
        demuxer = Demultiplexer()
        assert demuxer._match_channel("dhd0") == "dhd"
        assert demuxer._match_channel("dhd_runner") == "dhd"
        assert demuxer._match_channel("dhdpcie0") == "dhd"

    def test_pcie_regex(self) -> None:
        demuxer = Demultiplexer()
        assert demuxer._match_channel("bcm-pcie") == "pcie"
        assert demuxer._match_channel("pci ") == "pcie"

    def test_network_regex(self) -> None:
        demuxer = Demultiplexer()
        assert demuxer._match_channel("tc_netdev0") == "network"
        assert demuxer._match_channel("br0") == "network"
        assert demuxer._match_channel("NET") == "network"
        assert demuxer._match_channel("IPv6") == "network"
        assert demuxer._match_channel("e1000e") == "network"
        assert demuxer._match_channel("ixgbe") == "network"

    def test_regex_fullmatch(self) -> None:
        """Regex 使用 fullmatch，不應部分匹配."""
        demuxer = Demultiplexer()
        # "prefix_dhd0" 不應 fullmatch r"dhd.*"
        assert demuxer._match_channel("prefix_dhd0") == "other"


# ---------------------------------------------------------------------------
# 4. 無匹配行歸入 "other"
# ---------------------------------------------------------------------------
class TestOtherChannel:
    """驗證未匹配行歸入 other."""

    def test_none_module_goes_to_other(self) -> None:
        demuxer = Demultiplexer()
        assert demuxer._match_channel(None) == "other"

    def test_unknown_module_goes_to_other(self) -> None:
        demuxer = Demultiplexer()
        assert demuxer._match_channel("some_unknown_module") == "other"

    def test_empty_string_goes_to_other(self) -> None:
        demuxer = Demultiplexer()
        assert demuxer._match_channel("") == "other"

    def test_other_channel_always_in_demux_result(self) -> None:
        demuxer = Demultiplexer()
        channels = demuxer.demux(iter([]))
        assert "other" in channels


# ---------------------------------------------------------------------------
# 5. 自訂 channel 定義
# ---------------------------------------------------------------------------
class TestCustomChannelDefs:
    """驗證自訂 channel 定義."""

    def test_custom_exact_channel(self) -> None:
        custom = [ChannelDef(name="myapp", patterns=["APP", "MYAPP"], is_regex=False)]
        demuxer = Demultiplexer(channel_defs=custom)

        assert demuxer._match_channel("APP") == "myapp"
        assert demuxer._match_channel("MYAPP") == "myapp"
        assert demuxer._match_channel("OTHER") == "other"

    def test_custom_regex_channel(self) -> None:
        custom = [ChannelDef(name="service", patterns=[r"svc_.*"], is_regex=True)]
        demuxer = Demultiplexer(channel_defs=custom)

        assert demuxer._match_channel("svc_auth") == "service"
        assert demuxer._match_channel("svc_") == "service"
        assert demuxer._match_channel("nosvc_auth") == "other"

    def test_custom_replaces_defaults(self) -> None:
        custom = [ChannelDef(name="only", patterns=["ONLY"], is_regex=False)]
        demuxer = Demultiplexer(channel_defs=custom)

        assert len(demuxer.channel_defs) == 1
        # 預設的 wifi channel 不應存在
        assert demuxer._match_channel("wl0") == "other"

    def test_first_match_wins(self) -> None:
        custom = [
            ChannelDef(name="first", patterns=["FOO"], is_regex=False),
            ChannelDef(name="second", patterns=["FOO"], is_regex=False),
        ]
        demuxer = Demultiplexer(channel_defs=custom)
        assert demuxer._match_channel("FOO") == "first"


# ---------------------------------------------------------------------------
# 6. demux_single 方法
# ---------------------------------------------------------------------------
class TestDemuxSingle:
    """驗證 demux_single 方法."""

    def test_returns_channel_name(self) -> None:
        demuxer = Demultiplexer()
        line = _make_line("wl0")
        assert demuxer.demux_single(line) == "wifi"

    def test_returns_other_for_none_module(self) -> None:
        demuxer = Demultiplexer()
        line = _make_line(None)
        assert demuxer.demux_single(line) == "other"

    def test_returns_other_for_unknown(self) -> None:
        demuxer = Demultiplexer()
        line = _make_line("unknown_module")
        assert demuxer.demux_single(line) == "other"

    def test_regex_channel_via_single(self) -> None:
        demuxer = Demultiplexer()
        line = _make_line("dhd0")
        assert demuxer.demux_single(line) == "dhd"


# ---------------------------------------------------------------------------
# 7. demux 整合測試 - 使用 mock ParsedLine
# ---------------------------------------------------------------------------
class TestDemuxIntegration:
    """驗證 demux 方法的完整分流邏輯."""

    def test_basic_demux(self) -> None:
        lines = [
            _make_line("wl0", 1),
            _make_line("wl1", 2),
            _make_line("RPC", 3),
            _make_line("dhd0", 4),
            _make_line("unknown", 5),
            _make_line(None, 6),
        ]
        demuxer = Demultiplexer()
        channels = demuxer.demux(iter(lines))

        assert channels["wifi"].line_count == 2
        assert channels["rpc"].line_count == 1
        assert channels["dhd"].line_count == 1
        assert channels["other"].line_count == 2

    def test_empty_input(self) -> None:
        demuxer = Demultiplexer()
        channels = demuxer.demux(iter([]))

        # 所有 channel 應存在但為空
        for ch in channels.values():
            assert ch.line_count == 0
        assert "other" in channels

    def test_all_channels_present(self) -> None:
        demuxer = Demultiplexer()
        channels = demuxer.demux(iter([_make_line("wl0")]))

        expected = {"wifi", "dhd", "rpc", "pcie", "network", "kernel", "offload", "other"}
        assert set(channels.keys()) == expected

    def test_lines_preserved_in_order(self) -> None:
        lines = [_make_line("wl0", i) for i in range(5)]
        demuxer = Demultiplexer()
        channels = demuxer.demux(iter(lines))

        wifi_numbers = [ln.line_number for ln in channels["wifi"].lines]
        assert wifi_numbers == [0, 1, 2, 3, 4]

    def test_channel_line_count_property(self) -> None:
        ch = Channel(name="test")
        assert ch.line_count == 0
        ch.lines.append(_make_line("x"))
        assert ch.line_count == 1
