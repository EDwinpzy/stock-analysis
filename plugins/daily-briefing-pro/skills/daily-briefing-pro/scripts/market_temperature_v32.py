#!/usr/bin/env python3
"""市场温度（A股超短情绪温度模型 3.2）— 数据面板构建 + 运行入口。

模型本体在 sentiment_model_v32.py（公式与用户提供的参考实现逐行一致）。
本脚本负责把开盘啦的真实收盘数据整理成模型要求的输入面板：

    牛熊分组(上证 vs MA250) → 同景历史百分位 → 六因子 F/L/R/A/B/V
    → 基础强度 Q → 接缝 J → 非线性修正 → 最终温度 S → Δ1/Δ2 → 六阶段

面板保存在 data/sentiment_panel_v32.csv，逐日增量追加，重复运行只补新交易日。
输出兼容 panic_today.json 契约，并在 details 中给出全部因子与修正项。

用法:
    python market_temperature_v32.py [--date YYYY-MM-DD] [--rebuild]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
from runtime_paths import get_data_dir  # noqa: E402

DATA_DIR = get_data_dir(BASE_DIR)
PANEL_PATH = DATA_DIR / "sentiment_panel_v32.csv"
HISTORY_PATH = DATA_DIR / "sentiment_history.json"

import env_config  # noqa: F401,E402  注入本机凭证
from kaipanla_crawler import KaipanlaCrawler  # noqa: E402
from sentiment_model_v32 import compute_model  # noqa: E402

MODEL_VERSION = "A-SHORT-SENTIMENT-3.2"
WINDOW_DAYS = 400          # 回补窗口：约 1.6 年，覆盖模型建议的标定区间
MIN_ROWS = 60              # 少于该行数说明历史太短，模型分位不可用

PANEL_COLUMNS = [
    "date", "sh_close", "sh_ma250", "tradable_count", "advance_count", "turnover",
    "limit_up", "limit_down", "first_board", "consecutive", "space", "next_space",
    "bomb_rate", "yday_limitup_ret", "yday_lianban_ret", "p12", "p23", "p3p",
    # 保留板位原始数量，供次日计算晋级率
    "board2", "board3", "board4p",
    # 该行由哪个数据源产出（kaipanla / akshare），供热报告如实标注口径
    "source",
]


def _num(value, default=0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default  # 过滤 NaN


def index_history() -> pd.DataFrame:
    """上证指数收盘与 MA250，用于牛熊同景分组（单一数据源，避免口径漂移）。"""
    import akshare as ak

    frame = ak.stock_zh_index_daily(symbol="sh000001")
    frame = frame[["date", "close"]].copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
    frame["sh_close_idx"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["sh_ma250"] = frame["sh_close_idx"].rolling(250, min_periods=25).mean()
    return frame[["date", "sh_close_idx", "sh_ma250"]]


def ladder_levels(crawler: KaipanlaCrawler, date: str) -> list:
    """空间梯队高度（严格连续板），降序。失败返回空列表并由上层标注。"""
    try:
        payload = crawler.get_market_limit_up_ladder(date, timeout=15)
    except Exception as exc:
        print(f"  [WARN] {date} 空间梯队失败: {exc}", file=sys.stderr)
        return []
    ladder = payload.get("ladder", {}) if isinstance(payload, dict) else {}
    levels = []
    for level, stocks in ladder.items():
        if not stocks:
            continue
        try:
            levels.append(float(level))
        except (TypeError, ValueError):
            continue
    return sorted(set(levels), reverse=True)


def fetch_day(crawler: KaipanlaCrawler, date: str) -> dict | None:
    """抓取单个交易日的模型输入；源站未发布当日数据时返回 None。"""
    try:
        daily = dict(crawler.get_daily_data(date))
    except Exception as exc:
        print(f"  [WARN] {date} 日度数据失败: {exc}", file=sys.stderr)
        return None
    if _num(daily.get("实际涨停")) <= 0 and _num(daily.get("涨停数")) <= 0:
        return None

    try:
        ladder_df = crawler.get_limit_up_ladder(date)
        ladder = dict(ladder_df.iloc[0]) if len(ladder_df) else {}
    except Exception as exc:
        print(f"  [WARN] {date} 连板梯队指标失败: {exc}", file=sys.stderr)
        ladder = {}

    return {"daily": daily, "ladder": ladder, "levels": ladder_levels(crawler, date)}


def _previous_trade_date(idx: pd.DataFrame, date: str) -> str | None:
    days = list(idx["date"])
    if date not in days:
        return None
    position = days.index(date)
    return days[position - 1] if position > 0 else None


def _sina_prefix(code: str) -> str:
    if code.startswith(("6", "5", "9")):
        return "sh" + code
    if code.startswith(("8", "4")):
        return "bj" + code
    return "sz" + code


def load_universe() -> list:
    """本地全量A股代码表，用于按批取行情（避免依赖会限流的分页接口）。"""
    path = BASE_DIR / "data" / "_stock_names.csv"
    if not path.exists():
        return []
    import csv

    codes = []
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            code = (row.get("code") or "").strip()
            if len(code) == 6 and code.isdigit():
                codes.append(code)
    return codes


def sina_snapshot(codes: list, chunk_size: int = 300) -> dict:
    """新浪批量行情：一次拿多只个股的昨收/现价/成交额。

    比 ak.stock_zh_a_spot() 的分页接口稳定得多（本地实测 5205 只约 3.6 秒）。
    返回 {code: {"prev": , "last": , "amount": , "change": }}。
    """
    import ssl
    import urllib.request

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    out = {}
    for start in range(0, len(codes), chunk_size):
        chunk = codes[start:start + chunk_size]
        url = "https://hq.sinajs.cn/list=" + ",".join(_sina_prefix(c) for c in chunk)
        request = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36",
            "Referer": "https://finance.sina.com.cn/",
        })
        with urllib.request.urlopen(request, context=context, timeout=25) as response:
            raw = response.read().decode("gbk", "ignore")
        for line in raw.strip().split("\n"):
            if '="' not in line:
                continue
            key = line.split("=")[0].split("_")[-1][2:]
            fields = line.split('="', 1)[1].rstrip('";').split(",")
            if len(fields) < 10 or not fields[2]:
                continue
            try:
                prev, last, amount = float(fields[2]), float(fields[3]), float(fields[9])
            except ValueError:
                continue
            if prev <= 0:
                continue
            out[key] = {
                "prev": prev,
                "last": last,
                "amount": amount,
                "change": (last / prev - 1.0) * 100.0,
            }
    return out


def fetch_day_realtime(date: str, idx: pd.DataFrame, idx_map: dict) -> dict | None:
    """开盘啦当日聚合未发布时，用实时口径补齐当天这一行。

    各口径都在 2026-09-14 / 09-15 与开盘啦做过逐项对齐：
      · 涨停/跌停/炸板池（东方财富，经 AkShare）：09-14 涨停 55、跌停 16、
        炸板 30、首板 44、连板 11、空间 4、次高 3、炸板率 0.3529 —— 与开盘啦全等；
        09-15 涨停 32、跌停 27 亦与开盘啦实时接口一致。
      · 涨跌家数/成交额（新浪批量行情 + 本地全量代码表）：广度比值与开盘啦实时
        同为 20.4%，成交额 16,027 亿 vs 开盘啦 16,127 亿（差 0.6%）。
      · 昨涨停/昨连板今表现：用前一日涨停池的今日收益均值，09-15 算得 +0.667%，
        开盘啦实时字段 0.5495%，口径一致。
    行内 source 标记为 realtime，供热报告如实披露当天用的是实时口径。
    """
    import akshare as ak

    compact = date.replace("-", "")
    try:
        limit_up_pool = ak.stock_zt_pool_em(date=compact)
        limit_down_pool = ak.stock_zt_pool_dtgc_em(date=compact)
        broken_pool = ak.stock_zt_pool_zbgc_em(date=compact)
    except Exception as exc:
        print(f"  [WARN] {date} 涨停/跌停/炸板池失败: {exc}", file=sys.stderr)
        return None

    if limit_up_pool is None or len(limit_up_pool) == 0:
        return None

    boards = pd.to_numeric(limit_up_pool.get("连板数"), errors="coerce").fillna(1)
    levels = sorted({int(v) for v in boards if v >= 2}, reverse=True)
    limit_up = float(len(limit_up_pool))
    first_board = float((boards == 1).sum())
    consecutive = limit_up - first_board
    broken = float(len(broken_pool) if broken_pool is not None else 0)
    bomb_rate = broken / (limit_up + broken) if (limit_up + broken) else 0.0

    # 全市场快照：涨跌家数与成交额
    universe = load_universe()
    try:
        snapshot = sina_snapshot(universe) if universe else {}
    except Exception as exc:
        print(f"  [WARN] {date} 全市场快照失败: {exc}", file=sys.stderr)
        snapshot = {}
    change_lookup = {code: row["change"] for code, row in snapshot.items()}
    advance = float(sum(1 for row in snapshot.values() if row["last"] > row["prev"]))
    decline = float(sum(1 for row in snapshot.values() if row["last"] < row["prev"]))
    flat = float(sum(1 for row in snapshot.values() if row["last"] == row["prev"]))
    tradable = float(len(snapshot))
    # 面板的成交量口径是「上证市场成交额」，这里同样只取沪市，保持序列同质
    turnover = float(sum(row["amount"] for code, row in snapshot.items() if code.startswith("6")))
    if not snapshot:
        print(f"  [WARN] {date} 全市场快照为空，涨跌家数改用开盘啦实时", file=sys.stderr)
        try:
            mood = KaipanlaCrawler().get_realtime_market_mood()
            advance = float(mood.get("上涨家数") or 0)
            decline = float(mood.get("下跌家数") or 0)
            flat = 0.0
            tradable = advance + decline
        except Exception as exc:
            print(f"  [WARN] {date} 开盘啦实时情绪失败: {exc}", file=sys.stderr)

    # 上证成交额优先用开盘啦实时指数（与历史面板同源同口径）
    try:
        for item in KaipanlaCrawler().get_realtime_index_list().get("indexes", []):
            if item.get("stock_id") == "SH000001" and item.get("turnover"):
                turnover = float(item["turnover"])
                break
    except Exception as exc:
        print(f"  [WARN] {date} 开盘啦实时指数失败，成交额改用新浪沪市合计: {exc}", file=sys.stderr)

    # 昨日涨停/连板今日反馈：用前一交易日涨停池的代码取今日收益中位数
    yday_limitup_ret = yday_lianban_ret = 0.0
    prev_date = _previous_trade_date(idx, date)
    if prev_date:
        try:
            prev_pool = ak.stock_zt_pool_em(date=prev_date.replace("-", ""))
            prev_boards = pd.to_numeric(prev_pool.get("连板数"), errors="coerce").fillna(1)
            code_col = "代码" if "代码" in prev_pool.columns else prev_pool.columns[1]
            prev_codes = prev_pool[code_col].astype(str)
            all_ret = [change_lookup[c] for c in prev_codes if c in change_lookup]
            lb_codes = prev_codes[prev_boards >= 2]
            lb_ret = [change_lookup[c] for c in lb_codes if c in change_lookup]
            if all_ret:
                # 与开盘啦口径一致：均值（09-15 实测 +0.667% vs 开盘啦 0.5495%）
                yday_limitup_ret = float(pd.Series(all_ret).mean())
            if lb_ret:
                yday_lianban_ret = float(pd.Series(lb_ret).mean())
        except Exception as exc:
            print(f"  [WARN] {date} 昨日反馈计算失败: {exc}", file=sys.stderr)

    index_row = idx_map.get(date, {})
    return {
        "daily": {
            "实际涨停": limit_up,
            "实际跌停": float(len(limit_down_pool) if limit_down_pool is not None else 0),
            "首板数量": first_board,
            "上涨家数": advance,
            "下跌家数": decline,
            "平盘家数": flat,
            "成交额": turnover,
            "上证指数": _num(index_row.get("sh_close_idx")),
            "2连板数量": float((boards == 2).sum()),
            "3连板数量": float((boards == 3).sum()),
            "4连板以上数量": float((boards >= 4).sum()),
        },
        "ladder": {
            "今日涨停破板率(%)": bomb_rate * 100.0,
            "昨日涨停今表现(%)": yday_limitup_ret,
            "昨日连板今表现(%)": yday_lianban_ret,
        },
        "levels": [float(v) for v in levels],
        "source": "realtime",
    }


def panel_row(date: str, payload: dict, idx_map: dict) -> dict:
    daily, ladder = payload["daily"], payload["ladder"]
    levels = payload["levels"]
    limit_up = _num(daily.get("实际涨停")) or _num(daily.get("涨停数"))
    first_board = _num(daily.get("首板数量"))
    index_row = idx_map.get(date, {})
    return {
        "date": date,
        "sh_close": _num(daily.get("上证指数")) or _num(index_row.get("sh_close_idx")),
        "sh_ma250": _num(index_row.get("sh_ma250")),
        "tradable_count": (
            _num(daily.get("上涨家数")) + _num(daily.get("下跌家数")) + _num(daily.get("平盘家数"))
        ),
        "advance_count": _num(daily.get("上涨家数")),
        "turnover": _num(daily.get("成交额")),
        "limit_up": limit_up,
        "limit_down": _num(daily.get("实际跌停")) or _num(daily.get("跌停数")),
        "first_board": first_board,
        "consecutive": max(0.0, limit_up - first_board),
        "space": levels[0] if levels else 0.0,
        "next_space": levels[1] if len(levels) > 1 else 0.0,
        "bomb_rate": _num(ladder.get("今日涨停破板率(%)")) / 100.0,
        "yday_limitup_ret": _num(ladder.get("昨日涨停今表现(%)")),
        "yday_lianban_ret": _num(ladder.get("昨日连板今表现(%)")),
        "board2": _num(daily.get("2连板数量")),
        "board3": _num(daily.get("3连板数量")),
        "board4p": _num(daily.get("4连板以上数量")),
        "source": payload.get("source") or "kaipanla",
    }


def with_promotion_rates(panel: pd.DataFrame) -> pd.DataFrame:
    """按定义补算晋级率：1进2=当日2板/昨日首板，2进3=当日3板/昨日2板，
    3板以上=当日4板以上/昨日3板及以上。分母<3 时沿用前值（README 17.9）。"""
    panel = panel.sort_values("date").reset_index(drop=True)
    p12, p23, p3p = [], [], []
    for i in range(len(panel)):
        if i == 0:
            p12.append(float("nan")); p23.append(float("nan")); p3p.append(float("nan"))
            continue
        prev, cur = panel.iloc[i - 1], panel.iloc[i]
        p12.append(cur["board2"] / prev["first_board"] if prev["first_board"] >= 3 else float("nan"))
        p23.append(cur["board3"] / prev["board2"] if prev["board2"] >= 3 else float("nan"))
        denom = prev["board3"] + prev["board4p"]
        p3p.append(cur["board4p"] / denom if denom >= 3 else float("nan"))
    panel["p12"] = pd.Series(p12).ffill().fillna(0.0)
    panel["p23"] = pd.Series(p23).ffill().fillna(0.0)
    panel["p3p"] = pd.Series(p3p).ffill().fillna(0.0)
    return panel


def load_panel() -> pd.DataFrame:
    if not PANEL_PATH.exists():
        return pd.DataFrame(columns=PANEL_COLUMNS)
    frame = pd.read_csv(PANEL_PATH, dtype={"date": str})
    for col in PANEL_COLUMNS:
        if col not in frame.columns:
            # 历史行来自开盘啦；source 缺失时按 kaipanla 补齐，其余数值列补 0
            frame[col] = "kaipanla" if col == "source" else 0.0
    frame["source"] = frame["source"].fillna("kaipanla").replace("", "kaipanla")
    return frame[PANEL_COLUMNS]


def refresh_panel(end_date: str, rebuild: bool = False) -> tuple:
    """按需补齐到 end_date 的面板；返回 (面板, 失败日期列表)。"""
    idx = index_history()
    idx = idx[idx["date"] <= end_date]
    idx_map = idx.set_index("date").to_dict("index")

    panel = pd.DataFrame(columns=PANEL_COLUMNS) if rebuild else load_panel()
    if not panel.empty:
        panel = panel[panel["date"] <= end_date]
    existing = set(panel["date"]) if not panel.empty else set()

    if not existing:
        days = list(idx["date"])[-WINDOW_DAYS:]
        if len(days) < MIN_ROWS:
            raise RuntimeError(f"可用交易日仅 {len(days)} 天，不足模型最小样本 {MIN_ROWS}")
        missing = days
        print(f"首次构建面板：{days[0]} ~ {days[-1]}（{len(days)} 天）", file=sys.stderr)
    else:
        missing = [d for d in idx["date"] if d > max(existing)]
        print(f"增量补齐：已有 {len(existing)} 天，待补 {len(missing)} 天", file=sys.stderr)

    crawler = KaipanlaCrawler()
    failures, rows = [], []
    for day in missing:
        payload = fetch_day(crawler, day)
        if not payload:
            # 开盘啦尚未发布当日聚合时，用实时口径补齐，不让面板留洞
            payload = fetch_day_realtime(day, idx, idx_map)
        if not payload:
            failures.append(day)
            continue
        rows.append(panel_row(day, payload, idx_map))
        if len(rows) % 20 == 0:
            print(f"  已采集 {len(rows)}/{len(missing)}", file=sys.stderr)

    if rows:
        panel = pd.concat([panel, pd.DataFrame(rows)], ignore_index=True)
    panel = panel.drop_duplicates(subset="date", keep="last")
    if panel.empty:
        raise RuntimeError("面板为空：开盘啦未返回任何可用交易日数据")
    panel = with_promotion_rates(panel)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    panel.to_csv(PANEL_PATH, index=False, encoding="utf-8-sig")
    return panel, failures


def build_result(requested: str, panel: pd.DataFrame, failures: list) -> dict:
    if len(panel) < MIN_ROWS:
        return {
            "date": requested, "requested_date": requested, "data_date": "",
            "score": None, "status": "error", "phase": "数据获取失败", "momentum": "—",
            "cycle_label": "数据获取失败",
            "note": f"历史面板仅 {len(panel)} 行，不足模型最小样本 {MIN_ROWS}",
            "components": {}, "source": "开盘啦API",
            "model": MODEL_VERSION, "details": {}, "history": [],
        }

    output = compute_model(panel)
    last = output.iloc[-1]
    latest_input = panel.iloc[-1]

    history = [
        {
            "date": str(row["date"])[:10],
            "score": round(float(row["S"]), 1),
            "cycle_label": f"{row['phase']}｜{row['momentum']}" if row["momentum"] else str(row["phase"]),
        }
        for _, row in output.tail(14).iterrows()
    ]

    def nan_to_none(value):
        return None if pd.isna(value) else round(float(value), 1)

    data_date = str(last["date"])[:10]
    phase = str(last["phase"])
    momentum = str(last["momentum"]) if last["momentum"] else "动能待定"
    row_source = str(latest_input.get("source") or "kaipanla")
    source_label = (
        "开盘啦API" if row_source == "kaipanla"
        else "实时口径（东财涨停池 + 新浪全市场，已与开盘啦逐项对齐）"
    )
    factors = {
        "F": round(float(last["F"]), 1),
        "L": round(float(last["L"]), 1),
        "R": round(float(last["R"]), 1),
        "A": round(float(last["A"]), 1),
        "B": round(float(last["B"]), 1),
        "V": round(float(last["V"]), 1),
        "Q": round(float(last["Q"]), 1),
        "J": round(float(last["J"]), 1),
        "M": round(float(last["M"]), 1),
    }
    return {
        "date": requested,
        "requested_date": requested,
        "data_date": data_date,
        "score": round(float(last["S"]), 1),
        "status": "ok",
        "phase": phase,
        "momentum": momentum,
        "cycle_label": f"{phase}｜{momentum}",
        "delta1": nan_to_none(last["delta1"]),
        "delta2": nan_to_none(last["delta2"]),
        "note": (
            f"使用{data_date}数据（已回退）" if data_date != requested
            else ("" if row_source == "kaipanla" else "当日用实时口径补齐（已与开盘啦逐项对齐）")
        ),
        "model": MODEL_VERSION,
        "model_label": "情绪模型3.2 · 六因子加权 + 接缝修正 + 非线性校正",
        "regime": str(last["regime"]),
        "regime_label": (
            f'{last["regime"]}（上证{"高于" if last["regime"] == "Bull" else "低于"}MA250）'
        ),
        "j_label": str(last["J_label"]),
        "repair_confirmed": bool(last["repair_confirmed"]),
        "components": factors,
        "factor_display": [
            {"name": "赚钱反馈F", "value": factors["F"], "kind": "score"},
            {"name": "连板生态L", "value": factors["L"], "kind": "score"},
            {"name": "风险质量R", "value": factors["R"], "kind": "score"},
            {"name": "进攻扩散A", "value": factors["A"], "kind": "score"},
            {"name": "市场广度B", "value": factors["B"], "kind": "score"},
            {"name": "量能确认V", "value": factors["V"], "kind": "score"},
            {"name": "基础强度Q", "value": factors["Q"], "kind": "score"},
            {"name": "接缝J", "value": factors["J"], "kind": "signed"},
        ],
        "source": source_label,
        "details": {
            "raw_inputs": {
                "涨停": _num(latest_input["limit_up"]),
                "跌停": _num(latest_input["limit_down"]),
                "首板": _num(latest_input["first_board"]),
                "连板": _num(latest_input["consecutive"]),
                "空间": _num(latest_input["space"]),
                "次高": _num(latest_input["next_space"]),
                "炸板率": round(_num(latest_input["bomb_rate"]), 4),
                "成交额": _num(latest_input["turnover"]),
                "红盘数": _num(latest_input["advance_count"]),
            },
            "factors": factors,
            "corrections": {
                "C_hot": round(float(last["C_hot"]), 2),
                "C_J": round(float(last["C_J"]), 2),
                "P_breadth": round(float(last["P_breadth"]), 2),
                "P_down": round(float(last["P_down"]), 2),
                "P_bomb": round(float(last["P_bomb"]), 2),
                "P_cool": round(float(last["P_cool"]), 2),
                "P_inertia": round(float(last["P_inertia"]), 2),
            },
            "j_parts": {
                "leader": round(float(last["J_leader"]), 1),
                "follower": round(float(last["J_follower"]), 1),
                "promotion": round(float(last["J_promotion"]), 1),
            },
            "panel_rows": int(len(panel)),
            "panel_start": str(panel["date"].iloc[0]),
            "failures": failures,
        },
        "history": history,
    }


def save_history(result: dict) -> None:
    """把温度序列写入 sentiment_history.json，供折线图读取。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with HISTORY_PATH.open("w", encoding="utf-8") as handle:
        json.dump(
            {"model": MODEL_VERSION, "history": result.get("history") or []},
            handle, ensure_ascii=False, indent=2,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()
    requested = args.date or datetime.now().strftime("%Y-%m-%d")

    print(f"=== 市场温度（{MODEL_VERSION}）{requested} ===", file=sys.stderr)
    try:
        panel, failures = refresh_panel(requested, rebuild=args.rebuild)
        result = build_result(requested, panel, failures)
    except Exception as exc:
        print(f"  [ERROR] {exc}", file=sys.stderr)
        print(json.dumps({
            "date": requested, "requested_date": requested, "data_date": "",
            "score": None, "status": "error", "phase": "数据获取失败", "momentum": "—",
            "cycle_label": "数据获取失败", "note": str(exc), "components": {},
            "model": MODEL_VERSION, "source": "开盘啦API", "details": {}, "history": [],
        }, ensure_ascii=False))
        raise SystemExit(0)

    if result.get("score") is not None:
        save_history(result)
        print(
            f"S={result['score']:.1f} | Δ1={result.get('delta1')} | Δ2={result.get('delta2')} "
            f"| {result['cycle_label']} | {result['regime_label']}",
            file=sys.stderr,
        )
    else:
        print(f"  [WARN] {result.get('note')}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
