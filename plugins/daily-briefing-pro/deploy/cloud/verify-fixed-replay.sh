#!/bin/sh
set -eu

target_date="${1:-2026-11-11}"
expected_report_sha256="30fef1b913896dad4efb799a71d74d689139134c3dab3d407e9188bc14853869"
expected_broadsheet_sha256="eec2b1a899da4319c57d3969632afb1bf694b89a91920f1565dc2901aa3c5100"
output_dir="${BRIEFING_OUTPUT_DIR:-/runtime/reports}"
report_path="$output_dir/${target_date}简报.html"
broadsheet_path="$output_dir/${target_date}简报-报刊版.html"

python scripts/run_all.py --date "$target_date" --resume

report_sha256=$(sha256sum "$report_path" | awk '{print $1}')
broadsheet_sha256=$(sha256sum "$broadsheet_path" | awk '{print $1}')

if [ "$report_sha256" != "$expected_report_sha256" ]; then
    printf '固定重放源简报 SHA256 不匹配：expected=%s actual=%s\n' \
        "$expected_report_sha256" "$report_sha256" >&2
    exit 1
fi
if [ "$broadsheet_sha256" != "$expected_broadsheet_sha256" ]; then
    printf '固定重放报刊版 SHA256 不匹配：expected=%s actual=%s\n' \
        "$expected_broadsheet_sha256" "$broadsheet_sha256" >&2
    exit 1
fi

printf '固定重放通过：%s\n源简报 SHA256: %s\n报刊版 SHA256: %s\n' \
    "$target_date" "$report_sha256" "$broadsheet_sha256"
