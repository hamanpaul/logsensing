"""LogSensing CLI 測試."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest
from typer.testing import CliRunner

from logsensing.cli import _build_rag_retriever, app
from logsensing.config import AppConfig
from logsensing.rag.memory import (
    build_experience_artifact,
    get_platform_rag_store,
    write_experience_artifact,
)

runner = CliRunner()

SAMPLE_LOG = (
    Path(__file__).parent.parent / "docs" / "sample_logs" / "20260318_ATT_newHW7-normal_1354.log"
)


# ---------------------------------------------------------------------------
# Help tests
# ---------------------------------------------------------------------------

def test_main_help() -> None:
    """主指令 --help 應列出所有子指令."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "parse" in result.output
    assert "analyze" in result.output
    assert "report" in result.output
    assert "train" in result.output
    assert "agent" in result.output


def test_parse_help() -> None:
    """parse --help 應顯示選項說明."""
    result = runner.invoke(app, ["parse", "--help"])
    assert result.exit_code == 0
    assert "LOGFILE" in result.output or "logfile" in result.output.lower()
    assert "--output" in result.output
    assert "--config" in result.output


def test_analyze_help() -> None:
    """analyze --help 應顯示選項說明."""
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "--output" in result.output
    assert "--baseline" in result.output
    assert "--device-model" in result.output


def test_train_baseline_help() -> None:
    """train baseline --help 應顯示選項說明."""
    result = runner.invoke(app, ["train", "baseline", "--help"])
    assert result.exit_code == 0
    assert "LOGFILE" in result.output or "logfile" in result.output.lower()
    assert "--output" in result.output


def test_train_drain_help() -> None:
    """train drain --help 應顯示選項說明."""
    result = runner.invoke(app, ["train", "drain", "--help"])
    assert result.exit_code == 0
    assert "LOGFILE" in result.output or "logfile" in result.output.lower()
    assert "--output" in result.output


def test_report_help() -> None:
    """report --help 應顯示選項說明."""
    result = runner.invoke(app, ["report", "--help"])
    assert result.exit_code == 0
    assert "開機時間統計報告" in result.output


def test_agent_analyze_help() -> None:
    """agent analyze --help 應顯示 RAG 選項."""
    result = runner.invoke(app, ["agent", "analyze", "--help"])
    assert result.exit_code == 0
    assert "--knowledge-doc" in result.output
    assert "--bm25-index" in result.output
    assert "--faiss-index" in result.output
    assert "--platform" in result.output


def test_agent_chat_help() -> None:
    """agent chat --help 應顯示 RAG 選項."""
    result = runner.invoke(app, ["agent", "chat", "--help"])
    assert result.exit_code == 0
    assert "--knowledge-doc" in result.output
    assert "--bm25-index" in result.output
    assert "--faiss-index" in result.output
    assert "--platform" in result.output


# ---------------------------------------------------------------------------
# Functional tests (with sample log)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not SAMPLE_LOG.exists(), reason="sample log not found")
def test_parse_with_sample_log(tmp_path: Path) -> None:
    """parse 指令應能成功解析樣本日誌."""
    output_dir = tmp_path / "parse_output"
    result = runner.invoke(app, ["parse", str(SAMPLE_LOG), "--output", str(output_dir)])
    assert result.exit_code == 0, f"parse failed:\n{result.output}"
    assert output_dir.exists()
    state_file = output_dir / "drain_state.json"
    assert state_file.exists(), "drain_state.json should be created"
    assert state_file.stat().st_size > 0


@pytest.mark.skipif(not SAMPLE_LOG.exists(), reason="sample log not found")
def test_analyze_with_sample_log(tmp_path: Path) -> None:
    """analyze 指令應能成功分析並產出 anomalies.json."""
    output_file = tmp_path / "anomalies.json"
    result = runner.invoke(app, ["analyze", str(SAMPLE_LOG), "--output", str(output_file)])
    assert result.exit_code == 0, f"analyze failed:\n{result.output}"
    assert output_file.exists(), "anomalies.json should be created"
    assert output_file.stat().st_size > 0


@pytest.mark.skipif(not SAMPLE_LOG.exists(), reason="sample log not found")
def test_train_baseline_with_sample_log(tmp_path: Path) -> None:
    """train baseline 指令應能成功訓練並儲存 baseline.json."""
    output_file = tmp_path / "baseline.json"
    result = runner.invoke(
        app, ["train", "baseline", str(SAMPLE_LOG), "--output", str(output_file)]
    )
    assert result.exit_code == 0, f"train baseline failed:\n{result.output}"
    assert output_file.exists(), "baseline.json should be created"
    assert output_file.stat().st_size > 0


@pytest.mark.skipif(not SAMPLE_LOG.exists(), reason="sample log not found")
def test_train_drain_with_sample_log(tmp_path: Path) -> None:
    """train drain 指令應能成功訓練並儲存 drain state."""
    output_file = tmp_path / "drain_state.json"
    result = runner.invoke(
        app, ["train", "drain", str(SAMPLE_LOG), "--output", str(output_file)]
    )
    assert result.exit_code == 0, f"train drain failed:\n{result.output}"
    assert output_file.exists(), "drain_state.json should be created"
    assert output_file.stat().st_size > 0


def test_build_rag_retriever_from_docs_and_save_bm25(tmp_path: Path) -> None:
    """RAG retriever 應能從文件建立並儲存 BM25 索引."""
    kb_doc = tmp_path / "kb.md"
    kb_doc.write_text(
        "# Platform Notes\nRPC tunnel failure may cause kernel panic during boot.\n",
        encoding="utf-8",
    )
    bm25_path = tmp_path / "kb-bm25.json"

    retriever = _build_rag_retriever(
        AppConfig(),
        knowledge_docs=[kb_doc],
        bm25_index=bm25_path,
    )

    assert retriever is not None
    assert bm25_path.exists()
    results = retriever.search("kernel panic", top_k=3)
    assert results
    assert any("kernel panic" in r.chunk.text.lower() for r in results)


def test_agent_analyze_wires_rag_retriever(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """agent analyze 應將 RAG retriever 傳入 AgentToolkit."""
    anomalies_path = tmp_path / "anomalies.json"
    anomalies_path.write_text(
        json.dumps({"summary": {"total_anomalies": 1}, "traces": [{"cycle_id": 1, "spans": []}]}),
        encoding="utf-8",
    )
    kb_doc = tmp_path / "kb.md"
    kb_doc.write_text("Kernel panic is often related to RPC tunnel issues.", encoding="utf-8")

    captured: dict[str, object] = {}

    class FakeLLMClient:
        def __init__(
            self,
            model: str = "fake",
            api_base: str | None = None,
            temperature: float = 0.1,
            max_tokens: int = 4096,
        ) -> None:
            self._model = model

        def register_tool(self, *args: object, **kwargs: object) -> None:
            return None

        def chat(
            self,
            messages: list[dict[str, str]],
            system_prompt: str | None = None,
        ) -> str:
            return "RAG connected"

        @property
        def model(self) -> str:
            return self._model

    class FakeAgentToolkit:
        def __init__(self, **kwargs: object) -> None:
            captured["retriever"] = kwargs.get("retriever")
            captured["anomalies"] = kwargs.get("anomalies_data")

        def register_all(self, client: object) -> None:
            captured["registered"] = True

    fake_llm = types.ModuleType("logsensing.agent.llm")
    fake_llm.LLMClient = FakeLLMClient
    fake_tools = types.ModuleType("logsensing.agent.tools")
    fake_tools.AgentToolkit = FakeAgentToolkit
    monkeypatch.setitem(sys.modules, "logsensing.agent.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "logsensing.agent.tools", fake_tools)

    result = runner.invoke(
        app,
        ["agent", "analyze", "--anomalies", str(anomalies_path), "--knowledge-doc", str(kb_doc)],
    )
    assert result.exit_code == 0, result.output
    assert captured.get("registered") is True
    assert captured.get("retriever") is not None


def test_agent_chat_wires_rag_retriever(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """agent chat 應將 RAG retriever 傳入 AgentToolkit."""
    from rich.prompt import Prompt

    kb_doc = tmp_path / "kb.md"
    kb_doc.write_text("WiFi bring-up depends on PCIe link up.", encoding="utf-8")

    captured: dict[str, object] = {}

    class FakeLLMClient:
        def __init__(
            self,
            model: str = "fake",
            api_base: str | None = None,
            temperature: float = 0.1,
            max_tokens: int = 4096,
        ) -> None:
            self._model = model

        def register_tool(self, *args: object, **kwargs: object) -> None:
            return None

        def chat(
            self,
            messages: list[dict[str, str]],
            system_prompt: str | None = None,
        ) -> str:
            return "hello"

        @property
        def model(self) -> str:
            return self._model

    class FakeAgentToolkit:
        def __init__(self, **kwargs: object) -> None:
            captured["retriever"] = kwargs.get("retriever")

        def register_all(self, client: object) -> None:
            captured["registered"] = True

    fake_llm = types.ModuleType("logsensing.agent.llm")
    fake_llm.LLMClient = FakeLLMClient
    fake_tools = types.ModuleType("logsensing.agent.tools")
    fake_tools.AgentToolkit = FakeAgentToolkit
    monkeypatch.setitem(sys.modules, "logsensing.agent.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "logsensing.agent.tools", fake_tools)
    monkeypatch.setattr(Prompt, "ask", lambda *args, **kwargs: "quit")

    result = runner.invoke(app, ["agent", "chat", "--knowledge-doc", str(kb_doc)])
    assert result.exit_code == 0, result.output
    assert captured.get("registered") is True
    assert captured.get("retriever") is not None


def test_agent_analyze_writes_platform_experience(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """agent analyze 完成後會把經驗回寫到平台 RAG store."""
    anomalies_path = tmp_path / "anomalies.json"
    anomalies_path.write_text(
        json.dumps(
            {
                "resource": {"device.model": "BGW720-300"},
                "summary": {"total_anomalies": 1, "affected_cycles": [1]},
                "traces": [
                    {
                        "cycle_id": 1,
                        "spans": [
                            {
                                "attributes": {
                                    "anomaly.rule_id": "kernel_panic",
                                    "anomaly.rule_name": "Kernel Panic",
                                    "anomaly.severity": "critical",
                                    "anomaly.line_number": 2,
                                    "anomaly.message": "Kernel panic - not syncing",
                                },
                                "events": [],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    logfile = tmp_path / "device.log"
    logfile.write_text(
        "[2026-03-18 13:54:59.000] U-Boot TPL\n"
        "[2026-03-18 13:55:00.000] Kernel panic - not syncing\n",
        encoding="utf-8",
    )
    config_path = tmp_path / "config.toml"
    rag_root = (tmp_path / "rag-store").resolve()
    config_path.write_text(
        f'platform = "bdk"\n[rag]\nindex_root = "{rag_root}"\nauto_writeback = true\n',
        encoding="utf-8",
    )

    class FakeLLMClient:
        def __init__(
            self,
            model: str = "fake",
            api_base: str | None = None,
            temperature: float = 0.1,
            max_tokens: int = 4096,
        ) -> None:
            self._model = model

        def register_tool(self, *args: object, **kwargs: object) -> None:
            return None

        def chat(
            self,
            messages: list[dict[str, str]],
            system_prompt: str | None = None,
        ) -> str:
            return "Kernel panic root cause summary."

        @property
        def model(self) -> str:
            return self._model

    class FakeAgentToolkit:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def register_all(self, client: object) -> None:
            return None

    fake_llm = types.ModuleType("logsensing.agent.llm")
    fake_llm.LLMClient = FakeLLMClient
    fake_tools = types.ModuleType("logsensing.agent.tools")
    fake_tools.AgentToolkit = FakeAgentToolkit
    monkeypatch.setitem(sys.modules, "logsensing.agent.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "logsensing.agent.tools", fake_tools)

    result = runner.invoke(
        app,
        [
            "agent",
            "analyze",
            "--config",
            str(config_path),
            "--platform",
            "bdk",
            "--anomalies",
            str(anomalies_path),
            "--logfile",
            str(logfile),
        ],
    )
    assert result.exit_code == 0, result.output
    store = rag_root / "bdk"
    assert (store / "bm25.json").exists()
    assert len(list((store / "experiences").glob("*.md"))) == 1
    assert len(list((store / "experiences").glob("*.json"))) == 1


def test_agent_chat_loads_platform_experience_from_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """agent chat 在下一次分析時可讀回同平台經驗."""
    from rich.prompt import Prompt

    logfile = tmp_path / "device.log"
    logfile.write_text(
        "[2026-03-18 13:54:59.000] U-Boot TPL\n"
        "[2026-03-18 13:55:00.000] Kernel panic - not syncing\n",
        encoding="utf-8",
    )
    rag_root = (tmp_path / "rag-store").resolve()
    store = get_platform_rag_store(rag_root, "bdk")
    artifact = build_experience_artifact(
        platform="bdk",
        device_model="BGW720-300",
        logfile=logfile,
        anomalies_data={
            "resource": {"device.model": "BGW720-300"},
            "summary": {"total_anomalies": 1, "affected_cycles": [1]},
            "traces": [
                {
                    "cycle_id": 1,
                    "spans": [
                        {
                            "attributes": {
                                "anomaly.rule_id": "kernel_panic",
                                "anomaly.rule_name": "Kernel Panic",
                                "anomaly.severity": "critical",
                                "anomaly.line_number": 2,
                                "anomaly.message": "Kernel panic - not syncing",
                            },
                            "events": [],
                        }
                    ],
                }
            ],
        },
        drain_state={"clusters": []},
        analysis_text="Kernel panic root cause summary.",
        generated_by="llm",
    )
    write_experience_artifact(store, artifact)
    _build_rag_retriever(
        AppConfig(rag={"index_root": str(rag_root)}),
        platform_name="bdk",
        force_rebuild=True,
    )

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f'platform = "bdk"\n[rag]\nindex_root = "{rag_root}"\nauto_writeback = true\n',
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    class FakeLLMClient:
        def __init__(
            self,
            model: str = "fake",
            api_base: str | None = None,
            temperature: float = 0.1,
            max_tokens: int = 4096,
        ) -> None:
            self._model = model

        def register_tool(self, *args: object, **kwargs: object) -> None:
            return None

        def chat(
            self,
            messages: list[dict[str, str]],
            system_prompt: str | None = None,
        ) -> str:
            return "hello"

        @property
        def model(self) -> str:
            return self._model

    class FakeAgentToolkit:
        def __init__(self, **kwargs: object) -> None:
            retriever = kwargs.get("retriever")
            captured["retriever"] = retriever
            if retriever is not None:
                captured["hits"] = retriever.search("kernel panic", top_k=1)

        def register_all(self, client: object) -> None:
            captured["registered"] = True

    fake_llm = types.ModuleType("logsensing.agent.llm")
    fake_llm.LLMClient = FakeLLMClient
    fake_tools = types.ModuleType("logsensing.agent.tools")
    fake_tools.AgentToolkit = FakeAgentToolkit
    monkeypatch.setitem(sys.modules, "logsensing.agent.llm", fake_llm)
    monkeypatch.setitem(sys.modules, "logsensing.agent.tools", fake_tools)
    monkeypatch.setattr(Prompt, "ask", lambda *args, **kwargs: "quit")

    result = runner.invoke(
        app,
        [
            "agent",
            "chat",
            "--config",
            str(config_path),
            "--platform",
            "bdk",
            "--logfile",
            str(logfile),
        ],
    )
    assert result.exit_code == 0, result.output
    assert captured.get("registered") is True
    hits = captured.get("hits")
    assert isinstance(hits, list)
    assert hits
    assert hits[0].chunk.metadata.get("platform") == "bdk"
