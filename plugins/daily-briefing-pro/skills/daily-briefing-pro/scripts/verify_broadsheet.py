# -*- coding: utf-8 -*-
"""报刊风简报验收：渲染 → 校验 → 截图

校验项（期望值从源简报自动推导，无硬编码）：
  1. 板块数与源简报一致（源 sec 版块 + 大小周期节点票）
  2. 数据行数与源简报一致（不含分栏后重复的表头行）
  3. 每个板块图标（svg.ico）都有实际绘制尺寸
  4. 无横向溢出（图表等横向滚动容器内部不计）
并在桌面 1440 / 手机 390 两个视口截图，另切 4 段长图便于逐段查看。
超长页面使用滚动截图拼接，避免 Chromium full_page 截图的 16K 上限截断正文。

用法:
    python verify_broadsheet.py --out <报刊版.html> [--src <源简报.html>] [--shots <截图目录>]
"""
import argparse
import json
from io import BytesIO
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


def capture_long_page(page, destination: Path, chunk_height: int = 4096) -> dict:
    """Capture a long page in viewport-sized slices and stitch them.

    Chromium can return a correctly-sized but mostly blank image when a single
    full-page screenshot exceeds its texture limit. Capturing and stitching
    smaller viewport slices keeps every report section painted.
    """
    from PIL import Image

    width = int(page.evaluate("document.documentElement.clientWidth"))
    page.set_viewport_size({"width": width, "height": chunk_height})
    page.add_style_tag(
        content="html,body{scrollbar-width:none}body::-webkit-scrollbar{display:none}"
    )
    height = int(page.evaluate("document.documentElement.scrollHeight"))
    if width <= 0 or height <= 0:
        raise RuntimeError(f"invalid page size: {width}x{height}")

    canvas = Image.new("RGB", (width, height), "white")
    segments = 0
    top = 0
    max_scroll = max(0, height - chunk_height)
    while top < height:
        target = min(top, max_scroll)
        page.evaluate("(y) => window.scrollTo(0, y)", target)
        page.wait_for_timeout(80)
        actual_top = int(page.evaluate("window.scrollY"))
        segment = Image.open(BytesIO(page.screenshot(full_page=False))).convert("RGB")
        canvas.paste(segment, (0, actual_top))
        segments += 1
        if actual_top >= max_scroll:
            break
        top += chunk_height

    canvas.save(destination, format="PNG", optimize=True)
    return {"width": width, "height": height, "segments": segments}


def tail_ink_ratio(src_png: Path, fraction: float = 0.05) -> float:
    """Return the sampled non-background pixel ratio near the bottom edge."""
    from PIL import Image

    image = Image.open(src_png).convert("RGB")
    width, height = image.size
    pixels = image.load()
    start = max(0, int(height * (1.0 - fraction)))
    ink = 0
    total = 0
    for y in range(start, height, 10):
        for x in range(10, width - 10, 10):
            red, green, blue = pixels[x, y]
            total += 1
            if max(red, green, blue) < 215 or (
                max(red, green, blue) - min(red, green, blue) > 30
            ):
                ink += 1
    return ink / total if total else 0.0


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
            screenshot_path = shots / f"{label}.png"
            capture = capture_long_page(view, screenshot_path)
            ink_ratio = tail_ink_ratio(screenshot_path)
            print(
                "截图:",
                f"{label}.png",
                f"{capture['width']}x{capture['height']}",
                f"segments={capture['segments']}",
                f"tail_ink={ink_ratio:.5f}",
            )
            if ink_ratio < 0.0005:
                ok = False
                print("[FAIL] 长图尾部为空白，疑似截图截断")
            crop(screenshot_path, label[0])
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
