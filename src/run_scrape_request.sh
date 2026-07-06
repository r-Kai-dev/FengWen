#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

export PYTHONPATH="$PWD"
LOGS_DIR="../logs"
mkdir -p "$LOGS_DIR"

declare -A JOB_NAMES

for s in scrape_*.py; do
    name="$(basename "$s" .py)"
    python3 "$s" > "$LOGS_DIR/${name}.log" 2>&1 &
    JOB_NAMES[$!]="$name"
done

for s in request_*.py; do
    name="$(basename "$s" .py)"
    python3 "$s" > "$LOGS_DIR/${name}.log" 2>&1 &
    JOB_NAMES[$!]="$name"
done

for s in enhance_*.py; do
    name="$(basename "$s" .py)"
    python3 "$s" > "$LOGS_DIR/${name}.log" 2>&1 &
    JOB_NAMES[$!]="$name"
done

SUCCEEDED=0
FAILED=0
FAILED_NAMES=()

for job in $(jobs -p); do
    if wait "$job"; then
        SUCCEEDED=$((SUCCEEDED + 1))
    else
        FAILED=$((FAILED + 1))
        FAILED_NAMES+=("${JOB_NAMES[$job]}")
    fi
done

echo "scrape-request: $SUCCEEDED succeeded, $FAILED failed"

if [ "$FAILED" -gt 0 ]; then
    echo "Failed scripts:" >&2
    for name in "${FAILED_NAMES[@]}"; do
        echo "  - $name" >&2
        echo "--- tail of $LOGS_DIR/${name}.log ---" >&2
        tail -30 "$LOGS_DIR/${name}.log" >&2 || true
        echo "--- end of $LOGS_DIR/${name}.log ---" >&2
    done
fi

if [ "$SUCCEEDED" -eq 0 ]; then
    echo "WARNING: No scripts ran successfully — pipeline will continue but no scrape/request feeds were updated" >&2
fi
