#!/usr/bin/env bash
# Run all data-collection scripts sequentially (fetch → request → parse).
# Each subdir has its own run.sh with per-script logging under logs/.

set -euo pipefail

cd "$(dirname "$0")"

echo "========================================"
echo "[PHASE 1] Fetch (JS-rendered + HTML)"
echo "========================================"
bash fetch/run.sh || true

echo ""
echo "========================================"
echo "[PHASE 2] Request (API-based)"
echo "========================================"
bash request/run.sh || true

echo ""
echo "========================================"
echo "[PHASE 3] Parse (HTML cache → Atom feeds)"
echo "========================================"
bash parse/run.sh || true

echo ""
echo "========================================"
echo "All phases completed."
echo "========================================"
