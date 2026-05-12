"""logsensing skill sync tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = ROOT / "scripts" / "sync_logsensing_skill.sh"
SRC_DIR = ROOT / "docs" / "superpowers" / "skills" / "logsensing"


def _snapshot_tree(root: Path) -> tuple[set[str], dict[str, str]]:
    directories = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_dir()
    }
    files = {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in root.rglob("*")
        if path.is_file()
    }
    return directories, files


def _assert_matching_tree(dest_dir: Path) -> None:
    assert _snapshot_tree(dest_dir) == _snapshot_tree(SRC_DIR)


def test_sync_script_copies_skill_assets(tmp_path: Path) -> None:
    dest_root = tmp_path / "user-skills"
    dest_dir = dest_root / "logsensing"
    stale_file = dest_dir / "references" / "stale.md"

    stale_file.parent.mkdir(parents=True)
    stale_file.write_text("old content", encoding="utf-8")

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

    assert not stale_file.exists()
    _assert_matching_tree(dest_dir)


def test_sync_script_uses_default_destination(tmp_path: Path) -> None:
    env = dict(os.environ)
    env.pop("LOGSENSING_SKILL_DEST_ROOT", None)
    env["HOME"] = str(tmp_path)

    result = subprocess.run(
        ["bash", str(SYNC_SCRIPT)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    dest_root = tmp_path / ".agents" / "skills"
    _assert_matching_tree(dest_root / "logsensing")
