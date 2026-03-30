"""Platform module tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from logsensing.platform.bdk import BDK_PROFILE
from logsensing.platform.prplos import PRPLOS_PROFILE
from logsensing.platform.registry import (
    auto_detect,
    get_platform,
    list_platforms,
    resolve_platform,
)

# ---------------------------------------------------------------------------
# PlatformProfile basic
# ---------------------------------------------------------------------------


class TestPlatformProfile:
    def test_bdk_profile_frozen(self):
        with pytest.raises(AttributeError):
            BDK_PROFILE.name = "hacked"  # type: ignore[misc]

    def test_prplos_profile_frozen(self):
        with pytest.raises(AttributeError):
            PRPLOS_PROFILE.name = "hacked"  # type: ignore[misc]

    def test_bdk_has_timestamp(self):
        assert BDK_PROFILE.supports_timing is True
        assert BDK_PROFILE.timestamp_pattern is not None

    def test_prplos_no_timestamp(self):
        assert PRPLOS_PROFILE.supports_timing is False
        assert PRPLOS_PROFILE.timestamp_pattern is None

    def test_bdk_extract_timestamp(self):
        line = "[2026-03-18 13:54:59.000] some message"
        ts = BDK_PROFILE.extract_timestamp(line)
        assert ts is not None
        assert ts.year == 2026
        assert ts.month == 3

    def test_prplos_extract_timestamp_none(self):
        line = "Starting kernel ..."
        ts = PRPLOS_PROFILE.extract_timestamp(line)
        assert ts is None

    def test_bdk_matches_log(self):
        lines = [
            "some preamble",
            "[2026-03-18 13:55:05.000] acsd: channel scanning",
            "[2026-03-18 13:55:10.000] wait_enet_ready done",
        ]
        assert BDK_PROFILE.matches_log(lines) > 0

    def test_prplos_matches_log(self):
        lines = [
            "root@prplOS:~# reboot",
            "procd: - ubus -",
            "procd: - init -",
            "kmodloader: loading modules",
        ]
        assert PRPLOS_PROFILE.matches_log(lines) > 0

    def test_bdk_does_not_match_prplos(self):
        lines = [
            "procd: - ubus -",
            "procd: - init -",
            "root@prplOS:~#",
        ]
        assert BDK_PROFILE.matches_log(lines) == 0


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_list_platforms(self):
        platforms = list_platforms()
        assert "bdk" in platforms
        assert "prplos" in platforms

    def test_get_platform_bdk(self):
        p = get_platform("bdk")
        assert p.name == "bdk"

    def test_get_platform_prplos(self):
        p = get_platform("prplos")
        assert p.name == "prplos"

    def test_get_platform_unknown_raises(self):
        with pytest.raises(KeyError):
            get_platform("nonexistent")

    def test_resolve_none_returns_bdk(self):
        """None → default to BDK."""
        p = resolve_platform(None)
        assert p.name == "bdk"

    def test_resolve_explicit(self):
        p = resolve_platform("prplos")
        assert p.name == "prplos"


# ---------------------------------------------------------------------------
# Auto-detect
# ---------------------------------------------------------------------------


class TestAutoDetect:
    def test_auto_detect_bdk_sample(self):
        """Auto-detect BDK from sample log."""
        sample = Path("docs/sample_logs/20260318_ATT_newHW7-normal_1354.log")
        if not sample.exists():
            pytest.skip("BDK sample log not available")
        p = auto_detect(sample)
        assert p is not None
        assert p.name == "bdk"

    def test_auto_detect_prplos_sample(self):
        """Auto-detect prplOS from ~/b-log."""
        sample = Path.home() / "b-log" / "mini_COM1_260327-154959.log"
        if not sample.exists():
            pytest.skip("prplOS sample log not available")
        p = auto_detect(sample)
        assert p is not None
        assert p.name == "prplos"

    def test_resolve_auto_with_bdk_log(self):
        """resolve_platform('auto', logfile) picks BDK."""
        sample = Path("docs/sample_logs/20260318_ATT_newHW7-normal_1354.log")
        if not sample.exists():
            pytest.skip("BDK sample log not available")
        p = resolve_platform("auto", sample)
        assert p.name == "bdk"


# ---------------------------------------------------------------------------
# from_platform classmethods
# ---------------------------------------------------------------------------


class TestFromPlatform:
    def test_splitter_from_platform_bdk(self):
        from logsensing.parser.splitter import StreamSplitter

        s = StreamSplitter.from_platform(BDK_PROFILE)
        # Verify it was created successfully and has timestamp support
        assert s._ts_re is not None

    def test_splitter_from_platform_prplos(self):
        from logsensing.parser.splitter import StreamSplitter

        s = StreamSplitter.from_platform(PRPLOS_PROFILE)
        assert s._ts_re is None  # prplOS has no timestamp

    def test_demux_from_platform(self):
        from logsensing.parser.demux import Demultiplexer

        d = Demultiplexer.from_platform(BDK_PROFILE)
        assert len(d._channel_defs) > 0

    def test_baseline_from_platform(self):
        from logsensing.analyzer.baseline import BaselineProfiler

        b = BaselineProfiler.from_platform(BDK_PROFILE)
        # Just verify it was created OK
        assert b is not None

    def test_detector_from_platform(self):
        from logsensing.analyzer.detector import AnomalyDetector

        d = AnomalyDetector.from_platform(BDK_PROFILE)
        assert d._ts_re is not None

    def test_detector_from_platform_prplos(self):
        from logsensing.analyzer.detector import AnomalyDetector

        d = AnomalyDetector.from_platform(PRPLOS_PROFILE)
        assert d._ts_re is None

    def test_reporter_from_platform(self):
        from logsensing.analyzer.reporter import BootTimingAnalyzer

        r = BootTimingAnalyzer.from_platform(BDK_PROFILE)
        assert len(r._processes) > 0
