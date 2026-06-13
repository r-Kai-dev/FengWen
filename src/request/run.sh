#!/usr/bin/env bash
# Run all API-based request scripts.
# Output (stdout+stderr) is logged per script under logs/.

set -euo pipefail

cd "$(dirname "$0")"

LOGDIR="$(dirname "$(dirname "$PWD")")/logs"

# Add src/ to PYTHONPATH so feed_util.py is importable
export PYTHONPATH="$(dirname "$PWD"):${PYTHONPATH:-}"
mkdir -p "$LOGDIR"

shopt -s nullglob
SCRIPTS=(request_*.py)
shopt -u nullglob

if [ ${#SCRIPTS[@]} -eq 0 ]; then
    echo "No request_*.py scripts found."
    exit 0
fi

FAILED=0
for script in "${SCRIPTS[@]}"; do
    name="${script%.py}"
    logfile="$LOGDIR/${name}.log"

    echo "========================================"
    echo "[RUN]  $script  ->  $logfile"
    echo "========================================"

    if python3 "$script" > "$logfile" 2>&1; then
        echo "[DONE] $script"
    else
        echo "[FAIL] $script (exit code $? — see $logfile)"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
echo "========================================"
if [ "$FAILED" -eq 0 ]; then
    echo "All request scripts completed successfully."
else
    echo "$FAILED script(s) failed."
fi
echo "========================================"
exit "$FAILED"
