"""StreamSplitter 單元測試."""

from __future__ import annotations

import io
import textwrap
from datetime import datetime
from pathlib import Path

import pytest

from logsensing.parser.splitter import StreamSplitter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_LOG = textwrap.dedent("""\
    [2026-03-18 13:54:42.819] printenv
    [2026-03-18 13:54:44.646] COMMITTED=1
    [2026-03-18 13:55:35.815] U-Boot TPL 2024.04 (Feb 26 2026 - 10:48:29 +0800)
    [2026-03-18 13:55:36.000] Trying to boot from MMC1
    [2026-03-18 13:55:37.000] Loading kernel ...
    [2026-03-18 13:56:07.651] U-Boot TPL 2024.04 (Feb 26 2026 - 10:48:29 +0800)
    [2026-03-18 13:56:08.000] Second boot starting
""")

SAMPLE_LOG_PATH = Path(
    "/home/paul_chen/prj_arc/logsensing/docs/sample_logs/"
    "20260318_ATT_newHW7-normal_1354.log"
)


@pytest.fixture()
def splitter() -> StreamSplitter:
    return StreamSplitter()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSplitSmallLog:
    """基本切割：已知錨點的小型合成日誌。"""

    def test_split_yields_three_cycles(self, splitter: StreamSplitter) -> None:
        cycles = list(splitter.split(io.StringIO(SAMPLE_LOG)))
        assert len(cycles) == 3

    def test_cycle_id_increments(self, splitter: StreamSplitter) -> None:
        cycles = list(splitter.split(io.StringIO(SAMPLE_LOG)))
        assert [c.cycle_id for c in cycles] == [0, 1, 2]

    def test_pre_boot_cycle(self, splitter: StreamSplitter) -> None:
        cycles = list(splitter.split(io.StringIO(SAMPLE_LOG)))
        pre = cycles[0]
        assert pre.cycle_id == 0
        assert pre.start_line == 0
        assert pre.end_line == 2
        assert pre.line_count == 2
        assert pre.anchor_line == ""

    def test_first_boot_cycle(self, splitter: StreamSplitter) -> None:
        cycles = list(splitter.split(io.StringIO(SAMPLE_LOG)))
        c1 = cycles[1]
        assert c1.cycle_id == 1
        assert c1.start_line == 2
        assert c1.end_line == 5
        assert c1.line_count == 3
        assert "U-Boot TPL" in c1.anchor_line

    def test_second_boot_cycle(self, splitter: StreamSplitter) -> None:
        cycles = list(splitter.split(io.StringIO(SAMPLE_LOG)))
        c2 = cycles[2]
        assert c2.cycle_id == 2
        assert c2.start_line == 5
        assert c2.end_line == 7
        assert c2.line_count == 2

    def test_timestamps_tracked(self, splitter: StreamSplitter) -> None:
        cycles = list(splitter.split(io.StringIO(SAMPLE_LOG)))
        pre = cycles[0]
        assert pre.timestamp_start == datetime(2026, 3, 18, 13, 54, 42, 819000)
        assert pre.timestamp_end == datetime(2026, 3, 18, 13, 54, 44, 646000)

        c1 = cycles[1]
        assert c1.timestamp_start == datetime(2026, 3, 18, 13, 55, 35, 815000)
        assert c1.timestamp_end == datetime(2026, 3, 18, 13, 55, 37, 0)


class TestTimestampParsing:
    """_parse_timestamp 方法測試。"""

    def test_valid_timestamp(self, splitter: StreamSplitter) -> None:
        ts = splitter._parse_timestamp("[2026-03-18 13:54:42.819] hello")
        assert ts == datetime(2026, 3, 18, 13, 54, 42, 819000)

    def test_no_timestamp(self, splitter: StreamSplitter) -> None:
        assert splitter._parse_timestamp("no timestamp here") is None

    def test_malformed_timestamp(self, splitter: StreamSplitter) -> None:
        assert splitter._parse_timestamp("[9999-99-99 99:99:99.999] bad") is None


class TestIsAnchor:
    """_is_anchor 方法測試。"""

    def test_default_anchor_matches(self, splitter: StreamSplitter) -> None:
        assert splitter._is_anchor("[2026-03-18 13:55:35.815] U-Boot TPL 2024.04")

    def test_no_anchor(self, splitter: StreamSplitter) -> None:
        assert not splitter._is_anchor("[2026-03-18 13:55:35.815] Loading kernel ...")

    def test_custom_anchor(self) -> None:
        sp = StreamSplitter(anchors=["BOOT_START"])
        assert sp._is_anchor("xxx BOOT_START yyy")
        assert not sp._is_anchor("U-Boot TPL something")


class TestReadCycleLines:
    """read_cycle_lines 從檔案讀取指定 cycle 的行。"""

    def test_read_cycle(self, splitter: StreamSplitter, tmp_path: Path) -> None:
        log_file = tmp_path / "test.log"
        log_file.write_text(SAMPLE_LOG, encoding="utf-8")

        cycles = list(splitter.split(io.StringIO(SAMPLE_LOG)))
        # 讀取第二個 cycle (cycle_id=1)
        lines = list(splitter.read_cycle_lines(log_file, cycles[1]))
        assert len(lines) == 3
        assert "U-Boot TPL" in lines[0]
        assert "Loading kernel" in lines[2]


class TestTruncation:
    """超過 max_cycle_lines 時標記 truncated。"""

    def test_truncated_flag(self) -> None:
        sp = StreamSplitter(max_cycle_lines=3)
        # 5 lines before any anchor → pre-boot cycle exceeds limit of 3
        log = "\n".join(f"[2026-01-01 00:00:0{i}.000] line{i}" for i in range(5))
        cycles = list(sp.split(io.StringIO(log)))
        assert len(cycles) == 1
        assert cycles[0].truncated is True
        assert cycles[0].line_count == 5

    def test_not_truncated_when_within_limit(self) -> None:
        sp = StreamSplitter(max_cycle_lines=100)
        cycles = list(sp.split(io.StringIO(SAMPLE_LOG)))
        assert all(not c.truncated for c in cycles)


@pytest.mark.skipif(not SAMPLE_LOG_PATH.exists(), reason="sample log not present")
class TestWithRealLog:
    """使用實際樣本日誌進行整合測試。"""

    def test_split_real_log(self, splitter: StreamSplitter) -> None:
        # 先計算檔案中有幾個錨點
        with open(SAMPLE_LOG_PATH, encoding="utf-8", errors="replace") as fh:
            anchor_count = sum(1 for line in fh if "U-Boot TPL" in line)

        with open(SAMPLE_LOG_PATH, encoding="utf-8", errors="replace") as fh:
            cycles = list(splitter.split(fh))

        expected = anchor_count + 1  # pre-boot + N boot cycles
        assert len(cycles) == expected
        assert cycles[0].cycle_id == 0
        assert cycles[-1].cycle_id == anchor_count

        # 加總應等於檔案總行數 (Python enumerate 含末尾空行)
        total_lines = sum(c.line_count for c in cycles)
        with open(SAMPLE_LOG_PATH, encoding="utf-8", errors="replace") as fh:
            file_line_count = sum(1 for _ in fh)
        assert total_lines == file_line_count

    def test_read_cycle_lines_real(self, splitter: StreamSplitter) -> None:
        with open(SAMPLE_LOG_PATH, encoding="utf-8", errors="replace") as fh:
            cycles = list(splitter.split(fh))

        # 第一個 boot cycle
        c1 = cycles[1]
        lines = list(splitter.read_cycle_lines(SAMPLE_LOG_PATH, c1))
        assert len(lines) == c1.line_count
        assert "U-Boot TPL" in lines[0]
