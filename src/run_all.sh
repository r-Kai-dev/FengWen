#!/usr/bin/env bash
# Run all data-collection scripts sequentially.
# - parse_*.py scripts read from html_cache/ and write to feeds/
# - request_*.py scripts call APIs and write to feeds/
# Output (stdout+stderr) is logged per script under logs/.

set -euo pipefail

cd "$(dirname "$0")"

LOGDIR="$(dirname "$PWD")/logs"
mkdir -p "$LOGDIR"

SCRIPTS=(
    # HTML-based parsers (read html_cache/, write feeds/)
    parse_anthropic.py
    parse_github.py
    parse_meta.py
    parse_aibase.py
    parse_artianalysis.py
    parse_batch.py
    parse_minimax.py
    parse_moonshot.py
    parse_zai.py
    parse_kimi.py

    # API-based fetchers (call external APIs, write feeds/)
    request_hackernews.py
    request_huggingface.py
)

FAILED=0
for script in "${SCRIPTS[@]}"; do
    if [ ! -f "$script" ]; then
        echo "[SKIP] $script not found"
        continue
    fi

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
    echo "All scripts completed successfully."
else
    echo "$FAILED script(s) failed."
fi
echo "========================================"
exit "$FAILED"
