#!/usr/bin/env python3
"""断板后周期是否仍在延续（是否走出二波新高）——用日线收盘价核验。

节点模型把「最后一个连板日」记为 `break_date`。但断板不等于周期结束：
只要它随后还能**创新高（二波新高）**，就说明本轮周期仍在继续，只是中间
没有连板。本模块按统一口径把这段「没人头但周期没结束」的区间标出来，
供时间轴用虚线绘制。

判定规则（可复现，不依赖人工判断）：
- 参考高点 = 连板运行区间 [launch, break] 内的最高收盘价（前复权）；
- 断板后收盘价首次 > 参考高点的那天记为「二波新高日」；到窗口末都没出现，
  视为断板即结束，**不画虚线**（横盘不跌不等于周期还在走）；
- 虚线区间 = 断板次日起，到二波重新收盘跌回参考高点之下为止；窗口末仍未
  跌回则视为二波仍在延续，虚线延伸到最新交易日。

价格取不到时把 `cycle_status` 记为 unknown，时间轴只画实心段，不用猜测补虚线。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from runtime_paths import get_data_dir

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = get_data_dir(SCRIPT_DIR.parent)
CODE_CACHE_PATH = DATA_DIR / "stock_code_cache.json"
DAILY_CACHE_PATH = DATA_DIR / "stock_daily_cache.json"

_CALL_INTERVAL = 0.4
_last_call_at = 0.0
_FETCHED_THIS_RUN: set[str] = set()


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _throttle() -> None:
    global _last_call_at
    wait = _CALL_INTERVAL - (time.time() - _last_call_at)
    if wait > 0:
        time.sleep(wait)
    _last_call_at = time.time()


def resolve_code(name: str, cache: dict) -> str:
    """股票名称 -> 6 位代码，结果落盘缓存避免每次重复消歧。"""
    if cache.get(name):
        return str(cache[name])
    exe = shutil.which("hithink-finance")
    if not exe:
        return ""
    try:
        proc = subprocess.run(
            [exe, "--format", "json", "symbol", "search", "--q", name],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        payload = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except Exception:
        return ""
    items = (payload.get("data") or {}).get("item") or []
    picked = next((item for item in items if item.get("name") == name), None)
    if not picked or picked.get("asset_type") != "a-share":
        return ""
    code = str(picked.get("thscode") or "").split(".")[0]
    if code:
        cache[name] = code
    return code


def _market_prefix(code: str) -> str:
    """6 位代码 -> 交易所前缀，供新浪/腾讯行情源使用。"""
    if code.startswith(("60", "68", "90", "11", "50", "51", "58")):
        return "sh"
    if code.startswith(("00", "30", "20", "12", "15", "16")):
        return "sz"
    if code.startswith(("4", "8", "92")):
        return "bj"
    return "sh"


def _rows(frame, date_col: str, close_col: str) -> list[list]:
    if frame is None or frame.empty:
        return []
    return [[str(r[date_col]), float(r[close_col])] for _, r in frame.iterrows()]


def _fetch_one(ak, source: str, code: str, prefix: str, start: str, end: str) -> list[list]:
    """按数据源取一次日线；异常一律当作取不到，交给上层换源或重试。"""
    try:
        if source == "eastmoney":
            frame = ak.stock_zh_a_hist(symbol=code, period="daily",
                                       start_date=start, end_date=end, adjust="qfq")
            return _rows(frame, "日期", "收盘")
        if source == "sina":
            frame = ak.stock_zh_a_daily(symbol=f"{prefix}{code}",
                                        start_date=start, end_date=end, adjust="qfq")
            return _rows(frame, "date", "close")
        frame = ak.stock_zh_a_hist_tx(symbol=f"{prefix}{code}",
                                      start_date=start, end_date=end, adjust="qfq")
        return _rows(frame, "date", "close")
    except Exception:
        return []


def fetch_daily(code: str, start_date: str, end_date: str, cache: dict, run_date: str) -> list[list]:
    """返回 [[日期, 收盘价], ...]。东方财富为主，新浪/腾讯兜底，带磁盘缓存。

    东方财富接口在批量请求下经常 RemoteDisconnected，而新浪/腾讯的日线会
    滞后一天，所以不能"先成功先用"：这里按**覆盖到最新交易日**择优，
    只有主源彻底失败时才退回覆盖次好的备用源，并把 complete 标记落盘，
    当天后续运行可以继续补抓而不是复用半截数据。
    """
    entry = cache.get(code) or {}
    if (
        entry.get("fetched_at") == run_date
        and entry.get("rows")
        and (entry.get("complete") or code in _FETCHED_THIS_RUN)
    ):
        return entry["rows"]
    try:
        import akshare as ak
    except ImportError:
        return entry.get("rows") or []
    start = start_date.replace("-", "")
    end = end_date.replace("-", "")
    prefix = _market_prefix(code)
    best_rows: list[list] = entry.get("rows") if entry.get("fetched_at") == run_date else []
    best_source = str(entry.get("source") or "")
    done = False
    for round_no in range(3):
        for name in ("eastmoney", "sina", "tencent"):
            if name != "eastmoney" and prefix == "bj":
                continue
            _throttle()
            got = _fetch_one(ak, name, code, prefix, start, end)
            if got and (not best_rows or got[-1][0] > best_rows[-1][0]):
                best_rows, best_source = got, name
            if got and got[-1][0] >= end_date:
                done = True
                break
        if done:
            break
        # A suspended/delisted stock will never reach the window end.  One
        # complete pass over the three sources is enough; retrying only burns
        # the cloud runner's limited time budget.
        if best_rows:
            break
        time.sleep(1.5 * (round_no + 1))
    if best_rows:
        cache[code] = {
            "fetched_at": run_date,
            "rows": best_rows,
            "source": best_source,
            "complete": best_rows[-1][0] >= end_date,
        }
        _FETCHED_THIS_RUN.add(code)
    return best_rows


def _span_to(node: dict, end_index) -> int | None:
    """按交易日计数：从节点启动日到 end_index（含）的周期跨度。"""
    start_index = node.get("start_index")
    if not isinstance(start_index, int) or not isinstance(end_index, int):
        return None
    return end_index - start_index + 1


def attach_cycle_life(nodes: list[dict], axis_dates: list[str], end_date: str) -> dict:
    """就地写入 cycle_status / cycle_end_date / cycle_end_index / a_date，并返回统计。"""
    stats = {"second_wave": 0, "no_new_high": 0, "unknown": 0}
    if not nodes or not axis_dates:
        return stats
    code_cache = _load(CODE_CACHE_PATH, {})
    daily_cache = _load(DAILY_CACHE_PATH, {})
    index_of = {day: idx for idx, day in enumerate(axis_dates)}
    # 基准价取「启动日前一个交易日」，因此要多取窗口开始前约两周的数据。
    start_date = (datetime.strptime(axis_dates[0], "%Y-%m-%d")
                  - timedelta(days=14)).strftime("%Y-%m-%d")
    last_axis = axis_dates[-1]

    for node in nodes:
        node["cycle_status"] = "unknown"
        node["cycle_end_date"] = ""
        node["cycle_end_index"] = None
        node["reference_high"] = None
        node["wave2_date"] = ""
        node["end_reason"] = ""
        node["cycle_span_days"] = None
        name = str(node.get("name") or "")
        launch = str(node.get("launch_date") or "")
        code = resolve_code(name, code_cache)
        if not code or launch not in index_of:
            stats["unknown"] += 1
            continue
        node["code"] = code
        rows = fetch_daily(code, start_date, end_date, daily_cache, end_date)
        if not rows:
            stats["unknown"] += 1
            continue
        closes = {day: close for day, close in rows}
        break_date = str(node.get("break_date") or "")
        segment = [close for day, close in closes.items() if launch <= day <= break_date]
        if not segment:
            stats["unknown"] += 1
            continue
        ref_high = max(segment)
        node["reference_high"] = round(ref_high, 2)
        if break_date >= last_axis:
            # 断板日就是窗口最后一天：后面没有可核验的交易日，不需要虚线，也不算缺数据。
            node["cycle_status"] = "at_window_end"
            node["cycle_span_days"] = _span_to(node, index_of.get(break_date))
            continue
        after = [(day, closes[day]) for day in axis_dates if day > break_date and day in closes]
        if not after:
            stats["unknown"] += 1
            continue

        wave2 = next((index for index, (_, close) in enumerate(after) if close > ref_high), None)
        if wave2 is None:
            # 断板后一直没能超过连板段高点：周期没有走出二波，不画虚线。
            node["cycle_status"] = "no_new_high"
            node["end_reason"] = "断板后未再创新高"
            node["cycle_span_days"] = _span_to(node, index_of.get(break_date))
            stats["no_new_high"] += 1
            continue

        node["wave2_date"] = after[wave2][0]
        last_alive = wave2
        for index in range(wave2, len(after)):
            if after[index][1] >= ref_high:
                last_alive = index
            else:
                node["end_reason"] = f"{after[index][0]} 收盘跌回原高点之下，二波结束"
                break
        node["cycle_status"] = "second_wave"
        node["cycle_end_date"] = after[last_alive][0]
        node["cycle_end_index"] = index_of.get(node["cycle_end_date"])
        node["cycle_span_days"] = _span_to(node, node["cycle_end_index"])
        stats["second_wave"] += 1

    _save(CODE_CACHE_PATH, code_cache)
    _save(DAILY_CACHE_PATH, daily_cache)
    return stats
