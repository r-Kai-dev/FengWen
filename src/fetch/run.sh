#!/usr/bin/env bash
# Run all fetchers (HTML and JS-rendered).
# Output (stdout+stderr) is logged per script under logs/.

set -euo pipefail

cd "$(dirname "$0")"

LOGDIR="$(dirname "$(dirname "$PWD")")/logs"

# Add src/ to PYTHONPATH for any shared imports
PYTHONPATH="$(dirname "$PWD"):${PYTHONPATH:-}"
export PYTHONPATH
mkdir -p "$LOGDIR"

shopt -s nullglob
SCRIPTS=(fetch_*.py)
shopt -u nullglob

if [ ${#SCRIPTS[@]} -eq 0 ]; then
    echo "No fetch_*.py scripts found."
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
    echo "All fetch scripts completed successfully."
else
    echo "$FAILED script(s) failed."
fi
echo "========================================"
exit "$FAILED"
