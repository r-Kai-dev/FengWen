#!/usr/bin/env bash
# Run all data-collection parse scripts.
# - parse_*.py scripts read from html_cache/ and write to data/
# Output (stdout+stderr) is logged per script under logs/.

set -euo pipefail

cd "$(dirname "$0")"

LOGDIR="$(dirname "$(dirname "$PWD")")/logs"

# Add src/ to PYTHONPATH so feed_util.py is importable
export PYTHONPATH="$(dirname "$PWD"):${PYTHONPATH:-}"
mkdir -p "$LOGDIR"

shopt -s nullglob
SCRIPTS=(parse_*.py)
shopt -u nullglob

if [ ${#SCRIPTS[@]} -eq 0 ]; then
    echo "No parse_*.py scripts found."
    exit 0
fi

FAILED=0
SUCCEEDED=0
for script in "${SCRIPTS[@]}"; do
    name="${script%.py}"
    logfile="$LOGDIR/${name}.log"

    echo "========================================"
    echo "[RUN]  $script  ->  $logfile"
    echo "========================================"

    if python3 "$script" > "$logfile" 2>&1; then
        echo "[DONE] $script"
        SUCCEEDED=$((SUCCEEDED + 1))
    else
        rc=$?
        echo "[FAIL] $script (exit code $rc — see $logfile)"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
echo "========================================"
if [ "$FAILED" -eq 0 ]; then
    echo "All parse scripts completed successfully."
elif [ "$SUCCEEDED" -eq 0 ]; then
    echo "All $FAILED script(s) failed."
else
    echo "$SUCCEEDED script(s) succeeded, $FAILED script(s) failed."
fi
echo "========================================"

if [ "$SUCCEEDED" -gt 0 ] || [ ${#SCRIPTS[@]} -eq 0 ]; then
    exit 0
else
    exit "$FAILED"
fi
