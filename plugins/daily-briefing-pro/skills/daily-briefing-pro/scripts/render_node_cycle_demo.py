#!/usr/bin/env python3
"""生成节点票模块的本地示例页面，用于样式回归检查，不写入正式简报数据。"""

from pathlib import Path
import sys

from build_briefing import render_node_cycle_section
from node_cycle_model import build_node_model


def main() -> None:
    records = [
        {"date": "2026-08-20", "stocks": [
            {"name": "周期核心", "code": "000001", "board": 5, "role": "major", "cycle_id": "C1", "major_cycle": True, "evidence": {"level": "high", "source": "米开朗基瑞主帖"}},
            {"name": "内部小节点", "code": "000002", "board": 3, "cycle_id": "C1"},
        ]},
        {"date": "2026-08-21", "stocks": [
            {"name": "周期核心", "code": "000001", "board": 6, "role": "major", "cycle_id": "C1", "major_cycle": True, "evidence": {"level": "high", "source": "米开朗基瑞主帖"}},
            {"name": "内部小节点", "code": "000002", "board": 4, "cycle_id": "C1"},
        ]},
        {"date": "2026-08-22", "stocks": [
            {"name": "周期核心", "code": "000001", "board": 7, "role": "major", "cycle_id": "C1", "major_cycle": True, "evidence": {"level": "high", "source": "米开朗基瑞主帖"}},
            {"name": "内部小节点", "code": "000002", "board": 5, "cycle_id": "C1"},
        ]},
        {"date": "2026-08-25", "stocks": [
            {"name": "穿越样例", "code": "000003", "board": 4, "role": "穿越"},
        ]},
    ]
    model = build_node_model(records, "2026-08-25")
    section = render_node_cycle_section(model)
    template = (Path(__file__).parents[1] / "templates" / "briefing.html").read_text(encoding="utf-8")
    css = template[template.find("<style>"):template.find("</style>") + len("</style>")]
    html = f"<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>{css}</head><body><main class='c'><div class='g'>{section}</div></main></body></html>"
    out = Path(__file__).parents[1] / "output" / "node_cycle_demo.html"
    out.write_text(html, encoding="utf-8")
    print(out)
    if "--screenshot" in sys.argv:
        from playwright.sync_api import sync_playwright
        image = out.with_suffix(".png")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900, "device_scale_factor": 1})
            page.goto(out.as_uri(), wait_until="load")
            page.screenshot(path=str(image), full_page=True)
            browser.close()
        print(image)


if __name__ == "__main__":
    main()
