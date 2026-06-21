#!/usr/bin/env bash
# Run all feed scripts in parallel where safe, sequential for shared-browser crawls.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD"
mkdir -p ../logs

FAILED=0

# ── Phase 1: Scrape + Request in parallel (no shared resources) ──
echo "========================================"
echo "[PHASE 1] Scrape + Request (parallel)"
echo "========================================"

for s in scrape_*.py; do
    name="$(basename "$s" .py)"
    python3 "$s" > "../logs/${name}.log" 2>&1 &
done
for s in request_*.py; do
    name="$(basename "$s" .py)"
    python3 "$s" > "../logs/${name}.log" 2>&1 &
done
wait

echo ""
echo "========================================"
echo "[PHASE 2] Crawl (sequential — shared browser)"
echo "========================================"

if python3 crawl_runner.py > ../logs/crawl_runner.log 2>&1; then
    echo "Crawl runner completed."
else
    rc=$?
    echo "Crawl runner failed (exit $rc)."
    FAILED=$((FAILED + rc))
fi

echo ""
echo "========================================"
echo "All phases completed."
echo "========================================"

exit $FAILED
