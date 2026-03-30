"""開機時間統計報告生成器."""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logsensing.platform.base import PlatformProfile

TIMESTAMP_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\]")


@dataclass
class ProcessTiming:
    """單一 process/module 的 wake time 統計."""
    name: str
    pattern: str
    mean: float = 0.0
    stddev: float = 0.0
    min_val: float = 0.0
    max_val: float = 0.0
    hit_count: int = 0
    total_cycles: int = 0


@dataclass
class CycleTiming:
    """單一 cycle 的時間資料."""
    cycle_id: int
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    total_seconds: float = 0.0
    milestone_offsets: dict[str, float] = field(default_factory=dict)
    process_offsets: dict[str, float] = field(default_factory=dict)
    # Sequence analysis (used when no timestamp)
    process_line_offsets: dict[str, int] = field(default_factory=dict)
    total_lines: int = 0


@dataclass
class BootTimingReport:
    """完整開機時間統計報告."""
    device_model: str = "unknown"
    platform_name: str = "unknown"
    total_cycles: int = 0
    valid_cycles: int = 0
    supports_timing: bool = True
    cycle_timings: list[CycleTiming] = field(default_factory=list)
    process_stats: list[ProcessTiming] = field(default_factory=list)
    # Baseline summary
    boot_time_mean: float = 0.0
    boot_time_stddev: float = 0.0
    boot_time_min: float = 0.0
    boot_time_max: float = 0.0


# Default processes/modules to track (name, pattern) — BDK fallback
DEFAULT_PROCESSES: list[tuple[str, str]] = [
    ("U-Boot TPL", "U-Boot TPL"),
    ("U-Boot Main", "U-Boot 2024"),
    ("Kernel Start", "Starting kernel"),
    ("Linux Boot", "Booting Linux on physical CPU"),
    ("SMCOS", "SMCOS:"),
    ("RPC Tunnel", "Init complete for FIFO tunnel"),
    ("Flow Cache", "fcache"),
    ("PCIe Link UP", "Link UP"),
    ("Networking Config", "Configuring networking"),
    ("WiFi wl0", "wl0:"),
    ("Enet Ready", "wait_enet_ready done"),
    ("DHD FW Load", "dhd_bus_start_try download fw"),
    ("Offload (dol0)", "dol0:"),
    ("SBF", "SBF:"),
    ("WiFi wl1", "wl1:"),
    ("WiFi wl2", "wl2:"),
    ("ACS Daemon", "acsd:"),
]


def _parse_ts(
    line: str,
    ts_re: re.Pattern[str] | None = None,
    ts_fmt: str | None = None,
) -> datetime | None:
    regex = ts_re or TIMESTAMP_RE
    fmt = ts_fmt or "%Y-%m-%d %H:%M:%S.%f"
    m = regex.match(line)
    if m:
        return datetime.strptime(m.group(1), fmt)
    return None


class BootTimingAnalyzer:
    """分析開機時間統計."""

    def __init__(
        self,
        processes: list[tuple[str, str]] | None = None,
        skip_first_n: int = 2,
        *,
        supports_timing: bool = True,
        ts_re: re.Pattern[str] | None = None,
        ts_fmt: str | None = None,
        platform_name: str = "unknown",
    ):
        self._processes = processes or list(DEFAULT_PROCESSES)
        self._skip_first_n = skip_first_n
        self._supports_timing = supports_timing
        self._ts_re = ts_re
        self._ts_fmt = ts_fmt
        self._platform_name = platform_name

    @classmethod
    def from_platform(
        cls,
        platform: PlatformProfile,
        skip_first_n: int = 2,
    ) -> BootTimingAnalyzer:
        """從 PlatformProfile 建立 BootTimingAnalyzer."""
        ts_re = re.compile(platform.timestamp_pattern) if platform.timestamp_pattern else None
        return cls(
            processes=list(platform.processes) if platform.processes else None,
            skip_first_n=skip_first_n,
            supports_timing=platform.supports_timing,
            ts_re=ts_re,
            ts_fmt=platform.timestamp_format,
            platform_name=platform.name,
        )

    def analyze(
        self,
        logfile: Path,
        device_model: str = "unknown",
    ) -> BootTimingReport:
        """Analyze a log file and generate boot timing report."""
        from logsensing.parser.splitter import StreamSplitter

        splitter = StreamSplitter(anchors=["U-Boot TPL"])
        with open(logfile, encoding="utf-8", errors="replace") as fh:
            cycles = list(splitter.split(fh))

        cycle_timings: list[CycleTiming] = []

        for cycle in cycles:
            lines = list(splitter.read_cycle_lines(logfile, cycle))
            ct = self._analyze_cycle(lines, cycle.cycle_id)
            cycle_timings.append(ct)

        # Skip first N cycles for statistics
        valid_timings = cycle_timings[self._skip_first_n:]
        if self._supports_timing:
            valid_timings = [ct for ct in valid_timings if ct.total_seconds > 0]
        else:
            valid_timings = [ct for ct in valid_timings if ct.total_lines > 0]

        # Compute process stats
        process_stats = self._compute_process_stats(valid_timings)

        # Compute boot time stats (only for timing-capable platforms)
        report = BootTimingReport(
            device_model=device_model,
            platform_name=self._platform_name,
            total_cycles=len(cycles),
            valid_cycles=len(valid_timings),
            supports_timing=self._supports_timing,
            cycle_timings=cycle_timings,
            process_stats=process_stats,
        )
        if self._supports_timing:
            boot_times = [ct.total_seconds for ct in valid_timings if ct.total_seconds > 0]
            if boot_times:
                report.boot_time_mean = statistics.mean(boot_times)
                report.boot_time_stddev = (
                    statistics.pstdev(boot_times) if len(boot_times) > 1 else 0.0
                )
                report.boot_time_min = min(boot_times)
                report.boot_time_max = max(boot_times)

        return report

    def _analyze_cycle(self, lines: list[str], cycle_id: int) -> CycleTiming:
        """Analyze a single cycle for timing data."""
        first_ts: datetime | None = None
        last_ts: datetime | None = None

        if self._supports_timing:
            for line in lines:
                ts = _parse_ts(line, self._ts_re, self._ts_fmt)
                if ts:
                    if first_ts is None:
                        first_ts = ts
                    last_ts = ts

        ct = CycleTiming(
            cycle_id=cycle_id,
            first_timestamp=first_ts,
            last_timestamp=last_ts,
            total_lines=len(lines),
        )

        # Track process first-appearance offsets
        if self._supports_timing and first_ts:
            for pname, pattern in self._processes:
                for line in lines:
                    if pattern in line:
                        ts = _parse_ts(line, self._ts_re, self._ts_fmt)
                        if ts:
                            ct.process_offsets[pname] = (ts - first_ts).total_seconds()
                        break
        else:
            # Sequence analysis: record process first-occurrence line number
            for pname, pattern in self._processes:
                for idx, line in enumerate(lines):
                    if pattern in line:
                        ct.process_line_offsets[pname] = idx
                        break

        # Boot time = offset of last tracked milestone (not raw cycle duration)
        if ct.process_offsets:
            ct.total_seconds = max(ct.process_offsets.values())
        elif first_ts and last_ts:
            ct.total_seconds = (last_ts - first_ts).total_seconds()

        return ct

    def _compute_process_stats(
        self, timings: list[CycleTiming]
    ) -> list[ProcessTiming]:
        """Compute statistics for each process across cycles."""
        stats: list[ProcessTiming] = []
        for pname, pattern in self._processes:
            if self._supports_timing:
                vals = [
                    ct.process_offsets[pname]
                    for ct in timings
                    if pname in ct.process_offsets
                ]
            else:
                vals = [
                    float(ct.process_line_offsets[pname])
                    for ct in timings
                    if pname in ct.process_line_offsets
                ]
            pt = ProcessTiming(
                name=pname,
                pattern=pattern,
                hit_count=len(vals),
                total_cycles=len(timings),
            )
            if vals:
                pt.mean = statistics.mean(vals)
                pt.stddev = statistics.pstdev(vals) if len(vals) > 1 else 0.0
                pt.min_val = min(vals)
                pt.max_val = max(vals)
            stats.append(pt)
        return stats

    def to_markdown(self, report: BootTimingReport) -> str:
        """Generate markdown report."""
        unit = "s" if report.supports_timing else "行"
        lines: list[str] = []
        lines.append("# Boot Timing Report")
        lines.append("")
        lines.append(f"**裝置:** {report.device_model}")
        lines.append(f"**平台:** {report.platform_name}")
        lines.append(
            f"**總 Cycles:** {report.total_cycles}（有效: {report.valid_cycles}）"
        )
        lines.append("")

        if report.supports_timing:
            # Boot time summary
            lines.append("## 開機時間摘要")
            lines.append("")
            lines.append("| 指標 | 值 |")
            lines.append("|------|-----|")
            lines.append(f"| 平均 | {report.boot_time_mean:.3f}s |")
            lines.append(f"| 標準差 | {report.boot_time_stddev:.3f}s |")
            lines.append(f"| 最小 | {report.boot_time_min:.3f}s |")
            lines.append(f"| 最大 | {report.boot_time_max:.3f}s |")
            lines.append("")

        # Process wake time table
        lines.append("## Process/Module Wake Time")
        lines.append("")
        lines.append("| Process | Mean | StdDev | Min | Max | Hit% |")
        lines.append("|---------|------|--------|-----|-----|------|")
        for ps in report.process_stats:
            if ps.hit_count == 0:
                lines.append(f"| {ps.name} | N/A | N/A | N/A | N/A | 0% |")
            else:
                pct = (
                    ps.hit_count / ps.total_cycles * 100
                    if ps.total_cycles > 0
                    else 0
                )
                fmt = ".3f" if report.supports_timing else ".0f"
                lines.append(
                    f"| {ps.name} | {ps.mean:{fmt}}{unit} | {ps.stddev:{fmt}}{unit} | "
                    f"{ps.min_val:{fmt}}{unit} | {ps.max_val:{fmt}}{unit} | {pct:.0f}% |"
                )
        lines.append("")

        # Per-cycle timing table
        lines.append("## Per-Cycle Timing")
        lines.append("")
        key_processes = [p[0] for p in self._processes[:6]] if self._processes else []
        header = "| Cycle | Total |"
        sep = "|-------|-------|"
        for kp in key_processes:
            header += f" {kp} |"
            sep += "------|"
        lines.append(header)
        lines.append(sep)

        for ct in report.cycle_timings:
            offsets = ct.process_offsets if report.supports_timing else {
                k: float(v) for k, v in ct.process_line_offsets.items()
            }
            total = ct.total_seconds if report.supports_timing else ct.total_lines
            fmt = ".3f" if report.supports_timing else ".0f"
            row = f"| {ct.cycle_id} | {total:{fmt}}{unit} |"
            for kp in key_processes:
                if kp in offsets:
                    row += f" {offsets[kp]:{fmt}}{unit} |"
                else:
                    row += " N/A |"
            lines.append(row)
        lines.append("")

        return "\n".join(lines)
