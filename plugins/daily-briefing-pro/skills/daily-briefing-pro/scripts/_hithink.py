#!/usr/bin/env python3
"""同花顺官方金融数据服务（hithink-finance CLI）轻量封装。

每日简报的取数脚本统一走这里，避免各自拼命令行参数。
API Key 由 CLI 自己从系统凭据库读取，本模块不接触、不落盘 Key。

约定：CLI 缺失、未登录、被限流、返回非 JSON 一律抛 HithinkError，
调用方负责决定是降级到旧数据源还是如实报错，不要在这里吞异常。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

from network_config import is_cloud_runtime

CN = timezone(timedelta(hours=8))
SH_INDEX = "000001.SH"
SZ_INDEX = "399001.SZ"
POOL_PAGE_SIZE = 200


class HithinkError(RuntimeError):
    pass


def cli_path() -> str | None:
    return shutil.which("hithink-finance")


def available() -> bool:
    return cli_path() is not None


def call(*args: str, timeout: int = 120) -> dict:
    """执行 CLI 并返回信封中的 data 段。"""
    exe = cli_path()
    if not exe:
        raise HithinkError("未安装 hithink-finance CLI")
    cmd = [exe, *args, "--format", "json", "--no-color"]
    child_env = None
    if is_cloud_runtime():
        child_env = os.environ.copy()
        child_env.setdefault("NODE_USE_ENV_PROXY", "1")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=child_env,
        )
    except subprocess.TimeoutExpired as exc:
        raise HithinkError(f"命令超时：{' '.join(args)}") from exc
    raw = (proc.stdout or "").strip()
    if not raw:
        raise HithinkError(f"命令无输出：{' '.join(args)}；stderr={(proc.stderr or '').strip()[:200]}")
    try:
        payload = json.loads(raw.splitlines()[-1])
    except json.JSONDecodeError as exc:
        raise HithinkError(f"返回非 JSON：{raw[:200]}") from exc
    if not payload.get("ok"):
        err = payload.get("error") or {}
        raise HithinkError(f"{err.get('code')} {err.get('message')}")
    return payload.get("data") or {}


def date_ms(date_str: str) -> int:
    return int(datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=CN).timestamp() * 1000)


def end_of_day_ms(date_str: str) -> int:
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=CN) + timedelta(hours=23, minutes=59, seconds=59)
    return int(dt.timestamp() * 1000)


def today() -> str:
    return datetime.now(CN).strftime("%Y-%m-%d")


def trade_dates() -> list[str]:
    items = call("market", "calendar").get("item") or []
    days = []
    for row in items:
        raw = str(row.get("date") or "")
        if len(raw) == 8 and raw.isdigit():
            days.append(f"{raw[:4]}-{raw[4:6]}-{raw[6:]}")
    return sorted(days)


def latest_trade_date(days: list[str] | None = None) -> str | None:
    days = days or trade_dates()
    past = [d for d in days if d <= today()]
    return past[-1] if past else None


def previous_trade_date(date_str: str, days: list[str] | None = None) -> str | None:
    days = days or trade_dates()
    earlier = [d for d in days if d < date_str]
    return earlier[-1] if earlier else None


def fetch_pool(kind: str, date_str: str, page_size: int = POOL_PAGE_SIZE) -> list[dict]:
    """分页拉取涨停/跌停/炸板池。kind 取 limit-up-pool / limit-down-pool / limit-break-pool。"""
    ms = date_ms(date_str)
    items: list[dict] = []
    page = 1
    while page <= 30:
        data = call("special", kind, "--date-ms", str(ms), "--page", str(page), "--size", str(page_size))
        batch = data.get("item") or []
        items.extend(batch)
        if len(batch) < page_size:
            break
        page += 1
    return items


def ladder_stats(pool: list[dict]) -> dict:
    """涨停池 -> 首板/二板/三板/四板以上家数与最高板、次高板。"""
    first_board = board2 = board3 = board4p = 0
    levels: set[int] = set()
    for row in pool:
        n = int(row.get("continue_day_cnt") or 1)
        if n <= 1:
            first_board += 1
            continue
        levels.add(n)
        if n == 2:
            board2 += 1
        elif n == 3:
            board3 += 1
        else:
            board4p += 1
    ordered = sorted(levels, reverse=True)
    consecutive = board2 + board3 + board4p
    return {
        "first_board": first_board,
        "board2": board2,
        "board3": board3,
        "board4p": board4p,
        "consecutive": consecutive,
        "max_board": ordered[0] if ordered else 0,
        "next_board": ordered[1] if len(ordered) > 1 else 0,
    }


def pool_overview(date_str: str) -> dict:
    """一个交易日的盘面事实：涨停/跌停/炸板家数、封板率、炸板率、连板梯队。"""
    limit_up_pool = fetch_pool("limit-up-pool", date_str)
    down_pool = fetch_pool("limit-down-pool", date_str)
    break_pool = fetch_pool("limit-break-pool", date_str)
    stats = ladder_stats(limit_up_pool)
    limit_up = len(limit_up_pool)
    broken = len(break_pool)
    total = limit_up + broken
    return {
        "date": date_str,
        "limit_up": limit_up,
        "limit_down": len(down_pool),
        "broken": broken,
        "seal_rate": round(limit_up / total * 100, 2) if total else None,
        "broken_rate": round(broken / total * 100, 2) if total else None,
        "limit_up_pool": limit_up_pool,
        **stats,
    }


def index_turnover(thscode: str, date_str: str) -> float | None:
    data = call(
        "index", "history", "--thscode", thscode,
        "--start-ms", str(date_ms(date_str)), "--end-ms", str(end_of_day_ms(date_str)),
    )
    items = data.get("item") or []
    if not items:
        return None
    value = items[-1].get("turnover")
    return float(value) if value is not None else None


def market_breadth() -> dict | None:
    """全市场实时快照 -> {tradable, advance, decline, flat}。

    快照覆盖沪市 + 深市 + 北交所并含停牌股（停牌 volume/last_price 为 0），
    必须按 last_price > 0 剔除，否则家数口径会与既有面板对不上。
    该口径只有最近交易日可用，历史日期返回 None。
    """
    items: list[dict] = []
    offset = 0
    while offset <= 20000:
        data = call("market", "snapshot", "--limit", "5000", "--offset", str(offset), timeout=300)
        batch = data.get("item") or []
        items.extend(batch)
        total = data.get("total") or 0
        if not batch or len(items) >= total:
            break
        offset += len(batch)
    if not items:
        return None
    active = [row for row in items if (row.get("last_price") or 0) > 0]
    advance = sum(1 for row in active if (row.get("price_change") or 0) > 0)
    decline = sum(1 for row in active if (row.get("price_change") or 0) < 0)
    return {
        "tradable": len(active),
        "advance": advance,
        "decline": decline,
        "flat": len(active) - advance - decline,
    }


def format_turnover_yi(total: float | None) -> str:
    """成交额格式化成「X.XX万亿」/「XXXX亿」，与连板网展示口径一致。"""
    if not total:
        return ""
    if total >= 1e12:
        return f"{total / 1e12:.2f}万亿"
    return f"{total / 1e8:.0f}亿"
