"""README coverage for logsensing skill."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def test_readme_documents_logsensing_skill_install() -> None:
    text = README.read_text(encoding="utf-8")

    assert "logsensing skill" in text.lower()
    assert "bash scripts/sync_logsensing_skill.sh" in text
    assert "docs/superpowers/skills/logsensing/" in text
    assert "docs/superpowers/skills/logsensing/SKILL.md" in text
    assert "docs/superpowers/skills/logsensing/references/cli-workflows.md" in text
    assert "~/.agents/skills/logsensing/" in text
