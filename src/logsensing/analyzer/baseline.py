"""Baseline profiler — 開機里程碑分析與基準線訓練."""

from __future__ import annotations

import json
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from logsensing.platform.base import PlatformProfile

# ---------------------------------------------------------------------------
# Timestamp regex (same as parser/drain.py)
# ---------------------------------------------------------------------------
TIMESTAMP_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
class Milestone(BaseModel):
    """開機里程碑定義."""

    name: str
    pattern: str
    is_regex: bool = False
    expected_order: int

    def matches(self, text: str) -> bool:
        """判斷 *text* 是否命中此里程碑."""
        if self.is_regex:
            return bool(re.search(self.pattern, text))
        return self.pattern in text


class MilestoneHit(BaseModel):
    """里程碑命中紀錄."""

    milestone: str
    timestamp: datetime | None = None
    line_number: int = 0
    line_content: str = ""


class CycleProfile(BaseModel):
    """單一 cycle 的里程碑時間分析."""

    cycle_id: int
    hits: list[MilestoneHit] = Field(default_factory=list)
    deltas: dict[str, float] = Field(default_factory=dict)
    missing_milestones: list[str] = Field(default_factory=list)


class BaselineProfile(BaseModel):
    """基準線 profile（從正常 cycles 訓練）."""

    milestones: list[Milestone]
    mean_deltas: dict[str, float] = Field(default_factory=dict)
    stddev_deltas: dict[str, float] = Field(default_factory=dict)
    sample_count: int = 0


# ---------------------------------------------------------------------------
# BaselineProfiler
# ---------------------------------------------------------------------------
class BaselineProfiler:
    """從開機日誌中擷取里程碑，並訓練時間基準線."""

    DEFAULT_MILESTONES: ClassVar[list[Milestone]] = [
        Milestone(name="tpl_start", pattern="U-Boot TPL", expected_order=1),
        Milestone(name="uboot_main", pattern="U-Boot 2024", expected_order=2),
        Milestone(name="watchdog_start", pattern="WDT:   Started watchdog", expected_order=3),
        Milestone(name="kernel_start", pattern="Starting kernel", expected_order=4),
        Milestone(name="linux_boot", pattern="Booting Linux on physical CPU", expected_order=5),
        Milestone(
            name="rpc_tunnel_done",
            pattern="Init complete for FIFO tunnel",
            expected_order=6,
        ),
        Milestone(
            name="pcie_link_up", pattern="bcm-pcie: Core", is_regex=False, expected_order=7
        ),
        Milestone(name="network_config", pattern="Configuring networking", expected_order=8),
        Milestone(name="enet_ready", pattern="wait_enet_ready done", expected_order=9),
        Milestone(
            name="wifi_fw_load",
            pattern="dhd_bus_start_try download fw",
            expected_order=10,
        ),
    ]

    def __init__(self, milestones: list[Milestone] | None = None) -> None:
        self.milestones = milestones or list(self.DEFAULT_MILESTONES)
        self._baseline: BaselineProfile | None = None
        self._ts_re: re.Pattern[str] | None = TIMESTAMP_RE
        self._ts_fmt: str = "%Y-%m-%d %H:%M:%S.%f"

    @classmethod
    def from_platform(cls, platform: PlatformProfile) -> BaselineProfiler:
        """從 PlatformProfile 建立 BaselineProfiler."""
        milestones = [
            Milestone(
                name=m.name,
                pattern=m.pattern,
                is_regex=m.is_regex,
                expected_order=m.expected_order,
            )
            for m in platform.milestones
        ] if platform.milestones else None
        profiler = cls(milestones=milestones)
        if platform.timestamp_pattern:
            profiler._ts_re = re.compile(platform.timestamp_pattern)
        else:
            profiler._ts_re = None
        if platform.timestamp_format:
            profiler._ts_fmt = platform.timestamp_format
        return profiler

    # ---- helpers -----------------------------------------------------------

    def _parse_timestamp(self, line: str) -> datetime | None:
        if self._ts_re is None:
            return None
        m = self._ts_re.match(line)
        if m:
            return datetime.strptime(m.group(1), self._ts_fmt)
        return None

    # ---- public API --------------------------------------------------------

    def profile_cycle(self, lines: list[str], cycle_id: int = 0) -> CycleProfile:
        """Profile a single cycle: find milestone hits and compute deltas."""
        hit_map: dict[str, MilestoneHit] = {}

        for idx, line in enumerate(lines):
            for ms in self.milestones:
                if ms.name in hit_map:
                    continue
                if ms.matches(line):
                    hit_map[ms.name] = MilestoneHit(
                        milestone=ms.name,
                        timestamp=self._parse_timestamp(line),
                        line_number=idx,
                        line_content=line.rstrip("\n"),
                    )

        # Order hits by expected_order for delta computation
        ordered_names = [ms.name for ms in sorted(self.milestones, key=lambda m: m.expected_order)]
        ordered_hits = [hit_map[n] for n in ordered_names if n in hit_map]

        # Compute deltas between consecutive (by expected_order) hits
        deltas: dict[str, float] = {}
        for i in range(1, len(ordered_hits)):
            prev, cur = ordered_hits[i - 1], ordered_hits[i]
            if prev.timestamp and cur.timestamp:
                key = f"{prev.milestone}->{cur.milestone}"
                deltas[key] = (cur.timestamp - prev.timestamp).total_seconds()

        missing = [ms.name for ms in self.milestones if ms.name not in hit_map]

        return CycleProfile(
            cycle_id=cycle_id,
            hits=ordered_hits,
            deltas=deltas,
            missing_milestones=missing,
        )

    def train(self, cycle_profiles: list[CycleProfile]) -> BaselineProfile:
        """Train baseline from multiple cycle profiles."""
        all_keys: set[str] = set()
        for cp in cycle_profiles:
            all_keys.update(cp.deltas.keys())

        mean_deltas: dict[str, float] = {}
        stddev_deltas: dict[str, float] = {}

        for key in sorted(all_keys):
            values = [cp.deltas[key] for cp in cycle_profiles if key in cp.deltas]
            if len(values) >= 1:
                mean_deltas[key] = statistics.mean(values)
                stddev_deltas[key] = statistics.pstdev(values) if len(values) > 1 else 0.0

        self._baseline = BaselineProfile(
            milestones=list(self.milestones),
            mean_deltas=mean_deltas,
            stddev_deltas=stddev_deltas,
            sample_count=len(cycle_profiles),
        )
        return self._baseline

    def save(self, path: Path) -> None:
        """Save baseline profile to JSON file."""
        if self._baseline is None:
            msg = "No baseline trained yet — call train() first."
            raise RuntimeError(msg)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._baseline.model_dump_json(indent=2), encoding="utf-8")

    def load(self, path: Path) -> BaselineProfile:
        """Load baseline profile from JSON file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        self._baseline = BaselineProfile.model_validate(data)
        self.milestones = list(self._baseline.milestones)
        return self._baseline

    @property
    def baseline(self) -> BaselineProfile | None:
        return self._baseline
