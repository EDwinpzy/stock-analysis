#!/usr/bin/env python3
"""拉取东财板块资金流历史，落盘 CSV，供画图使用。

数据源：东方财富 push2 接口（akshare 的 stock_sector_fund_flow_hist / _rank 封装）。
该接口经代理访问时不稳定，所有请求统一走重试 + 退避。

输出：
    data/sector_fund_flow_行业.csv   行业板块 × 交易日 的主力净流入
    data/sector_fund_flow_概念.csv   概念板块 × 交易日 的主力净流入

示例：
    python tools/fetch_sector_fund_flow.py --days 30
    python tools/fetch_sector_fund_flow.py --days 30 --type 行业
    python tools/fetch_sector_fund_flow.py --days 30 --refresh   # 忽略缓存重取
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

MAX_RETRY = 10
RETRY_BASE_SLEEP = 1.5
MAX_CONCURRENCY = 2

# akshare 的 sector_type 取值带"资金流"后缀
SECTOR_TYPE_ARGS = {"行业": "行业资金流", "概念": "概念资金流"}


def _retry(fn, label: str):
    """东财经代理时频繁断连，统一重试并线性退避。"""
    last = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            return fn()
        except Exception as exc:  # 任何网络异常都重试
            # 参数/解析类错误重试没有意义，直接抛出
            if isinstance(exc, (KeyError, ValueError, TypeError)):
                raise
            last = exc
            if attempt == MAX_RETRY:
                break
            sleep = min(RETRY_BASE_SLEEP * attempt, 8.0)
            print(f"    [{label}] 第{attempt}次失败({type(exc).__name__})，{sleep:.1f}s后重试")
            time.sleep(sleep)
    raise RuntimeError(f"{label} 重试 {MAX_RETRY} 次仍失败: {last}") from last


def _sector_list(sector_type: str) -> list[str]:
    import akshare as ak

    api_type = SECTOR_TYPE_ARGS[sector_type]
    df = _retry(
        lambda: ak.stock_sector_fund_flow_rank(indicator="今日", sector_type=api_type),
        f"板块列表/{sector_type}",
    )
    if df is None or df.empty:
        raise RuntimeError(f"未取到 {sector_type} 板块列表")
    # 东财该接口的板块名列随版本变动过，两个名字都兜住
    for col in ("名称", "板块"):
        if col in df.columns:
            return df[col].tolist()
    raise RuntimeError(f"{sector_type} 板块列表缺少名称列，实际列：{df.columns.tolist()}")


def _sector_hist(symbol: str) -> pd.DataFrame:
    import akshare as ak

    return _retry(lambda: ak.stock_sector_fund_flow_hist(symbol=symbol), f"历史/{symbol}")


def fetch_flow_matrix(sector_type: str, days: int, refresh: bool) -> pd.DataFrame:
    """返回 交易日 × 板块 的主力净流入矩阵（单位：元）。"""
    out_csv = DATA_DIR / f"sector_fund_flow_{sector_type}.csv"
    if out_csv.exists() and not refresh:
        cached = pd.read_csv(out_csv, index_col=0, parse_dates=True)
        print(f"  已有缓存 {out_csv.name}，{len(cached)} 个板块，跳过（重取加 --refresh）")
        return cached

    sectors = _sector_list(sector_type)
    print(f"  {sector_type}板块 {len(sectors)} 个，开始拉取历史…")

    frames: dict[str, pd.Series] = {}
    failed: list[str] = []
    done = 0

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
        futures = {pool.submit(_sector_hist, s): s for s in sectors}
        for future in as_completed(futures):
            symbol = futures[future]
            done += 1
            try:
                df = future.result()
            except Exception as exc:  # 单板块失败不中断整体
                failed.append(symbol)
                print(f"  [{done}/{len(sectors)}] {symbol} 失败: {exc}")
                continue
            if df is None or df.empty or "日期" not in df:
                failed.append(symbol)
                continue
            recent = df.tail(days)
            col = "主力净流入-净额"
            if col not in recent:
                failed.append(symbol)
                continue
            series = recent.set_index("日期")[col]
            series.index = pd.to_datetime(series.index)
            frames[symbol] = series

    if not frames:
        raise RuntimeError(f"{sector_type} 全部板块取数失败")

    matrix = pd.DataFrame(frames).sort_index()
    matrix.index.name = "日期"
    matrix.to_csv(out_csv, encoding="utf-8-sig")

    if failed:
        tail = ", ".join(failed[:10]) + ("…" if len(failed) > 10 else "")
        print(f"  注意：{len(failed)} 个板块未取到，已跳过：{tail}")
    print(f"  已写入 {out_csv.name}：{matrix.shape[0]} 个交易日 × {matrix.shape[1]} 个板块")
    print(f"  区间 {matrix.index.min().date()} ~ {matrix.index.max().date()}")
    return matrix


def main() -> int:
    parser = argparse.ArgumentParser(description="拉取东财板块资金流历史")
    parser.add_argument("--days", type=int, default=30, help="最近多少个交易日（默认 30）")
    parser.add_argument(
        "--type",
        dest="sector_type",
        choices=["行业", "概念", "both"],
        default="both",
        help="板块类型（默认 both）",
    )
    parser.add_argument("--refresh", action="store_true", help="忽略已有缓存，强制重取")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    types = ["行业", "概念"] if args.sector_type == "both" else [args.sector_type]
    for sector_type in types:
        print(f"\n[{sector_type}]")
        try:
            fetch_flow_matrix(sector_type, args.days, args.refresh)
        except Exception as exc:  # noqa: BLE001
            print(f"  {sector_type} 整体失败: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
