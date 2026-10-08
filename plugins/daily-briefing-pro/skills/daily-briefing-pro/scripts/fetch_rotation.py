#!/usr/bin/env python3
"""板块轮动（行业轮动模型 v2.0.0）采集器。

模型本体在外部目录（默认见 MODEL_DIR_CANDIDATES），它自带离线数据：
  · data/ths_industry_daily.csv  同花顺行业指数 90 板块日线
  · outputs/                     打分与回测结果

本脚本只做三件事：调 predict → 读 outputs → 转成简报用的结构化 JSON。
不改模型代码、不改模型参数、不覆盖它的历史产物。

用法: python fetch_rotation.py [--date YYYY-MM-DD] [--refresh]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
from runtime_paths import get_data_dir

DATA_DIR = get_data_dir(BASE_DIR)
HISTORY_PATH = DATA_DIR / "rotation_history.json"

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

    command = [sys.executable, str(model_dir / "run.py"), "predict", "--asof", args.date]
    if args.refresh:
        command.append("--refresh")
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

    manifest_path = model_dir / "outputs" / f"predict_manifest_{args.date}.json"
    if manifest_path.exists():
        try:
            asof = json.loads(manifest_path.read_text(encoding="utf-8")).get("asof") or args.date
        except Exception:
            asof = args.date
    else:
        # 目标日不是交易日时模型会落到最近交易日，按产物里最大的日期取
        candidates = sorted(
            path.stem.split("_")[-1] for path in (model_dir / "outputs").glob("all_scores_*.csv")
        )
        asof = candidates[-1] if candidates else args.date

    json.dump(build_result(args.date, model_dir, asof), sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
