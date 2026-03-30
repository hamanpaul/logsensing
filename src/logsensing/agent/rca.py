"""Root Cause Analysis Agent."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

# Severity ordering for comparison
_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


class RCAReport:
    """RCA 報告生成器（不依賴 LLM 的規則式版本）."""

    def __init__(
        self,
        anomalies_path: Path | None = None,
        anomalies_data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize with anomalies JSON file or pre-loaded data."""
        if anomalies_data is not None:
            self._data = anomalies_data
        elif anomalies_path is not None:
            self._data = self._load_anomalies(anomalies_path)
        else:
            self._data = {"resource": {}, "summary": {}, "traces": []}

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def generate_cycle_report(self, cycle_id: int) -> str:
        """Generate a markdown RCA report for a specific cycle."""
        anomalies = self._get_cycle_anomalies(cycle_id)
        if not anomalies:
            return f"## Cycle #{cycle_id} - Root Cause Analysis\n\n此 cycle 未偵測到異常事件。\n"

        highest = self._highest_severity(anomalies)
        lines: list[str] = [
            f"## Cycle #{cycle_id} - Root Cause Analysis",
            "",
            f"**嚴重程度:** {highest.capitalize()}",
            f"**異常數量:** {len(anomalies)}",
            "",
            "### 異常事件",
        ]

        for a in anomalies:
            attrs = a.get("attributes", {})
            events = a.get("events", [])
            ctx_before = ""
            ctx_after = ""
            for evt in events:
                if evt.get("name") == "context":
                    ctx_before = evt.get("attributes", {}).get("log.context_before", "")
                    ctx_after = evt.get("attributes", {}).get("log.context_after", "")

            severity = attrs.get("anomaly.severity", "info")
            rule_name = attrs.get("anomaly.rule_name", "")
            rule_id = attrs.get("anomaly.rule_id", "")
            line_number = attrs.get("anomaly.line_number", 0)
            message = attrs.get("anomaly.message", "")

            lines.append(f"- **[{severity}] {rule_name}** ({rule_id})")
            lines.append(f"  - 時間: {a.get('startTimeUnixNano', 0)}")
            lines.append(f"  - 行號: {line_number}")
            lines.append(f"  - 訊息: {message}")

            before_lines = ctx_before.split("\n") if ctx_before else []
            after_lines = ctx_after.split("\n") if ctx_after else []
            lines.append(f"  - 上下文 (前): {', '.join(before_lines[:5])}")
            lines.append(f"  - 上下文 (後): {', '.join(after_lines[:5])}")

        lines.append("")
        lines.append("### 摘要")
        lines.append(
            f"Cycle #{cycle_id} 共偵測到 {len(anomalies)} 個異常事件,"
            f"最高嚴重程度為 {highest}。"
        )
        lines.append("")
        return "\n".join(lines)

    def generate_summary_report(self) -> str:
        """Generate a full summary report across all cycles."""
        resource = self._data.get("resource", {})
        summary = self._data.get("summary", {})
        device_model = resource.get("device.model", "unknown")
        total = summary.get("total_anomalies", 0)
        by_severity = summary.get("by_severity", {})
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines: list[str] = [
            "# LogSensing RCA Summary Report",
            "",
            f"**裝置:** {device_model}",
            f"**分析時間:** {now}",
            f"**總異常數:** {total}",
            "",
            "## 嚴重程度分布",
            f"- Critical: {by_severity.get('critical', 0)}",
            f"- Warning: {by_severity.get('warning', 0)}",
            f"- Info: {by_severity.get('info', 0)}",
            "",
        ]

        cycle_ids = self._get_all_cycle_ids()
        if cycle_ids:
            lines.append("## 受影響的 Cycles")
            lines.append("")
            lines.append("| Cycle | 異常數量 | 最高嚴重程度 |")
            lines.append("|-------|----------|-------------|")
            for cid in cycle_ids:
                cycle_anomalies = self._get_cycle_anomalies(cid)
                highest = self._highest_severity(cycle_anomalies)
                lines.append(f"| {cid} | {len(cycle_anomalies)} | {highest} |")
            lines.append("")

            lines.append("## 各 Cycle 詳細報告")
            lines.append("")
            for cid in cycle_ids:
                lines.append(self.generate_cycle_report(cid))
        else:
            lines.append("未偵測到任何異常事件。")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # private helpers
    # ------------------------------------------------------------------

    def _load_anomalies(self, path: Path) -> dict[str, Any]:
        """Load anomalies JSON file."""
        text = path.read_text(encoding="utf-8")
        return json.loads(text)  # type: ignore[no-any-return]

    def _get_cycle_anomalies(self, cycle_id: int) -> list[dict[str, Any]]:
        """Get anomalies (as span dicts) for a specific cycle."""
        for trace in self._data.get("traces", []):
            if trace.get("cycle_id") == cycle_id:
                return trace.get("spans", [])  # type: ignore[no-any-return]
        return []

    def _get_all_cycle_ids(self) -> list[int]:
        """Get all cycle IDs that have anomalies."""
        return [t["cycle_id"] for t in self._data.get("traces", []) if "cycle_id" in t]

    @staticmethod
    def _highest_severity(anomalies: list[dict[str, Any]]) -> str:
        """Return the highest severity among anomalies."""
        best = "info"
        for a in anomalies:
            sev = a.get("attributes", {}).get("anomaly.severity", "info")
            if _SEVERITY_ORDER.get(sev, 99) < _SEVERITY_ORDER.get(best, 99):
                best = sev
        return best
