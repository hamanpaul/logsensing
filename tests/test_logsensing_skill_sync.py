"""logsensing skill sync tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = ROOT / "scripts" / "sync_logsensing_skill.sh"
SRC_SKILL = ROOT / "docs" / "superpowers" / "skills" / "logsensing" / "SKILL.md"
SRC_REF = (
    ROOT
    / "docs"
    / "superpowers"
    / "skills"
    / "logsensing"
    / "references"
    / "cli-workflows.md"
)


def test_sync_script_copies_skill_assets(tmp_path: Path) -> None:
    dest_root = tmp_path / "user-skills"
    env = dict(os.environ)
    env["LOGSENSING_SKILL_DEST_ROOT"] = str(dest_root)

    result = subprocess.run(
        ["bash", str(SYNC_SCRIPT)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    dest_skill = dest_root / "logsensing" / "SKILL.md"
    dest_ref = dest_root / "logsensing" / "references" / "cli-workflows.md"

    assert dest_skill.read_text(encoding="utf-8") == SRC_SKILL.read_text(encoding="utf-8")
    assert dest_ref.read_text(encoding="utf-8") == SRC_REF.read_text(encoding="utf-8")
