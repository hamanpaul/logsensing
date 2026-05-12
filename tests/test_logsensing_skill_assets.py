"""logsensing skill asset tests."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_FILE = ROOT / "docs" / "superpowers" / "skills" / "logsensing" / "SKILL.md"
REFERENCE_FILE = (
    ROOT
    / "docs"
    / "superpowers"
    / "skills"
    / "logsensing"
    / "references"
    / "cli-workflows.md"
)


def test_logsensing_skill_files_exist() -> None:
    assert SKILL_FILE.exists(), "repo skill file should exist"
    assert REFERENCE_FILE.exists(), "repo reference file should exist"


def test_logsensing_skill_covers_required_playbooks() -> None:
    text = SKILL_FILE.read_text(encoding="utf-8")

    assert "name: logsensing" in text
    assert "analyze" in text
    assert "triage" in text
    assert "baseline_train" in text
    assert "rag_agent" in text
    assert "env_repair" in text
    assert "uv run logsensing --help" in text
    assert "uv sync" in text
    assert "line numbers" in text


def test_logsensing_reference_contains_command_examples() -> None:
    text = REFERENCE_FILE.read_text(encoding="utf-8")

    assert "uv run logsensing analyze" in text
    assert "uv run logsensing report" in text
    assert "uv run logsensing train baseline" in text
    assert "uv run logsensing train drain" in text
    assert "uv run logsensing agent analyze" in text
    assert "uv run logsensing agent chat" in text
