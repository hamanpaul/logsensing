"""Tests for platform-scoped RAG memory."""

from __future__ import annotations

import json
from pathlib import Path

from logsensing.cli import _build_rag_retriever
from logsensing.config import AppConfig
from logsensing.parser.aaak import AAAKLogCompressor
from logsensing.rag.memory import (
    build_experience_artifact,
    get_platform_rag_store,
    list_experience_docs,
    write_experience_artifact,
)


def _make_log(path: Path, lines: list[str]) -> Path:
    path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return path


def _make_anomalies(message: str, rule_id: str = "kernel_panic") -> dict:
    return {
        "resource": {"device.model": "BGW720-300"},
        "summary": {"total_anomalies": 1, "affected_cycles": [1]},
        "traces": [
            {
                "cycle_id": 1,
                "spans": [
                    {
                        "attributes": {
                            "anomaly.rule_id": rule_id,
                            "anomaly.rule_name": rule_id.replace("_", " ").title(),
                            "anomaly.severity": "critical",
                            "anomaly.line_number": 10,
                            "anomaly.message": message,
                        },
                        "events": [
                            {
                                "name": "context",
                                "attributes": {
                                    "log.context_before": "before line",
                                    "log.context_after": "after line",
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }


def _make_drain_state(template: str) -> dict:
    return {
        "clusters": [
            {
                "cluster_id": 1,
                "cluster_count": 10,
                "log_template_tokens": template.split(),
            }
        ]
    }


def test_write_experience_artifact_creates_json_and_markdown(tmp_path: Path) -> None:
    logfile = _make_log(
        tmp_path / "device.log",
        ["[2026-03-18 13:54:59.000] U-Boot TPL", "[2026-03-18 13:55:00.000] panic"],
    )
    store = get_platform_rag_store(tmp_path, "bdk")
    artifact = build_experience_artifact(
        platform="bdk",
        device_model="BGW720-300",
        logfile=logfile,
        anomalies_data=_make_anomalies("Kernel panic - not syncing"),
        drain_state=_make_drain_state("kernel panic <*>"),
        analysis_text="Kernel panic caused by RPC tunnel timeout.",
        generated_by="llm",
        model_name="gpt-4o",
    )

    md_path, created = write_experience_artifact(store, artifact)

    assert created is True
    assert md_path.exists()
    json_path = store.experiences_dir / f"{artifact.experience_id}.json"
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["platform"] == "bdk"
    assert "Kernel panic" in md_path.read_text(encoding="utf-8")
    assert list_experience_docs(store) == [md_path]


def test_build_experience_artifact_with_compressor_sets_compact_summary(tmp_path: Path) -> None:
    logfile = _make_log(
        tmp_path / "device.log",
        ["[2026-03-18 13:54:59.000] U-Boot TPL", "[2026-03-18 13:55:00.000] panic"],
    )
    artifact = build_experience_artifact(
        platform="bdk",
        device_model="BGW720-300",
        logfile=logfile,
        anomalies_data=_make_anomalies("Kernel panic - not syncing"),
        drain_state=_make_drain_state("kernel panic <*>"),
        analysis_text="Kernel panic caused by RPC tunnel timeout.",
        generated_by="llm",
        compressor=AAAKLogCompressor(),
    )

    assert artifact.compact_format == "aaak-log-v1"
    assert "EXP|fmt=aaak-log-v1|plat=bdk" in artifact.compact_summary
    assert "F|KRN|sev=critical|rule=kernel_panic" in artifact.compact_summary


def test_write_experience_artifact_writes_compact_file(tmp_path: Path) -> None:
    logfile = _make_log(
        tmp_path / "device.log",
        ["[2026-03-18 13:54:59.000] U-Boot TPL", "[2026-03-18 13:55:00.000] panic"],
    )
    store = get_platform_rag_store(tmp_path, "bdk")
    artifact = build_experience_artifact(
        platform="bdk",
        device_model="BGW720-300",
        logfile=logfile,
        anomalies_data=_make_anomalies("Kernel panic - not syncing"),
        drain_state=_make_drain_state("kernel panic <*>"),
        analysis_text="Kernel panic caused by RPC tunnel timeout.",
        generated_by="llm",
        compressor=AAAKLogCompressor(),
    )

    md_path, created = write_experience_artifact(store, artifact)

    assert created is True
    assert md_path.exists()
    compact_path = store.experiences_dir / f"{artifact.experience_id}.aaak"
    assert compact_path.exists()
    assert "EXP|fmt=aaak-log-v1|plat=bdk" in compact_path.read_text(encoding="utf-8")


def test_write_experience_artifact_deduplicates(tmp_path: Path) -> None:
    logfile = _make_log(
        tmp_path / "device.log",
        ["[2026-03-18 13:54:59.000] U-Boot TPL", "[2026-03-18 13:55:00.000] panic"],
    )
    store = get_platform_rag_store(tmp_path, "bdk")
    artifact = build_experience_artifact(
        platform="bdk",
        device_model="BGW720-300",
        logfile=logfile,
        anomalies_data=_make_anomalies("Kernel panic - not syncing"),
        drain_state=_make_drain_state("kernel panic <*>"),
        analysis_text="Kernel panic caused by RPC tunnel timeout.",
        generated_by="llm",
    )

    _, first_created = write_experience_artifact(store, artifact)
    _, second_created = write_experience_artifact(store, artifact)

    assert first_created is True
    assert second_created is False
    assert len(list(store.experiences_dir.glob("*.md"))) == 1
    assert len(list(store.experiences_dir.glob("*.json"))) == 1


def test_build_rag_retriever_reads_platform_experience(tmp_path: Path) -> None:
    logfile = _make_log(
        tmp_path / "device.log",
        ["[2026-03-18 13:54:59.000] U-Boot TPL", "[2026-03-18 13:55:00.000] panic"],
    )
    store = get_platform_rag_store(tmp_path, "bdk")
    artifact = build_experience_artifact(
        platform="bdk",
        device_model="BGW720-300",
        logfile=logfile,
        anomalies_data=_make_anomalies("Kernel panic - not syncing"),
        drain_state=_make_drain_state("kernel panic <*>"),
        analysis_text="Kernel panic caused by RPC tunnel timeout.",
        generated_by="llm",
    )
    write_experience_artifact(store, artifact)

    cfg = AppConfig(rag={"index_root": str(tmp_path)})
    retriever = _build_rag_retriever(cfg, platform_name="bdk", force_rebuild=True)

    assert retriever is not None
    results = retriever.search("kernel panic", top_k=3)
    assert results
    assert any(r.chunk.metadata.get("source_type") == "experience" for r in results)
    assert all(r.chunk.metadata.get("platform") == "bdk" for r in results)


def test_build_rag_retriever_prefers_compact_experience_docs(tmp_path: Path) -> None:
    logfile = _make_log(
        tmp_path / "device.log",
        ["[2026-03-18 13:54:59.000] U-Boot TPL", "[2026-03-18 13:55:00.000] panic"],
    )
    store = get_platform_rag_store(tmp_path, "bdk")
    artifact = build_experience_artifact(
        platform="bdk",
        device_model="BGW720-300",
        logfile=logfile,
        anomalies_data=_make_anomalies("Kernel panic - not syncing"),
        drain_state=_make_drain_state("kernel panic <*>"),
        analysis_text="Kernel panic caused by RPC tunnel timeout.",
        generated_by="llm",
        compressor=AAAKLogCompressor(),
    )
    write_experience_artifact(store, artifact)

    cfg = AppConfig(
        rag={"index_root": str(tmp_path), "prefer_compact_experience": True}
    )
    retriever = _build_rag_retriever(cfg, platform_name="bdk", force_rebuild=True)

    assert retriever is not None
    results = retriever.search("kernel panic", top_k=3)
    assert results
    assert any(result.chunk.source.endswith(".aaak") for result in results)
    assert all(result.chunk.metadata.get("source_type") == "experience" for result in results)


def test_platform_rag_retriever_is_isolated(tmp_path: Path) -> None:
    bdk_log = _make_log(
        tmp_path / "bdk.log",
        ["[2026-03-18 13:54:59.000] U-Boot TPL", "[2026-03-18 13:55:00.000] panic"],
    )
    prplos_log = _make_log(
        tmp_path / "prplos.log",
        ["U-Boot TPL", "hostapd started"],
    )
    bdk_store = get_platform_rag_store(tmp_path, "bdk")
    prplos_store = get_platform_rag_store(tmp_path, "prplos")

    bdk_artifact = build_experience_artifact(
        platform="bdk",
        device_model="BGW720-300",
        logfile=bdk_log,
        anomalies_data=_make_anomalies("Kernel panic - not syncing"),
        drain_state=_make_drain_state("kernel panic <*>"),
        analysis_text="Kernel panic caused by RPC tunnel timeout.",
        generated_by="llm",
    )
    prplos_artifact = build_experience_artifact(
        platform="prplos",
        device_model="BGW720-300",
        logfile=prplos_log,
        anomalies_data=_make_anomalies("hostapd failed to start", rule_id="hostapd_fail"),
        drain_state=_make_drain_state("hostapd <*>"),
        analysis_text="hostapd failed due to config mismatch.",
        generated_by="llm",
    )
    write_experience_artifact(bdk_store, bdk_artifact)
    write_experience_artifact(prplos_store, prplos_artifact)

    cfg = AppConfig(rag={"index_root": str(tmp_path)})
    bdk_retriever = _build_rag_retriever(cfg, platform_name="bdk", force_rebuild=True)
    prplos_retriever = _build_rag_retriever(cfg, platform_name="prplos", force_rebuild=True)

    assert bdk_retriever is not None
    assert prplos_retriever is not None
    bdk_hits = bdk_retriever.search("kernel panic", top_k=3)
    prplos_hits = prplos_retriever.search("hostapd", top_k=3)
    assert bdk_hits
    assert prplos_hits
    assert all(hit.chunk.metadata.get("platform") == "bdk" for hit in bdk_hits)
    assert all(hit.chunk.metadata.get("platform") == "prplos" for hit in prplos_hits)
