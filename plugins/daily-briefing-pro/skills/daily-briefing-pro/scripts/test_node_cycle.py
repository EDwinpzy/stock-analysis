import importlib.util
import re
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("node_cycle_model.py")
spec = importlib.util.spec_from_file_location("node_cycle_model", MODULE_PATH)
node_cycle_model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(node_cycle_model)


def _load_briefing_renderer():
    """加载 build_briefing 的时间轴渲染函数（只做渲染，不触发联网）。"""
    here = Path(__file__).parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    briefing_path = here / "build_briefing.py"
    spec = importlib.util.spec_from_file_location("build_briefing_under_test", briefing_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bar_tops(html: str) -> dict[str, int]:
    """从渲染结果里取出“票名 → 条形 top 像素”，top 越小越靠上。"""
    tops = {}
    for match in re.finditer(
        r'<div class="node-bar [^"]*" style="left:[^"]*top:(\d+)px"[^>]*>'
        r'(?:<i[^>]*>.*?</i>)?<b>([^<]*)</b>',
        html,
    ):
        tops[match.group(2)] = int(match.group(1))
    return tops


def test_same_dates_share_x_and_stack_lanes():
    records = [
        {"date": "2026-09-01", "stocks": [{"name": "甲", "code": "000001", "board": 5, "cycle_id": "C1", "role": "major"}, {"name": "乙", "code": "000002", "board": 3, "cycle_id": "C1"}]},
        {"date": "2026-09-02", "stocks": [{"name": "甲", "code": "000001", "board": 6, "cycle_id": "C1", "role": "major"}, {"name": "乙", "code": "000002", "board": 4, "cycle_id": "C1"}]},
        {"date": "2026-09-03", "stocks": [{"name": "甲", "code": "000001", "board": 7, "cycle_id": "C1", "role": "major"}, {"name": "乙", "code": "000002", "board": 5, "cycle_id": "C1"}]},
    ]
    result = node_cycle_model.build_node_model(records, "2026-09-03")
    major = next(n for n in result["nodes"] if n["name"] == "甲")
    small = next(n for n in result["nodes"] if n["name"] == "乙")
    assert major["x_start"] == small["x_start"] == 0
    assert major["x_end"] == small["x_end"] == 2
    assert small["parent_id"] == major["id"]
    assert small["lane"] > major["lane"]


def test_crossing_and_observation_are_not_new_nodes():
    records = [
        {"date": "2026-09-01", "stocks": [{"name": "穿越", "code": "000003", "board": 4, "role": "穿越"}, {"name": "观察", "code": "000004", "board": 3, "role": "观察"}]},
        {"date": "2026-09-02", "stocks": [{"name": "穿越", "code": "000003", "board": 5, "role": "穿越"}, {"name": "观察", "code": "000004", "board": 4, "role": "观察"}]},
    ]
    result = node_cycle_model.build_node_model(records, "2026-09-02")
    assert result["nodes"] == []
    assert {item["定位"] for item in result["excluded"]} == {"穿越", "观察"}


def test_three_month_window_and_confidence_note():
    records = [
        {"date": "2026-05-01", "stocks": [{"name": "旧票", "code": "000005", "board": 6}]},
        {"date": "2026-08-20", "stocks": [{"name": "新票", "code": "000006", "board": 5, "evidence": {"level": "high", "source": "米开朗基瑞主帖"}}]},
    ]
    result = node_cycle_model.build_node_model(records, "2026-08-20")
    assert [n["name"] for n in result["nodes"]] == ["新票"]
    assert result["nodes"][0]["confidence"] == "高"
    assert "近1个月" in result["evidence_note"]


def test_one_month_window_excludes_older_than_31_days():
    records = [
        {"date": "2026-07-01", "stocks": [{"name": "过期票", "code": "000007", "board": 6}]},
        {"date": "2026-08-01", "stocks": [{"name": "窗口票", "code": "000008", "board": 3}]},
    ]
    result = node_cycle_model.build_node_model(records, "2026-08-20")
    assert [n["name"] for n in result["nodes"]] == ["窗口票"]


def test_backfill_fetches_missing_trading_days():
    records, meta = __import__("build_node_cycle").backfill_missing_records(
        "2026-08-20",
        [],
        fetch_pool=lambda day: [{"name": "历史票", "code": "000009", "continue_day_cnt": 3}],
        trade_dates=["2026-08-19", "2026-08-20"],
    )
    assert meta["fetched"] == 2
    assert [record["date"] for record in records] == ["2026-08-19", "2026-08-20"]


def test_longest_total_span_is_major_and_ranks_first():
    """连板段＋虚线二波段总跨度最长的票地位最高，排在节点列表最前。"""
    records = [
        {"date": "2026-09-01", "stocks": [{"name": "甲", "code": "000001", "board": 6},
                                          {"name": "乙", "code": "000002", "board": 4}]},
        {"date": "2026-09-02", "stocks": [{"name": "甲", "code": "000001", "board": 7},
                                          {"name": "乙", "code": "000002", "board": 4}]},
        {"date": "2026-09-03", "stocks": [{"name": "甲", "code": "000001", "board": 8}]},
    ]
    spans = {("乙", "2026-09-01"): 9, ("甲", "2026-09-01"): 3}

    result = node_cycle_model.build_node_model(records, "2026-09-03", cycle_spans=spans)

    assert [n["name"] for n in result["nodes"]] == ["乙", "甲"]
    best = result["nodes"][0]
    assert best["kind"] == "major"
    assert best["total_span_days"] == 9
    assert "周期跨度" in best["evidence_source"]
    assert "行序口径" in result["evidence_note"]


def test_span_falls_back_to_board_run_without_daily_data():
    """拿不到日线核验结果时，跨度退回纯连板天数，高连板票仍是周期核心。"""
    records = [
        {"date": "2026-09-01", "stocks": [{"name": "甲", "code": "000001", "board": 6},
                                          {"name": "乙", "code": "000002", "board": 4}]},
        {"date": "2026-09-02", "stocks": [{"name": "甲", "code": "000001", "board": 7}]},
        {"date": "2026-09-03", "stocks": [{"name": "甲", "code": "000001", "board": 8}]},
        {"date": "2026-09-04", "stocks": [{"name": "甲", "code": "000001", "board": 8}]},
        {"date": "2026-09-05", "stocks": [{"name": "甲", "code": "000001", "board": 9}]},
    ]

    result = node_cycle_model.build_node_model(records, "2026-09-05")

    assert result["nodes"][0]["name"] == "甲"
    assert result["nodes"][0]["kind"] == "major"
    assert result["nodes"][0]["total_span_days"] == 5
    assert next(n for n in result["nodes"] if n["name"] == "乙")["total_span_days"] == 1


def _render_for_layout(nodes, dates):
    renderer = _load_briefing_renderer()
    return renderer.render_node_cycle_section({
        "model_version": "节点模型 V1.0",
        "axis_dates": dates,
        "nodes": nodes,
        "summary": {},
        "evidence_note": "测试口径",
    })


def _node(name, node_id, launch, break_date, board, lane, cycle_end_index=None, parent_id=None, kind="small"):
    return {
        "id": node_id,
        "name": name,
        "code": "000001",
        "kind": kind,
        "role": "小节点" if kind == "small" else "大节点（周期核心·待公开认定）",
        "launch_date": launch,
        "break_date": break_date,
        "max_board": board,
        "confidence": "低",
        "evidence_source": "测试",
        "lane": lane,
        "cycle_end_index": cycle_end_index,
        "cycle_status": "second_wave" if cycle_end_index else "no_new_high",
        "parent_id": parent_id,
    }


def test_render_puts_longest_total_bar_on_top_row():
    """渲染时连板＋虚线最长的条形排在第一行，重叠的另一条顺延到下一行。"""
    dates = [f"2026-09-{day:02d}" for day in range(1, 9)]
    nodes = [
        _node("长跨度", "n1", "2026-09-01", "2026-09-01", 4, 1, cycle_end_index=7),
        _node("重叠票", "n2", "2026-09-02", "2026-09-07", 7, 1),
    ]

    html = _render_for_layout(nodes, dates)
    tops = _bar_tops(html)

    assert tops["长跨度"] == 0
    assert tops["重叠票"] > tops["长跨度"]
    assert "周期跨度8个交易日（连板1＋二波延续7）" in html


def test_render_never_puts_child_above_parent():
    """小节点跨度更长时也不能越过父节点之上，嵌套关系保持。"""
    dates = [f"2026-09-{day:02d}" for day in range(1, 9)]
    nodes = [
        _node("父节点", "n1", "2026-09-01", "2026-09-03", 5, 0, kind="major"),
        _node("子节点", "n2", "2026-09-01", "2026-09-07", 6, 1, cycle_end_index=7, parent_id="n1"),
    ]

    html = _render_for_layout(nodes, dates)
    tops = _bar_tops(html)

    assert tops["父节点"] == 0
    assert tops["子节点"] > tops["父节点"]
