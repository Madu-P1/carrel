#!/usr/bin/env bash
# Activate the committed git hooks at .githooks/ for this clone.
#
# Runs once per fresh clone of the repo. Idempotent: safe to re-run.
# Disable later with:
#   git config --unset core.hooksPath

set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if [ ! -d ".githooks" ]; then
  echo "error: .githooks/ directory not found. Are you in the carrel repo root?" >&2
  exit 1
fi

# Mark every hook executable in case the file mode didn't survive the
# clone (e.g., shared on a non-Unix filesystem).
chmod +x .githooks/* 2>/dev/null || true

git config core.hooksPath .githooks

echo "✓ Git hooks activated."
echo "  Path: $(git config --get core.hooksPath)"
echo "  Hooks installed: $(ls .githooks | tr '\n' ' ')"
echo
echo "Commits in this clone will now run the pre-commit checks."
echo "Bypass with --no-verify only for genuine emergencies."
