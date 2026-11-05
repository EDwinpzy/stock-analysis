#!/bin/sh
set -eu

cd "$(dirname "$0")"
umask 077

mkdir -p secrets runtime/data runtime/models runtime/reports verification

for file in \
    deepseek_api_key openai_api_key siliconflow_api_key groq_api_key \
    ima_openapi_clientid ima_openapi_apikey hithink_finance_api_key \
    tgb_cookies.json douyin_cookies.json xueqiu_cookies.json ths_selfstock.json
do
    path="secrets/$file"
    if [ ! -e "$path" ]; then
        : > "$path"
    fi
    chown 10001:10001 "$path"
    chmod 600 "$path"
done

chown -R 10001:10001 runtime
chown -R 10001:10001 verification
chmod -R u+rwX,go+rX verification
