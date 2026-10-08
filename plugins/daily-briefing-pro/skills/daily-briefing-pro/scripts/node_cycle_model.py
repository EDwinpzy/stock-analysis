"""节点票模型 V1.0。

这个模块只负责确定性筛选与布局，不负责联网。输入是按交易日保存的涨停池/连板池
快照，外加可选的淘股吧证据字段；输出可直接被每日简报编译器渲染。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import hashlib
from typing import Any


MODEL_VERSION = "节点模型 V1.0"
MIN_BOARD = 3
WINDOW_DAYS = 31
EXCLUDED_ROLES = {"穿越", "观察", "穿越票", "观察票"}


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _board(row: dict) -> int:
    for key in ("board", "continue_day_cnt", "max_board", "连板"):
        try:
            value = int(row.get(key) or 0)
            if value:
                return value
        except (TypeError, ValueError):
            pass
    return 0


def _role(row: dict) -> str:
    raw = str(row.get("role") or row.get("定位") or "").strip()
    return raw if raw in EXCLUDED_ROLES else raw.lower()


def _confidence(row: dict) -> tuple[str, str]:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    level = str(evidence.get("level") or row.get("evidence_level") or "").lower()
    source = str(evidence.get("source") or row.get("evidence_source") or "")
    if level in {"high", "高"} or "米开朗基瑞" in source and (row.get("explicit_major") or row.get("major_cycle")):
        return "高", source or "米开朗基瑞公开主帖/楼主回复"
    if level in {"medium", "中"} or "淘股吧" in source or "tgb" in source.lower():
        return "中", source or "淘股吧公开内容"
    return "低", source or "公开连板数据（未取得明确周期认定）"


def _node_id(name: str, code: str, start: str) -> str:
    raw = f"{name}|{code}|{start}".encode("utf-8")
    return "node-" + hashlib.sha1(raw).hexdigest()[:10]


def _normalize_records(records: list[dict], end_date: str) -> list[dict]:
    end = _date(end_date) or date.today()
    cutoff = end - timedelta(days=WINDOW_DAYS)
    result = []
    for record in records or []:
        day = _date(record.get("date") or record.get("data_date"))
        if not day or day < cutoff or day > end:
            continue
        stocks = record.get("stocks") or record.get("limit_up_pool") or record.get("node_pool") or []
        if not isinstance(stocks, list):
            continue
        clean = []
        for row in stocks:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("名称") or "").strip()
            if not name:
                continue
            item = dict(row)
            item["name"] = name
            item["code"] = str(row.get("code") or row.get("股票代码") or "").strip()
            item["board"] = _board(row)
            item["role"] = _role(row)
            clean.append(item)
        result.append({"date": day, "stocks": clean, "source": record.get("source", "")})
    return sorted(result, key=lambda r: r["date"])


def _intervals(records: list[dict]) -> list[dict]:
    dates = [r["date"] for r in records]
    date_index = {day: index for index, day in enumerate(dates)}
    by_stock: dict[tuple[str, str], list[tuple[int, dict]]] = defaultdict(list)
    for record in records:
        idx = date_index[record["date"]]
        for row in record["stocks"]:
            if row["board"] >= MIN_BOARD or row["role"] in EXCLUDED_ROLES:
                by_stock[(row["name"], row["code"])].append((idx, row))

    output = []
    for (name, code), observations in by_stock.items():
        observations.sort(key=lambda item: item[0])
        chunk: list[tuple[int, dict]] = []
        chunks: list[list[tuple[int, dict]]] = []
        for item in observations:
            if chunk and item[0] != chunk[-1][0] + 1:
                chunks.append(chunk)
                chunk = []
            chunk.append(item)
        if chunk:
            chunks.append(chunk)
        for chunk in chunks:
            first_idx, first = chunk[0]
            last_idx, last = chunk[-1]
            max_row = max((row for _, row in chunk), key=lambda row: row["board"])
            role = next((row["role"] for _, row in chunk if row["role"] in EXCLUDED_ROLES), "")
            confidence, evidence_source = _confidence(max_row)
            explicit_major = bool(
                max_row.get("major") or max_row.get("major_cycle") or max_row.get("explicit_major")
                or str(max_row.get("role") or "").lower() in {"major", "大节点", "核心"}
            )
            max_board = max(row["board"] for _, row in chunk)
            # V1.0：明确周期核心优先；没有明确认定时，只把高度和独立性信号
            # 都具备的票视作大节点，避免把普通高标误判为周期核心。
            major_signals = int(max_row.get("cycle_switch") or 0) + int(max_row.get("funding_loop") or 0) + int(max_row.get("distinctive") or 0)
            kind = "major" if explicit_major or (max_board >= 6 and major_signals >= 2) else "small"
            start = dates[first_idx].isoformat()
            end = dates[last_idx].isoformat()
            output.append({
                "id": _node_id(name, code, start),
                "name": name,
                "code": code,
                "kind": kind,
                "role": role or ("节点" if kind == "major" else "小节点"),
                "launch_date": start,
                "break_date": end,
                "max_board": max_board,
                "cycle_id": str(max_row.get("cycle_id") or "").strip(),
                "confidence": confidence,
                "evidence_source": evidence_source,
                "evidence": max_row.get("evidence") or {},
                "start_index": first_idx,
                "end_index": last_idx,
                "major_signals": major_signals,
                "parent_id": None,
            })
    return output


def _span_days(node: dict) -> int:
    """节点连板运行天数（含首尾交易日）。"""
    return int(node.get("end_index", 0) or 0) - int(node.get("start_index", 0) or 0) + 1


def _total_span(node: dict, cycle_spans: dict | None = None) -> int:
    """周期总跨度（交易日）＝连板运行区间 + 断板后二波延续区间。

    `cycle_spans` 由 scripts/cycle_life.py 用日线核验后提供，键为
    (name, launch_date)。拿不到日线核验结果时退回纯连板天数。
    """
    spans = cycle_spans or {}
    # 首选 (名称, 启动日) 精确匹配；两趟计算间启动日可能变化，再用名称兜底。
    value = 0
    for key in ((node.get("name"), node.get("launch_date")), node.get("name")):
        try:
            value = int(spans.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            break
    return value if value > 0 else _span_days(node)


def _mark_height_core(nodes: list[dict], cycle_spans: dict | None = None) -> None:
    """兜底认定大节点：拿不到明确公开周期认定时，用可核验信号推断。

    口径（SKILL 规则 2 的兜底分支 + 用户口径）：**周期跨度最长**的票地位最高，
    直接置顶为大节点。周期跨度 = 连板运行区间 + 断板后走出二波新高的延续区间
    （`cycle_spans` 由 scripts/cycle_life.py 用日线核验后提供，按交易日计）。

    没有日线数据时退回「连板高度最高 + 连板天数最长」的纯连板口径。
    最低门槛 5 个交易日，太短的连板不硬凑大节点。
    措辞统一保留「待公开认定」，不写成确定周期核心。
    """
    if any(node["kind"] == "major" for node in nodes):
        return

    def total_span(node: dict) -> int:
        return _total_span(node, cycle_spans)

    has_board_height = any(node["max_board"] >= 5 for node in nodes)
    best = max(nodes, key=lambda node: (total_span(node), node["max_board"], -node["start_index"]),
               default=None)
    if best is None:
        return
    # 死水窗口（全场最高不足 5 板）不硬凑周期核心。
    if not has_board_height:
        return
    if total_span(best) < 5:
        return

    best_total, best_board = total_span(best), best["max_board"]
    for node in nodes:
        if total_span(node) != best_total or node["max_board"] != best_board:
            continue
        node["kind"] = "major"
        node["role"] = "大节点（周期核心·待公开认定）"
        node["major_signals"] = 2
        node["cycle_total_days"] = best_total
        node["evidence_source"] = (node.get("evidence_source") or "").strip() + \
            f"；窗口内周期跨度最长（{best_total}个交易日）推断"


def _assign_parents(nodes: list[dict]) -> None:
    majors = [n for n in nodes if n["kind"] == "major"]
    for node in nodes:
        if node["kind"] != "small":
            continue
        same_cycle = [m for m in majors if node["cycle_id"] and node["cycle_id"] == m["cycle_id"]]
        candidates = same_cycle or [
            m for m in majors
            if m["start_index"] <= node["start_index"] <= m["end_index"]
            or m["start_index"] <= node["end_index"] <= m["end_index"]
        ]
        if candidates:
            node["parent_id"] = min(candidates, key=lambda m: abs(m["start_index"] - node["start_index"]))["id"]


def _assign_layout(nodes: list[dict], total_dates: int) -> None:
    occupied: dict[tuple[int, int], int] = defaultdict(int)
    for node in sorted(nodes, key=lambda n: (n["kind"] != "major", n["start_index"], -n["max_board"])):
        base_lane = 0 if node["kind"] == "major" else 1
        if node["parent_id"]:
            parent = next((p for p in nodes if p["id"] == node["parent_id"]), None)
            base_lane = (parent.get("lane", 0) + 1) if parent else base_lane
        key = (node["start_index"], node["end_index"])
        lane = base_lane
        while occupied[(node["start_index"], lane)]:
            lane += 1
        occupied[(node["start_index"], lane)] += 1
        node["lane"] = lane
        node["x_start"] = node["start_index"]
        node["x_end"] = node["end_index"]
        node["width"] = max(1, node["x_end"] - node["x_start"] + 1)
    for node in nodes:
        node["x_pct"] = round(node["x_start"] / max(total_dates - 1, 1) * 100, 4)
        node["width_pct"] = round(node["width"] / max(total_dates, 1) * 100, 4)


def build_node_model(
    records: list[dict],
    end_date: str,
    cycle_spans: dict | None = None,
    keep_all_smalls: bool = False,
) -> dict:
    """构建节点模型。

    `keep_all_smalls=True` 用于第一趟探测：不做 12 个名额的截取，保证每个候选
    都能拿到日线核验出的周期跨度，第二趟再按跨度口径定大节点与行序。
    """
    normalized = _normalize_records(records, end_date)
    dates = [record["date"] for record in normalized]
    nodes = _intervals(normalized)
    excluded = []
    for node in nodes[:]:
        if node["role"] in EXCLUDED_ROLES:
            nodes.remove(node)
            excluded.append({"name": node["name"], "code": node["code"], "定位": node["role"], "最高连板": node["max_board"]})
    _mark_height_core(nodes, cycle_spans)
    # 每个节点都挂上跨度口径：连板段（实心）+ 二波延续段（虚线）= 周期跨度。
    # 时间轴的行序与"地位"都用这个字段排序：跨度最长的票置顶，视为本轮周期核心。
    for node in nodes:
        node["board_span_days"] = _span_days(node)
        node["total_span_days"] = _total_span(node, cycle_spans)
    _assign_parents(nodes)
    raw_node_count = len(nodes)
    majors = [node for node in nodes if node["kind"] == "major"]
    smalls = [node for node in nodes if node["kind"] == "small"]
    confidence_rank = {"高": 3, "中": 2, "低": 1}
    # 3板只是候选门槛，不应把整个连板池塞进简报。优先保留：已有大节点归属、
    # 公开证据、5板以上，再用最高板和最近反馈补足一个有限的关键名单。
    # 排序口径与"大节点=高度最高+天数最长"保持一致：先看连板高度，再看连板
    # 天数，然后才是证据等级与是否挂靠大节点，最后用启动日越早越靠前来稳定
    # 同分名额，避免同分票在不同运行之间来回换人。
    smalls.sort(key=lambda node: (
        node.get("max_board", 0),
        _span_days(node),
        confidence_rank.get(node.get("confidence"), 0),
        bool(node.get("parent_id")),
        -int(node.get("start_index", 0) or 0),
    ), reverse=True)
    selected_smalls = []
    for node in smalls:
        if node.get("parent_id") or node.get("confidence") != "低" or node.get("max_board", 0) >= 5:
            selected_smalls.append(node)
    for node in smalls:
        if node not in selected_smalls and len(selected_smalls) < 12:
            selected_smalls.append(node)
    nodes = majors + (smalls if keep_all_smalls else selected_smalls[:12])
    _assign_parents(nodes)
    _assign_layout(nodes, len(dates))
    # 输出顺序＝时间轴行序口径：周期跨度（连板＋虚线）降序，最长者置顶；
    # 跨度并列时再比连板高度、启动日，保证同一份数据每次排序结果稳定。
    nodes.sort(key=lambda n: (
        -int(n.get("total_span_days", 0) or 0),
        n["kind"] != "major",
        -int(n.get("max_board", 0) or 0),
        int(n.get("start_index", 0) or 0),
    ))
    active = [n for n in nodes if n["break_date"] == (dates[-1].isoformat() if dates else "")]
    active_major = next((n for n in active if n["kind"] == "major"), None)
    active_small = [n for n in active if n["kind"] == "small"]
    latest_major = max((n for n in nodes if n["kind"] == "major"), key=lambda n: n["end_index"], default=None)
    current_major = (
        active_major["name"] if active_major
        else (f"过渡期（上一大节点：{latest_major['name']}）" if latest_major else "大节点证据不足")
    )
    current_small = "、".join(n["name"] for n in active_small[:3]) or "过渡/观察阶段"
    high_count = sum(1 for n in nodes if n["confidence"] == "高")
    filtered_count = max(0, raw_node_count - len(nodes))
    source_note = f"数据窗口：近1个月滚动至 {end_date}；关键节点{len(nodes)}个（从{raw_node_count}个候选中压缩，排除普通票{filtered_count}个）；穿越/观察{len(excluded)}个；高置信证据{high_count}个。"
    source_note += " 行序口径：连板段＋虚线二波段的总交易日数降序，最长者置顶即本轮周期核心（地位最高）。"
    if high_count < len(nodes):
        source_note += " 未取得明确公开周期认定的票按中/低置信度展示，不作为确定事实。"
    rows = []
    for major in [n for n in nodes if n["kind"] == "major"]:
        children = [n for n in nodes if n.get("parent_id") == major["id"]]
        rows.append({
            "大节点": major["name"],
            "内部重要小节点": "、".join(n["name"] for n in children) or "—",
            "最高连板": max([major["max_board"]] + [n["max_board"] for n in children]),
            "起止日期": f"{major['launch_date']} → {major['break_date']}",
            "定位": major["role"],
            "置信度": major["confidence"],
        })
    return {
        "model_version": MODEL_VERSION,
        "window_days": WINDOW_DAYS,
        "axis_dates": [day.isoformat() for day in dates],
        "nodes": nodes,
        "excluded": excluded,
        "rows": rows,
        "summary": {"current_major": current_major, "current_small": current_small},
        "evidence_note": source_note,
        "status": "ok" if nodes else "empty",
    }
