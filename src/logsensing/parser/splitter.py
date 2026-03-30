"""StreamSplitter — 將巨型日誌檔依開機錨點切割成 BootCycle 區塊."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO

if __name__ != "__main__":
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from logsensing.platform.base import PlatformProfile

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_DEFAULT_ANCHORS: list[str] = ["U-Boot TPL"]

_TS_FMT = "%Y-%m-%d %H:%M:%S.%f"


@dataclass
class BootCycle:
    """單次開機週期的元資料（不含原始文字）。"""

    cycle_id: int
    start_line: int  # 0-based
    end_line: int  # exclusive
    anchor_line: str  # 觸發切割的那一行
    timestamp_start: datetime | None = None
    timestamp_end: datetime | None = None
    line_count: int = 0
    truncated: bool = False


# ---------------------------------------------------------------------------
# Splitter
# ---------------------------------------------------------------------------


class StreamSplitter:
    """串流式日誌切割器，逐行掃描並依錨點字串產出 BootCycle。"""

    def __init__(
        self,
        anchors: list[str] | None = None,
        fallback_anchors: list[str] | None = None,
        max_cycle_lines: int = 100_000,
        timestamp_pattern: str = r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] ",
    ) -> None:
        self.anchors: list[str] = anchors if anchors is not None else list(_DEFAULT_ANCHORS)
        self.fallback_anchors: list[str] = fallback_anchors or []
        self.max_cycle_lines = max_cycle_lines
        self._ts_re = re.compile(timestamp_pattern) if timestamp_pattern else None
        self._ts_fmt = _TS_FMT

    @classmethod
    def from_platform(
        cls,
        platform: PlatformProfile,
        max_cycle_lines: int = 100_000,
    ) -> StreamSplitter:
        """從 PlatformProfile 建立 StreamSplitter."""
        return cls(
            anchors=list(platform.boot_anchors),
            fallback_anchors=list(platform.fallback_anchors),
            max_cycle_lines=max_cycle_lines,
            timestamp_pattern=platform.timestamp_pattern or "",
        )

    # -- public -------------------------------------------------------------

    def split(self, stream: IO[str]) -> Iterator[BootCycle]:
        """逐行讀取 *stream*，遇到錨點時切割並 yield BootCycle 元資料。

        第一段（錨點出現之前）為 cycle_id=0（pre-boot）。
        """
        cycle_id = 0
        start_line = 0
        line_count = 0
        truncated = False
        anchor_line = ""
        ts_start: datetime | None = None
        ts_end: datetime | None = None

        for lineno, raw in enumerate(stream):
            line = raw.rstrip("\n\r")

            if self._is_anchor(line):
                # 結束前一個 cycle
                yield BootCycle(
                    cycle_id=cycle_id,
                    start_line=start_line,
                    end_line=lineno,
                    anchor_line=anchor_line,
                    timestamp_start=ts_start,
                    timestamp_end=ts_end,
                    line_count=line_count,
                    truncated=truncated,
                )
                # 開始新 cycle
                cycle_id += 1
                start_line = lineno
                line_count = 0
                truncated = False
                anchor_line = line
                ts_start = None
                ts_end = None

            # 追蹤行數與時間戳
            line_count += 1
            if line_count > self.max_cycle_lines:
                truncated = True

            ts = self._parse_timestamp(line)
            if ts is not None:
                if ts_start is None:
                    ts_start = ts
                ts_end = ts

        # 最後一個 cycle
        yield BootCycle(
            cycle_id=cycle_id,
            start_line=start_line,
            end_line=lineno + 1 if "lineno" in dir() else 0,
            anchor_line=anchor_line,
            timestamp_start=ts_start,
            timestamp_end=ts_end,
            line_count=line_count,
            truncated=truncated,
        )

    def read_cycle_lines(self, path: Path, cycle: BootCycle) -> Iterator[str]:
        """根據 *cycle* 的行號範圍，從 *path* 讀取對應的原始行。"""
        with open(path, encoding="utf-8", errors="replace") as fh:
            for lineno, raw in enumerate(fh):
                if lineno < cycle.start_line:
                    continue
                if lineno >= cycle.end_line:
                    break
                yield raw.rstrip("\n\r")

    # -- private ------------------------------------------------------------

    def _parse_timestamp(self, line: str) -> datetime | None:
        """從日誌行擷取時間戳，無法匹配則回傳 None。"""
        if self._ts_re is None:
            return None
        m = self._ts_re.match(line)
        if m is None:
            return None
        try:
            return datetime.strptime(m.group(1), _TS_FMT)
        except ValueError:
            return None

    def _is_anchor(self, line: str) -> bool:
        """檢查 *line* 是否包含任一錨點字串。"""
        return any(anchor in line for anchor in self.anchors)
