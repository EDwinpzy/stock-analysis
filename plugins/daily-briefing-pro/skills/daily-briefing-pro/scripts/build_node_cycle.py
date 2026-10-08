#!/usr/bin/env python3
"""更新近三个月节点票历史并输出节点模型结果。"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from node_cycle_model import WINDOW_DAYS, build_node_model
from cycle_life import attach_cycle_life
from runtime_paths import get_data_dir


SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
DATA_DIR = get_data_dir(BASE_DIR)
HISTORY_PATH = DATA_DIR / "node_cycle_history.json"


def _target_date() -> str:
    if "--date" in sys.argv:
        index = sys.argv.index("--date")
        if index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return date.today().isoformat()


def _load(path: Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except (OSError, ValueError):
        return default


def _tgb_evidence(name: str) -> dict | None:
    payload = _load(DATA_DIR / "tgb_today.json", {})
    if not isinstance(payload, dict):
        return None
    texts = []
    for blogger in (payload.get("bloggers") or {}).values():
        if not isinstance(blogger, dict):
            continue
        texts.extend(str(item.get("content") or "") for item in blogger.get("top_replies", []) if isinstance(item, dict))
        texts.extend(str(item.get("content") or item.get("summary") or "") for item in blogger.get("posts", []) if isinstance(item, dict))
    joined = " ".join(texts)
    if name and name in joined and re.search(r"周期|节点|龙头|核心|穿越|补涨", joined):
        return {
            "level": "medium",
            "source": "淘股吧公开主帖/楼主回复（当日可访问片段）",
            "distinctive": 1,
            "cycle_switch": 1 if re.search(r"新周期|周期切换|转主升|开启", joined) else 0,
            "explicit_major": 1 if re.search(r"周期核心|核心龙头|明确认定", joined) else 0,
        }
    return None


def _node_pool_from_pool(pool: list[dict]) -> list[dict]:
    """从历史涨停池保留3板以上记录，避免把普通首板写入节点历史。"""
    result = []
    for row in pool or []:
        try:
            board = int(row.get("continue_day_cnt") or row.get("board") or 0)
        except (TypeError, ValueError):
            board = 0
        if board < 3:
            continue
        result.append({
            "name": str(row.get("name") or "").strip(),
            "code": str(row.get("code") or row.get("ts_code") or "").strip(),
            "board": board,
            "theme": str(row.get("limit_up_reason") or row.get("theme") or "").strip(),
            "status": "limit_up",
            "source": "同花顺官方历史连板池",
        })
    return [item for item in result if item["name"]][:80]


def backfill_missing_records(target_date: str, records: list[dict], fetch_pool=None, trade_dates: list[str] | None = None) -> tuple[list[dict], dict]:
    """补齐目标日前一个月缺失的交易日历史；fetch_pool 可注入测试替身。"""
    if fetch_pool is None:
        try:
            import _hithink
            if not _hithink.available():
                return records, {"status": "unavailable", "fetched": 0, "missing": 0}
            fetch_pool = lambda day: _hithink.pool_overview(day).get("limit_up_pool") or []
            trade_dates = _hithink.trade_dates()
        except Exception as exc:  # pragma: no cover - 环境差异由运行时记录
            return records, {"status": "error", "fetched": 0, "missing": 0, "note": str(exc)}
    elif trade_dates is None:
        trade_dates = []

    end = date.fromisoformat(target_date)
    cutoff = end - timedelta(days=WINDOW_DAYS - 1)
    known = {str(item.get("date"))[:10] for item in records if item.get("date")}
    candidates = [day for day in trade_dates if cutoff.isoformat() <= day <= target_date and day not in known]
    fetched = 0
    errors = []
    for day in candidates:
        try:
            pool = fetch_pool(day)
            records.append({"date": day, "stocks": _node_pool_from_pool(pool), "source": "同花顺官方历史连板池"})
            fetched += 1
        except Exception as exc:  # 一个交易日失败不阻断其它历史日
            errors.append(f"{day}:{type(exc).__name__}")
    return records, {
        "status": "ok" if not errors else "partial",
        "fetched": fetched,
        "missing": len(candidates),
        "errors": errors[:5],
    }


def update_history(target_date: str) -> tuple[list[dict], dict]:
    existing = _load(HISTORY_PATH, {"records": []})
    records = existing.get("records", []) if isinstance(existing, dict) else existing
    records = [record for record in records if isinstance(record, dict)]
    today_payload = _load(DATA_DIR / "lianban_today.json", {})
    if not isinstance(today_payload, dict):
        today_payload = {}
    pool = today_payload.get("node_pool") or []
    if pool:
        stocks = []
        for row in pool:
            item = dict(row)
            evidence = _tgb_evidence(str(item.get("name") or ""))
            if evidence:
                item["evidence"] = evidence
                item.update({key: value for key, value in evidence.items() if key in {"distinctive", "cycle_switch", "explicit_major"}})
            stocks.append(item)
        records = [r for r in records if str(r.get("date"))[:10] != target_date]
        records.append({"date": target_date, "stocks": stocks, "source": today_payload.get("source", "")})
    records, history_fetch = backfill_missing_records(target_date, records)
    cutoff = date.fromisoformat(target_date) - timedelta(days=WINDOW_DAYS - 1)
    records = [r for r in records if str(r.get("date", ""))[:10] >= cutoff.isoformat()]
    records.sort(key=lambda r: str(r.get("date", "")))
    HISTORY_PATH.write_text(json.dumps({"records": records, "model_version": "节点模型 V1.0"}, ensure_ascii=False, indent=2), encoding="utf-8")
    return records, history_fetch


def main() -> None:
    target = _target_date()
    records, history_fetch = update_history(target)

    # 两趟计算：第一趟先拿到候选节点，用日线核验「断板后是否走出二波新高」，
    # 得到每个节点的周期总跨度；第二趟再按「周期跨度最长者为大节点」重算归属
    # 与布局。日线结果有磁盘缓存，第二趟几乎不增加请求。
    probe = build_node_model(records, target, keep_all_smalls=True)
    attach_cycle_life(probe.get("nodes") or [], probe.get("axis_dates") or [], target)
    cycle_spans = {}
    for node in probe.get("nodes") or []:
        span = node.get("cycle_span_days")
        if not isinstance(span, int):
            continue
        cycle_spans[(node.get("name"), node.get("launch_date"))] = span
        # 名称兜底：第二趟重算时启动日可能微调，避免跨度字段退回纯连板天数。
        cycle_spans.setdefault(node.get("name"), span)
    result = build_node_model(records, target, cycle_spans=cycle_spans)
    # 重新绑定到最终节点对象（第二趟的节点是新建的）
    life = attach_cycle_life(result.get("nodes") or [], result.get("axis_dates") or [], target)
    result["cycle_life"] = life
    note = (f" 断板≠周期结束：日线核验后 {life['second_wave']} 个节点断板后走出二波新高、"
            f"周期延续（虚线），{life['no_new_high']} 个未再创新高（不加虚线）。")
    if life.get("unknown"):
        note += f" 其中 {life['unknown']} 个缺少日线未判定。"
    result["evidence_note"] += note
    result["history_fetch"] = history_fetch
    if history_fetch.get("status") == "unavailable":
        result["evidence_note"] += " 未检测到同花顺历史接口，本次仅使用已有缓存。"
    elif history_fetch.get("status") == "partial":
        result["evidence_note"] += f" 历史回补部分失败：{', '.join(history_fetch.get('errors', []))}。"
    cycle_payload = _load(DATA_DIR / "langwang_cycle.json", {})
    cycle_current = cycle_payload.get("current") if isinstance(cycle_payload, dict) else None
    if isinstance(cycle_current, dict) and cycle_current.get("stage"):
        result["cycle_context"] = {
            "stage": str(cycle_current.get("stage")),
            "date": str(cycle_current.get("date") or ""),
            "source": str(cycle_payload.get("source") or "狼王行千里"),
        }
        if result.get("summary", {}).get("current_major") == "大节点证据不足":
            result["summary"]["current_major"] = f"{cycle_current['stage']}（节点票待确认）"
        result["evidence_note"] += f" 周期背景参考：{cycle_payload.get('source', '公开周期复盘')} {cycle_current.get('stage')}（{cycle_current.get('date', '')}）。"
    result["history_file"] = str(HISTORY_PATH)
    result["source"] = "同花顺官方连板池 + 米开朗基瑞/淘股吧公开内容（可访问片段）"
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
