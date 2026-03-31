"""Tests for AgentToolkit (agent tools)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from logsensing.agent.tools import AgentToolkit

# ---------------------------------------------------------------------------
# Sample data (matches OTel format used in test_agent.py)
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
                    "events": [],
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
                    "events": [],
                }
            ],
        },
    ],
}

SAMPLE_BASELINE: dict[str, Any] = {
    "mean_deltas": {"tpl_start→uboot_main": 1.5, "uboot_main→kernel_start": 3.2},
    "stddev_deltas": {"tpl_start→uboot_main": 0.1, "uboot_main→kernel_start": 0.3},
    "sample_count": 10,
}

SAMPLE_DRAIN_STATE: dict[str, Any] = {
    "clusters": [
        {
            "cluster_id": 1,
            "cluster_count": 200,
            "log_template_tokens": ["U-Boot", "TPL", "<*>"],
        },
        {
            "cluster_id": 2,
            "cluster_count": 50,
            "log_template_tokens": ["dhcp", "lease", "renewed"],
        },
        {
            "cluster_id": 3,
            "cluster_count": 150,
            "log_template_tokens": ["wifi", "module", "loaded"],
        },
    ],
}

SAMPLE_LOG_LINES: dict[int, list[str]] = {
    1: [
        "[2026-03-18 13:54:42.819] U-Boot TPL 2024.04",
        "[2026-03-18 13:54:43.000] Kernel panic - not syncing",
        "[2026-03-18 13:54:44.000] dhcp lease renewed",
        "[2026-03-18 13:54:45.000] wifi module loaded",
        "[2026-03-18 13:54:46.000] boot complete",
    ],
    2: [
        "[2026-03-18 14:00:00.000] U-Boot TPL 2024.04",
        "[2026-03-18 14:00:01.000] watchdog timer reset",
        "[2026-03-18 14:00:02.000] system recovered",
    ],
}


@pytest.fixture()
def toolkit() -> AgentToolkit:
    """Fully-populated toolkit for most tests."""
    return AgentToolkit(
        anomalies_data=SAMPLE_ANOMALIES,
        baseline_data=SAMPLE_BASELINE,
        drain_state=SAMPLE_DRAIN_STATE,
        log_lines=SAMPLE_LOG_LINES,
    )


# ===================================================================
# get_anomalies
# ===================================================================
class TestGetAnomalies:
    """get_anomalies 測試."""

    def test_get_anomalies_all(self, toolkit: AgentToolkit) -> None:
        """Returns all anomalies when no cycle_id given."""
        raw = toolkit.get_anomalies()
        data = json.loads(raw)
        assert data["total"] == 2
        assert len(data["cycles"]) == 2

    def test_get_anomalies_by_cycle(self, toolkit: AgentToolkit) -> None:
        """Filters by cycle_id."""
        raw = toolkit.get_anomalies(cycle_id=1)
        data = json.loads(raw)
        assert data["total"] == 1
        assert len(data["cycles"]) == 1
        assert data["cycles"][0]["cycle_id"] == 1
        assert data["cycles"][0]["anomalies"][0]["rule_id"] == "kernel_panic"

    def test_get_anomalies_empty(self) -> None:
        """Empty anomalies_data returns total 0."""
        tk = AgentToolkit()
        raw = tk.get_anomalies()
        data = json.loads(raw)
        assert data["total"] == 0
        assert data["cycles"] == []


# ===================================================================
# get_cycle_context
# ===================================================================
class TestGetCycleContext:
    """get_cycle_context 測試."""

    def test_get_cycle_context(self, toolkit: AgentToolkit) -> None:
        """Returns log lines for a cycle."""
        raw = toolkit.get_cycle_context(cycle_id=1)
        data = json.loads(raw)
        assert data["cycle_id"] == 1
        assert data["total_lines"] == 5
        assert data["returned_lines"] == 5
        assert len(data["lines"]) == 5

    def test_get_cycle_context_range(self, toolkit: AgentToolkit) -> None:
        """Respects start_line / end_line."""
        raw = toolkit.get_cycle_context(cycle_id=1, start_line=1, end_line=3)
        data = json.loads(raw)
        assert data["returned_lines"] == 2
        assert "Kernel panic" in data["lines"][0]

    def test_get_cycle_context_missing(self, toolkit: AgentToolkit) -> None:
        """Returns error for missing cycle."""
        raw = toolkit.get_cycle_context(cycle_id=999)
        data = json.loads(raw)
        assert "error" in data


# ===================================================================
# get_baseline
# ===================================================================
class TestGetBaseline:
    """get_baseline 測試."""

    def test_get_baseline(self, toolkit: AgentToolkit) -> None:
        """Returns baseline JSON."""
        raw = toolkit.get_baseline()
        data = json.loads(raw)
        assert "mean_deltas" in data
        assert data["sample_count"] == 10


# ===================================================================
# get_templates
# ===================================================================
class TestGetTemplates:
    """get_templates 測試."""

    def test_get_templates(self, toolkit: AgentToolkit) -> None:
        """Returns templates sorted by frequency (descending)."""
        raw = toolkit.get_templates(top_k=20)
        data = json.loads(raw)
        assert data["total_templates"] == 3
        templates = data["top_templates"]
        assert len(templates) == 3
        # First should be cluster_id=1 (count=200), second cluster_id=3 (count=150)
        assert templates[0]["count"] >= templates[1]["count"]
        assert templates[1]["count"] >= templates[2]["count"]


# ===================================================================
# search_logs
# ===================================================================
class TestSearchLogs:
    """search_logs 測試."""

    def test_search_logs(self, toolkit: AgentToolkit) -> None:
        """Finds matching lines across all cycles."""
        raw = toolkit.search_logs(query="Kernel panic")
        data = json.loads(raw)
        assert data["total_matches"] >= 1
        assert any("Kernel panic" in r["line"] for r in data["results"])

    def test_search_logs_by_cycle(self, toolkit: AgentToolkit) -> None:
        """Filters search to specific cycle."""
        raw = toolkit.search_logs(query="U-Boot", cycle_id=2)
        data = json.loads(raw)
        assert data["total_matches"] >= 1
        assert all(r["cycle_id"] == 2 for r in data["results"])


# ===================================================================
# search_knowledge_base
# ===================================================================
class TestSearchKnowledgeBase:
    """search_knowledge_base 測試."""

    def test_search_knowledge_base_no_retriever(self) -> None:
        """Returns error when no retriever configured."""
        tk = AgentToolkit()
        raw = tk.search_knowledge_base(query="anything")
        data = json.loads(raw)
        assert "error" in data
        assert "not configured" in data["error"].lower()

    def test_search_knowledge_base_with_metadata(self) -> None:
        """Returns source_type/platform when retriever has chunk metadata."""
        from logsensing.rag.bm25 import SearchResult
        from logsensing.rag.chunker import Chunk

        class FakeRetriever:
            def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
                return [
                    SearchResult(
                        chunk=Chunk(
                            chunk_id="exp-1",
                            text="Kernel panic likely linked to RPC tunnel timeout.",
                            source="experience.md",
                            chunk_index=0,
                            metadata={"source_type": "experience", "platform": "bdk"},
                        ),
                        score=0.91,
                    )
                ]

        tk = AgentToolkit(retriever=FakeRetriever())
        raw = tk.search_knowledge_base(query="kernel panic")
        data = json.loads(raw)
        assert data["results"][0]["source_type"] == "experience"
        assert data["results"][0]["platform"] == "bdk"
