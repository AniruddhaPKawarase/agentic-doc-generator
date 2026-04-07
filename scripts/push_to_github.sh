#!/bin/bash
set -euo pipefail
REPO_PATH="../../../../agentic-ai-platform"
TARGET="${REPO_PATH}/agents/doc-generator"

echo "=== Syncing to GitHub repo ==="
rsync -av --delete \
    --exclude='.env' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='generated_docs/' --exclude='venv/' --exclude='.code-review-graph/' \
    . "$TARGET/"

cd "$REPO_PATH"
git add agents/doc-generator/
git status
echo ""
echo "Ready to commit. Run:"
echo "  cd $REPO_PATH && git commit -m 'feat(doc-generator): bugfix + hardening' && git push"
