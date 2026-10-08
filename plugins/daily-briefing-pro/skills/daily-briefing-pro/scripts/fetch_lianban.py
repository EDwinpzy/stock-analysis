#!/usr/bin/env python3
"""盘面补充数据采集（温度卡「盘面补充」那一行 + 策略卡的主线/观察名单）。

两个数据源，各管一段，缺谁都能出：

1. 同花顺官方（hithink-finance CLI，主源）—— 可核对的盘面事实
   涨停/跌停/炸板家数、封板率、炸板率、最高板与次高板、连板家数、
   涨跌家数、两市成交、当日主线（按涨停原因归并）、总龙头。
   支持任意历史交易日回填。
2. 连板网 lianban.net（补充源）—— 官方接口没有的字段
   63 日新高新低、融资余额、主力资金流、AI 复盘文本、次日观察名单。
   Playwright 无头渲染，失败不影响同花顺那部分。

⛔ 温度只有一个来源：连板网自带的“情绪温度/情绪周期”是它自己的刻度，
既不参与计算、也不展示，本脚本不把它写进结果。

设 BRIEFING_LIANBAN_SUPPLEMENT=0 可只跑同花顺、完全跳过 Playwright。

用法: python fetch_lianban.py [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent

sys.path.insert(0, str(SCRIPT_DIR))
from runtime_paths import get_data_dir  # noqa: E402

DATA_DIR = get_data_dir(BASE_DIR)
import _hithink  # noqa: E402

CN = timezone(timedelta(hours=8))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
BASE_URL = "https://lianban.net"


def _int(text):
    try:
        return int(str(text).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _float(text):
    try:
        return float(str(text).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def parse_overview(text: str) -> dict:
    """从页面文本里解析概况区块；取不到就留空，不猜数。"""
    out = {}

    def grab(pattern, key, caster=_int, group=1):
        match = re.search(pattern, text)
        if match:
            value = caster(match.group(group))
            if value is not None:
                out[key] = value

    grab(r"涨停\s*\n?\s*([\d,]+)\s*\n?\s*昨\s*([\d,]+)", "limit_up")
    grab(r"涨停\s*\n?\s*([\d,]+)\s*\n?\s*昨\s*([\d,]+)", "limit_up_prev", group=2)
    grab(r"连板\s*\n?\s*([\d,]+)\s*\n?\s*昨\s*([\d,]+)", "consecutive")
    grab(r"连板\s*\n?\s*([\d,]+)\s*\n?\s*昨\s*([\d,]+)", "consecutive_prev", group=2)
    grab(r"最高板\s*\n?\s*(\d+)\s*板", "max_board")
    grab(r"最高板\s*\n?\s*\d+\s*板\s*\n?\s*昨\s*(\d+)\s*板", "max_board_prev")
    grab(r"跌停\s*\n?\s*([\d,]+)\s*\n?\s*昨\s*([\d,]+)", "limit_down")
    grab(r"跌停\s*\n?\s*([\d,]+)\s*\n?\s*昨\s*([\d,]+)", "limit_down_prev", group=2)
    grab(r"封板率\s*\n?\s*([\d.]+)\s*%", "seal_rate", _float)
    grab(r"封板率\s*\n?\s*[\d.]+\s*%\s*\n?\s*昨\s*([\d.]+)\s*%", "seal_rate_prev", _float)
    grab(r"炸板\s*\n?\s*([\d,]+)\s*\n?\s*率\s*([\d.]+)\s*%", "broken")
    grab(r"炸板\s*\n?\s*[\d,]+\s*\n?\s*率\s*([\d.]+)\s*%", "broken_rate", _float)
    grab(r"率\s*[\d.]+\s*%\s*·\s*昨\s*([\d.]+)\s*%", "broken_rate_prev", _float)
    grab(r"昨涨停今表现\s*\n?\s*([+\-\d.]+)\s*%", "yday_limitup_perf", _float)
    grab(r"中位\s*([+\-\d.]+)\s*%", "yday_limitup_median", _float)
    grab(r"翻红\s*(\d+)\s*%", "yday_red_ratio")
    match = re.search(r"情绪周期\s*\n?\s*(\S+?)\s*\n?\s*温度\s*([+\-\d.]+)", text)
    if match:
        out["phase"] = match.group(1)
        out["temperature"] = _float(match.group(2))
    grab(r"上涨/下跌\s*\n?\s*([\d,]+)/([\d,]+)", "advance")
    grab(r"上涨/下跌\s*\n?\s*[\d,]+/([\d,]+)", "decline")
    grab(r"红盘\s*(\d+)\s*%", "red_ratio")
    grab(r"新高/新低\s*\d+日\s*\n?\s*([\d,]+)/([\d,]+)", "new_high_63")
    grab(r"新高/新低\s*\d+日\s*\n?\s*[\d,]+/([\d,]+)", "new_low_63")
    match = re.search(r"两市成交\s*\n?\s*([\d.]+万亿|[\d.]+亿)", text)
    if match:
        out["market_turnover"] = match.group(1)
    match = re.search(
        r"融资余额\s*(\d\d-\d\d)\s*\n?\s*([\d.]+万亿|[\d.]+亿)\s*\n?\s*较前日\s*([+\-]?[\d.]+)\s*亿",
        text,
    )
    if match:
        out["margin_date"] = match.group(1)
        out["margin_balance"] = match.group(2)
        out["margin_change"] = _float(match.group(3))
    return out


def parse_leaders(text: str) -> dict:
    """解析「当日主线」区块：总龙头 + 各主线板块（涨停家数/龙头/驱动逻辑）。"""
    result = {"top_leader": "", "sectors": []}
    match = re.search(r"总龙头\s*(\S+?\d+天\d+板)", text)
    if match:
        result["top_leader"] = match.group(1)

    block = text
    start = block.find("当日主线")
    if start >= 0:
        end = block.find("主线强度", start)
        block = block[start:end if end > start else start + 1500]

    # 逐行解析比整体正则稳：形如
    #   风电 / 涨停6家 ▾ / 龙头 天顺风能4天2板 / 欧洲海风需求有望提升
    lines = [line.strip() for line in block.split("\n") if line.strip()]
    index = 0
    while index < len(lines):
        matched = re.match(r"^涨停\s*(\d+)\s*家", lines[index])
        if matched and index > 0:
            sector = lines[index - 1]
            cursor = index + 1
            leader, logic = "", ""
            if cursor < len(lines) and lines[cursor].startswith("龙头"):
                leader = lines[cursor][2:].strip()
                cursor += 1
            if cursor < len(lines):
                logic = lines[cursor]
            if not any(kw in sector for kw in ("涨停", "总龙头", "主线", "当日")):
                result["sectors"].append({
                    "sector": sector,
                    "limit_up_count": _int(matched.group(1)),
                    "leader": leader,
                    "logic": logic,
                })
            index = cursor + 1
            continue
        index += 1
    return result


async def collect_lianban(target_date: str) -> dict:
    from playwright.async_api import async_playwright

    result = {
        "date": target_date,
        "source": "连板网 lianban.net",
        "status": "empty",
        "overview": {},
        "top_leader": "",
        "main_sectors": [],
        "fund_flow": {},
        "ai_review": "",
        "watch_next": [],
        "signals": [],
        "node_pool": [],
        "note": "",
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=UA)
        page = await context.new_page()
        try:
            await page.goto(f"{BASE_URL}/days/{target_date}.html", wait_until="load", timeout=60000)
            await page.wait_for_timeout(6000)
            text = await page.evaluate("() => document.body.innerText")
        except Exception as exc:
            result["status"] = "error"
            result["note"] = f"连板网页面打开失败：{type(exc).__name__} {exc}"
            await browser.close()
            return result

        if target_date not in text:
            result["status"] = "error"
            result["note"] = f"连板网页面未包含 {target_date} 的复盘数据"
            await browser.close()
            return result

        result["overview"] = parse_overview(text)
        leaders = parse_leaders(text)
        result["top_leader"] = leaders["top_leader"]
        result["main_sectors"] = leaders["sectors"]
        # 信号灯只取“跌势延续/科创超跌”这类盘面信号，排除“🟢 在线 170”这类状态条
        raw_signals = re.findall(
            r"[\U0001F534\U0001F535\u2744\u26a0\U0001F7E1\U0001F7E2]\ufe0f?\s*([^\n]{2,16})", text
        )
        result["signals"] = [
            s.strip().strip("️") for s in raw_signals
            if not re.search(r"在线|登录|收藏|摸鱼", s)
        ][:6]

        try:
            response = await page.request.get(
                f"{BASE_URL}/live/zjflow.json",
                headers={"Referer": f"{BASE_URL}/days/{target_date}.html"},
            )
            flow = json.loads(await response.text())
            result["fund_flow"] = {
                "time": flow.get("t", ""),
                "industry_in": (flow.get("ind_in") or [])[:8],
                "industry_out": (flow.get("ind_out") or [])[:8],
                "concept_in": (flow.get("cpt_in") or [])[:8],
                "concept_out": (flow.get("cpt_out") or [])[:8],
                "stock_in": (flow.get("stk_in") or [])[:8],
                "stock_out": (flow.get("stk_out") or [])[:8],
            }
        except Exception as exc:
            print(f"  [WARN] 连板网资金流获取失败: {exc}", file=sys.stderr)

        try:
            response = await page.request.get(
                f"{BASE_URL}/summary/{target_date}.json",
                headers={"Referer": f"{BASE_URL}/days/{target_date}.html"},
            )
            summary = json.loads(await response.text())
            result["ai_review"] = str(summary.get("text") or "")
            result["watch_next"] = [
                {"name": w.get("n", ""), "code": w.get("c", ""), "why": w.get("why", "")}
                for w in (summary.get("watch") or []) if isinstance(w, dict)
            ]
        except Exception as exc:
            print(f"  [WARN] 连板网AI复盘获取失败: {exc}", file=sys.stderr)

        await browser.close()

    if result["overview"] or result["main_sectors"]:
        result["status"] = "ok"
        result["note"] = "连板网公开概况与主线数据；其情绪温度为自有刻度，仅作对照"
    else:
        result["note"] = "连板网页面未解析到概况数据"
    return result


def _sectors_from_pool(pool: list[dict], limit: int = 6) -> list[dict]:
    """按涨停原因归并主线：首个原因标签作为板块，组内最高连板作为龙头。"""
    buckets: dict[str, dict] = {}
    for row in pool:
        reason = str(row.get("limit_up_reason") or "").strip()
        if not reason:
            continue
        key = reason.split("+")[0].strip() or reason
        bucket = buckets.setdefault(key, {"count": 0, "leader": "", "leader_n": 0, "logic": reason})
        bucket["count"] += 1
        board = int(row.get("continue_day_cnt") or 1)
        if board > bucket["leader_n"]:
            name = str(row.get("name") or "")
            bucket["leader_n"] = board
            bucket["leader"] = f"{name}{board}天{board}板" if board > 1 else name
    ordered = sorted(buckets.items(), key=lambda kv: kv[1]["count"], reverse=True)
    return [
        {"sector": name, "limit_up_count": value["count"],
         "leader": value["leader"], "logic": value["logic"]}
        for name, value in ordered[:limit]
    ]


def _top_leader(pool: list[dict]) -> str:
    """最高连板个股，格式与连板网一致：名称N天N板。"""
    best_name, best_board = "", 0
    for row in pool:
        board = int(row.get("continue_day_cnt") or 1)
        if board >= 2 and board > best_board:
            best_name, best_board = str(row.get("name") or ""), board
    return f"{best_name}{best_board}天{best_board}板" if best_board else ""


def _node_pool(pool: list[dict], limit: int = 80) -> list[dict]:
    """保留可供节点模型滚动计算的关键连板快照，不把普通首板写入历史。"""
    rows = []
    for row in pool:
        board = int(row.get("continue_day_cnt") or 1)
        if board < 3:
            continue
        rows.append({
            "name": str(row.get("name") or "").strip(),
            "code": str(row.get("code") or row.get("ts_code") or "").strip(),
            "board": board,
            "theme": str(row.get("limit_up_reason") or "").strip(),
            "status": "limit_up",
            "source": "同花顺官方金融数据（hithink-finance）",
        })
    return rows[:limit]


def collect_hithink(target_date: str) -> dict:
    """同花顺官方路径：可核对的盘面事实。"""
    days = _hithink.trade_dates()
    usable = [d for d in days if d <= target_date]
    if not usable:
        raise _hithink.HithinkError(f"{target_date} 之前没有可用的交易日")
    trade_date = usable[-1]
    prev_date = _hithink.previous_trade_date(trade_date, days)
    print(f"盘面补充(同花顺官方): 请求 {target_date} → 交易日 {trade_date}", file=sys.stderr)

    today = _hithink.pool_overview(trade_date)
    yesterday = _hithink.pool_overview(prev_date) if prev_date else {}
    pool = today.get("limit_up_pool") or []

    overview = {
        "limit_up": today["limit_up"],
        "limit_up_prev": yesterday.get("limit_up"),
        "consecutive": today["consecutive"],
        "consecutive_prev": yesterday.get("consecutive"),
        "max_board": today["max_board"],
        "max_board_prev": yesterday.get("max_board"),
        "next_board": today["next_board"],
        "limit_down": today["limit_down"],
        "limit_down_prev": yesterday.get("limit_down"),
        "seal_rate": today["seal_rate"],
        "seal_rate_prev": yesterday.get("seal_rate"),
        "broken": today["broken"],
        "broken_rate": today["broken_rate"],
        "broken_rate_prev": yesterday.get("broken_rate"),
    }

    # 涨跌家数与两市成交：只有最近交易日有实时口径
    if trade_date == _hithink.latest_trade_date(days):
        breadth = _hithink.market_breadth()
        if breadth and breadth.get("tradable"):
            overview["advance"] = breadth["advance"]
            overview["decline"] = breadth["decline"]
            overview["red_ratio"] = round(breadth["advance"] / breadth["tradable"] * 100)
        sh = _hithink.index_turnover(_hithink.SH_INDEX, trade_date)
        sz = _hithink.index_turnover(_hithink.SZ_INDEX, trade_date)
        if sh and sz:
            overview["market_turnover"] = _hithink.format_turnover_yi(sh + sz)

    return {
        "date": trade_date,
        "requested_date": target_date,
        "source": "同花顺官方金融数据（hithink-finance）",
        "status": "ok" if today["limit_up"] else "empty",
        "overview": overview,
        "top_leader": _top_leader(pool),
        "main_sectors": _sectors_from_pool(pool),
        "fund_flow": {},
        "ai_review": "",
        "watch_next": [],
        "signals": [],
        "node_pool": _node_pool(pool),
        "note": f"同花顺官方盘面事实，{trade_date}；连板家数与最高板取严格连续板",
    }


def merge_sources(hithink: dict, lianban: dict) -> dict:
    """同花顺管事实，连板网补它独有的字段。两边都没有的键保持缺失，不猜数。"""
    result = dict(hithink)
    # 概况：先用连板网垫底（它独有新高新低/融资余额），再用同花顺的非空事实覆盖
    merged = dict(lianban.get("overview") or {})
    for key, value in (hithink.get("overview") or {}).items():
        if value is not None:
            merged[key] = value
    # 连板网自带的情绪刻度不进入结果，避免与模型算出的 S 并列
    merged.pop("phase", None)
    merged.pop("temperature", None)
    result["overview"] = merged

    if not result.get("top_leader"):
        result["top_leader"] = lianban.get("top_leader") or ""
    if not result.get("main_sectors"):
        result["main_sectors"] = lianban.get("main_sectors") or []
    for key in ("fund_flow", "ai_review", "watch_next", "signals"):
        if not result.get(key) and lianban.get(key):
            result[key] = lianban[key]

    result["source"] = "同花顺官方金融数据（hithink-finance）+ 连板网 lianban.net 补充"
    result["status"] = "ok"
    result["note"] = (
        f"盘面事实取同花顺官方（{hithink.get('date')}）；"
        "新高新低、融资余额、资金流与次日观察取连板网；连板网情绪温度不采用"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(CN).strftime("%Y-%m-%d"))
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    hithink_result = None
    if _hithink.available():
        try:
            hithink_result = collect_hithink(args.date)
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARN] 同花顺盘面补充失败：{type(exc).__name__} {exc}", file=sys.stderr)
    else:
        print("  [WARN] 未检测到 hithink-finance CLI，盘面补充只有连板网", file=sys.stderr)

    target = str(hithink_result.get("date") if hithink_result else args.date)
    lianban_result = None
    if os.environ.get("BRIEFING_LIANBAN_SUPPLEMENT", "1") != "0":
        try:
            lianban_result = asyncio.run(collect_lianban(target))
            if lianban_result.get("status") != "ok":
                print(f"  [WARN] 连板网补充未取到数据：{lianban_result.get('note')}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARN] 连板网补充失败：{type(exc).__name__} {exc}", file=sys.stderr)

    if hithink_result and lianban_result and lianban_result.get("status") == "ok":
        result = merge_sources(hithink_result, lianban_result)
    elif hithink_result:
        result = hithink_result
        result["note"] = f"{result['note']}；连板网补充不可用，新高新低/融资余额/次日观察留空"
    elif lianban_result:
        result = lianban_result
    else:
        result = {
            "date": args.date, "source": "不可用", "status": "error",
            "overview": {}, "top_leader": "", "main_sectors": [],
            "fund_flow": {}, "ai_review": "", "watch_next": [], "signals": [],
            "note": "同花顺与连板网都没有取到数据，未使用旧缓存",
        }

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
