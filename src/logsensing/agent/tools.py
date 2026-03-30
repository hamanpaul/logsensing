"""Agent 工具定義 — 提供 LLM 可呼叫的分析工具."""
from __future__ import annotations

import json
from typing import Any

from logsensing.agent.llm import LLMClient

# Tool parameter schemas (JSON Schema format)
TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "get_anomalies": {
        "type": "object",
        "properties": {
            "cycle_id": {
                "type": "integer",
                "description": "Boot cycle ID. If omitted, return all anomalies.",
            },
        },
        "required": [],
    },
    "get_cycle_context": {
        "type": "object",
        "properties": {
            "cycle_id": {"type": "integer", "description": "Boot cycle ID"},
            "start_line": {"type": "integer", "description": "Start line number (optional)"},
            "end_line": {"type": "integer", "description": "End line number (optional)"},
        },
        "required": ["cycle_id"],
    },
    "get_baseline": {
        "type": "object",
        "properties": {},
        "required": [],
    },
    "get_templates": {
        "type": "object",
        "properties": {
            "top_k": {
                "type": "integer",
                "description": "Number of top templates to return",
                "default": 20,
            },
        },
        "required": [],
    },
    "search_logs": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query string"},
            "cycle_id": {
                "type": "integer",
                "description": "Limit search to specific cycle (optional)",
            },
        },
        "required": ["query"],
    },
    "search_knowledge_base": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query for documentation/knowledge base",
            },
            "top_k": {"type": "integer", "description": "Number of results", "default": 5},
        },
        "required": ["query"],
    },
}


class AgentToolkit:
    """Provides tool implementations for the LLM agent."""

    def __init__(
        self,
        anomalies_data: dict[str, Any] | None = None,
        baseline_data: dict[str, Any] | None = None,
        drain_state: dict[str, Any] | None = None,
        log_lines: dict[int, list[str]] | None = None,
        retriever: Any = None,
    ):
        self._anomalies = anomalies_data or {}
        self._baseline = baseline_data or {}
        self._drain_state = drain_state or {}
        self._log_lines = log_lines or {}
        self._retriever = retriever

    def register_all(self, client: LLMClient) -> None:
        """Register all tools with the LLM client."""
        client.register_tool(
            "get_anomalies", "取得異常事件清單", TOOL_SCHEMAS["get_anomalies"], self.get_anomalies
        )
        client.register_tool(
            "get_cycle_context",
            "取得指定 cycle 原始日誌",
            TOOL_SCHEMAS["get_cycle_context"],
            self.get_cycle_context,
        )
        client.register_tool(
            "get_baseline", "取得基準線 profile", TOOL_SCHEMAS["get_baseline"], self.get_baseline
        )
        client.register_tool(
            "get_templates",
            "取得 Drain3 模板清單",
            TOOL_SCHEMAS["get_templates"],
            self.get_templates,
        )
        client.register_tool(
            "search_logs", "全文搜尋日誌", TOOL_SCHEMAS["search_logs"], self.search_logs
        )
        client.register_tool(
            "search_knowledge_base",
            "搜尋文件知識庫",
            TOOL_SCHEMAS["search_knowledge_base"],
            self.search_knowledge_base,
        )

    def get_anomalies(self, cycle_id: int | None = None) -> str:
        """Get anomalies, optionally filtered by cycle_id."""
        traces = self._anomalies.get("traces", [])
        if cycle_id is not None:
            traces = [t for t in traces if t.get("cycle_id") == cycle_id]

        result: dict[str, Any] = {
            "total": sum(len(t.get("spans", [])) for t in traces),
            "cycles": [],
        }
        for t in traces:
            spans = t.get("spans", [])
            cycle_info = {
                "cycle_id": t.get("cycle_id"),
                "anomaly_count": len(spans),
                "anomalies": [
                    {
                        "severity": s.get("attributes", {}).get("anomaly.severity", "info"),
                        "rule_id": s.get("attributes", {}).get("anomaly.rule_id", ""),
                        "rule_name": s.get("attributes", {}).get("anomaly.rule_name", ""),
                        "message": s.get("attributes", {}).get("anomaly.message", ""),
                        "line_number": s.get("attributes", {}).get("anomaly.line_number", 0),
                    }
                    for s in spans
                ],
            }
            result["cycles"].append(cycle_info)
        return json.dumps(result, ensure_ascii=False, indent=2)

    def get_cycle_context(
        self, cycle_id: int, start_line: int | None = None, end_line: int | None = None
    ) -> str:
        """Get raw log lines for a cycle."""
        lines = self._log_lines.get(cycle_id, [])
        if not lines:
            return json.dumps({"error": f"No log data for cycle {cycle_id}"})

        if start_line is not None and end_line is not None:
            lines = lines[start_line:end_line]
        elif start_line is not None:
            lines = lines[start_line : start_line + 100]  # default 100 lines

        return json.dumps(
            {
                "cycle_id": cycle_id,
                "total_lines": len(self._log_lines.get(cycle_id, [])),
                "returned_lines": len(lines),
                "lines": lines[:200],  # cap at 200 lines to avoid token overflow
            },
            ensure_ascii=False,
        )

    def get_baseline(self) -> str:
        """Get baseline profile."""
        return json.dumps(self._baseline, ensure_ascii=False, indent=2)

    def get_templates(self, top_k: int = 20) -> str:
        """Get top Drain3 templates by frequency."""
        clusters = self._drain_state.get("clusters", [])
        sorted_clusters = sorted(
            clusters, key=lambda c: c.get("cluster_count", c.get("size", 0)), reverse=True
        )
        top = sorted_clusters[:top_k]
        result = {
            "total_templates": len(clusters),
            "top_templates": [
                {
                    "id": c.get("cluster_id", "?"),
                    "count": c.get("cluster_count", c.get("size", 0)),
                    "template": " ".join(c["log_template_tokens"])
                    if isinstance(c.get("log_template_tokens"), list)
                    else c.get("template", ""),
                }
                for c in top
            ],
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    def search_logs(self, query: str, cycle_id: int | None = None) -> str:
        """Full-text search across log lines."""
        results: list[dict[str, Any]] = []
        query_lower = query.lower()

        cycles_to_search = (
            {cycle_id: self._log_lines[cycle_id]}
            if cycle_id and cycle_id in self._log_lines
            else self._log_lines
        )

        for cid, cid_lines in cycles_to_search.items():
            for i, line in enumerate(cid_lines):
                if query_lower in line.lower():
                    results.append({"cycle_id": cid, "line_number": i, "line": line.rstrip()})
                    if len(results) >= 50:
                        break
            if len(results) >= 50:
                break

        return json.dumps(
            {"query": query, "total_matches": len(results), "results": results[:50]},
            ensure_ascii=False,
        )

    def search_knowledge_base(self, query: str, top_k: int = 5) -> str:
        """Search knowledge base using RAG retriever."""
        if self._retriever is None:
            return json.dumps({"error": "Knowledge base not configured"})

        search_results = self._retriever.search(query, top_k=top_k)
        return json.dumps(
            {
                "query": query,
                "results": [
                    {
                        "source": r.chunk.source,
                        "score": round(r.score, 4),
                        "text": r.chunk.text[:500],
                    }
                    for r in search_results
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
