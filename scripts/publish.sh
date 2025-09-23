#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

# Verifica que exista el HTML de Pages
if [[ ! -f docs/index.html ]]; then
  echo "docs/index.html not found. Run: .venv/bin/python main.py (to generate) and try again."
  exit 1
fi

# Branch actual (main/master/etc)
BRANCH="$(git branch --show-current 2>/dev/null || echo main)"

# Asegura cambios actualizados
git pull --rebase origin "$BRANCH" || true

# Prepara cambios de Pages
git add docs/index.html docs/charts || true

# Commit solo si hay cambios staged
if ! git diff --cached --quiet; then
  git commit -m "chore: publish fresh brief to GitHub Pages"
  git push origin "$BRANCH"
  echo "[publish] Changes pushed to $BRANCH."
else
  echo "[publish] No changes to publish."
fi
