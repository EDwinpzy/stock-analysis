# -*- coding: utf-8 -*-
"""每日简报 · 报刊风（纸张质感）模板渲染器

把 build_briefing.py 生成的当日简报 HTML 重排成报刊版：保留全部板块、全部数据行，
为每个板块配线描图标，龙虎榜与板块轮动左右并列成两栏（各自保留一张整表），
机构研报按行对半拆栏，整页带纸张质感（细颗粒 + 纸浆斑纹 + 淡帘纹）。

用法:
    python build_broadsheet.py                      # 取输出目录下日期最新的简报
    python build_broadsheet.py --src <简报.html>    # 指定源简报
    python build_broadsheet.py --out <输出.html>    # 指定输出
    python build_broadsheet.py --date 2026-09-21    # 指定日期（默认从源文件名推断）

默认源：<工作目录>/报告/每日简报/ 下日期最新的 *简报.html（排除已有报刊版）
默认输出：与源文件同目录的 <日期>简报-报刊版.html
样式资产：../templates/broadsheet.css
"""
import argparse
import re
from datetime import date as _date, datetime
from pathlib import Path

from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
DEFAULT_REPORT_SUBDIR = ("报告", "每日简报")
WEEKDAYS = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
REMOTE_FONT_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com"/>\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>\n'
    '<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700;900'
    '&family=Playfair+Display:wght@700;900&display=swap" rel="stylesheet"/>\n'
)


def default_output_dir() -> Path:
    return Path.cwd().joinpath(*DEFAULT_REPORT_SUBDIR)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="每日简报 · 报刊风模板渲染器")
    ap.add_argument("--src", help="源简报 HTML 路径")
    ap.add_argument("--out", help="输出 HTML 路径")
    ap.add_argument("--date", help="日期 YYYY-MM-DD（默认从源文件名推断）")
    ap.add_argument("--dir", help="简报目录（默认 <cwd>/报告/每日简报）")
    ap.add_argument(
        "--remote-fonts",
        action="store_true",
        help="写入原始 Google Fonts 链接，用于验证旧基准；默认使用系统字体",
    )
    return ap.parse_args(argv)


def resolve_paths(args):
    """定位源简报与输出路径；源文件默认取目录中日期最新的简报。"""
    src_arg = getattr(args, "src", None)
    if src_arg:
        src = Path(src_arg).expanduser().resolve()
    else:
        folder = Path(getattr(args, "dir", None) or default_output_dir())
        if not folder.is_dir():
            raise SystemExit(f"找不到简报目录：{folder}（可用 --dir 或 --src 指定）")
        cands = [p for p in folder.glob("*简报.html") if "报刊版" not in p.name]
        if not cands:
            raise SystemExit(f"{folder} 下没有可用的简报 HTML")
        src = sorted(cands, key=lambda p: (re.findall(r"\d{4}-\d{2}-\d{2}", p.name) or [""])[0],
                     reverse=True)[0]

    date_str = getattr(args, "date", None) or (re.findall(r"\d{4}-\d{2}-\d{2}", src.name) or [""])[0]
    if not date_str:
        raise SystemExit(f"无法从 {src.name} 推断日期，请用 --date 指定")
    out_arg = getattr(args, "out", None)
    out = Path(out_arg).expanduser().resolve() if out_arg else src.with_name(f"{date_str}简报-报刊版.html")
    return src, out, date_str


def date_labels(date_str: str) -> dict:
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return {
        "date": date_str,
        "dot": f"{d.year}.{d.month:02d}.{d.day:02d}",
        "cn": f"{d.year} 年 {d.month} 月 {d.day} 日",
        "weekday": WEEKDAYS[d.weekday()],
        "weekday_short": "周" + "一二三四五六日"[d.weekday()],
    }


def source_data_date(soup: BeautifulSoup, fallback: str) -> str:
    """Read the completed trading date from the source briefing, not the edition date."""
    mast = soup.select_one(".np-mast-sub")
    if mast:
        match = re.search(r"行情数据日\s*(\d{4}-\d{2}-\d{2})", mast.get_text(" ", strip=True))
        if match:
            return match.group(1)
    sent_date = soup.select_one(".sent-date")
    if sent_date:
        match = re.search(r"(\d{4}-\d{2}-\d{2})", sent_date.get_text(" ", strip=True))
        if match:
            return match.group(1)
    return fallback


PHASE_COLORS = {
    "冰点": "#f0d0c2",
    "退潮": "#e3a68f",
    "降温": "#d47a5f",
    "修复": "#bf4a32",
    "高潮": "#76140d",
}

# 板块 -> (图标 id, 英文栏目名)
ICONS = {
    "大小周期节点票": ("i-nodes", "Cycle Nodes"),
    "财经科技新闻": ("i-news", "News Desk"),
    "自选股新闻": ("i-star", "Watchlist"),
    "龙虎榜": ("i-rank", "Dragon & Tiger List"),
    "板块轮动": ("i-rotate", "Sector Rotation"),
    "机构研报": ("i-report", "Research"),
    "博主多空统计": ("i-gauge", "Sentiment Survey"),
    "淘股吧": ("i-chat", "Trader Notes"),
    "抖音": ("i-video", "Video Brief"),
    "未来大事件": ("i-calendar", "Calendar"),
    "策略": ("i-target", "The Editor's View"),
}
WIDE = {"机构研报", "策略"}

SPRITE = """
<svg aria-hidden="true" class="sprite" focusable="false">
<defs>
<symbol id="i-nodes" viewBox="0 0 24 24"><path d="M3 12h18"/><circle cx="6.5" cy="12" r="2.4"/><circle cx="13" cy="12" r="2.4"/><circle cx="19.5" cy="12" r="2.4"/><path d="M6.5 9.6V7h6.5M19.5 14.4V17H13"/></symbol>
<symbol id="i-news" viewBox="0 0 24 24"><path d="M4 5.5h13v13H5.5A1.5 1.5 0 0 1 4 17V5.5Z"/><path d="M17 8.5h3v9.5a1.5 1.5 0 0 1-1.5 1.5H5.5"/><path d="M7 8.5h7M7 11.5h7M7 14.5h4.5"/></symbol>
<symbol id="i-star" viewBox="0 0 24 24"><path d="m12 4 2.5 5.2 5.5.8-4 3.9 1 5.5-5-2.7-5 2.7 1-5.5-4-3.9 5.5-.8Z"/></symbol>
<symbol id="i-rank" viewBox="0 0 24 24"><path d="M4 20h16"/><path d="M7 20v-6M12 20V6M17 20v-9"/><path d="M12 4.5 13.2 6h-2.4Z"/></symbol>
<symbol id="i-rotate" viewBox="0 0 24 24"><path d="M4.5 12a7.5 7.5 0 0 1 12.8-5.3"/><path d="M19.5 12a7.5 7.5 0 0 1-12.8 5.3"/><path d="M17.3 3.2v3.5h-3.5M6.7 20.8v-3.5h3.5"/></symbol>
<symbol id="i-report" viewBox="0 0 24 24"><path d="M6 3.5h8l4 4V20.5H6Z"/><path d="M14 3.5v4h4"/><path d="M9 12h6M9 15h6M9 9h2.5"/></symbol>
<symbol id="i-gauge" viewBox="0 0 24 24"><path d="M4 17a8 8 0 1 1 16 0"/><path d="m12 17 4.2-5"/><circle cx="12" cy="17" r="1.3"/><path d="M4 17h1.6M18.4 17H20"/></symbol>
<symbol id="i-chat" viewBox="0 0 24 24"><path d="M4.5 5.5h15v10h-8l-4.5 3.5v-3.5H4.5Z"/><path d="M8 9h8M8 12h5"/></symbol>
<symbol id="i-video" viewBox="0 0 24 24"><rect height="14" rx="3" width="16" x="4" y="5"/><path d="M10.5 9.5 15 12l-4.5 2.5Z"/></symbol>
<symbol id="i-calendar" viewBox="0 0 24 24"><rect height="15" rx="2" width="16" x="4" y="5"/><path d="M4 9.5h16M8.5 3.8v2.7M15.5 3.8v2.7"/><path d="M8 13h2M14 13h2M8 16.5h2M14 16.5h2"/></symbol>
<symbol id="i-target" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.4"/><path d="M12 2.6v3M12 18.4v3M2.6 12h3M18.4 12h3"/></symbol>
<symbol id="i-chart" viewBox="0 0 24 24"><path d="M4 4v16h16"/><path d="M8 16.5v-4M12 16.5v-7M16 16.5v-2.5"/></symbol>
</defs>
</svg>
"""

def _tex(svg):
    return 'url("data:image/svg+xml,' + svg.replace("<", "%3C").replace(">", "%3E").replace("#", "%23") + '")'


# 纸张纹理：细颗粒（纸面纤维）+ 粗斑纹（纸浆厚薄），均在白底上做极淡的乘算
TEX_FINE = _tex(
    "<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200'><filter id='f'>"
    "<feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/>"
    "<feColorMatrix type='matrix' values='0 0 0 0 0.94 0 0 0 0 0.91 0 0 0 0 0.85 0.5 0.5 0.5 0 -0.38'/>"
    "</filter><rect width='200' height='200' filter='url(#f)'/></svg>"
)
TEX_MOTTLE = _tex(
    "<svg xmlns='http://www.w3.org/2000/svg' width='600' height='600'><filter id='m'>"
    "<feTurbulence type='fractalNoise' baseFrequency='0.008 0.013' numOctaves='4' stitchTiles='stitch'/>"
    "<feColorMatrix type='matrix' values='0 0 0 0 0.95 0 0 0 0 0.92 0 0 0 0 0.85 0.3 0.3 0.3 0 -0.3'/>"
    "</filter><rect width='600' height='600' filter='url(#m)'/></svg>"
)

TEMPLATE_DIR = BASE_DIR / "templates"

# 样式全部外置在 templates/broadsheet.css，便于单独调整配色与纸张纹理
CSS = (TEMPLATE_DIR / "broadsheet.css").read_text(encoding="utf-8")
CSS = CSS.replace("__TEX_FINE__", TEX_FINE).replace("__TEX_MOTTLE__", TEX_MOTTLE)


def norm_meta(text):
    text = re.sub(r"(\d)(条|篇|个|位|只|家|主帖|跟帖|数据)", r"\1 \2", text)
    text = re.sub(r"\s*/\s*", " / ", text)
    return re.sub(r"\s+", " ", text).strip()


def sub_heads(html_text):
    """把源简报里靠内联 margin 排布的段落标题换成可样式化的类名。"""
    html_text = html_text.replace('<div style="margin-top:8px">', '<div class="sub-head">')
    html_text = html_text.replace('<div style="margin-top:6px">', '<div class="inline-row">')
    html_text = html_text.replace('<div style="margin-top:4px">', '<div class="inline-row">')
    return html_text


def inner_html(node):
    return sub_heads("".join(str(c) for c in node.children))


def single_table(body_html, tbl_class):
    """给正文里的第一张表加类名，但不拆栏。

    龙虎榜与板块轮动改为左右并列的两个栏目后，各自只保留一张整表，
    列宽由 CSS 按百分比统一控制（.tbl-lhb / .tbl-rot）。"""
    frag = BeautifulSoup(body_html, "html.parser")
    tbl = frag.find("table")
    if tbl is None:
        return body_html
    tbl["class"] = list(tbl.get("class") or []) + [tbl_class]
    return "".join(str(c) for c in frag.children)


def two_col_table(body_html, tbl_class):
    """把板块正文里的长表按行对半拆成左右两栏，表头在每栏各重复一次；
    表格前后的说明块（KPI 条、口径框）保持通栏。
    两栏列宽由 CSS 按百分比统一指定，保证左右两半逐列对齐。"""
    frag = BeautifulSoup(body_html, "html.parser")
    kids = [c for c in frag.children if getattr(c, "name", None)]
    idx = next((i for i, c in enumerate(kids) if c.name == "table"), None)
    if idx is None:
        return body_html
    tbl = kids[idx]
    rows = tbl.find_all("tr")
    if len(rows) < 3:
        return body_html
    head_html = str(rows[0])
    data = rows[1:]
    half = -(-len(data) // 2)

    def half_table(chunk):
        return (f'<table class="split-tbl {tbl_class}">' + head_html
                + "".join(str(r) for r in chunk) + "</table>")

    left = '<div class="split-col">' + half_table(data[:half]) + "</div>"
    right = '<div class="split-col">' + half_table(data[half:]) + "</div>"
    html = ("".join(str(c) for c in kids[:idx])
            + '<div class="split-2col">' + left + right + "</div>")
    tail = kids[idx + 1:]
    if tail:
        html += '<div class="split-foot">' + "".join(str(c) for c in tail) + "</div>"
    return html


def chart_svg(data, labels, phases):
    n = len(data)
    w, h = 1020, 232
    left, right, top, bottom = 34, 12, 30, 196
    plot_w = w - left - right
    slot = plot_w / n
    bar_w = slot * 0.54
    scale = (bottom - top) / 100.0
    out = [
        f'<svg class="market-plot" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="近{n}个交易日市场温度阶段柱状图">'
    ]
    for v in (25, 75, 100):
        y = bottom - v * scale
        out.append(f'<line class="plot-grid" x1="{left}" y1="{y:.1f}" x2="{w - right}" y2="{y:.1f}"/>')
        out.append(f'<text class="plot-y" x="{left - 6}" y="{y + 3.4:.1f}" text-anchor="end">{v}</text>')
    y50 = bottom - 50 * scale
    out.append(f'<line class="plot-mid" x1="{left}" y1="{y50:.1f}" x2="{w - right}" y2="{y50:.1f}"/>')
    out.append(f'<text class="plot-mid-label" x="{left - 6}" y="{y50 + 3.4:.1f}" text-anchor="end">50</text>')
    for i, (v, label, phase) in enumerate(zip(data, labels, phases)):
        color = PHASE_COLORS.get(phase.split("｜")[0], "#b9b2a3")
        bar_h = v * scale
        x = left + i * slot + (slot - bar_w) / 2
        y = bottom - bar_h
        out.append(
            f'<rect class="plot-bar" x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
            f'fill="{color}"><title>{label}｜{v}｜{phase}</title></rect>'
        )
        out.append(f'<text class="plot-val" x="{x + bar_w / 2:.1f}" y="{y - 3:.1f}" text-anchor="middle">{v}</text>')
        cls = "plot-today" if i == n - 1 else "plot-date"
        out.append(
            f'<text class="{cls}" x="{x + bar_w / 2:.1f}" y="{bottom + 15:.1f}" text-anchor="middle">{label}</text>'
        )
    out.append(f'<line class="plot-base" x1="{left}" y1="{bottom}" x2="{w - right}" y2="{bottom}"/>')
    out.append("</svg>")
    return "".join(out)


def render(src: Path, out: Path, date_str: str, remote_fonts: bool = False) -> Path:
    SRC, OUT = src, out
    labels_cn = date_labels(date_str)
    soup = BeautifulSoup(SRC.read_text(encoding="utf-8"), "html.parser")
    data_date = source_data_date(soup, date_str)

    scripts = "\n".join(s.get_text() for s in soup.find_all("script"))
    series = [float(x) for x in re.search(r"const data=\[([^\]]+)\]", scripts).group(1).split(",")]
    labels = re.findall(r'"([\d\-]+)"', re.search(r"const labels=\[([^\]]+)\]", scripts).group(1))
    phases = re.findall(r'"([^"]+)"', re.search(r"const phases=\[([^\]]+)\]", scripts).group(1))

    sent = soup.select_one(".sent-box")
    temp_value = sent.select_one(".sent-val").get_text(strip=True)
    temp_desc = sent.select_one(".sent-desc").get_text(strip=True)
    deltas = [(d.select_one("span").get_text(strip=True), d.select_one("b").get_text(strip=True))
              for d in sent.select(".sent-deltas > div")]
    factor_groups = sent.select(".sent-factors")
    factors = [s.get_text(strip=True) for s in factor_groups[0].select(".sent-factor")]
    board_factors = [s.get_text(strip=True) for s in factor_groups[1].select(".sent-factor")]
    temp_date = sent.select_one(".sent-date").get_text(strip=True)

    indices = []
    for mc in soup.select(".ms .mc"):
        indices.append({
            "label": mc.select_one(".lb").get_text(strip=True),
            "value": mc.select_one(".vl").get_text(strip=True),
            "change": mc.select_one(".cg").get_text(strip=True),
            "up": "up" in (mc.get("class") or []),
        })

    node = soup.select_one("section.node-cycle")
    node_head = node.select_one(".sh")
    node_meta = node_head.select_one(".meta").get_text(strip=True)
    node_title = head_title(node_head, node_meta)
    node_head.extract()
    node_body = inner_html(node)
    node.extract()

    quote = soup.select_one("section.quote-banner")
    quote_text = quote.select_one(".quote-text").get_text(strip=True)
    quote_author = quote.select_one(".quote-author strong").get_text(strip=True)
    quote_title = quote.select_one(".quote-title").get_text(strip=True)
    quote_principle = inner_html(quote.select_one(".quote-principle"))
    quote_tags = [t.get_text(strip=True) for t in quote.select(".quote-tag")]
    quote_meta = quote.select_one(".quote-meta").get_text(strip=True)

    soup.select_one("section.hero").extract()

    sections = []
    for sec in soup.select("section.sec"):
        head = sec.select_one(".sh")
        meta = head.select_one(".meta").get_text(strip=True)
        title = head_title(head, meta)
        head.extract()
        sec["style"] = ""
        body = inner_html(sec)
        if title == "龙虎榜":
            body = single_table(body, "tbl-lhb")
        elif title == "板块轮动":
            body = single_table(body, "tbl-rot")
        elif title == "机构研报":
            body = two_col_table(body, "tbl-yb")
        sections.append({"title": title, "meta": norm_meta(meta), "body": body})

    print("板块顺序:", " / ".join(s["title"] for s in sections))
    print("数据行数:", sum(s["body"].count("<tr") for s in sections))
    board_count = len(sections) + 1  # 版面板块 + 大小周期节点票

    def sec_block(item, wide):
        icon, en = ICONS.get(item["title"], ("i-news", ""))
        return (
            f'<section class="section{" wide" if wide else ""}" data-board="{item["title"]}">'
            f'<div class="sec-head"><svg class="ico" aria-hidden="true"><use href="#{icon}"/></svg>'
            f'<h2>{item["title"]}</h2><span class="en">{en}</span>'
            f'<span class="meta">{item["meta"]}</span></div>{item["body"]}</section>'
        )

    rows, buffer = [], []
    for item in sections:
        if item["title"] in WIDE:
            if buffer:
                rows.append(("pair", buffer))
                buffer = []
            rows.append(("wide", [item]))
        else:
            buffer.append(item)
            if len(buffer) == 2:
                rows.append(("pair", buffer))
                buffer = []
    if buffer:
        rows.append(("pair", buffer))

    layout = []
    for kind, items in rows:
        if kind == "wide":
            layout.append(f'<div class="row wide">{sec_block(items[0], True)}</div>')
        else:
            layout.append('<div class="row">' + "".join(sec_block(i, False) for i in items) + "</div>")

    ticker = "".join(
        f'<div class="quote"><small>{i["label"]}</small><b>{i["value"]}</b>'
        f'<em class="{"up" if i["up"] else "dn"}">{i["change"]}</em></div>'
        for i in indices
    )
    board_html = ('<span class="head">' + board_factors[0] + "</span>" +
                  "".join(f"<span>{f}</span>" for f in board_factors[1:]))
    delta_html = "".join(f"<span>{k}<b>{v}</b></span>" for k, v in deltas)
    legend = "".join(
        f'<span><i style="background:{color}"></i>{phase}</span>' for phase, color in PHASE_COLORS.items()
    ) + '<span><i class="mid"></i>50 中性线</span>'
    quote_tag_html = "".join(f'<span class="tag">{t}</span>' for t in quote_tags)
    phase_word = re.split(r"[｜|\s]", temp_desc.strip())[0] or "过渡"
    headline = f"市场温度 {temp_value}，盘面进入{phase_word}区"

    values = {
        "font_links": REMOTE_FONT_LINKS if remote_fonts else "",
        "css": CSS,
        "sprite": SPRITE,
        "headline": headline,
        "date_dash": labels_cn["date"],
        "data_date": data_date,
        "date_dot": labels_cn["dot"],
        "date_cn": labels_cn["cn"],
        "weekday": labels_cn["weekday"],
        "weekday_short": labels_cn["weekday_short"],
        "board_count": str(board_count),
        "ticker": ticker,
        "temp_value": temp_value,
        "temp_desc": temp_desc,
        "delta_html": delta_html,
        "board_html": board_html,
        "temp_date": temp_date,
        "series_len": str(len(series)),
        "chart": chart_svg(series, labels, phases),
        "legend": legend,
        "node_title": node_title,
        "node_meta": norm_meta(node_meta),
        "node_body": node_body,
        "quote_text": quote_text,
        "quote_author": quote_author,
        "quote_title": quote_title,
        "quote_principle": quote_principle,
        "quote_tag_html": quote_tag_html,
        "quote_meta": quote_meta,
        "layout": "".join(layout),
    }
    # 模板含大量 CSS/JS 花括号，改用逐项替换而非 str.format
    doc = DOC_TEMPLATE
    for key, value in values.items():
        doc = doc.replace("{" + key + "}", value)
    # Keep generated HTML byte-identical across Windows and Linux builds.
    with OUT.open("w", encoding="utf-8", newline="\r\n") as f:
        f.write(doc)
    print("输出:", OUT, len(doc), "bytes")
    return OUT


def main(argv=None):
    args = parse_args(argv)
    src, out, date_str = resolve_paths(args)
    print("源简报:", src)
    print("日期:", date_str)
    render(src, out, date_str, remote_fonts=args.remote_fonts)


def head_title(head, meta):
    text = head.get_text(" ", strip=True)
    ico = head.select_one(".ico")
    if ico:
        text = text.replace(ico.get_text(strip=True), " ")
    return re.sub(r"\s+", " ", text.replace(meta, " ")).strip()


DOC_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{date_dash} 每日简报｜报刊版（全 {board_count} 板块）</title>
{font_links}<style>{css}</style>
</head>
<body>
{sprite}
<main class="page">
<div class="topline"><span>{date_cn}　{weekday}　|　每日简报 · 第 1 版</span><span class="demo">报刊版 · 全 {board_count} 板块</span></div>
<header class="mast">
  <div class="kicker">A-Share Daily Briefing · Broadsheet Edition</div>
  <h1>每 日 简 报</h1>
  <div class="subtitle">盘面温度 / 资金流向 / 观点汇编 / 风险提示</div>
  <div class="dateline"><span>{date_dot} {weekday_short}</span><span class="sep">·</span><span>行情数据日 <b>{data_date}</b></span><span class="sep">·</span><span>共 <b>{board_count}</b> 个板块</span><span class="sep">·</span><span>情绪模型 3.2</span></div>
  <div class="double-rule"></div>
</header>

<section class="quote-band">
  <div class="qmark">&#10077;</div>
  <div>
    <div class="qtext">{quote_text}</div>
    <div class="qauthor">—— <strong>{quote_author}</strong><span class="qtitle">{quote_title}</span></div>
    <div class="qprinciple">{quote_principle}</div>
  </div>
  <div class="qside"><div>{quote_tag_html}</div>{quote_meta}</div>
</section>

<div class="ticker" aria-label="指数行情">{ticker}</div>

<section class="lead">
  <div class="eyebrow">头版导读　|　市场温度与情绪周期</div>
  <h2>{headline}</h2>
  <div class="lead-body">
    <aside class="temperature">
      <div class="temp-kicker"><span>市场温度 S</span><em>情绪模型 3.2</em></div>
      <div class="temp-number">{temp_value}<small>/100</small></div>
      <div class="temp-phase">{temp_desc}</div>
      <div class="temp-deltas">{delta_html}</div>
      <div class="bar"><i style="left:{temp_value}%"></i></div>
      <div class="factor-list">{board_html}</div>
      <div class="temp-date">{temp_date}</div>
    </aside>
    <div class="lead-chart">
      <div class="chart-head"><svg class="ico" aria-hidden="true"><use href="#i-chart"/></svg>
        <h3>情绪阶段柱状图</h3><span class="en">Market Temperature</span>
        <span class="meta">近 {series_len} 个交易日 · 数据日 {data_date}</span></div>
      <div class="chart-wrap">{chart}</div>
      <div class="legend">{legend}</div>
    </div>
  </div>
</section>

<section class="section node-cycle" data-board="大小周期节点票">
  <div class="sec-head"><svg class="ico" aria-hidden="true"><use href="#i-nodes"/></svg>
    <h2>{node_title}</h2><span class="en">Cycle Nodes</span><span class="meta">{node_meta}</span></div>
  {node_body}
</section>

<div class="layout">{layout}</div>

<footer class="foot">
  <span>每日简报 · {date_dash} 报刊版 · {board_count} 个板块全部保留</span>
  <span>内容取自 {date_dash} 当日简报原文　/　各板块数据窗口见栏目表头</span>
</footer>
</main>
<script>(()=>{
const scroll=document.querySelector('[data-node-scroll]'),track=scroll?.querySelector('.node-track'),value=document.querySelector('[data-node-zoom-value]');
if(!scroll||!track)return;let zoom=1;
const apply=()=>{track.style.setProperty('--node-zoom',zoom);value.textContent=Math.round(zoom*100)+'%'};
document.querySelectorAll('[data-node-zoom]').forEach(b=>b.addEventListener('click',()=>{
  const a=b.dataset.nodeZoom;zoom=a==='reset'?1:Math.max(.8,Math.min(2.4,zoom+(a==='in'?.2:-.2)));apply()}));
let down=false,x=0,left=0;
scroll.addEventListener('pointerdown',e=>{down=true;x=e.clientX;left=scroll.scrollLeft;scroll.classList.add('dragging');scroll.setPointerCapture(e.pointerId)});
scroll.addEventListener('pointermove',e=>{if(down)scroll.scrollLeft=left-(e.clientX-x)});
scroll.addEventListener('pointerup',()=>{down=false;scroll.classList.remove('dragging')});
scroll.addEventListener('pointercancel',()=>{down=false;scroll.classList.remove('dragging')});
scroll.addEventListener('wheel',e=>{if(e.ctrlKey){e.preventDefault();zoom=Math.max(.8,Math.min(2.4,zoom+(e.deltaY<0?.1:-.1)));apply()}},{passive:false});
})();</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
