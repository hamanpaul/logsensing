#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$REPO_ROOT/docs/superpowers/skills/logsensing"
DEST_ROOT="${LOGSENSING_SKILL_DEST_ROOT:-$HOME/.agents/skills}"
DEST_DIR="$DEST_ROOT/logsensing"

mkdir -p "$DEST_ROOT"
rm -rf "$DEST_DIR"
cp -a "$SRC_DIR" "$DEST_DIR"

echo "Installed logsensing skill to $DEST_DIR"
