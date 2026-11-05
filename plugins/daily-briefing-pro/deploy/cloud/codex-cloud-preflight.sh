#!/usr/bin/env bash
set -euo pipefail
set +x

BASE="${DAILY_BRIEFING_HOME:-/workspace/.daily-briefing-pro}"
STATUS="$BASE/preflight.status.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATE="${DAILY_BRIEFING_DATE:-$(TZ=Asia/Shanghai date +%F)}"

record_status() {
  local exit_code=$?
  printf '{"state":"%s","exit_code":%d,"finished_at":"%s"}\n' \
    "$([ "$exit_code" -eq 0 ] && printf completed || printf failed)" \
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
python scripts/run_all.py --date "$DATE" --preflight-only \
  > "$BASE/preflight.stdout.json" \
  2> "$BASE/preflight.stderr.log"

python - "$BASE/preflight.stdout.json" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["status"] in {"ok", "warning"}, report["status"]
assert report["summary"]["error"] == 0, report["summary"]
checks = {row["key"]: row for row in report.get("checks", [])}
for key in (
    "hithink",
    "semantic_summary",
    "tgb_cookie",
    "douyin_cookie",
    "xueqiu_cookie",
    "rotation_model",
):
    assert checks.get(key, {}).get("state") == "ok", (key, checks.get(key))
print("cloud preflight assertions ok")
PY
