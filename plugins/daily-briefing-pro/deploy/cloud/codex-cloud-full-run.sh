#!/usr/bin/env bash
set -euo pipefail
set +x

BASE="${DAILY_BRIEFING_HOME:-/workspace/.daily-briefing-pro}"
STATUS="$BASE/full-run.status.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATE="${DAILY_BRIEFING_DATE:-$(TZ=Asia/Shanghai date +%F)}"

record_status() {
  local exit_code=$?
  printf '{"state":"%s","date":"%s","exit_code":%d,"finished_at":"%s"}\n' \
    "$([ "$exit_code" -eq 0 ] && printf completed || printf failed)" \
    "$DATE" \
    "$exit_code" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATUS"
}
trap record_status EXIT

printf '{"state":"running","date":"%s","started_at":"%s"}\n' \
  "$DATE" \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$STATUS"

source "$BASE/activate.sh"
"$SCRIPT_DIR/codex-cloud-runtime-env.sh"

if [ -n "${DAILY_BRIEFING_EXPECTED_SHA:-}" ]; then
  test "$(git rev-parse HEAD)" = "$DAILY_BRIEFING_EXPECTED_SHA"
fi

cd plugins/daily-briefing-pro/skills/daily-briefing-pro
python scripts/run_all.py --date "$DATE" \
  > "$BASE/full-run.stdout.log" \
  2> "$BASE/full-run.stderr.log"
