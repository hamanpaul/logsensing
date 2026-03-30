"""Analyzer 模組測試 — baseline profiler + anomaly detector."""

from __future__ import annotations

from pathlib import Path

import pytest

from logsensing.analyzer.baseline import (
    BaselineProfile,
    BaselineProfiler,
    CycleProfile,
    Milestone,
    MilestoneHit,
)
from logsensing.analyzer.detector import AnomalyDetector, AnomalyRule

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
SAMPLE_LOG = (
    Path(__file__).parent.parent / "docs" / "sample_logs" / "20260318_ATT_newHW7-normal_1354.log"
)


def _make_lines(*entries: tuple[str, str]) -> list[str]:
    """Build synthetic log lines from (timestamp_suffix, content) pairs."""
    return [f"[2026-03-18 13:56:{ts}] {content}\n" for ts, content in entries]


@pytest.fixture
def simple_lines() -> list[str]:
    """6 lines with 3 known milestones."""
    return _make_lines(
        ("00.000", "boot start"),
        ("01.000", "U-Boot TPL 2024.04"),
        ("02.500", "some noise"),
        ("03.000", "U-Boot 2024.04 main"),
        ("05.000", "WDT:   Started watchdog with 1000ms"),
        ("06.000", "done"),
    )


@pytest.fixture
def profiler() -> BaselineProfiler:
    return BaselineProfiler()


# ---------------------------------------------------------------------------
# BaselineProfiler — profile_cycle
# ---------------------------------------------------------------------------
class TestProfileCycle:
    def test_hits_found(self, profiler: BaselineProfiler, simple_lines: list[str]) -> None:
        cp = profiler.profile_cycle(simple_lines)
        hit_names = [h.milestone for h in cp.hits]
        assert "tpl_start" in hit_names
        assert "uboot_main" in hit_names
        assert "watchdog_start" in hit_names

    def test_hit_line_numbers(self, profiler: BaselineProfiler, simple_lines: list[str]) -> None:
        cp = profiler.profile_cycle(simple_lines)
        by_name = {h.milestone: h for h in cp.hits}
        assert by_name["tpl_start"].line_number == 1
        assert by_name["uboot_main"].line_number == 3
        assert by_name["watchdog_start"].line_number == 4

    def test_deltas(self, profiler: BaselineProfiler, simple_lines: list[str]) -> None:
        cp = profiler.profile_cycle(simple_lines)
        assert "tpl_start->uboot_main" in cp.deltas
        assert "uboot_main->watchdog_start" in cp.deltas
        assert cp.deltas["tpl_start->uboot_main"] == pytest.approx(2.0, abs=0.01)
        assert cp.deltas["uboot_main->watchdog_start"] == pytest.approx(2.0, abs=0.01)

    def test_missing_milestones(self, profiler: BaselineProfiler, simple_lines: list[str]) -> None:
        cp = profiler.profile_cycle(simple_lines)
        assert "kernel_start" in cp.missing_milestones
        assert "linux_boot" in cp.missing_milestones

    def test_first_hit_wins(self, profiler: BaselineProfiler) -> None:
        """同一 milestone 出現兩次，只取第一次."""
        lines = _make_lines(
            ("01.000", "U-Boot TPL first"),
            ("05.000", "U-Boot TPL second"),
        )
        cp = profiler.profile_cycle(lines)
        by_name = {h.milestone: h for h in cp.hits}
        assert by_name["tpl_start"].line_number == 0

    def test_empty_lines(self, profiler: BaselineProfiler) -> None:
        cp = profiler.profile_cycle([])
        assert cp.hits == []
        assert cp.deltas == {}
        assert len(cp.missing_milestones) == len(profiler.milestones)


# ---------------------------------------------------------------------------
# BaselineProfiler — train
# ---------------------------------------------------------------------------
class TestTrain:
    def test_mean_stddev(self) -> None:
        profiler = BaselineProfiler(
            milestones=[
                Milestone(name="a", pattern="AAA", expected_order=1),
                Milestone(name="b", pattern="BBB", expected_order=2),
            ]
        )
        cp1 = CycleProfile(cycle_id=0, deltas={"a->b": 10.0})
        cp2 = CycleProfile(cycle_id=1, deltas={"a->b": 20.0})
        bp = profiler.train([cp1, cp2])

        assert bp.mean_deltas["a->b"] == pytest.approx(15.0)
        assert bp.stddev_deltas["a->b"] == pytest.approx(5.0, abs=0.01)
        assert bp.sample_count == 2

    def test_single_cycle_zero_stddev(self) -> None:
        profiler = BaselineProfiler(
            milestones=[
                Milestone(name="a", pattern="AAA", expected_order=1),
                Milestone(name="b", pattern="BBB", expected_order=2),
            ]
        )
        cp = CycleProfile(cycle_id=0, deltas={"a->b": 5.0})
        bp = profiler.train([cp])
        assert bp.stddev_deltas["a->b"] == 0.0


# ---------------------------------------------------------------------------
# BaselineProfiler — save / load roundtrip
# ---------------------------------------------------------------------------
class TestSaveLoad:
    def test_roundtrip(self, profiler: BaselineProfiler, simple_lines: list[str]) -> None:
        cp = profiler.profile_cycle(simple_lines)
        profiler.train([cp])
        save_path = Path("_test_baseline.json")
        try:
            profiler.save(save_path)
            loaded = profiler.load(save_path)
            assert loaded.sample_count == 1
            assert loaded.mean_deltas == profiler.baseline.mean_deltas
            assert len(loaded.milestones) == len(profiler.milestones)
        finally:
            save_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# AnomalyDetector — pattern detection
# ---------------------------------------------------------------------------
class TestPatternDetection:
    def test_kernel_panic(self) -> None:
        lines = _make_lines(
            ("00.000", "normal line"),
            ("01.000", "Kernel panic - not syncing: Fatal exception"),
            ("02.000", "after panic"),
        )
        detector = AnomalyDetector()
        anomalies = detector.detect(lines, cycle_id=0)
        assert len(anomalies) == 1
        assert anomalies[0].rule_id == "kernel_panic"
        assert anomalies[0].severity == "critical"

    def test_oom(self) -> None:
        lines = _make_lines(("10.000", "Out of memory: Killed process 123"))
        detector = AnomalyDetector()
        anomalies = detector.detect(lines, cycle_id=0)
        assert any(a.rule_id == "oom_killer" for a in anomalies)

    def test_no_anomalies(self) -> None:
        lines = _make_lines(
            ("00.000", "Everything is fine"),
            ("01.000", "System booted OK"),
        )
        detector = AnomalyDetector()
        anomalies = detector.detect(lines, cycle_id=0)
        assert anomalies == []

    def test_regex_rule(self) -> None:
        lines = _make_lines(("00.000", "watchdog triggered a reset"))
        detector = AnomalyDetector()
        anomalies = detector.detect(lines, cycle_id=0)
        assert any(a.rule_id == "watchdog_reset" for a in anomalies)


# ---------------------------------------------------------------------------
# AnomalyDetector — context clipping
# ---------------------------------------------------------------------------
class TestContextClipping:
    def test_context_size(self) -> None:
        lines = [f"[2026-03-18 13:56:00.{i:03d}] line {i}\n" for i in range(200)]
        lines[100] = "[2026-03-18 13:56:01.000] Kernel panic - not syncing\n"
        detector = AnomalyDetector(context_lines_before=5, context_lines_after=3)
        anomalies = detector.detect(lines, cycle_id=0)
        assert len(anomalies) == 1
        assert len(anomalies[0].context_before) == 5
        assert len(anomalies[0].context_after) == 3

    def test_context_at_start(self) -> None:
        lines = _make_lines(("00.000", "Kernel panic"))
        detector = AnomalyDetector(context_lines_before=10, context_lines_after=10)
        anomalies = detector.detect(lines, cycle_id=0)
        assert len(anomalies) == 1
        assert anomalies[0].context_before == []
        assert anomalies[0].context_after == []


# ---------------------------------------------------------------------------
# AnomalyDetector — timeout detection
# ---------------------------------------------------------------------------
class TestTimeoutDetection:
    def test_timeout_exceeded(self) -> None:
        baseline = BaselineProfile(
            milestones=[],
            mean_deltas={"a->b": 10.0},
            stddev_deltas={"a->b": 1.0},
            sample_count=5,
        )
        rule = AnomalyRule(
            rule_id="slow_ab",
            name="Slow A->B",
            severity="warning",
            rule_type="timeout",
            timeout_sigma=2.0,
            milestone_pair="a->b",
        )
        profile = CycleProfile(cycle_id=0, deltas={"a->b": 15.0})  # > 10 + 2*1 = 12
        detector = AnomalyDetector(rules=[rule], baseline=baseline)
        anomalies = detector.detect([], cycle_id=0, cycle_profile=profile)
        assert len(anomalies) == 1
        assert anomalies[0].rule_id == "slow_ab"
        assert anomalies[0].metadata["actual"] == 15.0

    def test_timeout_within_bounds(self) -> None:
        baseline = BaselineProfile(
            milestones=[],
            mean_deltas={"a->b": 10.0},
            stddev_deltas={"a->b": 1.0},
            sample_count=5,
        )
        rule = AnomalyRule(
            rule_id="slow_ab",
            name="Slow A->B",
            severity="warning",
            rule_type="timeout",
            timeout_sigma=3.0,
            milestone_pair="a->b",
        )
        profile = CycleProfile(cycle_id=0, deltas={"a->b": 12.0})  # < 10 + 3*1 = 13
        detector = AnomalyDetector(rules=[rule], baseline=baseline)
        anomalies = detector.detect([], cycle_id=0, cycle_profile=profile)
        assert anomalies == []


# ---------------------------------------------------------------------------
# AnomalyDetector — sequence detection
# ---------------------------------------------------------------------------
class TestSequenceDetection:
    def test_missing_milestone(self) -> None:
        rule = AnomalyRule(
            rule_id="boot_seq",
            name="Boot Sequence",
            severity="warning",
            rule_type="sequence",
            required_milestones=["kernel_start", "network_config"],
        )
        profile = CycleProfile(
            cycle_id=0,
            hits=[MilestoneHit(milestone="kernel_start")],
        )
        detector = AnomalyDetector(rules=[rule])
        anomalies = detector.detect([], cycle_id=0, cycle_profile=profile)
        assert len(anomalies) == 1
        assert "network_config" in anomalies[0].message

    def test_all_present(self) -> None:
        rule = AnomalyRule(
            rule_id="boot_seq",
            name="Boot Sequence",
            severity="warning",
            rule_type="sequence",
            required_milestones=["kernel_start", "network_config"],
        )
        profile = CycleProfile(
            cycle_id=0,
            hits=[
                MilestoneHit(milestone="kernel_start"),
                MilestoneHit(milestone="network_config"),
            ],
        )
        detector = AnomalyDetector(rules=[rule])
        anomalies = detector.detect([], cycle_id=0, cycle_profile=profile)
        assert anomalies == []


# ---------------------------------------------------------------------------
# Integration with sample log (skipped if file absent)
# ---------------------------------------------------------------------------
class TestIntegration:
    @pytest.mark.skipif(not SAMPLE_LOG.exists(), reason="sample log not available")
    def test_profile_real_cycle(self) -> None:
        """Profile the second boot cycle from the sample log."""
        with open(SAMPLE_LOG, encoding="utf-8") as f:
            all_lines = f.readlines()
        # Second cycle spans roughly lines 3275-8434
        cycle_lines = all_lines[3274:8434]

        profiler = BaselineProfiler()
        cp = profiler.profile_cycle(cycle_lines, cycle_id=1)

        # At least several milestones should be found
        hit_names = {h.milestone for h in cp.hits}
        assert "kernel_start" in hit_names
        assert "linux_boot" in hit_names
        assert len(cp.deltas) >= 3

    @pytest.mark.skipif(not SAMPLE_LOG.exists(), reason="sample log not available")
    def test_detect_normal_cycle(self) -> None:
        """A normal boot cycle should have zero critical pattern anomalies."""
        with open(SAMPLE_LOG, encoding="utf-8") as f:
            all_lines = f.readlines()
        cycle_lines = all_lines[3274:8434]

        detector = AnomalyDetector()
        anomalies = detector.detect(cycle_lines, cycle_id=1)
        critical = [a for a in anomalies if a.severity == "critical"]
        assert len(critical) == 0, f"unexpected critical anomalies: {critical}"
