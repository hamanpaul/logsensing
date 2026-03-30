"""OTel Exporter - 將異常資料轉為 OpenTelemetry 標準 JSON."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from logsensing.analyzer.detector import Anomaly
except ImportError:
    from dataclasses import dataclass, field

    @dataclass
    class Anomaly:  # type: ignore[no-redef]
        """與 detector.Anomaly 相容的最小介面."""

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


class OTelExporter:
    """將異常資料轉為 OpenTelemetry 標準 JSON."""

    def __init__(
        self,
        service_name: str = "logsensing",
        device_model: str = "unknown",
    ) -> None:
        self.service_name = service_name
        self.device_model = device_model

    def export(
        self,
        anomalies: list[Any],
        output_path: Path | None = None,
    ) -> dict[str, Any]:
        """Convert anomalies to OTel JSON format and optionally write to file."""
        by_cycle: dict[int, list[Any]] = defaultdict(list)
        severity_counts: dict[str, int] = defaultdict(int)

        for a in anomalies:
            cid = a.cycle_id if hasattr(a, "cycle_id") else a.get("cycle_id", 0)
            by_cycle[cid].append(a)
            sev = a.severity if hasattr(a, "severity") else a.get("severity", "info")
            severity_counts[sev] += 1

        traces = []
        for cycle_id in sorted(by_cycle):
            spans = [self._anomaly_to_span(a) for a in by_cycle[cycle_id]]
            traces.append(
                {
                    "traceId": self._generate_trace_id(cycle_id),
                    "cycle_id": cycle_id,
                    "spans": spans,
                }
            )

        result: dict[str, Any] = {
            "resource": {
                "service.name": self.service_name,
                "device.model": self.device_model,
            },
            "summary": {
                "total_anomalies": len(anomalies),
                "by_severity": dict(severity_counts),
                "affected_cycles": sorted(by_cycle.keys()),
            },
            "traces": traces,
        }

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(result, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )

        return result

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _anomaly_to_span(self, a: Any) -> dict[str, Any]:
        """將單一 anomaly 轉為 OTel span dict."""

        def _get(obj: Any, attr: str, default: Any = "") -> Any:
            return getattr(obj, attr, None) if hasattr(obj, attr) else obj.get(attr, default)

        ctx_before = _get(a, "context_before", [])
        ctx_after = _get(a, "context_after", [])
        ts = _get(a, "timestamp", None)

        return {
            "spanId": self._generate_span_id(str(_get(a, "anomaly_id", ""))),
            "name": f"anomaly.{_get(a, 'rule_id', '')}",
            "startTimeUnixNano": self._timestamp_to_nano(ts),
            "attributes": {
                "anomaly.severity": _get(a, "severity", "info"),
                "anomaly.rule_id": _get(a, "rule_id", ""),
                "anomaly.rule_name": _get(a, "rule_name", ""),
                "anomaly.rule_type": _get(a, "rule_type", ""),
                "anomaly.cycle_id": _get(a, "cycle_id", 0),
                "anomaly.line_number": _get(a, "line_number", 0),
                "anomaly.message": _get(a, "message", ""),
            },
            "events": [
                {
                    "name": "context",
                    "attributes": {
                        "log.context_before": "\n".join(ctx_before),
                        "log.context_after": "\n".join(ctx_after),
                    },
                }
            ],
        }

    def _generate_trace_id(self, cycle_id: int) -> str:
        """Generate deterministic 32-char hex trace ID from cycle_id."""
        return hashlib.md5(f"cycle_{cycle_id}".encode()).hexdigest()

    def _generate_span_id(self, anomaly_id: str) -> str:
        """Generate 16-char hex span ID from anomaly_id."""
        return hashlib.md5(anomaly_id.encode()).hexdigest()[:16]

    def _timestamp_to_nano(self, ts: datetime | None) -> int:
        """Convert datetime to Unix nanoseconds. Return 0 if None."""
        if ts is None:
            return 0
        return int(ts.timestamp() * 1_000_000_000)

    def to_json(self, anomalies: list[Any]) -> str:
        """Export to JSON string."""
        return json.dumps(
            self.export(anomalies),
            indent=2,
            ensure_ascii=False,
            default=str,
        )
