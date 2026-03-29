#!/usr/bin/env bash
# Install all LangSight git hooks.
# Run once after cloning: bash scripts/install-hooks.sh
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_SRC="$REPO_ROOT/scripts/hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

# Install pre-commit framework hooks (ruff, mypy, secrets, no-print)
if command -v pre-commit &>/dev/null; then
  pre-commit install
  echo "✓ pre-commit hooks installed"
else
  echo "⚠  pre-commit not found — install with: uv tool install pre-commit"
fi

# Install pre-push hook
cp "$HOOKS_SRC/pre-push" "$HOOKS_DST/pre-push"
chmod +x "$HOOKS_DST/pre-push"
echo "✓ pre-push hook installed (ruff lint+format, mypy, unit tests, coverage ≥ 70%, tsc)"

echo ""
echo "Hooks active:"
echo "  pre-commit  →  ruff, mypy, secret detection, no print()"
echo "  pre-push    →  ruff lint, ruff format, mypy, pytest unit, coverage ≥ 70%, integration tests, tsc"
