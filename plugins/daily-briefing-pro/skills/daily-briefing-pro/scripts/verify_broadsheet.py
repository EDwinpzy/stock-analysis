# -*- coding: utf-8 -*-
"""报刊风简报验收：渲染 → 校验 → 截图

校验项（期望值从源简报自动推导，无硬编码）：
  1. 板块数与源简报一致（源 sec 版块 + 大小周期节点票）
  2. 数据行数与源简报一致（不含分栏后重复的表头行）
  3. 每个板块图标（svg.ico）都有实际绘制尺寸
  4. 无横向溢出（图表等横向滚动容器内部不计）
并在桌面 1440 / 手机 390 两个视口截图，另切 4 段长图便于逐段查看。

用法:
    python verify_broadsheet.py --out <报刊版.html> [--src <源简报.html>] [--shots <截图目录>]
"""
import argparse
import json
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

CHECK_JS = """() => {
  const boards = [...document.querySelectorAll('.section[data-board]')].map(s => s.dataset.board);
  const icons = [...document.querySelectorAll('svg.ico')].map(svg => {
    let w = 0, h = 0;
    try { const b = svg.getBBox(); w = Math.round(b.width); h = Math.round(b.height); } catch (e) {}
    const use = svg.querySelector('use');
    return { id: use ? use.getAttribute('href') : null, w, h };
  });
  // 横向滚动容器（如移动端图表条）内部元素不算页面溢出
  const inScroller = el => {
    for (let n = el.parentElement; n; n = n.parentElement) {
      const ox = getComputedStyle(n).overflowX;
      if (ox === 'auto' || ox === 'scroll') return true;
    }
    return false;
  };
  const over = [...document.querySelectorAll('.page *')].filter(el => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && !inScroller(el)
        && (r.right > document.documentElement.clientWidth + 1 || r.left < -1);
  }).slice(0, 12).map(el => el.className && typeof el.className === 'string'
      ? el.tagName + '.' + el.className.split(' ')[0] : el.tagName);
  return {
    boards,
    rows: document.querySelectorAll('.layout tr').length,
    dataRows: document.querySelectorAll('.layout tr:not(:has(th))').length,
    headRows: document.querySelectorAll('.layout tr:has(th)').length,
    icons,
    brokenIcons: icons.filter(i => i.w === 0 || i.h === 0).length,
    docScrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    overflowing: [...new Set(over)],
    height: document.documentElement.scrollHeight
  };
}"""


def source_expectations(src: Path) -> dict:
    """从源简报推导应保留的板块数与数据行数。"""
    soup = BeautifulSoup(src.read_text(encoding="utf-8"), "html.parser")
    secs = [s for s in soup.select("section.sec") if "node-cycle" not in (s.get("class") or [])]
    node = soup.select_one("section.node-cycle")
    scope = secs + ([node] if node else [])
    data_rows = sum(1 for t in scope for r in t.find_all("tr") if not r.find_all("th"))
    return {"boards": len(secs) + (1 if node else 0), "dataRows": data_rows}


def crop(src_png: Path, prefix: str, chunks: int = 4) -> None:
    try:
        from PIL import Image
    except Exception:
        return
    img = Image.open(src_png)
    w, h = img.size
    step = -(-h // chunks)
    for i in range(chunks):
        top, bot = i * step, min(h, (i + 1) * step)
        if top >= bot:
            break
        img.crop((0, top, w, bot)).save(src_png.with_name(f"{prefix}{i + 1}.png"))
    print("切片:", prefix + f"1..{chunks}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="报刊风简报验收")
    ap.add_argument("--out", required=True, help="报刊版 HTML")
    ap.add_argument("--src", help="源简报 HTML（用于推导期望的板块数与数据行数）")
    ap.add_argument("--shots", help="截图目录（默认 <输出目录>/_验收）")
    args = ap.parse_args(argv)

    page_path = Path(args.out).expanduser().resolve()
    if not page_path.exists():
        raise SystemExit(f"找不到输出文件：{page_path}")
    shots = Path(args.shots).expanduser().resolve() if args.shots else page_path.parent / "_验收"
    shots.mkdir(parents=True, exist_ok=True)
    expect = source_expectations(Path(args.src).expanduser().resolve()) if args.src else {}
    print("期望值:", expect or "（未提供源简报，跳过数量校验）")

    ok = True
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for label, width, height in (("desktop", 1440, 1000), ("mobile", 390, 844)):
            view = browser.new_page(viewport={"width": width, "height": height},
                                    device_scale_factor=1)
            view.goto(page_path.as_uri(), wait_until="load")
            try:
                view.wait_for_function("document.fonts.status === 'loaded'", timeout=8000)
            except Exception:
                pass
            view.wait_for_timeout(700)
            report = view.evaluate(CHECK_JS)
            print(f"--- {label} ---")
            print(json.dumps(report, ensure_ascii=False, indent=1))
            view.screenshot(path=str(shots / f"{label}.png"), full_page=True)
            print("截图:", f"{label}.png")
            crop(shots / f"{label}.png", label[0])
            if expect:
                if len(report["boards"]) != expect["boards"]:
                    ok = False
                    print(f"[FAIL] 板块数 {len(report['boards'])} != {expect['boards']}")
                if report["dataRows"] != expect["dataRows"]:
                    ok = False
                    print(f"[FAIL] 数据行数 {report['dataRows']} != {expect['dataRows']}")
            if report["brokenIcons"]:
                ok = False
                print(f"[FAIL] 图标未渲染 {report['brokenIcons']} 个")
            if report["overflowing"]:
                ok = False
                print("[FAIL] 横向溢出:", report["overflowing"])
            view.close()
        browser.close()
    print("验收:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
