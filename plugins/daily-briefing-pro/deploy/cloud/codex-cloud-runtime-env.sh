#!/usr/bin/env bash
set -euo pipefail
set +x

BASE="${DAILY_BRIEFING_HOME:-/workspace/.daily-briefing-pro}"
REPO="${DAILY_BRIEFING_REPO_ROOT:?source activate.sh before this script}"

test -d "$REPO/.git"
mkdir -p \
  "$BASE/data" \
  "$BASE/reports" \
  "$BASE/cache" \
  "$BASE/secrets" \
  "$BASE/models"
chmod 700 "$BASE" "$BASE/secrets"

decode_secret_if_missing() {
  local variable_name="$1"
  local target="$2"
  if [ -s "$target" ]; then
    chmod 600 "$target"
    return 0
  fi
  local encoded="${!variable_name:-}"
  test -n "$encoded"
  local temporary="${target}.tmp.$$"
  umask 077
  printf '%s' "$encoded" | base64 -d | gzip -dc > "$temporary"
  chmod 600 "$temporary"
  mv "$temporary" "$target"
}

decode_secret_if_missing TGB_COOKIE_GZ_B64 "$BASE/secrets/tgb_cookies.json"
decode_secret_if_missing DOUYIN_COOKIE_GZ_B64 "$BASE/secrets/douyin_cookies.json"
decode_secret_if_missing XUEQIU_COOKIE_GZ_B64 "$BASE/secrets/xueqiu_cookies.json"

export DAILY_BRIEFING_CLOUD=1
export DAILY_BRIEFING_DATA_DIR="$BASE/data"
export BRIEFING_OUTPUT_DIR="$BASE/reports"
export DAILY_BRIEFING_MODEL_CACHE="$BASE/models"
export TGB_COOKIE_PATH="$BASE/secrets/tgb_cookies.json"
export DOUYIN_COOKIE_PATH="$BASE/secrets/douyin_cookies.json"
export XUEQIU_COOKIE_PATH="$BASE/secrets/xueqiu_cookies.json"
export PYTHONIOENCODING=utf-8
export PYTHONHASHSEED=2
export NODE_USE_ENV_PROXY=1
export PLAYWRIGHT_BROWSERS_PATH="$BASE/cache/ms-playwright"
export XDG_CACHE_HOME="$BASE/cache"
export PATH="$BASE/venv/bin:$BASE/npm-global/bin:$PATH"

unset TGB_COOKIE_GZ_B64
unset DOUYIN_COOKIE_GZ_B64
unset XUEQIU_COOKIE_GZ_B64

cd "$REPO"
