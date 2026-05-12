"""Tests for AAAK compact summaries."""

from __future__ import annotations

from logsensing.config import AppConfig
from logsensing.parser.aaak import AAAKLogCompressor
from logsensing.parser.drain import LogTemplate
from logsensing.rag.memory import ExperienceArtifact


def test_app_config_aaak_defaults() -> None:
    cfg = AppConfig()

    assert cfg.parser.aaak_enabled is False
    assert cfg.parser.aaak_entity_map == {}
    assert cfg.parser.aaak_max_summary_items == 5
    assert cfg.rag.prefer_compact_experience is False
    assert cfg.rag.vector_backend == "faiss"
    assert cfg.rag.vector_compression_bits == 4
    assert cfg.rag.vector_rotation_seed == 0


def test_compress_templates_uses_domain_entity_codes() -> None:
    compressor = AAAKLogCompressor()
    templates = [
        LogTemplate(
            template_id=1,
            template="RPC: initializing rpc_init service",
            count=8,
            cluster_id=1,
        ),
        LogTemplate(
            template_id=2,
            template="Kernel panic <*> occurred",
            count=3,
            cluster_id=2,
        ),
    ]

    compact = compressor.compress_templates(templates)

    assert "TPLSET|fmt=aaak-log-v1|count=2" in compact
    assert 'TPL|RPC|hit=8|kw=rpc_initializing|"RPC: initializing rpc_init service"' in compact
    assert 'TPL|KRN|hit=3|kw=kernel_panic|"Kernel panic * occurred"' in compact


def test_compress_experience_formats_findings_templates_and_rca() -> None:
    artifact = ExperienceArtifact(
        experience_id="bdk-001",
        platform="bdk",
        device_model="BGW720-300",
        source_log={"path": "/tmp/device.log", "size_bytes": 10, "mtime_ns": 1},
        created_at="2026-04-09T00:00:00Z",
        analysis_mode="agent_analyze",
        summary={"total_anomalies": 1, "highest_severity": "critical", "affected_cycles": [1]},
        findings=[
            {
                "cycle_id": 1,
                "rule_id": "kernel_panic",
                "rule_name": "Kernel Panic",
                "severity": "critical",
                "line_number": 10,
                "message": "Kernel panic - not syncing",
            }
        ],
        rca={"short_summary": "Kernel panic caused by RPC timeout during boot."},
        evidence={"top_templates": ["RPC: initializing rpc_init service"], "log_snippets": []},
        provenance={"generated_by": "llm", "model": "gpt-4o", "confidence": "medium"},
    )
    compressor = AAAKLogCompressor()

    compact = compressor.compress_experience(artifact)

    assert (
        "EXP|fmt=aaak-log-v1|plat=bdk|model=BGW720-300|anom=1|sev=critical|cycles=1"
        in compact
    )
    assert (
        'F|KRN|sev=critical|rule=kernel_panic|cycle=1|line=10|"Kernel panic - not syncing"'
        in compact
    )
    assert 'TPL|RPC|kw=rpc_initializing|"RPC: initializing rpc_init service"' in compact
    assert 'RCA|KRN|"Kernel panic caused by RPC timeout during boot."' in compact
