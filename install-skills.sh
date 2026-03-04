#!/usr/bin/env bash
# install-skills.sh — Install debate-tool Claude Code skill globally
#
# Usage: bash install-skills.sh
#
# Idempotent: safe to run multiple times.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_SRC="$SCRIPT_DIR/.claude/commands/debate.md"
SKILL_DST="$HOME/.claude/commands/debate.md"

# ─── 1. Install skill file ───────────────────────────────────────────────────

if [[ ! -f "$SKILL_SRC" ]]; then
  echo "ERROR: Skill source not found: $SKILL_SRC"
  exit 1
fi

mkdir -p "$(dirname "$SKILL_DST")"
cp "$SKILL_SRC" "$SKILL_DST"
echo "✓ Installed skill: $SKILL_DST"

# ─── 2. Set DEBATE_TOOL_DIR in shell profile ─────────────────────────────────

EXPORT_LINE="export DEBATE_TOOL_DIR=\"$SCRIPT_DIR\""
MARKER="# debate-tool"

# Detect shell profile
if [[ -n "${ZSH_VERSION:-}" ]] || [[ "$SHELL" == */zsh ]]; then
  PROFILE="$HOME/.zshrc"
elif [[ -f "$HOME/.bash_profile" ]]; then
  PROFILE="$HOME/.bash_profile"
else
  PROFILE="$HOME/.bashrc"
fi

if grep -qF "$MARKER" "$PROFILE" 2>/dev/null; then
  # Update existing entry in-place
  sed -i.bak "/$MARKER/c\\
$EXPORT_LINE  $MARKER" "$PROFILE"
  rm -f "${PROFILE}.bak"
  echo "✓ Updated DEBATE_TOOL_DIR in $PROFILE"
else
  # Append new entry
  printf '\n%s  %s\n' "$EXPORT_LINE" "$MARKER" >> "$PROFILE"
  echo "✓ Added DEBATE_TOOL_DIR to $PROFILE"
fi

echo "  DEBATE_TOOL_DIR=$SCRIPT_DIR"

# ─── 3. Done ─────────────────────────────────────────────────────────────────

echo ""
echo "Installation complete."
echo "Run 'source $PROFILE' or open a new terminal to apply changes."
echo "Then use /debate in Claude Code to start a debate."
