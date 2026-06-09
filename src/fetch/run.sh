#!/usr/bin/env bash
# Run all JS-rendered and HTML fetchers.
# Output (stdout+stderr) is logged per script under logs/.

set -euo pipefail

cd "$(dirname "$0")"

LOGDIR="$(dirname "$(dirname "$PWD")")/logs"
mkdir -p "$LOGDIR"

SCRIPTS=(
    fetch_html.py
    fetch_js.py
)

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
