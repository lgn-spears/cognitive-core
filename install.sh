#!/usr/bin/env bash
# cognitive-core installer — clone, symlink, done.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
SKILLS_DIR="${HOME}/.claude/skills"

mkdir -p "$BIN_DIR"
ln -sf "$REPO/bin/core" "$BIN_DIR/core"
echo "✓ core -> $BIN_DIR/core"

if [ -d "$SKILLS_DIR" ]; then
  ln -sfn "$REPO/skill" "$SKILLS_DIR/cognitive-core"
  echo "✓ skill installed for Claude Code"
fi

"$BIN_DIR/core" inject >/dev/null && echo "✓ clock running. Try: core inject"
