from __future__ import annotations

import html
import math
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
STOCK_TEMPLATE = PLUGIN_ROOT / "skills" / "stock-analysis" / "assets" / "template.html"
CN_TZ = ZoneInfo("Asia/Shanghai")
EMPTY_MARKERS = {"", "-", "--", "暂无", "暂无数据", "none", "null", "nan", "nat", "n/a"}


INDUSTRY_CSS = r"""
:root{--paper:#f5f1e8;--ink:#1b1915;--bg2:#fffdf8;--bg3:#f1ece1;--bd:rgba(27,25,21,.16);--bd2:rgba(27,25,21,.34);--t2:#45413a;--t3:#7c7566;--up:#b3261e;--dn:#1c6b46;--gld:#8a6a12;--a:#8c1c13;--sans:'Microsoft YaHei UI','Microsoft YaHei','PingFang SC','Noto Sans CJK SC','Segoe UI',system-ui,sans-serif}
*{margin:0;padding:0;box-sizing:border-box}body{background:var(--paper);color:var(--ink);font-family:var(--sans);line-height:1.75;font-size:13.5px;font-variant-numeric:tabular-nums}.c{max-width:1280px;margin:0 auto;padding:20px 24px 40px}.np-mast{margin:4px 0 20px;padding:14px 0 11px;border-top:1px solid var(--ink);border-bottom:3px double var(--ink);text-align:center}.np-mast-kicker{font-size:11px;font-weight:700;letter-spacing:.3em;color:var(--a);margin-bottom:6px}.np-mast-title{font-size:44px;line-height:1.12;font-weight:900;letter-spacing:.2em;text-indent:.2em}.np-mast-sub{display:flex;justify-content:center;gap:10px;flex-wrap:wrap;margin-top:8px;font-size:11.5px;color:var(--t2)}.g{display:grid;grid-template-columns:minmax(0,1fr);gap:18px}.sec{background:var(--bg2);border:1px solid var(--bd);border-top:2px solid var(--ink);overflow:hidden}.sh{display:flex;align-items:center;gap:8px;padding:11px 16px 10px;border-bottom:1px solid var(--ink)}.sh .icon{font-size:12px;color:var(--a)}.sh h2{font-size:15.5px;font-weight:700;letter-spacing:.03em}.sb{padding:14px 16px}.sc{margin-bottom:18px}.sc:last-child{margin-bottom:0}.sch{display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--bg3);border-left:3px solid var(--a);margin-bottom:12px}.sch h3{font-size:13.5px;font-weight:700}.sch .tag{font-size:10.5px;font-weight:700;padding:2px 8px;border:1px solid var(--bd2);color:var(--t2);margin-left:auto}.kv{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:16px}.kvi{background:var(--bg3);border:1px solid var(--bd);border-top:2px solid var(--ink);padding:12px 14px}.kvk{font-size:11px;color:var(--t3);margin-bottom:4px;letter-spacing:.08em}.kvv{font-size:21px;font-weight:700;line-height:1.2}.kvv.up{color:var(--up)}.kvv.dn{color:var(--dn)}.kvv.gold{color:var(--gld)}.kvsub{font-size:11px;color:var(--t3);margin-top:4px;line-height:1.55}.dt{width:100%;border-collapse:collapse;font-size:12.5px;margin-bottom:16px}.dt th{padding:8px 10px;text-align:left;font-weight:700;color:var(--t3);font-size:11px;border-bottom:1px solid var(--ink);white-space:nowrap}.dt td{padding:7px 10px;border-bottom:1px solid rgba(27,25,21,.10);color:var(--t2);line-height:1.5}.dt tr:hover td{background:rgba(140,28,19,.045)}.up{color:var(--up);font-weight:600}.dn{color:var(--dn)}.gold{color:var(--gld);font-weight:700}.lb{border:1px solid var(--bd);border-left:3px solid var(--a);background:rgba(140,28,19,.05);padding:14px 18px;margin-bottom:16px}.lb.warn{border-left-color:var(--dn);background:rgba(28,107,70,.05)}.lb .li{padding:4px 0;display:flex;gap:8px}.lb .li::before{content:'—';color:var(--a);font-weight:700}.cf{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}.cfi{flex:1 1 150px;background:var(--bg3);border:1px solid var(--bd);border-top:2px solid var(--ink);padding:12px;text-align:center}.cfn{font-weight:700;margin-bottom:4px}.cfd{font-size:11px;color:var(--t3)}.src{font-size:11px;color:var(--t3);margin:8px 0 16px}.ft{text-align:center;padding:28px 0 12px;font-size:11.5px;color:var(--t3);border-top:1px solid var(--ink);margin-top:24px;line-height:2}@media(max-width:960px){.c{padding:14px}.np-mast-title{font-size:29px}.kv{grid-template-columns:repeat(2,minmax(0,1fr))}.dt{display:block;overflow-x:auto}}
"""

MOBILE_TABLE_CSS = r"""
@media(max-width:768px){
.dt{display:block;width:100%;border-collapse:collapse}
.dt thead{display:none}
.dt tbody{display:block}
.dt tr{display:block;border-bottom:1px solid var(--bd);padding:4px 0}
.dt td{display:grid;grid-template-columns:88px minmax(0,1fr);gap:8px;width:auto!important;padding:6px 10px;border-bottom:none;font-size:12px}
.dt td::before{content:attr(data-label);color:var(--t3);font-size:10.5px;font-weight:700;letter-spacing:.05em;line-height:1.6}
.dt td[colspan]{display:block;text-align:center}
.dt td[colspan]::before{content:none}
.dt.kv tr{display:grid;grid-template-columns:88px minmax(0,1fr);gap:8px;padding:6px 10px}
.dt.kv td{display:block;padding:0;border:none}
.dt.kv td::before{content:none}
}
"""


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, str):
        text = value.strip()
        return None if text.lower() in EMPTY_MARKERS else text
    return value


def number(value: Any) -> float | None:
    value = clean(value)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace("%", "").strip()
    if text.lower() in EMPTY_MARKERS:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fnum(value: Any, digits: int = 2, fallback: str = "公开数据未覆盖") -> str:
    parsed = number(value)
    return fallback if parsed is None else f"{parsed:,.{digits}f}"


def fpct(value: Any, digits: int = 2, signed: bool = True, fallback: str = "公开数据未覆盖") -> str:
    parsed = number(value)
    if parsed is None:
        return fallback
    sign = "+" if signed and parsed > 0 else ""
    return f"{sign}{parsed:,.{digits}f}%"


def fyi(value: Any, digits: int = 2) -> str:
    parsed = number(value)
    return "公开数据未覆盖" if parsed is None else f"{parsed / 1e8:,.{digits}f} 亿"


def median(values: Iterable[Any]) -> float | None:
    parsed = [number(value) for value in values]
    valid = [value for value in parsed if value is not None]
    return statistics.median(valid) if valid else None


def pick(mapping: Any, *fragments: str, exclude: Iterable[str] = (), year: int | None = None) -> Any:
    if not isinstance(mapping, dict):
        return None
    for key, value in mapping.items():
        text = str(key)
        lowered = text.lower()
        if not all(fragment.lower() in lowered for fragment in fragments):
            continue
        if any(fragment.lower() in lowered for fragment in exclude):
            continue
        if year is not None and f"[{year}" not in text:
            continue
        if clean(value) is not None:
            return clean(value)
    return None


def annual_series(mapping: Any, *fragments: str, exclude: Iterable[str] = ()) -> dict[int, float]:
    if not isinstance(mapping, dict):
        return {}
    result: dict[int, float] = {}
    for key, value in mapping.items():
        text = str(key)
        if not all(fragment.lower() in text.lower() for fragment in fragments):
            continue
        if any(fragment.lower() in text.lower() for fragment in exclude):
            continue
        match = re.search(r"\[(\d{4})1231\]", text)
        if not match:
            continue
        parsed = number(value)
        if parsed is not None:
            result[int(match.group(1))] = parsed
    return dict(sorted(result.items()))


def latest_values(series: dict[int, float], count: int = 3) -> list[tuple[int, float]]:
    return list(series.items())[-count:]


def change_rate(series: dict[int, float]) -> float | None:
    years = sorted(series)
    if len(years) < 2 or series[years[-2]] == 0:
        return None
    return (series[years[-1]] / series[years[-2]] - 1) * 100


def first_text(value: Any) -> str:
    value = clean(value)
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for item in value.values():
            text = first_text(item)
            if text:
                return text
    if isinstance(value, list):
        for item in value:
            text = first_text(item)
            if text:
                return text
    return str(value)


def epoch_text(value: Any) -> str:
    parsed = number(value)
    if parsed is None or parsed <= 0:
        return "时间未返回"
    try:
        return datetime.fromtimestamp(parsed, tz=timezone.utc).astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return "时间未返回"


def table(headers: Iterable[Any], rows: Iterable[Iterable[Any]], empty: str = "当前数据快照没有可列示记录") -> str:
    header_tuple = tuple(headers)
    header_html = "".join(f"<th>{esc(item)}</th>" for item in header_tuple)
    body_rows = [tuple(row) for row in rows]
    if body_rows:
        body = "".join(
            "<tr>"
            + "".join(
                f'<td data-label="{esc(header_tuple[index]) if index < len(header_tuple) else ""}">'
                f"{esc(item)}</td>"
                for index, item in enumerate(row)
            )
            + "</tr>"
            for row in body_rows
        )
    else:
        body = f'<tr><td colspan="{len(header_tuple)}">{esc(empty)}</td></tr>'
    css_class = "dt kv" if header_tuple == ("项目", "内容") else "dt"
    return f'<table class="{css_class}"><thead><tr>{header_html}</tr></thead><tbody>{body}</tbody></table>'


def kv_grid(items: Iterable[tuple[str, str, str, str]]) -> str:
    cards = []
    for label, value, sub, tone in items:
        cards.append(
            '<div class="kvi">'
            f'<div class="kvk">{esc(label)}</div>'
            f'<div class="kvv {esc(tone)}">{esc(value)}</div>'
            f'<div class="kvsub">{esc(sub)}</div>'
            "</div>"
        )
    return '<div class="kv">' + "".join(cards) + "</div>"


def section(index: str, title: str, body: str, meta: str = "") -> str:
    meta_html = f'<span class="tag">{esc(meta)}</span>' if meta else ""
    return (
        '<div class="sec"><div class="sh">'
        f'<span class="icon">{esc(index)}</span><h2>{esc(title)}</h2>{meta_html}'
        f'</div><div class="sb">{body}</div></div>'
    )


def tone(value: Any) -> str:
    parsed = number(value)
    return "up" if parsed is not None and parsed > 0 else "dn" if parsed is not None and parsed < 0 else ""


def split_products(*values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = clean(value)
        if not text:
            continue
        for item in str(text).split("||"):
            normalized = item.strip()
            if normalized and normalized not in result:
                result.append(normalized)
    return result


def stock_css() -> str:
    source = STOCK_TEMPLATE.read_text(encoding="utf-8")
    match = re.search(r"<style>(.*?)</style>", source, flags=re.S | re.I)
    if not match:
        raise RuntimeError(f"个股模板缺少内嵌样式：{STOCK_TEMPLATE}")
    return match.group(1)


def document(kind: str, title: str, body: str) -> str:
    css = (stock_css() if kind == "stock" else INDUSTRY_CSS) + MOBILE_TABLE_CSS
    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
        f"<title>{esc(title)}</title><style>{css}</style></head>"
        f"<body>{body}</body></html>"
    )
