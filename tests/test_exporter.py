"""Tests for OTelExporter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from logsensing.analyzer.exporter import OTelExporter


# ---------------------------------------------------------------------------
# Mock Anomaly compatible with the real Anomaly interface
# ---------------------------------------------------------------------------
@dataclass
class MockAnomaly:
    anomaly_id: str = ""
    cycle_id: int = 0
    rule_id: str = ""
    rule_name: str = ""
    severity: str = "info"
    rule_type: str = ""
    timestamp: datetime | None = None
    line_number: int = 0
    message: str = ""
    context_before: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def exporter() -> OTelExporter:
    return OTelExporter(service_name="test-svc", device_model="test-device")


# ---------------------------------------------------------------------------
# 1. Empty anomalies → valid structure with 0 traces
# ---------------------------------------------------------------------------
def test_empty_anomalies(exporter: OTelExporter) -> None:
    result = exporter.export([])
    assert result["resource"]["service.name"] == "test-svc"
    assert result["resource"]["device.model"] == "test-device"
    assert result["summary"]["total_anomalies"] == 0
    assert result["traces"] == []


# ---------------------------------------------------------------------------
# 2. Single anomaly → correct trace / span structure
# ---------------------------------------------------------------------------
def test_single_anomaly(exporter: OTelExporter) -> None:
    a = MockAnomaly(
        anomaly_id="a1",
        cycle_id=1,
        rule_id="kernel_panic",
        rule_name="Kernel Panic",
        severity="critical",
        rule_type="pattern",
        line_number=100,
        message="panic detected",
    )
    result = exporter.export([a])

    assert len(result["traces"]) == 1
    trace = result["traces"][0]
    assert trace["cycle_id"] == 1
    assert len(trace["spans"]) == 1

    span = trace["spans"][0]
    assert span["name"] == "anomaly.kernel_panic"
    assert span["attributes"]["anomaly.severity"] == "critical"
    assert span["attributes"]["anomaly.rule_id"] == "kernel_panic"
    assert span["attributes"]["anomaly.rule_name"] == "Kernel Panic"
    assert span["attributes"]["anomaly.line_number"] == 100
    assert span["attributes"]["anomaly.message"] == "panic detected"


# ---------------------------------------------------------------------------
# 3. Multiple anomalies in same cycle → grouped into one trace
# ---------------------------------------------------------------------------
def test_same_cycle_grouped(exporter: OTelExporter) -> None:
    anomalies = [
        MockAnomaly(anomaly_id="a1", cycle_id=5, rule_id="r1", severity="warning"),
        MockAnomaly(anomaly_id="a2", cycle_id=5, rule_id="r2", severity="critical"),
    ]
    result = exporter.export(anomalies)

    assert len(result["traces"]) == 1
    assert len(result["traces"][0]["spans"]) == 2


# ---------------------------------------------------------------------------
# 4. Multiple cycles → multiple traces
# ---------------------------------------------------------------------------
def test_multiple_cycles(exporter: OTelExporter) -> None:
    anomalies = [
        MockAnomaly(anomaly_id="a1", cycle_id=1, rule_id="r1"),
        MockAnomaly(anomaly_id="a2", cycle_id=2, rule_id="r2"),
        MockAnomaly(anomaly_id="a3", cycle_id=3, rule_id="r3"),
    ]
    result = exporter.export(anomalies)

    assert len(result["traces"]) == 3
    cycle_ids = [t["cycle_id"] for t in result["traces"]]
    assert cycle_ids == [1, 2, 3]


# ---------------------------------------------------------------------------
# 5. Timestamp conversion to nanoseconds
# ---------------------------------------------------------------------------
def test_timestamp_to_nanoseconds(exporter: OTelExporter) -> None:
    ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    nano = exporter._timestamp_to_nano(ts)
    assert nano == int(ts.timestamp() * 1_000_000_000)
    assert exporter._timestamp_to_nano(None) == 0


# ---------------------------------------------------------------------------
# 6. Trace ID is deterministic for same cycle_id
# ---------------------------------------------------------------------------
def test_trace_id_deterministic(exporter: OTelExporter) -> None:
    tid1 = exporter._generate_trace_id(42)
    tid2 = exporter._generate_trace_id(42)
    tid_other = exporter._generate_trace_id(99)

    assert tid1 == tid2
    assert len(tid1) == 32
    assert tid1 != tid_other


# ---------------------------------------------------------------------------
# 7. context_before / context_after included in events
# ---------------------------------------------------------------------------
def test_context_in_events(exporter: OTelExporter) -> None:
    a = MockAnomaly(
        anomaly_id="a1",
        cycle_id=1,
        rule_id="r1",
        context_before=["line1", "line2"],
        context_after=["line3", "line4"],
    )
    result = exporter.export([a])
    events = result["traces"][0]["spans"][0]["events"]

    assert len(events) == 1
    attrs = events[0]["attributes"]
    assert attrs["log.context_before"] == "line1\nline2"
    assert attrs["log.context_after"] == "line3\nline4"


# ---------------------------------------------------------------------------
# 8. Export to file (write and read back)
# ---------------------------------------------------------------------------
def test_export_to_file(exporter: OTelExporter, tmp_path: Path) -> None:
    a = MockAnomaly(anomaly_id="a1", cycle_id=1, rule_id="r1", severity="info")
    out = tmp_path / "out.json"
    result = exporter.export([a], output_path=out)

    assert out.exists()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["summary"]["total_anomalies"] == 1
    assert loaded == json.loads(json.dumps(result, default=str))


# ---------------------------------------------------------------------------
# 9. Summary counts (by_severity, affected_cycles)
# ---------------------------------------------------------------------------
def test_summary_counts(exporter: OTelExporter) -> None:
    anomalies = [
        MockAnomaly(anomaly_id="a1", cycle_id=1, severity="critical"),
        MockAnomaly(anomaly_id="a2", cycle_id=1, severity="warning"),
        MockAnomaly(anomaly_id="a3", cycle_id=2, severity="critical"),
        MockAnomaly(anomaly_id="a4", cycle_id=3, severity="info"),
    ]
    result = exporter.export(anomalies)
    summary = result["summary"]

    assert summary["total_anomalies"] == 4
    assert summary["by_severity"]["critical"] == 2
    assert summary["by_severity"]["warning"] == 1
    assert summary["by_severity"]["info"] == 1
    assert summary["affected_cycles"] == [1, 2, 3]
