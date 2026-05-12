#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "Error: $*" >&2
  exit 1
}

resolve_absolute_path() {
  python3 - "$1" <<'PY'
import os
import sys

print(os.path.abspath(os.path.expanduser(sys.argv[1])))
PY
}

is_within_path() {
  local base="$1"
  local candidate="$2"

  [[ "$candidate" == "$base" || "$candidate" == "$base/"* ]]
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$REPO_ROOT/docs/superpowers/skills/logsensing"
RAW_DEST_ROOT="${LOGSENSING_SKILL_DEST_ROOT-$HOME/.agents/skills}"

if [[ -z "$RAW_DEST_ROOT" ]]; then
  fail "LOGSENSING_SKILL_DEST_ROOT must not be empty"
fi

DEST_ROOT="$(resolve_absolute_path "$RAW_DEST_ROOT")"
DEST_DIR="$DEST_ROOT/logsensing"

if [[ "$DEST_ROOT" == "/" ]]; then
  fail "Refusing to install into /; set LOGSENSING_SKILL_DEST_ROOT to a dedicated directory"
fi

if is_within_path "$REPO_ROOT" "$DEST_DIR"; then
  fail "Refusing to install inside the repository: $DEST_DIR"
fi

mkdir -p "$DEST_ROOT"
rm -rf "$DEST_DIR"
cp -a "$SRC_DIR" "$DEST_DIR"

echo "Installed logsensing skill to $DEST_DIR"
