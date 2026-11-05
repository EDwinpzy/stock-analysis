#!/bin/sh
set -eu

target_date="${1:-2026-10-10}"
baseline_report="${2:-/verification/2026-10-10简报.html}"
baseline_broadsheet="${3:-/verification/2026-10-10简报-报刊版.html}"
fixture_dir="/verification/${target_date}-data"
expected_sha256="0c58228f4c38aae39ef1e5209c19d005680070cf37c1bff57ef10f3bc4248fbd"
expected_broadsheet_sha256="fb74862b6caecb19230728f0fc3a249926e34afe658ffd02907fb1c395c98f44"
expected_css_sha256="4e49e37c382ad0b318c645888b8c4905c5ce206ab655f9e2aca819ac60a592cd"
test_root=$(mktemp -d /tmp/daily-briefing-baseline.XXXXXX)
trap 'rm -rf "$test_root"' EXIT
test_data="$test_root/data"
output_dir="$test_root/reports"
output_report="$output_dir/${target_date}简报.html"
output_broadsheet="$output_dir/${target_date}简报-报刊版.html"

if [ ! -f "$baseline_report" ]; then
    printf '基准报告不存在：%s\n' "$baseline_report" >&2
    exit 2
fi
if [ ! -f "$baseline_broadsheet" ]; then
    printf '报刊版基准文件不存在：%s\n' "$baseline_broadsheet" >&2
    exit 2
fi
if [ ! -d "$fixture_dir" ]; then
    printf '基准数据快照不存在：%s\n' "$fixture_dir" >&2
    exit 2
fi

baseline_sha256=$(sha256sum "$baseline_report" | awk '{print $1}')
if [ "$baseline_sha256" != "$expected_sha256" ]; then
    printf '基准文件 SHA256 不匹配：%s\n' "$baseline_sha256" >&2
    exit 2
fi

mkdir -p "$test_data" "$output_dir"
cp -R "$fixture_dir"/. "$test_data"/
DAILY_BRIEFING_DATA_DIR="$test_data" \
BRIEFING_OUTPUT_DIR="$output_dir" \
PYTHONHASHSEED=2 \
python scripts/build_briefing.py --date "$target_date"
actual_sha256=$(sha256sum "$output_report" | awk '{print $1}')

if [ "$actual_sha256" != "$expected_sha256" ] || ! cmp -s "$baseline_report" "$output_report"; then
    printf '云端报告不一致：expected=%s actual=%s\n' "$expected_sha256" "$actual_sha256" >&2
    exit 1
fi

printf '云端报告逐字节一致：%s\nSHA256: %s\n' "$output_report" "$actual_sha256"

python scripts/build_broadsheet.py --src "$output_report" --out "$output_broadsheet" --date "$target_date"
python scripts/verify_broadsheet.py --out "$output_broadsheet" --src "$output_report" --shots "$test_root/shots"
actual_css_sha256=$(python - "$output_broadsheet" <<'PY'
import hashlib
import sys
from pathlib import Path
from bs4 import BeautifulSoup

sys.path.insert(0, "scripts")
import build_broadsheet

page = BeautifulSoup(Path(sys.argv[1]).read_text(encoding="utf-8"), "html.parser")
styles = page.find_all("style")
if len(styles) != 1 or styles[0].get_text() != build_broadsheet.CSS:
    raise SystemExit("输出报告的内嵌样式与固定报刊模板不一致")
print(hashlib.sha256(styles[0].get_text().encode("utf-8")).hexdigest())
PY
)
if [ "$actual_css_sha256" != "$expected_css_sha256" ]; then
    printf '报刊模板样式指纹不一致：expected=%s actual=%s\n' "$expected_css_sha256" "$actual_css_sha256" >&2
    exit 1
fi
actual_broadsheet_sha256=$(sha256sum "$output_broadsheet" | awk '{print $1}')
if [ "$actual_broadsheet_sha256" != "$expected_broadsheet_sha256" ] || ! cmp -s "$baseline_broadsheet" "$output_broadsheet"; then
    printf '云端报刊版不一致：expected=%s actual=%s\n' "$expected_broadsheet_sha256" "$actual_broadsheet_sha256" >&2
    exit 1
fi
printf '云端报刊版逐字节一致：%s\nSHA256: %s\nCSS: %s\n' "$output_broadsheet" "$actual_broadsheet_sha256" "$actual_css_sha256"
