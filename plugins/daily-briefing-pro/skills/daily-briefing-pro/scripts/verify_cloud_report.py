#!/usr/bin/env python3
"""Verify a stock or industry report in the cloud container.

The checks are intentionally structural and browser-based: every expected
section and table must exist, and both desktop and mobile layouts must render
without horizontal overflow. Long screenshots are captured for evidence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from verify_broadsheet import capture_long_page, crop, tail_ink_ratio


CHECK_JS = """() => {
  const inScroller = el => {
    for (let n = el.parentElement; n; n = n.parentElement) {
      const ox = getComputedStyle(n).overflowX;
      if (ox === 'auto' || ox === 'scroll') return true;
    }
    return false;
  };
  const over = [...document.querySelectorAll('.c *')].filter(el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && !inScroller(el)
      && (r.right > document.documentElement.clientWidth + 1 || r.left < -1);
  }).slice(0, 12).map(el => el.tagName + (typeof el.className === 'string'
    ? '.' + el.className.split(' ')[0] : ''));
  const tables = [...document.querySelectorAll('.sec table')];
  return {
    sections: document.querySelectorAll('.sec').length,
    tables: tables.length,
    emptyTables: tables.filter(t => !t.querySelector('tbody tr')).length,
    rows: document.querySelectorAll('.sec table tr').length,
    title: document.title,
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    overflowing: [...new Set(over)],
    height: document.documentElement.scrollHeight,
  };
}"""


def inspect_html(path: Path) -> dict:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    sections = soup.select(".sec")
    tables = soup.select(".sec table")
    return {
        "sections": len(sections),
        "tables": len(tables),
        "rows": sum(len(table.select("tr")) for table in tables),
        "title": soup.title.get_text(strip=True) if soup.title else "",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="云端个股/行业报告渲染门禁")
    parser.add_argument("--report", required=True)
    parser.add_argument("--shots", required=True)
    parser.add_argument("--json", required=True)
    parser.add_argument("--sections", type=int, required=True)
    parser.add_argument("--tables", type=int, required=True)
    parser.add_argument("--label", default="report")
    args = parser.parse_args(argv)

    report = Path(args.report).resolve()
    shots = Path(args.shots).resolve()
    result_path = Path(args.json).resolve()
    shots.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict = {
        "ok": False,
        "report": str(report),
        "expected": {"sections": args.sections, "tables": args.tables},
        "html": inspect_html(report),
        "views": {},
        "problems": [],
    }
    if payload["html"]["sections"] != args.sections:
        payload["problems"].append(
            f"HTML 板块数 {payload['html']['sections']} != {args.sections}"
        )
    if payload["html"]["tables"] != args.tables:
        payload["problems"].append(
            f"HTML 表格数 {payload['html']['tables']} != {args.tables}"
        )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox"])
        for name, width, height in (
            ("desktop", 1440, 1000),
            ("mobile", 390, 844),
        ):
            page = browser.new_page(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
            )
            page.goto(report.as_uri(), wait_until="load", timeout=60000)
            try:
                page.wait_for_function(
                    "document.fonts.status === 'loaded'", timeout=8000
                )
            except Exception:
                pass
            page.wait_for_timeout(500)
            report_data = page.evaluate(CHECK_JS)
            screenshot = shots / f"{args.label}-{name}.png"
            capture = capture_long_page(page, screenshot)
            ink_ratio = tail_ink_ratio(screenshot)
            report_data.update(
                {
                    "screenshot": str(screenshot),
                    "screenshot_size": [capture["width"], capture["height"]],
                    "segments": capture["segments"],
                    "tail_ink_ratio": round(ink_ratio, 8),
                }
            )
            crop(screenshot, f"{args.label}-{name[0]}")
            payload["views"][name] = report_data
            if report_data["sections"] != args.sections:
                payload["problems"].append(
                    f"{name} 板块数 {report_data['sections']} != {args.sections}"
                )
            if report_data["tables"] != args.tables:
                payload["problems"].append(
                    f"{name} 表格数 {report_data['tables']} != {args.tables}"
                )
            if report_data["emptyTables"]:
                payload["problems"].append(
                    f"{name} 空表 {report_data['emptyTables']} 个"
                )
            if report_data["overflowing"]:
                payload["problems"].append(
                    f"{name} 横向溢出: {report_data['overflowing']}"
                )
            if report_data["scrollWidth"] > report_data["clientWidth"] + 1:
                payload["problems"].append(
                    f"{name} 页面宽度 {report_data['scrollWidth']} "
                    f"> {report_data['clientWidth']}"
                )
            if ink_ratio < 0.0005:
                payload["problems"].append(f"{name} 长图底部疑似空白")
            page.close()
        browser.close()

    payload["ok"] = not payload["problems"]
    result_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if payload["problems"]:
        for problem in payload["problems"]:
            print(f"[FAIL] {problem}")
        return 1
    print("[PASS] 云端报告桌面/手机渲染门禁通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
