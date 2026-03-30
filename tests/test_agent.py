"""Tests for RCA and InteractiveAgent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from logsensing.agent.interactive import InteractiveAgent
from logsensing.agent.rca import RCAReport

# ---------------------------------------------------------------------------
# Sample OTel anomalies data
# ---------------------------------------------------------------------------
SAMPLE_ANOMALIES: dict[str, Any] = {
    "resource": {"service.name": "logsensing", "device.model": "BGW720-300"},
    "summary": {
        "total_anomalies": 2,
        "by_severity": {"critical": 1, "warning": 1},
        "affected_cycles": [1, 2],
    },
    "traces": [
        {
            "traceId": "abc123",
            "cycle_id": 1,
            "spans": [
                {
                    "spanId": "span1",
                    "name": "anomaly.kernel_panic",
                    "startTimeUnixNano": 0,
                    "attributes": {
                        "anomaly.severity": "critical",
                        "anomaly.rule_id": "kernel_panic",
                        "anomaly.rule_name": "Kernel Panic",
                        "anomaly.rule_type": "pattern",
                        "anomaly.cycle_id": 1,
                        "anomaly.line_number": 100,
                        "anomaly.message": "Kernel panic - not syncing",
                    },
                    "events": [
                        {
                            "name": "context",
                            "attributes": {
                                "log.context_before": "line1\nline2",
                                "log.context_after": "line3\nline4",
                            },
                        }
                    ],
                }
            ],
        },
        {
            "traceId": "def456",
            "cycle_id": 2,
            "spans": [
                {
                    "spanId": "span2",
                    "name": "anomaly.watchdog_reset",
                    "startTimeUnixNano": 0,
                    "attributes": {
                        "anomaly.severity": "warning",
                        "anomaly.rule_id": "watchdog_reset",
                        "anomaly.rule_name": "Watchdog Reset",
                        "anomaly.rule_type": "pattern",
                        "anomaly.cycle_id": 2,
                        "anomaly.line_number": 500,
                        "anomaly.message": "watchdog timer reset",
                    },
                    "events": [
                        {
                            "name": "context",
                            "attributes": {
                                "log.context_before": "ctx_a",
                                "log.context_after": "ctx_b",
                            },
                        }
                    ],
                }
            ],
        },
    ],
}


MULTI_ANOMALY_CYCLE: dict[str, Any] = {
    "resource": {"service.name": "logsensing", "device.model": "TestDevice"},
    "summary": {
        "total_anomalies": 3,
        "by_severity": {"critical": 2, "warning": 1},
        "affected_cycles": [1],
    },
    "traces": [
        {
            "traceId": "multi123",
            "cycle_id": 1,
            "spans": [
                {
                    "spanId": "s1",
                    "name": "anomaly.kernel_panic",
                    "startTimeUnixNano": 0,
                    "attributes": {
                        "anomaly.severity": "critical",
                        "anomaly.rule_id": "kernel_panic",
                        "anomaly.rule_name": "Kernel Panic",
                        "anomaly.rule_type": "pattern",
                        "anomaly.cycle_id": 1,
                        "anomaly.line_number": 10,
                        "anomaly.message": "Kernel panic",
                    },
                    "events": [],
                },
                {
                    "spanId": "s2",
                    "name": "anomaly.oom_killer",
                    "startTimeUnixNano": 0,
                    "attributes": {
                        "anomaly.severity": "critical",
                        "anomaly.rule_id": "oom_killer",
                        "anomaly.rule_name": "OOM Killer",
                        "anomaly.rule_type": "pattern",
                        "anomaly.cycle_id": 1,
                        "anomaly.line_number": 20,
                        "anomaly.message": "Out of memory",
                    },
                    "events": [],
                },
                {
                    "spanId": "s3",
                    "name": "anomaly.watchdog_reset",
                    "startTimeUnixNano": 0,
                    "attributes": {
                        "anomaly.severity": "warning",
                        "anomaly.rule_id": "watchdog_reset",
                        "anomaly.rule_name": "Watchdog Reset",
                        "anomaly.rule_type": "pattern",
                        "anomaly.cycle_id": 1,
                        "anomaly.line_number": 30,
                        "anomaly.message": "watchdog reset",
                    },
                    "events": [],
                },
            ],
        }
    ],
}


# ===================================================================
# RCAReport tests
# ===================================================================
class TestRCAReport:
    """RCAReport 測試."""

    def test_generate_cycle_report(self) -> None:
        """Test generate_cycle_report with mock anomaly data."""
        rca = RCAReport(anomalies_data=SAMPLE_ANOMALIES)
        report = rca.generate_cycle_report(1)

        assert "## Cycle #1 - Root Cause Analysis" in report
        assert "**嚴重程度:** Critical" in report
        assert "**異常數量:** 1" in report
        assert "Kernel Panic" in report
        assert "kernel_panic" in report
        assert "Kernel panic - not syncing" in report
        assert "line1" in report
        assert "line3" in report

    def test_generate_summary_report(self) -> None:
        """Test generate_summary_report."""
        rca = RCAReport(anomalies_data=SAMPLE_ANOMALIES)
        report = rca.generate_summary_report()

        assert "# LogSensing RCA Summary Report" in report
        assert "**裝置:** BGW720-300" in report
        assert "**總異常數:** 2" in report
        assert "Critical: 1" in report
        assert "Warning: 1" in report
        assert "## 受影響的 Cycles" in report
        assert "## 各 Cycle 詳細報告" in report

    def test_cycle_no_anomalies(self) -> None:
        """Test cycle with no anomalies returns appropriate message."""
        rca = RCAReport(anomalies_data=SAMPLE_ANOMALIES)
        report = rca.generate_cycle_report(999)

        assert "## Cycle #999 - Root Cause Analysis" in report
        assert "未偵測到異常事件" in report

    def test_loading_from_json_file(self, tmp_path: Path) -> None:
        """Test loading from JSON file."""
        json_path = tmp_path / "anomalies.json"
        json_path.write_text(json.dumps(SAMPLE_ANOMALIES), encoding="utf-8")

        rca = RCAReport(anomalies_path=json_path)
        report = rca.generate_cycle_report(1)

        assert "Kernel Panic" in report
        assert "**異常數量:** 1" in report

    def test_multiple_anomalies_in_one_cycle(self) -> None:
        """Test multiple anomalies in one cycle."""
        rca = RCAReport(anomalies_data=MULTI_ANOMALY_CYCLE)
        report = rca.generate_cycle_report(1)

        assert "**異常數量:** 3" in report
        assert "**嚴重程度:** Critical" in report
        assert "Kernel Panic" in report
        assert "OOM Killer" in report
        assert "Watchdog Reset" in report


# ===================================================================
# InteractiveAgent tests
# ===================================================================
class TestInteractiveAgent:
    """InteractiveAgent 測試."""

    def _make_agent(self) -> InteractiveAgent:
        return InteractiveAgent()

    def test_handle_help_returns_true(self) -> None:
        """Test _handle_command('help') returns True."""
        agent = self._make_agent()
        assert agent._handle_command("help") is True

    def test_handle_quit_returns_false(self) -> None:
        """Test _handle_command('quit') returns False."""
        agent = self._make_agent()
        assert agent._handle_command("quit") is False

    def test_handle_exit_returns_false(self) -> None:
        """Test _handle_command('exit') returns False."""
        agent = self._make_agent()
        assert agent._handle_command("exit") is False

    def test_handle_unknown_command_returns_true(self) -> None:
        """Test _handle_command with unknown command returns True."""
        agent = self._make_agent()
        assert agent._handle_command("foobar") is True
