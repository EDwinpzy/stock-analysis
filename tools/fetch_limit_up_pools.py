#!/usr/bin/env python3
"""拉取每个交易日的涨停池明细并落盘缓存，供节点票/梯队分析使用。

数据来自同花顺官方 CLI（hithink-finance），逐日分页抓取「涨停池」，
按交易日缓存到 data/pools/YYYY-MM-DD.json。

示例：
    python tools/fetch_limit_up_pools.py --start 2026-01-01
    python tools/fetch_limit_up_pools.py --start 2025-01-01 --end 2026-09-17
    python tools/fetch_limit_up_pools.py --start 2026-09-01 --refresh
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POOL_DIR = PROJECT_ROOT / "data" / "pools"
INDEX_CODE = "000001.SH"
DEFAULT_CONCURRENCY = 5
MAX_RETRY = 3
PAGE_SIZE = 200

TZ = ZoneInfo("Asia/Shanghai")

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _run_cli(args: list[str]) -> dict:
    """调用 hithink-finance，返回解析后的 JSON envelope。"""
    completed = subprocess.run(
        ["cmd", "/c", "hithink-finance", *args],
        capture_output=True,
        check=False,
    )
    text = completed.stdout.decode("utf-8", errors="replace").strip()
    if not text:
        stderr = completed.stderr.decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"CLI 无输出: {' '.join(args)} stderr={stderr}")
    return json.loads(text)


def _midnight_ms(day: date) -> int:
    """返回该日 Asia/Shanghai 零点对应的毫秒时间戳。"""
    return int(datetime(day.year, day.month, day.day, tzinfo=TZ).timestamp() * 1000)


def trading_days(start: date, end: date) -> list[date]:
    """用上证指数日线反推区间内的交易日。"""
    envelope = _run_cli(
        [
            "index",
            "history",
            "--thscode",
            INDEX_CODE,
            "--start-ms",
            str(_midnight_ms(start)),
            "--end-ms",
            str(_midnight_ms(end) + 86_400_000),
            "--format",
            "json",
        ]
    )
    if not envelope.get("ok"):
        raise RuntimeError(f"取交易日失败: {envelope.get('error')}")

    data = envelope["data"]
    rows = data.get("item") or data.get("items") or []
    days: list[date] = []
    for row in rows:
        raw = (
            row.get("date_ms")
            or row.get("date")
            or row.get("trade_date")
            or row.get("time")
        )
        if raw is None:
            continue
        stamp = str(raw)
        if stamp.isdigit():
            seconds = int(stamp) / 1000 if len(stamp) > 10 else int(stamp)
            days.append(datetime.fromtimestamp(seconds, TZ).date())
        else:
            days.append(datetime.fromisoformat(stamp[:10]).date())
    return sorted({d for d in days if start <= d <= end})


def fetch_pool(day: date) -> list[dict]:
    """抓取单个交易日的全部涨停池记录（自动翻页）。"""
    date_ms = _midnight_ms(day)
    items: list[dict] = []
    page = 1
    while True:
        envelope = _run_cli(
            [
                "special",
                "limit-up-pool",
                "--date-ms",
                str(date_ms),
                "--page",
                str(page),
                "--size",
                str(PAGE_SIZE),
                "--sort-field",
                "continue_day_cnt",
                "--sort-dir",
                "desc",
                "--format",
                "json",
            ]
        )
        if not envelope.get("ok"):
            raise RuntimeError(f"{day} 第{page}页失败: {envelope.get('error')}")
        data = envelope["data"]
        batch = data.get("item") or []
        items.extend(batch)
        pagination = data.get("pagination") or {}
        pages = int(pagination.get("pages") or 1)
        if page >= pages or not batch:
            break
        page += 1
    return items


def fetch_with_retry(day: date) -> tuple[date, list[dict] | None, str | None]:
    last_error: str | None = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            return day, fetch_pool(day), None
        except Exception as exc:  # noqa: BLE001 - 需要记录任意网络/解析错误
            last_error = str(exc)
            if attempt < MAX_RETRY:
                time.sleep(1.5 * attempt)
    return day, None, last_error


def main() -> int:
    parser = argparse.ArgumentParser(description="缓存每个交易日的涨停池明细")
    parser.add_argument("--start", default="2025-01-21", help="起始日期 YYYY-MM-DD（含）")
    parser.add_argument("--end", default=None, help="结束日期 YYYY-MM-DD（含），默认今天")
    parser.add_argument("--out", default=str(POOL_DIR), help="缓存目录")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--refresh", action="store_true", help="已有缓存也重新抓取")
    args = parser.parse_args()

    start = datetime.fromisoformat(args.start).date()
    end = datetime.fromisoformat(args.end).date() if args.end else datetime.now(TZ).date()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    days = trading_days(start, end)
    pending = [
        d for d in days if args.refresh or not (out_dir / f"{d.isoformat()}.json").exists()
    ]
    print(f"交易日 {len(days)} 天，区间 {start} ~ {end}，待抓取 {len(pending)} 天")
    if not pending:
        return 0

    failed: list[tuple[date, str]] = []
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = {pool.submit(fetch_with_retry, d): d for d in pending}
        for future in as_completed(futures):
            day, items, error = future.result()
            done += 1
            if items is None:
                failed.append((day, error or "unknown"))
                print(f"[{done}/{len(pending)}] {day} 失败: {error}")
                continue
            payload = {
                "date": day.isoformat(),
                "count": len(items),
                "items": items,
            }
            (out_dir / f"{day.isoformat()}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            print(f"[{done}/{len(pending)}] {day} {len(items)} 只")

    print(f"完成：成功 {len(pending) - len(failed)} 天，失败 {len(failed)} 天")
    for day, error in failed:
        print(f"  - {day}: {error}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
