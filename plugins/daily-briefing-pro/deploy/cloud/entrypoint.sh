#!/bin/sh
set -eu

load_secret() {
    variable_name="$1"
    secret_path="$2"
    if [ -s "$secret_path" ]; then
        secret_value=$(cat "$secret_path")
        export "$variable_name=$secret_value"
        unset secret_value
    fi
}

load_secret DEEPSEEK_API_KEY /run/secrets/deepseek_api_key
load_secret OPENAI_API_KEY /run/secrets/openai_api_key
load_secret SILICONFLOW_API_KEY /run/secrets/siliconflow_api_key
load_secret GROQ_API_KEY /run/secrets/groq_api_key
load_secret IMA_OPENAPI_CLIENTID /run/secrets/ima_openapi_clientid
load_secret IMA_OPENAPI_APIKEY /run/secrets/ima_openapi_apikey
load_secret HITHINK_FINANCE_API_KEY /run/secrets/hithink_finance_api_key
load_secret FUYAO_API_KEY /run/secrets/fuyao_api_key
load_secret IWENCAI_API_KEY /run/secrets/iwencai_api_key
load_secret THS_USERNAME /run/secrets/ths_username
load_secret THS_PASSWORD /run/secrets/ths_password
load_secret THS_MAC /run/secrets/ths_mac
if [ -z "${HITHINK_FINANCE_API_KEY:-}" ]; then
    if [ -s /run/secrets/fuyao_api_key ]; then
        load_secret HITHINK_FINANCE_API_KEY /run/secrets/fuyao_api_key
    elif [ -n "${FUYAO_API_KEY:-}" ]; then
        export HITHINK_FINANCE_API_KEY="$FUYAO_API_KEY"
    fi
fi

# The image carries the small Whisper checkpoint; the named home volume does
# not. Copy it once so local transcription works before any download.
if [ -d /opt/whisper-cache/whisper ] && [ ! -e /runtime/home/.cache/whisper ]; then
    mkdir -p /runtime/home/.cache
    cp -a /opt/whisper-cache/whisper /runtime/home/.cache/whisper
fi

model_template=/opt/daily-briefing-pro/models/sw_rotation_model
model_runtime=/runtime/models/sw_rotation_model
mkdir -p /runtime/models
if [ -f "$model_template/run.py" ] && [ -f "$model_template/config.json" ]; then
    if [ ! -f "$model_runtime/run.py" ] || [ ! -f "$model_runtime/config.json" ]; then
        mkdir -p "$model_runtime"
        cp -a "$model_template/." "$model_runtime/"
    fi
fi
export ROTATION_MODEL_DIR="${ROTATION_MODEL_DIR:-$model_runtime}"

if [ -s /run/secrets/tgb_cookies.json ]; then
    export TGB_COOKIE_PATH="${TGB_COOKIE_PATH:-/run/secrets/tgb_cookies.json}"
fi
if [ -s /run/secrets/douyin_cookies.json ]; then
    export DOUYIN_COOKIE_PATH="${DOUYIN_COOKIE_PATH:-/run/secrets/douyin_cookies.json}"
fi
if [ -s /run/secrets/xueqiu_cookies.json ]; then
    export XUEQIU_COOKIE_PATH="${XUEQIU_COOKIE_PATH:-/run/secrets/xueqiu_cookies.json}"
fi
if [ -s /run/secrets/ths_selfstock.json ]; then
    export THS_SELFSTOCK_PATH="${THS_SELFSTOCK_PATH:-/run/secrets/ths_selfstock.json}"
fi

exec "$@"
