"""LogSensing CLI 測試."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from logsensing.cli import app

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
