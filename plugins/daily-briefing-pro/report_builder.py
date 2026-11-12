#!/usr/bin/env python3
"""Build and verify stock or industry reports from collector JSON."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


PLUGIN_ROOT = Path(__file__).resolve().parent
VERIFY_DIR = PLUGIN_ROOT / "skills" / "daily-briefing-pro" / "scripts"
if str(VERIFY_DIR) not in sys.path:
    sys.path.insert(0, str(VERIFY_DIR))

import verify_skill_report  # noqa: E402
from reporting import build_industry_report, build_stock_report  # noqa: E402


def output_dir() -> Path:
    return Path(os.getenv("BRIEFING_OUTPUT_DIR", str(Path.home() / ".codex" / "daily-briefing-pro" / "reports"))).expanduser()


def safe_name(value: str) -> str:
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", value).strip("_")
    return text or "report"


def default_output(kind: str, data: dict) -> Path:
    if kind == "industry":
        sector = data.get("sector") if isinstance(data.get("sector"), dict) else {}
        subject = sector.get("name") or data.get("keyword") or "industry"
        return output_dir() / f"{safe_name(str(subject))}-行业分析.html"
    finance = data.get("finance_raw") if isinstance(data.get("finance_raw"), dict) else {}
    quote = data.get("quote") if isinstance(data.get("quote"), dict) else {}
    subject = quote.get("name") or data.get("stock_name") or data.get("stock_code") or "stock"
    code = data.get("stock_code") or ""
    return output_dir() / f"{safe_name(str(subject))}-{safe_name(str(code))}-个股分析.html"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从采集 JSON 生成个股/行业 HTML 报告并执行完整性门禁")
    parser.add_argument("--type", choices=("stock", "industry"), required=True)
    parser.add_argument("--data-json", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--no-verify", action="store_true")
    args = parser.parse_args(argv)

    data_path = Path(args.data_json).expanduser().resolve()
    if not data_path.is_file():
        print(json.dumps({"ok": False, "error": f"采集 JSON 不存在：{data_path}"}, ensure_ascii=False, indent=2))
        return 2
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"采集 JSON 无法解析：{exc}"}, ensure_ascii=False, indent=2))
        return 2

    data_check = verify_skill_report.verify_data(data_path, args.type)
    if not data_check.get("ok"):
        print(json.dumps({"ok": False, "data_check": data_check}, ensure_ascii=False, indent=2))
        return 1

    output = Path(args.output).expanduser().resolve() if args.output else default_output(args.type, data).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    document = build_stock_report(data) if args.type == "stock" else build_industry_report(data)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(document, encoding="utf-8")
    temp.replace(output)

    result: dict = {
        "ok": True,
        "type": args.type,
        "report": str(output),
        "data": str(data_path),
        "data_check": data_check,
    }
    if not args.no_verify:
        report_check = verify_skill_report.verify_report(output, args.type, data=data)
        report_check["data_check"] = data_check
        report_check["ok"] = bool(report_check.get("ok")) and bool(data_check.get("ok"))
        result["report_check"] = report_check
        result["ok"] = result["ok"] and bool(report_check["ok"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
