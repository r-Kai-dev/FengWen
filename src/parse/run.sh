#!/usr/bin/env bash
# Run all data-collection parse scripts.
# - parse_*.py scripts read from html_cache/ and write to data/
# Output (stdout+stderr) is logged per script under logs/.

set -euo pipefail

cd "$(dirname "$0")"

LOGDIR="$(dirname "$(dirname "$PWD")")/logs"
mkdir -p "$LOGDIR"

SCRIPTS=(
    parse_aibase.py
    parse_anthropic.py
    parse_artianalysis.py
    parse_batch.py
    parse_bytedance.py
    parse_deepseek.py
    parse_github.py
    parse_kimi.py
    parse_meta.py
    parse_minimax.py
    parse_moonshot.py
    parse_qwen.py
    parse_zai.py
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
    echo "All parse scripts completed successfully."
else
    echo "$FAILED script(s) failed."
fi
echo "========================================"
exit "$FAILED"
