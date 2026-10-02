#!/usr/bin/env bash
# cognitive-core installer — clone, symlink, done.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
SKILLS_DIR="${HOME}/.claude/skills"

mkdir -p "$BIN_DIR"
ln -sf "$REPO/bin/core" "$BIN_DIR/core"
echo "✓ core -> $BIN_DIR/core"

if [ -d "${HOME}/.claude" ]; then
  mkdir -p "$SKILLS_DIR"
  ln -sfn "$REPO/skill" "$SKILLS_DIR/cognitive-core"
  echo "✓ skill installed for Claude Code"
else
  echo "· Claude Code not found (~/.claude missing) — skill not installed; the CLI works on its own"
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "! $BIN_DIR is not on your PATH. Add this to your shell profile, then open a new terminal:"
     echo "    export PATH=\"$BIN_DIR:\$PATH\"" ;;
esac

"$BIN_DIR/core" inject >/dev/null && echo "✓ clock running. Try: core inject"
