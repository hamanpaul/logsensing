#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$REPO_ROOT/docs/superpowers/skills/logsensing"
DEST_ROOT="${LOGSENSING_SKILL_DEST_ROOT:-$HOME/.agents/skills}"
DEST_DIR="$DEST_ROOT/logsensing"

mkdir -p "$DEST_DIR/references"

cp "$SRC_DIR/SKILL.md" "$DEST_DIR/SKILL.md"
cp "$SRC_DIR/references/cli-workflows.md" "$DEST_DIR/references/cli-workflows.md"

echo "Installed logsensing skill to $DEST_DIR"
