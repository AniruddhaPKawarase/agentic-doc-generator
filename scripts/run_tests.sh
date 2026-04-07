#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "=== Running tests with coverage ==="
python -m pytest tests/ --cov=. --cov-report=term-missing --cov-fail-under=80 -v
echo "=== Tests complete ==="

echo "=== CVE Scan ==="
pip-audit -r requirements.txt || echo "WARNING: CVE issues found — review above"
