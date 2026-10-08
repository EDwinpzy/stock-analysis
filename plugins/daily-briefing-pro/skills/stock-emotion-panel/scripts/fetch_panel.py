#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""同花顺官方金融数据 -> A股超短情绪温度模型 v3.2 日频面板行。

数据源：hithink-finance CLI（同花顺官方 A 股金融数据服务），需先 `hithink-finance auth login`。

用法：
  python fetch_panel.py --date 2026-09-14
  python fetch_panel.py --date 2026-09-14 --format csv
  python fetch_panel.py --date 2026-09-14 --append D:\\MyProjects\\股票分析\\data\\panel_history.csv
  python fetch_panel.py --date 2026-09-14 --lite      # 跳过全市场快照与逐股历史（快，缺 4 个字段）

字段口径见 ../references/panel-fields.md。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8))

# 与 panel_history.csv / market_temperature_v32.py 完全一致的列序
PANEL_COLUMNS = [
    "date", "sh_close", "sh_ma250", "tradable_count", "advance_count", "turnover",
    "limit_up", "limit_down", "first_board", "consecutive", "space", "next_space",
    "bomb_rate", "yday_limitup_ret", "yday_lianban_ret", "p12", "p23", "p3p",
    "board2", "board3", "board4p",
]

SH_INDEX = "000001.SH"
POOL_PAGE_SIZE = 200
MIN_DENOM = 3  # 晋级率分母下限，与 market_temperature_v32.with_promotion_rates 一致


class CliError(RuntimeError):
    pass


def cli_path() -> str:
    found = shutil.which("hithink-finance")
    if not found:
        raise CliError(
            "找不到 hithink-finance CLI。先安装：\n"
            "  npm install -g @hithink-tech/hithink-finance-cli\n"
            "然后配置 API Key：\n"
            "  hithink-finance auth login"
        )
    return found


def run_cli(*args: str, timeout: int = 240) -> dict:
    """调用 CLI 并返回 --format json 信封中的 data 段。"""
    cmd = [cli_path(), *args, "--format", "json", "--no-color"]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
    )
    raw = (proc.stdout or "").strip()
    if not raw:
        raise CliError(f"{' '.join(args)} 无输出；stderr: {(proc.stderr or '').strip()[:300]}")
    try:
        payload = json.loads(raw.splitlines()[-1])
    except json.JSONDecodeError as exc:
        raise CliError(f"{' '.join(args)} 返回非 JSON：{raw[:300]}") from exc
    if not payload.get("ok"):
        err = payload.get("error") or {}
        raise CliError(
            f"{' '.join(args)} 失败：{err.get('code')} {err.get('message')}"
            + (f"（{err.get('hint')}）" if err.get("hint") else "")
        )
    return payload.get("data") or {}


def date_ms(date_str: str) -> int:
    """交易日的 Asia/Shanghai 零点毫秒时间戳。"""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=TZ)
    return int(dt.timestamp() * 1000)


def end_of_day_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=TZ) + timedelta(hours=23, minutes=59, seconds=59)
    return int(dt.timestamp() * 1000)


def trading_days() -> list[str]:
    items = run_cli("market", "calendar").get("item") or []
    days = []
    for row in items:
        raw = str(row.get("date") or "")
        if len(raw) == 8 and raw.isdigit():
            days.append(f"{raw[:4]}-{raw[4:6]}-{raw[6:]}")
    return sorted(days)


def resolve_trade_date(date_str: str | None, days: list[str]) -> str:
    """未指定日期时取 <= 今天的最后一个交易日。"""
    if date_str:
        if date_str not in days:
            raise CliError(f"{date_str} 不在交易日历中（当前日历覆盖 {days[0]} ~ {days[-1]}）")
        return date_str
    return latest_trade_date(days)


def latest_trade_date(days: list[str]) -> str:
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    past = [d for d in days if d <= today]
    if not past:
        raise CliError("交易日历中没有已过去的交易日")
    return past[-1]


def previous_trade_date(date_str: str, days: list[str]) -> str:
    earlier = [d for d in days if d < date_str]
    if not earlier:
        raise CliError(f"{date_str} 之前没有可用的交易日（日历覆盖 {days[0]} 起）")
    return earlier[-1]


def fetch_pool(kind: str, trade_date: str) -> list[dict]:
    """分页拉取涨停/跌停/炸板池。"""
    ms = date_ms(trade_date)
    items: list[dict] = []
    page = 1
    while True:
        data = run_cli("special", kind, "--date-ms", str(ms), "--page", str(page), "--size", str(POOL_PAGE_SIZE))
        batch = data.get("item") or []
        items.extend(batch)
        if len(batch) < POOL_PAGE_SIZE:
            return items
        page += 1
        if page > 30:
            return items


def index_history(start_ms: int, end_ms: int) -> list[dict]:
    data = run_cli("index", "history", "--thscode", SH_INDEX, "--start-ms", str(start_ms), "--end-ms", str(end_ms))
    return data.get("item") or []


def sh_index_metrics(trade_date: str) -> tuple[float, float | None, float | None]:
    """返回 (上证收盘, 上证MA250, 上证成交额)。"""
    ms = date_ms(trade_date)
    window = index_history(ms - 400 * 86400000, end_of_day_ms(trade_date))
    closes = [float(r["close_price"]) for r in window if r.get("close_price") is not None]
    if not closes:
        raise CliError(f"{trade_date} 未取到上证指数历史数据")
    close = closes[-1]
    ma250 = sum(closes[-250:]) / 250 if len(closes) >= 250 else None
    turnover = window[-1].get("turnover")
    return close, ma250, (float(turnover) if turnover is not None else None)


def market_breadth() -> tuple[int | None, int | None]:
    """全市场实时快照 -> (可交易家数, 上涨家数)。仅最近交易日可用。

    快照覆盖沪市 + 深市 + 北交所，含停牌股；停牌股 volume/last_price 为 0，
    必须剔除才能与面板既有的 tradable_count 口径对齐（实测 5573 - 23 = 5550）。
    """
    items: list[dict] = []
    offset = 0
    while True:
        data = run_cli("market", "snapshot", "--limit", "5000", "--offset", str(offset), timeout=300)
        batch = data.get("item") or []
        items.extend(batch)
        total = data.get("total") or 0
        if not batch or len(items) >= total or offset > 20000:
            break
        offset += len(batch)
    if not items:
        return None, None
    active = [row for row in items if (row.get("last_price") or 0) > 0]
    advance = sum(1 for row in active if (row.get("price_change") or 0) > 0)
    return len(active), advance


def board_counts(pool: list[dict]) -> dict:
    """按严格连续板高度分桶。continue_day_cnt 直接来自同花顺涨停池。"""
    counts = {"first_board": 0, "board2": 0, "board3": 0, "board4p": 0}
    levels: set[int] = set()
    for row in pool:
        n = int(row.get("continue_day_cnt") or 1)
        if n <= 1:
            counts["first_board"] += 1
            continue
        levels.add(n)
        if n == 2:
            counts["board2"] += 1
        elif n == 3:
            counts["board3"] += 1
        else:
            counts["board4p"] += 1
    ordered = sorted(levels, reverse=True)
    counts["consecutive"] = sum(1 for row in pool if int(row.get("continue_day_cnt") or 1) >= 2)
    counts["space"] = float(ordered[0]) if ordered else 0.0
    counts["next_space"] = float(ordered[1]) if len(ordered) > 1 else 0.0
    return counts


def yday_feedback(prev_pool: list[dict], prev_date: str, trade_date: str, max_codes: int) -> tuple[float | None, float | None]:
    """昨日涨停/连板股今日涨跌幅均值（百分点）。逐股取区间日线后计算。"""
    codes = [row.get("thscode") for row in prev_pool if row.get("thscode")]
    if not codes or len(codes) > max_codes:
        return None, None
    start = date_ms(prev_date)
    end = end_of_day_ms(trade_date)
    all_ret: list[float] = []
    lb_ret: list[float] = []
    for row in prev_pool:
        code = row.get("thscode")
        if not code:
            continue
        try:
            bars = run_cli("market", "history", "--thscode", code, "--start-ms", str(start), "--end-ms", str(end)).get("item") or []
        except CliError:
            continue
        closes = [float(b["close_price"]) for b in bars if b.get("close_price")]
        if len(closes) < 2 or closes[-2] == 0:
            continue
        ret = (closes[-1] / closes[-2] - 1.0) * 100.0
        all_ret.append(ret)
        if int(row.get("continue_day_cnt") or 1) >= 2:
            lb_ret.append(ret)
    def mean(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 4) if xs else None
    return mean(all_ret), mean(lb_ret)


def promotion_rates(today: dict, prev: dict) -> tuple[float | None, float | None, float | None]:
    p12 = today["board2"] / prev["first_board"] if prev["first_board"] >= MIN_DENOM else None
    p23 = today["board3"] / prev["board2"] if prev["board2"] >= MIN_DENOM else None
    denom = prev["board3"] + prev["board4p"]
    p3p = today["board4p"] / denom if denom >= MIN_DENOM else None
    return (
        p12,
        p23,
        p3p,
    )


def build_row(
    trade_date: str, days: list[str], lite: bool, max_codes: int, allow_breadth: bool
) -> tuple[dict, list[str]]:
    notes: list[str] = []
    prev_date = previous_trade_date(trade_date, days)

    close, ma250, turnover = sh_index_metrics(trade_date)
    today_pool = fetch_pool("limit-up-pool", trade_date)
    if not today_pool:
        raise CliError(f"{trade_date} 涨停池为空，可能不是交易日或数据未生成")
    down_pool = fetch_pool("limit-down-pool", trade_date)
    break_pool = fetch_pool("limit-break-pool", trade_date)
    prev_pool = fetch_pool("limit-up-pool", prev_date)

    today = board_counts(today_pool)
    prev = board_counts(prev_pool)
    limit_up = len(today_pool)
    broken = len(break_pool)
    p12, p23, p3p = promotion_rates(today, prev)

    tradable = advance = None
    yday_lu = yday_lb = None
    if lite:
        notes.append("--lite：跳过全市场快照与逐股历史，tradable_count/advance_count/yday_limitup_ret/yday_lianban_ret 留空")
    else:
        if allow_breadth:
            tradable, advance = market_breadth()
            if tradable is None:
                notes.append("全市场快照为空，tradable_count/advance_count 留空")
            else:
                notes.append(
                    "tradable_count/advance_count 来自实时全市场快照（沪+深+北交所，已剔除停牌）；"
                    "该字段只有最近交易日口径，历史行需另行补齐"
                )
        else:
            notes.append(
                f"{trade_date} 是历史交易日：全市场快照只有实时口径，tradable_count/advance_count 留空，"
                "需要时用 market-dumps 全市场日线或本地库补齐"
            )
        yday_lu, yday_lb = yday_feedback(prev_pool, prev_date, trade_date, max_codes)
        if yday_lu is None:
            notes.append(f"昨涨停今表现未计算（上一交易日 {prev_date} 涨停池 {len(prev_pool)} 只，超出 --max-yday-codes={max_codes} 或取数失败）")

    row = {
        "date": trade_date,
        "sh_close": round(close, 2),
        "sh_ma250": round(ma250, 6) if ma250 is not None else None,
        "tradable_count": tradable,
        "advance_count": advance,
        "turnover": turnover,
        "limit_up": limit_up,
        "limit_down": len(down_pool),
        "first_board": today["first_board"],
        "consecutive": today["consecutive"],
        "space": today["space"],
        "next_space": today["next_space"],
        "bomb_rate": round(broken / (limit_up + broken), 4) if (limit_up + broken) else 0.0,
        "yday_limitup_ret": yday_lu,
        "yday_lianban_ret": yday_lb,
        "p12": p12,
        "p23": p23,
        "p3p": p3p,
        "board2": today["board2"],
        "board3": today["board3"],
        "board4p": today["board4p"],
    }
    return row, notes


def to_csv_line(row: dict) -> str:
    cells = []
    for col in PANEL_COLUMNS:
        value = row.get(col)
        cells.append("" if value is None else str(value))
    return ",".join(cells)


def append_row(path: str, row: dict) -> str:
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        raise CliError(f"目标面板不存在：{p}")
    text = p.read_text(encoding="utf-8")
    lines = text.rstrip("\n").split("\n")
    header = lines[0].strip().split(",")
    if header != PANEL_COLUMNS:
        raise CliError(f"表头与模型列序不一致：\n面板: {header}\n期望: {PANEL_COLUMNS}")
    target_date = row["date"]
    body = [ln for ln in lines[1:] if ln.strip() and not ln.strip().startswith(f"{target_date},")]
    body.append(to_csv_line(row))
    body.sort(key=lambda ln: ln.split(",", 1)[0])
    p.write_text("\n".join([lines[0], *body]) + "\n", encoding="utf-8")
    return str(p)


def main() -> int:
    parser = argparse.ArgumentParser(description="同花顺官方数据 -> 情绪温度模型 v3.2 面板行")
    parser.add_argument("--date", help="交易日 YYYY-MM-DD，默认最近一个交易日")
    parser.add_argument("--format", choices=["json", "csv"], default="json")
    parser.add_argument("--append", help="把该行写入指定 panel_history.csv（按日期去重后重排）")
    parser.add_argument("--preview", action="store_true", help="与 --append 连用时不落盘，只打印结果")
    parser.add_argument("--lite", action="store_true", help="跳过全市场快照与逐股历史")
    parser.add_argument("--max-yday-codes", type=int, default=300, help="逐股计算昨涨停反馈的股票上限")
    args = parser.parse_args()

    try:
        days = trading_days()
        trade_date = resolve_trade_date(args.date, days)
        allow_breadth = trade_date == latest_trade_date(days)
        row, notes = build_row(trade_date, days, args.lite, args.max_yday_codes, allow_breadth)
    except CliError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2

    if args.format == "csv":
        print(",".join(PANEL_COLUMNS))
        print(to_csv_line(row))
    else:
        print(json.dumps(row, ensure_ascii=False, indent=2))
    for note in notes:
        print(f"[提示] {note}", file=sys.stderr)

    if args.append:
        try:
            if args.preview:
                print(f"[预览] 未写入 {args.append}", file=sys.stderr)
            else:
                print(f"[写入] {append_row(args.append, row)}", file=sys.stderr)
        except CliError as exc:
            print(f"[错误] {exc}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
