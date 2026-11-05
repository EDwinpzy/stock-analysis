#!/usr/bin/env python3
"""板块轮动（行业轮动模型 v2.0.0）采集器。

模型本体在外部目录（默认见 MODEL_DIR_CANDIDATES），它自带离线数据：
  · data/ths_industry_daily.csv  同花顺行业指数 90 板块日线
  · outputs/                     打分与回测结果

本脚本增量更新行业行情，核验完整覆盖后调 predict，并转成简报 JSON。
保留训练历史备份，不改模型代码与参数。

用法: python fetch_rotation.py [--date YYYY-MM-DD] [--refresh]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta, time as datetime_time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
from runtime_paths import get_data_dir
from _hithink import trade_dates

DATA_DIR = get_data_dir(BASE_DIR)
HISTORY_PATH = DATA_DIR / "rotation_history.json"
ASOF_RE = re.compile(r"\bas of (\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)

CN = timezone(timedelta(hours=8))
MODEL_DIR_CANDIDATES = [
    os.environ.get("ROTATION_MODEL_DIR", ""),
    r"D:\Codex\2026-09-15\referenced-chatgpt-conversation-this-is-an\outputs\sw_rotation_model",
]


def find_model_dir() -> Path | None:
    for candidate in MODEL_DIR_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate)
        if (path / "run.py").exists() and (path / "config.json").exists():
            return path
    root = Path("D:/Codex")
    if root.exists():
        for config in root.glob("*/*/outputs/sw_rotation_model/config.json"):
            return config.parent
    return None


def read_csv_rows(path: Path) -> list:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def expected_trade_date(target_date: str, trading_days: list[str], now: datetime | None = None) -> str:
    """Return the last exchange session available for a report date.

    The report is commonly generated after the close. For a same-day run before
    16:00 China time, use the previous session because today's daily bars may not
    have settled yet. Exchange holidays come from the shared Hithink calendar;
    weekdays alone are not enough to decide whether a cached model date is stale.
    """
    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    current = now or datetime.now(CN)
    if target == current.date() and current.timetz().replace(tzinfo=None) < datetime_time(16, 0):
        target -= timedelta(days=1)

    valid_days = []
    for value in trading_days:
        try:
            session = datetime.strptime(str(value), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        if session <= target:
            valid_days.append(session)
    if not valid_days:
        raise ValueError(f"交易日历未覆盖目标日 {target_date}")
    return max(valid_days).strftime("%Y-%m-%d")


def prediction_asof(stdout: str) -> str | None:
    """Read the actual date selected by this predict invocation, never old outputs."""
    matches = ASOF_RE.findall(stdout or "")
    if not matches:
        return None
    value = matches[-1]
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None
    return value


def error_result(target_date: str, note: str, asof: str = "") -> dict:
    return {
        "date": target_date,
        "asof": asof,
        "status": "error",
        "entries": [],
        "new_entries": [],
        "dropped": [],
        "note": note,
    }


def refresh_benchmark_data(model_dir: Path, expected: str, force: bool = False) -> str:
    """Refresh the CSI 300 benchmark cache when it lacks the expected session.

    The model aligns industry bars with this separate benchmark file. Updating
    industry bars alone still leaves predictions capped at the benchmark's old
    last date, so both inputs must cover the requested session.
    """
    import pandas as pd
    import akshare as ak

    path = model_dir / 'data/benchmark_csi300.csv'
    if path.exists():
        old = pd.read_csv(path, encoding='utf-8-sig')
        if {'date', 'close'} - set(old.columns):
            raise ValueError('沪深300基准缓存缺少 date/close 列')
        old = old[['date', 'close']].copy()
        old['date'] = pd.to_datetime(old['date'], errors='coerce').dt.strftime('%Y-%m-%d')
        old['close'] = pd.to_numeric(old['close'], errors='coerce')
        old = old.dropna(subset=['date', 'close'])
        if not force and ((old['date'] == expected) & (old['close'] > 0)).any():
            return expected
    else:
        old = pd.DataFrame(columns=['date', 'close'])

    failures = []
    for source in ('stock_zh_index_daily', 'stock_zh_index_daily_tx'):
        try:
            fresh = getattr(ak, source)(symbol='sh000300')
            if {'date', 'close'} - set(fresh.columns):
                raise ValueError('返回缺少 date/close 列')
            fresh = fresh[['date', 'close']].copy()
            fresh['date'] = pd.to_datetime(fresh['date'], errors='coerce').dt.strftime('%Y-%m-%d')
            fresh['close'] = pd.to_numeric(fresh['close'], errors='coerce')
            fresh = fresh.dropna(subset=['date', 'close'])
            fresh = fresh[(fresh['date'] <= expected) & (fresh['close'] > 0)]
            if fresh.empty or fresh['date'].max() != expected:
                raise ValueError(f'最新有效日期为 {fresh["date"].max() if not fresh.empty else "未知"}')

            merged = pd.concat([old, fresh], ignore_index=True)
            merged = merged.drop_duplicates('date', keep='last').sort_values('date')
            if path.exists():
                backup = path.with_name(f'benchmark_csi300.before-{expected}.csv')
                if not backup.exists():
                    backup.write_bytes(path.read_bytes())
            temp = path.with_suffix('.refresh.tmp')
            merged.to_csv(temp, index=False, encoding='utf-8-sig')
            temp.replace(path)
            return expected
        except Exception as exc:
            failures.append(f'{source}: {exc}')

    raise ValueError(f'沪深300基准行情未补齐到 {expected}：' + ' / '.join(failures))


def refresh_industry_data(model_dir: Path, expected: str, force: bool = False) -> dict:
    """Update model inputs and commit industry bars only after validation.

    Keep the older training history and model parameters intact. A partial
    refresh must never be passed to prediction as a complete universe.
    """
    import pandas as pd
    import akshare as ak
    path = model_dir / 'data/ths_industry_daily.csv'
    info = pd.read_csv(model_dir / 'data/ths_industry_info.csv', dtype={'code': str})
    old = pd.read_csv(path, dtype={'code': str})
    latest = old[old.date <= expected].groupby('code').date.max()
    needed = info[info.code.map(latest).fillna('') < expected] if not force else info
    columns = {'日期': 'date', '收盘价': 'close', '开盘价': 'open', '最高价': 'high', '最低价': 'low', '成交量': 'volume', '成交额': 'amount'}

    def fetch(row):
        for attempt in range(3):
            try:
                frame = ak.stock_board_industry_index_ths(symbol=row['name'], start_date=expected[:4] + '0101', end_date=expected.replace('-', '')).rename(columns=columns)
                frame['date'] = pd.to_datetime(frame['date']).dt.strftime('%Y-%m-%d')
                frame = frame[frame.date <= expected].copy()
                if frame.empty or frame.date.max() != expected or not (pd.to_numeric(frame.close, errors='coerce') > 0).all():
                    raise ValueError('最新交易日或收盘价无效')
                frame['code'], frame['name'] = row['code'], row['name']
                return frame[old.columns]
            except Exception:
                if attempt == 2:
                    raise ValueError(f"行业行情未补齐：{row['name']}")
                time.sleep(attempt + 1)

    if not needed.empty:
        print(f'[rotation] 增量更新 {len(needed)}/{len(info)} 个行业', file=sys.stderr)
        with ThreadPoolExecutor(max_workers=4) as executor:
            parts = list(executor.map(fetch, needed.to_dict('records')))
        merged = pd.concat([old, *parts], ignore_index=True).drop_duplicates(['code', 'date'], keep='last').sort_values(['date', 'code'])
        backup = path.with_name(f'ths_industry_daily.before-{expected}.csv')
        if not backup.exists():
            backup.write_bytes(path.read_bytes())
        temp = path.with_suffix('.refresh.tmp')
        merged.to_csv(temp, index=False, encoding='utf-8-sig')
        temp.replace(path)
        old = merged
    latest = old[old.date <= expected].groupby('code').date.max()
    complete = int((info.code.map(latest) == expected).sum())
    if complete != len(info):
        raise ValueError(f'行业行情覆盖不完整：{complete}/{len(info)}')
    benchmark_date = refresh_benchmark_data(model_dir, expected, force=force)
    return {
        'expected_industries': len(info),
        'complete_industries': complete,
        'data_date': expected,
        'benchmark_data_date': benchmark_date,
    }


def load_history() -> dict:
    if not HISTORY_PATH.exists():
        return {}
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_history(history: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def build_result(target_date: str, model_dir: Path, asof: str) -> dict:
    config = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
    universe = config.get("universe", "sw")
    universe_cfg = (config.get("universes") or {}).get(universe, {})
    top_k = int(universe_cfg.get("top_k") or 5)
    horizons = config.get("horizons") or [3, 5]
    primary = int(config.get("primary_horizon") or (horizons[-1] if horizons else 5))

    out_dir = model_dir / "outputs"
    manifest = {}
    manifest_path = out_dir / f"predict_manifest_{asof}.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    rows = read_csv_rows(out_dir / f"all_scores_{asof}.csv")
    if not rows:
        return {
            "date": target_date, "asof": asof, "status": "error",
            "note": f"轮动模型未产出 {asof} 的打分（缺少 all_scores_{asof}.csv）",
            "source": f"{config.get('name')} v{config.get('version')}",
            "universe_label": universe_cfg.get("label", universe),
            "top_k": top_k, "primary_horizon": primary, "entries": [],
            "new_entries": [], "dropped": [],
        }

    entries = []
    for row in rows:
        rank_t5 = _num(row.get("rank_T5"))
        rank_t3 = _num(row.get("rank_T3"))
        entries.append({
            "code": str(row.get("code") or ""),
            "name": str(row.get("name") or ""),
            "score_t5": _num(row.get("score_T5")),
            "score_t3": _num(row.get("score_T3")),
            "rank_t5": int(rank_t5) if rank_t5 else None,
            "rank_t3": int(rank_t3) if rank_t3 else None,
            # T+3 与 T+5 同时进入前 K，说明短周期与主周期同向
            "aligned": bool(rank_t3 is not None and rank_t3 <= top_k),
        })

    top = sorted([e for e in entries if e["rank_t5"]], key=lambda e: e["rank_t5"])[:top_k]

    # 与上一次快照比较，得出新进/跌出（首次运行没有基线就留空）
    history = load_history()
    previous_dates = sorted(d for d in history if d < asof)
    previous_top = set(history[previous_dates[-1]].get("names", [])) if previous_dates else set()
    current_names = {e["name"] for e in top}
    new_entries = sorted(current_names - previous_top) if previous_top else []
    dropped = sorted(previous_top - current_names) if previous_top else []

    for item in top:
        if not previous_top:
            item["change"] = "baseline"
        elif item["name"] in new_entries:
            item["change"] = "new"
        else:
            item["change"] = "hold"

    history[asof] = {"names": sorted(current_names), "top_k": top_k, "universe": universe}
    history = {d: history[d] for d in sorted(history)[-60:]}
    save_history(history)

    return {
        "date": target_date,
        "asof": asof,
        "status": "ok",
        "source": f"{config.get('name')} v{config.get('version')}",
        "universe_label": universe_cfg.get("label", universe),
        "top_k": top_k,
        "primary_horizon": primary,
        "horizons": horizons,
        "train_last": manifest.get("train_last") or {},
        "train_rows": manifest.get("train_rows") or {},
        "entries": top,
        "new_entries": new_entries,
        "dropped": dropped,
        "compare_base": previous_dates[-1] if previous_dates else "",
        "note": (
            "模型只给行业相对排序，分数不是上涨概率；"
            f"主周期 T+{primary}，按 {top_k} 个板块等权调仓"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(CN).strftime("%Y-%m-%d"))
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    model_dir = find_model_dir()
    if model_dir is None:
        json.dump({
            "date": args.date, "status": "error", "entries": [],
            "note": "未找到行业轮动模型目录（可用环境变量 ROTATION_MODEL_DIR 指定）",
        }, sys.stdout, ensure_ascii=False, indent=2)
        return

    try:
        expected = expected_trade_date(args.date, trade_dates())
        config = json.loads((model_dir / 'config.json').read_text(encoding='utf-8'))
        coverage = refresh_industry_data(model_dir, expected, args.refresh) if config.get('universe') == 'ths' else {}
    except Exception as exc:
        json.dump(error_result(args.date, f'无法更新或核验模型行情：{exc}'), sys.stdout, ensure_ascii=False, indent=2)
        return
    command = [sys.executable, str(model_dir / "run.py"), "predict", "--asof", expected]
    if args.refresh and config.get('universe') != 'ths':
        command.append('--refresh')
    print(f"[rotation] {model_dir}", file=sys.stderr)
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=900, cwd=str(model_dir), env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        json.dump({"date": args.date, "status": "error", "entries": [],
                   "note": "轮动模型打分超时（>900s）"}, sys.stdout, ensure_ascii=False, indent=2)
        return

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        json.dump({"date": args.date, "status": "error", "entries": [],
                   "note": "轮动模型打分失败：" + " / ".join(tail)},
                  sys.stdout, ensure_ascii=False, indent=2)
        return

    asof = prediction_asof(proc.stdout)
    try:
        expected = expected_trade_date(args.date, trade_dates())
    except Exception as exc:
        json.dump(error_result(args.date, f"无法核验模型交易日：{exc}", asof or ""),
                  sys.stdout, ensure_ascii=False, indent=2)
        return
    if asof != expected:
        json.dump(error_result(args.date, f"模型数据截至{asof or '未知'}，要求{expected}；请刷新行情后重算", asof or ""),
                  sys.stdout, ensure_ascii=False, indent=2)
        return

    result = build_result(args.date, model_dir, asof)
    result['coverage'] = coverage
    if coverage and len(read_csv_rows(model_dir / 'outputs' / f'all_scores_{asof}.csv')) != coverage['complete_industries']:
        result = error_result(args.date, '模型打分未覆盖全部行业', asof)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
