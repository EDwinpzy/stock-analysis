#!/usr/bin/env bash
set -euo pipefail
set +x

BASE="${DAILY_BRIEFING_HOME:-/workspace/.daily-briefing-pro}"
OUT="$BASE/tests"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$BASE/activate.sh"
"$SCRIPT_DIR/codex-cloud-runtime-env.sh"

if [ -n "${DAILY_BRIEFING_EXPECTED_SHA:-}" ]; then
  test "$(git rev-parse HEAD)" = "$DAILY_BRIEFING_EXPECTED_SHA"
fi

rm -rf "$OUT"
mkdir -p "$OUT"

python -m unittest discover -s tests -v > "$OUT/top-level.log" 2>&1
(
  cd plugins/daily-briefing-pro/skills/daily-briefing-pro
  python -m unittest discover -s tests -v
) > "$OUT/plugin.log" 2>&1

tail -n 8 "$OUT/top-level.log"
tail -n 8 "$OUT/plugin.log"
