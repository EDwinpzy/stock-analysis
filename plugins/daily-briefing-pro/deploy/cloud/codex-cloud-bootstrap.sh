#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PYTHONIOENCODING=utf-8

BASE="${DAILY_BRIEFING_HOME:-/workspace/.daily-briefing-pro}"
BRANCH="${DAILY_BRIEFING_BRANCH:-codex/daily-briefing-cloud-parity}"
EXPECTED_SHA="${DAILY_BRIEFING_EXPECTED_SHA:?DAILY_BRIEFING_EXPECTED_SHA must pin the cloud runtime commit}"
REPO_URL="${DAILY_BRIEFING_REPO_URL:-https://github.com/EDwinpzy/stock-analysis.git}"
VENV="$BASE/venv"
NODE_VERSION="24.18.0"

mkdir -p \
  "$BASE/data" \
  "$BASE/reports" \
  "$BASE/cache" \
  "$BASE/cache/ms-playwright" \
  "$BASE/secrets" \
  "$BASE/models" \
  "$BASE/npm-global"

APT=()
if [ "$(id -u)" -eq 0 ]; then
  APT=(apt-get)
elif command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
  APT=(sudo apt-get)
fi

if [ "${#APT[@]}" -gt 0 ]; then
  "${APT[@]}" update
  "${APT[@]}" install -y --no-install-recommends \
    ca-certificates curl ffmpeg fonts-noto-cjk git python3 python3-venv xz-utils
else
  for required in curl ffmpeg git python3; do
    command -v "$required" >/dev/null 2>&1 ||
      { echo "Missing preinstalled command: $required" >&2; exit 1; }
  done
fi

is_briefing_repo() {
  [ -d "$1" ] &&
    git -C "$1" rev-parse --is-inside-work-tree >/dev/null 2>&1 &&
    git -C "$1" cat-file -e \
      'HEAD:plugins/daily-briefing-pro/skills/daily-briefing-pro/scripts/run_all.py' \
      >/dev/null 2>&1
}

find_repo_root() {
  if [ -n "${DAILY_BRIEFING_REPO_ROOT:-}" ] &&
    is_briefing_repo "$DAILY_BRIEFING_REPO_ROOT"; then
    printf '%s\n' "$DAILY_BRIEFING_REPO_ROOT"
    return
  fi

  for candidate in "$PWD" "$PWD/stock-analysis" "/workspace/stock-analysis" "/workspace/repo"; do
    if is_briefing_repo "$candidate"; then
      printf '%s\n' "$candidate"
      return
    fi
  done

  while IFS= read -r candidate; do
    if is_briefing_repo "$candidate"; then
      printf '%s\n' "$candidate"
      return
    fi
  done < <(find /workspace -maxdepth 4 -type d -name .git -printf '%h\n' 2>/dev/null)
}

REPO_ROOT="$(find_repo_root)"
if [ -z "$REPO_ROOT" ]; then
  REPO_ROOT="/workspace/stock-analysis"
  mkdir -p "$(dirname "$REPO_ROOT")"
  git clone --no-checkout "$REPO_URL" "$REPO_ROOT"
fi
export DAILY_BRIEFING_REPO_ROOT="$REPO_ROOT"
git -C "$REPO_ROOT" fetch --no-tags origin "$BRANCH"
git -C "$REPO_ROOT" cat-file -e "${EXPECTED_SHA}^{commit}"
git -C "$REPO_ROOT" checkout --force --detach "$EXPECTED_SHA"
test "$(git -C "$REPO_ROOT" rev-parse HEAD)" = "$EXPECTED_SHA"

git -C "$REPO_ROOT" show \
  "$EXPECTED_SHA:plugins/daily-briefing-pro/deploy/cloud/requirements-cloud.txt" \
  > "$BASE/requirements-cloud.txt"

python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV/bin/python" -m pip install \
  --index-url https://download.pytorch.org/whl/cpu "torch==2.5.1"
"$VENV/bin/python" -m pip install -r "$BASE/requirements-cloud.txt"

if command -v node >/dev/null 2>&1 &&
  command -v npm >/dev/null 2>&1 &&
  node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 20 ? 0 : 1)'; then
  NODE_HOME="$(cd "$(dirname "$(command -v node)")/.." && pwd)"
else
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64) NODE_ARCH="x64" ;;
    aarch64|arm64) NODE_ARCH="arm64" ;;
    *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;;
  esac
  NODE_HOME="$BASE/node-v$NODE_VERSION-linux-$NODE_ARCH"
  if [ ! -x "$NODE_HOME/bin/node" ]; then
    NODE_ARCHIVE="$BASE/node-v$NODE_VERSION-linux-$NODE_ARCH.tar.xz"
    curl -fsSL --retry 3 \
      "https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-linux-$NODE_ARCH.tar.xz" \
      -o "$NODE_ARCHIVE"
    tar -xJf "$NODE_ARCHIVE" -C "$BASE"
    rm -f "$NODE_ARCHIVE"
  fi
fi
export PATH="$VENV/bin:$NODE_HOME/bin:$BASE/npm-global/bin:/usr/local/bin:$PATH"
mkdir -p "$BASE/bin"
ln -sfn "$NODE_HOME/bin/node" "$BASE/bin/node"
ln -sfn "$NODE_HOME/bin/npm" "$BASE/bin/npm"
ln -sfn "$NODE_HOME/bin/npx" "$BASE/bin/npx"

npm install --global --prefix "$BASE/npm-global" --no-audit --no-fund \
  "@hithink-tech/hithink-finance-cli@0.1.13"

export PLAYWRIGHT_BROWSERS_PATH="$BASE/cache/ms-playwright"
if [ "${#APT[@]}" -gt 0 ]; then
  "$VENV/bin/python" -m playwright install --with-deps chromium
else
  "$VENV/bin/python" -m playwright install chromium
fi

export XDG_CACHE_HOME="$BASE/cache"
export DOUYIN_WHISPER_MODEL="small"
"$VENV/bin/python" - <<'PY'
import whisper
whisper.load_model("small")
PY

rm -rf "$BASE/cache/pip"
"$VENV/bin/python" -m pip cache purge || true

base_q="$(printf '%q' "$BASE")"
repo_q="$(printf '%q' "$REPO_ROOT")"
node_q="$(printf '%q' "$NODE_HOME")"
cat > "$BASE/activate.sh" <<EOF
#!/usr/bin/env bash
set +x
export DAILY_BRIEFING_HOME=$base_q
export DAILY_BRIEFING_REPO_ROOT=$repo_q
export DAILY_BRIEFING_DATA_DIR="$base_q/data"
export BRIEFING_OUTPUT_DIR="$base_q/reports"
export DAILY_BRIEFING_MODEL_CACHE="$base_q/models"
export PLAYWRIGHT_BROWSERS_PATH="$base_q/cache/ms-playwright"
export XDG_CACHE_HOME="$base_q/cache"
export NODE_HOME=$node_q
export PATH="$base_q/venv/bin:$node_q/bin:$base_q/npm-global/bin:/usr/local/bin:\$PATH"
export PYTHONIOENCODING=utf-8
export PYTHONHASHSEED=2
EOF
chmod 700 "$BASE/activate.sh"

echo "Daily Briefing Pro Codex Cloud bootstrap completed for $EXPECTED_SHA."
