"""Tests for BootTimingAnalyzer."""
from __future__ import annotations

import pytest

from logsensing.analyzer.reporter import (
    BootTimingAnalyzer,
    BootTimingReport,
    CycleTiming,
    ProcessTiming,
)


class TestBootTimingAnalyzer:
    def test_analyze_cycle_basic(self):
        """Test _analyze_cycle with synthetic lines."""
        lines = [
            "[2026-03-18 10:00:00.000] U-Boot TPL start\n",
            "[2026-03-18 10:00:01.000] U-Boot 2024 main\n",
            "[2026-03-18 10:00:05.000] Starting kernel ...\n",
            "[2026-03-18 10:00:06.000] Booting Linux on physical CPU 0x0\n",
            "[2026-03-18 10:00:07.500] Init complete for FIFO tunnel\n",
            "[2026-03-18 10:00:15.000] dhd_bus_start_try download fw\n",
        ]
        analyzer = BootTimingAnalyzer(skip_first_n=0)
        ct = analyzer._analyze_cycle(lines, cycle_id=1)
        assert ct.cycle_id == 1
        assert ct.total_seconds == 15.0
        assert "U-Boot TPL" in ct.process_offsets
        assert ct.process_offsets["Kernel Start"] == pytest.approx(5.0)
        assert ct.process_offsets["DHD FW Load"] == pytest.approx(15.0)

    def test_to_markdown(self):
        """Test markdown report generation."""
        report = BootTimingReport(
            device_model="TestDevice",
            total_cycles=3,
            valid_cycles=1,
            boot_time_mean=15.0,
            boot_time_stddev=0.1,
            boot_time_min=14.9,
            boot_time_max=15.1,
            process_stats=[
                ProcessTiming(
                    name="Kernel",
                    pattern="kernel",
                    mean=5.0,
                    stddev=0.1,
                    min_val=4.9,
                    max_val=5.1,
                    hit_count=1,
                    total_cycles=1,
                ),
            ],
        )
        analyzer = BootTimingAnalyzer()
        md = analyzer.to_markdown(report)
        assert "# Boot Timing Report" in md
        assert "TestDevice" in md
        assert "15.000s" in md
        assert "Kernel" in md

    def test_compute_process_stats(self):
        """Test process stats computation."""
        analyzer = BootTimingAnalyzer(processes=[("TestProc", "test")])
        timings = [
            CycleTiming(cycle_id=1, process_offsets={"TestProc": 5.0}),
            CycleTiming(cycle_id=2, process_offsets={"TestProc": 6.0}),
            CycleTiming(cycle_id=3, process_offsets={"TestProc": 7.0}),
        ]
        stats = analyzer._compute_process_stats(timings)
        assert len(stats) == 1
        assert stats[0].mean == pytest.approx(6.0)
        assert stats[0].hit_count == 3

    def test_empty_lines(self):
        """Test with empty lines."""
        analyzer = BootTimingAnalyzer(skip_first_n=0)
        ct = analyzer._analyze_cycle([], cycle_id=0)
        assert ct.total_seconds == 0.0
        assert len(ct.process_offsets) == 0
