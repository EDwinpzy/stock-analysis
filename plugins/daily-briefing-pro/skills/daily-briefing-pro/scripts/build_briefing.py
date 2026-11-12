#!/usr/bin/env python3
"""
每日简报HTML编译器
从 data/ 目录读取各板块JSON数据，编译为自包含HTML文件

用法: python build_briefing.py [--date YYYY-MM-DD]
"""
import json
import html as html_lib
import math
import os
import re
import sys
import concurrent.futures
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import env_config  # noqa: F401  注入本机凭证（~/.codex/daily-briefing.env）
from market_temperature import format_delta
from data_quality import dataset_state, data_error_reason
from codex_summary_cli import (
    api_summary_config,
    call_api_text,
    semantic_summary_available,
    summarize_tasks,
)
from runtime_paths import get_data_dir
from summary_cache import (
    NO_CLEAR_OPINION,
    get_cached_summary,
    load_summary_cache,
    normalize_ai_summary,
    save_summary_cache,
    set_cached_summary,
    tgb_content_text,
)
from trading_date import get_recent_trade_date

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
DATA_DIR = get_data_dir(BASE_DIR)

# 输出目录：优先使用环境变量 BRIEFING_OUTPUT_DIR（run_all 会按调用方目录注入），
# 否则落到当前工作目录下的 报告/每日简报，保证"从哪里调用就写到哪里"。
_cwd = Path(os.getcwd())
if ".agents" in _cwd.parts and "skills" in _cwd.parts:
    WORKSPACE_ROOT = Path.cwd()
else:
    WORKSPACE_ROOT = _cwd
OUTPUT_DIR = Path(os.environ.get("BRIEFING_OUTPUT_DIR") or (WORKSPACE_ROOT / "报告" / "每日简报"))

# AI 凭证被服务端拒绝（401/403）后置位，避免对每个博主/视频重复空重试
_AI_CREDENTIAL_REJECTED = False


def get_date():
    """获取日期（支持 --date 参数）"""
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return datetime.now().strftime("%Y-%m-%d")


def load_json(filename: str) -> dict:
    """加载JSON数据文件，不存在或失败返回空dict"""
    path = DATA_DIR / filename
    if not path.exists():
        print(f"  [WARN] 数据文件缺失: {filename}", file=sys.stderr)
        return {}
    try:
        payload = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(payload, dict):
            print(f"  [WARN] 数据文件不是对象: {filename}", file=sys.stderr)
            return {}
        return payload
    except Exception as e:
        print(f"  [WARN] 数据文件解析失败: {filename} - {e}", file=sys.stderr)
        return {}


def fetch_index_data(target_date: str | None = None) -> dict:
    """获取主要指数数据（上证、科创50、纳斯达克、KOSPI）。

    只取"最近一个已收盘的交易日"：盘中运行时不能把当天未完成的分时价
    当成收盘价展示，因此按各市场的北京时间收盘时刻决定数据截止日。
    """
    indices = {}
    index_errors = {}

    # 各市场北京时间收盘时刻（用于判断当天是否已收官）
    def _cutoff_for(name: str) -> str | None:
        if not target_date:
            return None
        try:
            day = datetime.strptime(target_date, "%Y-%m-%d")
        except ValueError:
            return target_date
        from zoneinfo import ZoneInfo
        market_zone, close_time = {
            "纳斯达克": ("America/New_York", (16, 0)),
            "KOSPI": ("Asia/Seoul", (15, 30)),
        }.get(name, ("Asia/Shanghai", (15, 0)))
        now = datetime.now(ZoneInfo(market_zone))
        cutoff = now.date()
        if (now.hour, now.minute) < close_time:
            cutoff -= timedelta(days=1)
        return min(day.date(), cutoff).isoformat()

    def _last_pair(frame, cutoff):
        if frame is None or len(frame) < 2:
            return None
        frame = frame.copy()
        # 数据源偶尔会把最新一行写成 0（KOSPI 曾出现 close=0 → 显示成 -100%），
        # 这类无效收盘必须剔除，否则会把坏值当成真实行情渲染。
        if "close" in frame.columns:
            def _valid_close(value) -> bool:
                try:
                    num = float(str(value).replace(",", ""))
                except (TypeError, ValueError):
                    return False
                return math.isfinite(num) and num > 0
            frame = frame[frame["close"].map(_valid_close)]
            if len(frame) < 2:
                return None
        date_col = next((c for c in ("date", "日期", "trade_date") if c in frame.columns), None)
        if date_col and cutoff:
            try:
                frame["_date"] = frame[date_col].astype(str).str[:10]
                frame = frame[frame["_date"].str.fullmatch(r"\d{4}-\d{2}-\d{2}")]
                frame = frame[frame["_date"] <= cutoff]
            except Exception:
                pass
        if date_col and "_date" in frame.columns:
            frame = frame.sort_values("_date")
        if len(frame) < 2:
            return None
        return frame.iloc[-2], frame.iloc[-1], (str(frame.iloc[-1][date_col])[:10] if date_col else "")

    def _record(name: str, frame, decimals: int = 2):
        pair = _last_pair(frame, _cutoff_for(name))
        if not pair:
            index_errors[name] = "数据源未返回足够的交易日数据"
            return
        prev, last, data_date = pair
        close = float(last["close"])
        prev_close = float(prev["close"])
        if not (math.isfinite(close) and close > 0):
            index_errors[name] = f"收盘价无效（{close}），按取数失败处理"
            return
        if not prev_close:
            index_errors[name] = "前收为 0，无法计算涨跌幅"
            return
        chg = (close - prev_close) / prev_close * 100
        indices[name] = {"close": round(close, decimals), "chg": round(chg, 2), "data_date": data_date}

    try:
        import akshare as ak
    except Exception as e:
        print(f"  [WARN] 指数数据获取失败: {e}", file=sys.stderr)
        return indices

    # 每项独立 try：一个指数失败不影响其余指数，但必须记录真实原因
    for name, symbol in (("上证", "sh000001"), ("科创50", "sh000688")):
        try:
            _record(name, ak.stock_zh_index_daily(symbol=symbol), decimals=2)
        except Exception as e:
            index_errors[name] = f"{type(e).__name__}: {e}"

    try:
        _record("纳斯达克", ak.index_us_stock_sina(symbol=".IXIC"), decimals=2)
    except Exception as e:
        index_errors["纳斯达克"] = f"{type(e).__name__}: {e}"

    # KOSPI：新浪环球指数里韩国指数登记名为「首尔综合指数」
    for symbol in ("首尔综合指数", "KOSPI"):
        if "KOSPI" in indices:
            break
        try:
            _record("KOSPI", ak.index_global_hist_sina(symbol=symbol), decimals=2)
        except Exception as e:
            index_errors["KOSPI"] = f"{symbol}: {type(e).__name__}: {e}"
    if "KOSPI" not in indices:
        try:
            frame = ak.index_global_hist_em(symbol="韩国KOSPI").rename(columns={"日期": "date", "最新价": "close"})
            _record("KOSPI", frame, decimals=2)
            if "KOSPI" in indices:
                index_errors.pop("KOSPI", None)
        except Exception as e:
            index_errors["KOSPI"] = f"东方财富备用源：{type(e).__name__}: {e}"

    for name, reason in index_errors.items():
        print(f"  [WARN] 指数{name}获取失败：{reason}", file=sys.stderr)
    indices["_errors"] = index_errors

    return indices


def _safe_float(value, default=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def esc(value) -> str:
    """Escape source text before inserting it into the generated HTML."""
    return html_lib.escape("" if value is None else str(value), quote=True)


def summary_direction(summary: str, default: str = '中性') -> str:
    """Use an explicit semantic label; word occurrence is not a market stance."""
    match = re.match(r'^【(看多|看空|中性|关注)】', str(summary or '').strip())
    return match.group(1) if match else default


def _date_label(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    return str(data.get("data_date") or data.get("date") or data.get("raw_date") or "").strip()


def section_data_note(data: dict, requested_date: str, fallback_date: str | None = None) -> str:
    """Return a truthful, compact freshness/error note for a section."""
    if not isinstance(data, dict) or not data:
        return "数据获取失败：数据文件缺失或为空"
    state, reason = dataset_state(data, requested_date, fallback_date)
    status = str(data.get("status") or "").lower()
    if status in {"error", "failed", "failure"} or state == "error":
        return f"数据获取失败：{esc(data.get('note') or reason or data.get('error') or '未知错误')}"
    if state in {"missing", "stale", "future", "unknown"}:
        return f"数据获取失败：{esc(reason)}"
    if status == "empty":
        return esc(data.get("note") or "暂无有效数据")
    data_date = _date_label(data)
    if data_date and data_date != requested_date:
        return f"使用{esc(data_date)}数据（目标日无更新）"
    return esc(data.get("note") or "")


def section_meta(data: dict, requested_date: str, fallback_date: str | None = None, count: int | None = None, unit: str = "") -> str:
    """Build a section header meta string with the actual data date."""
    if not isinstance(data, dict) or not data:
        return "数据获取失败"
    state, reason = dataset_state(data, requested_date, fallback_date)
    if state in {"error", "missing", "stale", "future", "unknown"} or str(data.get("status", "")).lower() in {"error", "failed", "failure"}:
        return "数据获取失败"
    if str(data.get("status", "")).lower() == "empty":
        # ``date`` is the requested/report date, not proof that a record exists.
        # Empty datasets must not present it as an actual data date.
        actual = str(data.get("data_date") or "").strip()
        return f"0{unit} · {esc(actual)}数据 · 暂无有效数据" if actual else f"0{unit} · 暂无有效数据"
    actual = _date_label(data)
    prefix = f"{count if count is not None else ''}{unit}"
    return f"{prefix} · {esc(actual or requested_date)}数据" if prefix else esc(actual or requested_date)


def section_has_live_data(data: dict, requested_date: str, fallback_date: str | None = None) -> bool:
    """列表类板块只有"日期对得上且抓取成功"才允许渲染条目。

    否则会把过期缓存当成当日内容展示（标题写着失败、下面却是别的日期的数据）。
    """
    if not isinstance(data, dict) or not data:
        return False
    state, _ = dataset_state(data, requested_date, fallback_date)
    status = str(data.get("status") or "").lower()
    if status in {"error", "failed", "failure"}:
        return False
    return state == "ok"


def render_index_card(name: str, index: dict | None) -> str:
    """Render a real index value, or an explicit error card without defaults."""
    if not isinstance(index, dict):
        return f'<div class="mc dn"><div class="lb">{esc(name)}</div><div class="vl">—</div><div class="cg dn">数据获取失败</div></div>'
    close = _safe_float(index.get("close"))
    chg = _safe_float(index.get("chg"))
    if close is None or chg is None:
        return f'<div class="mc dn"><div class="lb">{esc(name)}</div><div class="vl">—</div><div class="cg dn">数据获取失败</div></div>'
    cls = mc_cls(chg)
    return f'<div class="mc {cls}"><div class="lb">{esc(name)}</div><div class="vl">{close:,.2f}</div><div class="cg {cls}">{arrow(chg)}{abs(chg):.2f}%</div></div>'


def _sentiment_color(phase: str) -> str:
    if any(word in phase for word in ("退潮", "冰点")):
        return "var(--dn)"
    if any(word in phase for word in ("分歧", "混沌", "失败")):
        return "var(--wrn)"
    return "var(--up)"


def _format_factor(name: str, value, kind: str = "raw") -> str:
    number = _safe_float(value)
    if number is None:
        return f"{name} —"
    if kind == "signed":
        return f"{name} {number:+.1f}"
    if kind == "score":
        return f"{name} {number:.1f}"
    if name == "炸板率":
        return f"{name} {number * 100:.1f}%"
    if name in ("昨连板", "昨涨停"):
        return f"{name} {number * 100:+.2f}%"
    if name == "成交量":
        return f"{name} {number:,.0f}亿"
    return f"{name} {number:,.0f}"


def render_rotation_section(rotation: dict, data_note: str = "") -> str:
    """板块轮动：行业轮动模型的横截面排序榜（沿用简报既有版式）。"""
    rotation = rotation if isinstance(rotation, dict) else {}
    status = str(rotation.get("status") or "").lower()
    if status != "ok" or not rotation.get("entries"):
        reason = rotation.get("note") or "轮动模型未产出打分"
        return f'''<section class="sec">
<div class="sh"><span class="ico">◉</span> 板块轮动 <span class="meta">数据获取失败</span></div>
<div class="lbox" style="color:var(--wrn)">数据获取失败：{esc(reason)}</div>
</section>'''

    entries = [e for e in rotation["entries"] if isinstance(e, dict)]
    top_k = rotation.get("top_k") or len(entries)
    primary = rotation.get("primary_horizon") or 5
    aligned = sum(1 for e in entries if e.get("aligned"))
    new_names = rotation.get("new_entries") or []
    dropped = rotation.get("dropped") or []
    asof = str(rotation.get("asof") or "")

    rows = []
    for item in entries:
        rank = item.get("rank_t5")
        name = str(item.get("name") or "")
        score = item.get("score_t5")
        rank_t3 = item.get("rank_t3")
        score_text = f"{score:.4f}" if isinstance(score, (int, float)) else "—"
        t3_text = f"第{rank_t3}名" if rank_t3 else "—"
        align_badge = (
            '<span class="bg_">共振</span>' if item.get("aligned")
            else '<span class="bbl">仅T+5</span>'
        )
        if item.get("change") == "new":
            change_badge = '<span class="br">新进</span>'
        elif item.get("change") == "dropped":
            change_badge = '<span class="bo">跌出</span>'
        elif item.get("change") == "baseline":
            change_badge = '<span class="t3">首次</span>'
        else:
            change_badge = '<span class="t3">—</span>'
        rows.append(
            f'<tr><td class="tr" style="color:var(--gld);font-weight:700">{esc(str(rank))}</td>'
            f'<td class="tb">{esc(name)}</td>'
            f'<td class="t2" style="font-family:var(--mono)">{score_text}</td>'
            f'<td class="t3">{esc(t3_text)}</td>'
            f'<td>{align_badge}</td>'
            f'<td>{change_badge}</td></tr>'
        )

    changes = []
    if new_names:
        changes.append("新进：" + "、".join(new_names))
    if dropped:
        changes.append("跌出：" + "、".join(dropped))
    compare_base = rotation.get("compare_base") or ""
    if changes and compare_base:
        change_line = f"{compare_base} → {asof} 对比 · " + "；".join(changes)
    elif changes:
        change_line = "；".join(changes)
    else:
        change_line = "首次运行，暂无上一期名单可比对"

    meta = (
        f'{top_k}个板块 · T+{primary} · {esc(asof)}数据'
        f'{" · " + esc(data_note) if data_note else ""}'
    )
    return f'''<section class="sec">
<div class="sh"><span class="ico">◉</span> 板块轮动 <span class="meta">{meta}</span></div>
<div class="rot-head">
  <div class="rot-kpi"><span class="rot-kpi-v">{aligned}<i>/{len(entries)}</i></span><span class="rot-kpi-l">短周期共振</span></div>
  <div class="rot-kpi"><span class="rot-kpi-v">{len(new_names)}</span><span class="rot-kpi-l">本期新进</span></div>
  <div class="rot-kpi"><span class="rot-kpi-v">{len(dropped)}</span><span class="rot-kpi-l">本期跌出</span></div>
  <div class="rot-note">{esc(rotation.get("note") or "")}<br><span class="t3">{esc(change_line)}</span></div>
</div>
<table class="rot-tbl"><colgroup><col style="width:44px"><col style="width:150px"><col style="width:90px"><col style="width:78px"><col style="width:74px"><col></colgroup>
<tr><th>排名</th><th>板块</th><th>T+{primary} 分数</th><th>T+3 排名</th><th>周期</th><th>变动</th></tr>
{"".join(rows)}</table>
<div class="lbox"><b>口径：</b>{esc(rotation.get("source") or "")} · {esc(rotation.get("universe_label") or "")}；模型只给行业相对排序，分数不是上涨概率，按 T+{primary} 周期调仓。</div>
</section>'''


def render_node_cycle_section(node_cycle: dict) -> str:
    """渲染节点模型 V1.0：真实日期轴、同日同 x、上下堆叠与嵌套周期。"""
    node_cycle = node_cycle if isinstance(node_cycle, dict) else {}
    summary = node_cycle.get("summary") or {}
    model_version = str(node_cycle.get("model_version") or "节点模型 V1.0")
    evidence_note = str(node_cycle.get("evidence_note") or "节点票数据尚未形成可核验历史")
    current_major = str(summary.get("current_major") or "大节点证据不足")
    current_small = str(summary.get("current_small") or "过渡/观察阶段")
    dates = [str(day)[:10] for day in (node_cycle.get("axis_dates") or [])]
    nodes = [item for item in (node_cycle.get("nodes") or []) if isinstance(item, dict)]
    rows = [item for item in (node_cycle.get("rows") or []) if isinstance(item, dict)]
    excluded = [item for item in (node_cycle.get("excluded") or []) if isinstance(item, dict)]
    axis_last = max(len(dates) - 1, 1)

    def x_of(index: int) -> float:
        return index / axis_last * 100.0

    if dates:
        # 每一天都要有日期刻度（用户口径）。跨周的第一个交易日另用更重的
        # 网格线做节奏参照，避免 21 条同强度竖线糊在一起。
        labelled = set(range(len(dates)))
        strong = {0, len(dates) - 1}
        for index in range(1, len(dates)):
            try:
                gap = (datetime.strptime(dates[index], "%Y-%m-%d")
                       - datetime.strptime(dates[index - 1], "%Y-%m-%d")).days
            except ValueError:
                gap = 1
            if gap > 1:
                strong.add(index)
        axis_parts = []
        for index, day in enumerate(dates):
            if index not in labelled:
                continue
            if index == 0:
                cls = " edge"
            elif index == len(dates) - 1:
                cls = " edge edge-end"
            else:
                cls = ""
            axis_parts.append(f'<span class="{cls.strip()}" style="left:{x_of(index):.3f}%">{esc(day[5:])}</span>')
        axis_html = "".join(axis_parts)
        grid_html = "".join(
            f'<div class="node-grid{" strong" if index in strong else ""}" style="left:{x_of(index):.3f}%"></div>'
            for index in range(len(dates))
        )
    else:
        axis_html = '<span class="node-axis-empty">等待最近1个月连板历史</span>'
        grid_html = ""

    # ---- 冲突消解：横向不重叠，纵向按周期跨度排位 ----
    # 每条票先算出它在图上的真实跨度（实心段 + 虚线段），再按跨度从长到短依次
    # 占位；重叠时顺延到下一行，保证横向永远不压在一起。
    # 每个节点拆成两段：实心=连板运行区间；虚线=断板后仍未走A、周期仍在延续的交易日。
    index_of = {day: index for index, day in enumerate(dates)}
    axis_n = max(len(dates), 1)
    per_day = 100.0 / axis_n

    entries = []
    for order, item in enumerate(nodes):
        launch_i = index_of.get(str(item.get("launch_date") or ""))
        break_i = index_of.get(str(item.get("break_date") or ""))
        model_span = item.get("total_span_days") or item.get("cycle_span_days")
        solid_days = dash_days = 0
        if launch_i is None or break_i is None or break_i < launch_i:
            left = max(0.0, float(item.get("x_pct", 0) or 0))
            width = max(3.0, float(item.get("width_pct", 0) or 0))
            dash_left = dash_width = None
            right = left + min(width, max(3.0, 100.0 - left))
            width = min(width, max(3.0, 100.0 - left))
        else:
            left = x_of(launch_i)
            right = min(left + (break_i - launch_i + 1) * per_day, 100.0)
            width = max(0.6, right - left)
            right = left + width
            dash_left = dash_width = None
            solid_days = break_i - launch_i + 1
            cycle_end_i = item.get("cycle_end_index")
            if isinstance(cycle_end_i, int) and cycle_end_i > break_i:
                dash_left = x_of(break_i + 1)
                dash_right = min(dash_left + (cycle_end_i - break_i) * per_day, 100.0)
                dash_width = dash_right - dash_left
                if dash_width <= 0.05:
                    dash_left = dash_width = None
                else:
                    right = dash_right
                    dash_days = min(cycle_end_i, axis_n - 1) - break_i
        # 行序用的跨度取“图上真实画出来的长度”（实心段天数 + 虚线段天数），
        # 拿不到横坐标时才退回模型给的周期跨度字段。
        span_days = solid_days + dash_days
        if span_days <= 0:
            try:
                span_days = max(1, int(model_span))
            except (TypeError, ValueError):
                span_days = 1
        entries.append({
            "item": item,
            "left": left,
            "width": width,
            "right": right,
            "dash_left": dash_left,
            "dash_width": dash_width,
            "solid_days": solid_days,
            "dash_days": dash_days,
            "span_days": span_days,
            "level": max(0, int(item.get("lane", 0) or 0)),
            "order": order,
        })

    # 行序口径（用户口径）：连板段 + 虚线二波段的总交易日数越长，周期越大、地位
    # 越高，就越靠上。所以按跨度从长到短依次占位，每条票落在第一行不与已有条形
    # 重叠的位置；小节点永远排在它的大节点下方，嵌套关系不会被打破。
    by_id = {str(entry["item"].get("id") or ""): entry for entry in entries}
    row_end: dict[int, float] = {}
    placed_rows: dict[str, int] = {}
    queue = sorted(entries, key=lambda e: (-e["span_days"], e["left"], e["order"]))
    while queue:
        deferred = []
        placed_any = False
        for entry in queue:
            node_id = str(entry["item"].get("id") or "")
            parent = by_id.get(str(entry["item"].get("parent_id") or ""))
            parent_id = str(parent["item"].get("id") or "") if parent else ""
            if parent is not None and parent_id not in placed_rows:
                # 父节点还没落位，本票先顺延，保证子节点不会跑到父节点上面
                deferred.append(entry)
                continue
            row = placed_rows[parent_id] + 1 if parent is not None else 0
            while row_end.get(row, -999.0) + 1.2 > entry["left"]:
                row += 1
            row_end[row] = max(row_end.get(row, -999.0), entry["right"])
            placed_rows[node_id] = row
            entry["display_row"] = row
            placed_any = True
        if not placed_any:  # 父子链异常时兜底，避免死循环
            base_row = (max(row_end) + 1) if row_end else 0
            for offset, entry in enumerate(deferred):
                entry["display_row"] = base_row + offset
            break
        queue = deferred

    total_rows = max([entry["display_row"] for entry in entries] + [0]) + 1

    bar_h, row_gap = 24, 33
    lanes_height = total_rows * row_gap + 4

    bands = "".join(
        f'<div class="node-row-band" style="top:{row * row_gap}px;height:{bar_h}px"></div>'
        for row in range(1, total_rows, 2)
    )

    # 表格里的字段全部并入图内：名称、连板高度、起止日期、定位、置信度；
    # 悬停标题补上证据来源，不再单独占用一块表格。
    bars = []
    for entry in sorted(entries, key=lambda e: (e["display_row"], e["left"], e["order"])):
        item = entry["item"]
        is_major = item.get("kind") == "major"
        kind = "major" if is_major else "small"
        confidence = str(item.get("confidence") or "低")
        role = str(item.get("role") or ("节点" if is_major else "小节点"))
        name = str(item.get("name") or "")
        life = str(item.get("cycle_status") or "")
        ref_high = item.get("reference_high")
        status_text = {
            "second_wave": (f"{item.get('wave2_date', '')} 二波创新高（前高 {ref_high}），"
                            f"{item.get('end_reason') or '二波仍在延续'}"),
            "no_new_high": f"断板后未再创新高（前高 {ref_high}），周期结束",
            "at_window_end": "断板日即窗口最后一日",
        }.get(life, "周期延续待核验")
        span_text = f"周期跨度{entry['span_days']}个交易日"
        if entry["solid_days"]:
            span_text += f"（连板{entry['solid_days']}＋二波延续{entry['dash_days']}）"
        title = (f"{role}｜{name} · {item.get('max_board', 0)}板 · "
                 f"{item.get('launch_date', '')}→{item.get('break_date', '')} · {span_text} · "
                 f"{confidence}置信｜{status_text}｜{item.get('evidence_source', '')}")
        marker = '<i class="node-crown">★</i>' if is_major else ""
        top = entry["display_row"] * row_gap
        if entry["dash_left"] is not None:
            bars.append(
                f'<div class="node-bar {kind} cycle-tail" style="left:{entry["dash_left"]:.3f}%;'
                f'width:{entry["dash_width"]:.3f}%;top:{top + 10}px" title="{esc(title)}"></div>'
            )
        bars.append(
            f'<div class="node-bar {kind}" style="left:{entry["left"]:.3f}%;'
            f'width:{entry["width"]:.3f}%;top:{top}px" title="{esc(title)}">'
            f'{marker}<b>{esc(name)}</b>'
            f'<em>{esc(str(item.get("max_board") or ""))}板</em>'
            f'<small>{esc(confidence)}置信</small></div>'
        )

    # 穿越/观察票不参与节点，但也要在图内可见，用虚线幽灵条单独一行标出。
    ghost_html = ""
    if excluded:
        ghost_top = total_rows * row_gap
        ghost_html = "".join(
            f'<div class="node-bar ghost" style="left:{float(item.get("x_pct", 0) or 0):.3f}%;'
            f'width:{max(3.0, float(item.get("width_pct", 0) or 0)):.3f}%;top:{ghost_top}px" '
            f'title="{esc(str(item.get("定位") or "穿越/观察"))}｜{esc(str(item.get("name") or ""))}">'
            f'<b>{esc(str(item.get("name") or ""))}</b>'
            f'<em>{esc(str(item.get("定位") or ""))}</em></div>'
            for item in excluded[:8]
        )
        lanes_height = max(lanes_height, ghost_top + row_gap)

    excluded_note = "、".join(f"{item.get('name', '')}（{item.get('定位', '')}）" for item in excluded[:8])
    cycle_context = node_cycle.get("cycle_context") or {}
    cycle_chip = ""
    if isinstance(cycle_context, dict) and cycle_context.get("stage"):
        cycle_chip = (f'<span class="node-cycle-tag">周期背景：{esc(str(cycle_context.get("stage")))}'
                      f' · {esc(str(cycle_context.get("source") or "公开周期复盘"))}'
                      f'（{esc(str(cycle_context.get("date") or ""))}）</span>')
    legend_parts = [
        '<span><i class="node-dot major"></i>大节点（周期核心）</span>',
        '<span><i class="node-dot small"></i>内部重要小节点</span>',
        '<span><i class="node-dot tail"></i>虚线＝断板后走出二波新高、周期仍在延续</span>',
    ]
    if excluded:
        legend_parts.append('<span><i class="node-dot ghost"></i>穿越/观察（不计入节点）</span>')
    legend_parts.append('<span>横轴为真实交易日；同一启动/断板日共用横坐标，重叠时纵向堆叠</span>')
    legend_html = "".join(legend_parts)
    return f'''<section class="sec fw node-cycle">
<div class="sh"><span class="ico">◉</span> 大小周期节点票 <span class="meta">{esc(model_version)} · 近1个月滚动</span></div>
<div class="node-conclusion"><b>当前判断：</b>处于<strong>{esc(current_major)}</strong>，主要小节点/过渡节点为<strong>{esc(current_small)}</strong>。{cycle_chip}</div>
<div class="node-toolbar">
  <div class="node-zoom" role="group" aria-label="时间轴缩放">
    <button type="button" data-node-zoom="out" title="缩小时间轴">−</button>
    <span class="node-zoom-val" data-node-zoom-value>100%</span>
    <button type="button" data-node-zoom="in" title="放大时间轴">＋</button>
    <button type="button" class="node-zoom-reset" data-node-zoom="reset" title="回到默认缩放">重置</button>
  </div>
  <span class="node-hint">拖动或滚轮左右查看 · Ctrl+滚轮缩放</span>
</div>
<div class="node-scroll" data-node-scroll>
  <div class="node-track" style="--node-zoom:1">
    <div class="node-axis">{axis_html}</div>
    <div class="node-lanes" style="height:{lanes_height}px">
      {grid_html}
      {bands}
      {''.join(bars) or '<div class="node-empty">暂无可绘制节点条形；等待连板历史积累</div>'}
      {ghost_html}
    </div>
  </div>
</div>
<div class="node-legend">{legend_html}</div>
<div class="lbox"><b>证据与边界：</b>{esc(evidence_note)}{f' 排除项：{esc(excluded_note)}。' if excluded_note else ''}</div>
</section>'''


def render_lianban_strip(lianban: dict) -> str:
    """盘面补充概况（同花顺官方事实 + 连板网独有字段），显示在温度卡片里（不替换模型算出的 S）。"""
    if not isinstance(lianban, dict) or lianban.get("status") != "ok":
        return ""
    ov = lianban.get("overview") or {}
    if not ov:
        return ""

    items = []

    def add(label, value, unit=""):
        if value in (None, ""):
            return
        items.append(f'<span class="sent-factor">{esc(label)} {esc(str(value))}{unit}</span>')

    max_board = ov.get("max_board")
    if max_board is not None:
        prev = ov.get("max_board_prev")
        add("最高板", f"{max_board}板" + (f"（昨{prev}板）" if prev else ""))
    consecutive = ov.get("consecutive")
    if consecutive is not None:
        prev = ov.get("consecutive_prev")
        add("连板", f"{consecutive}家" + (f"（昨{prev}）" if prev else ""))
    seal = ov.get("seal_rate")
    if seal is not None:
        prev = ov.get("seal_rate_prev")
        add("封板率", f"{seal}%" + (f"（昨{prev}%）" if prev else ""))
    broken_rate = ov.get("broken_rate")
    if broken_rate is not None:
        add("炸板率", f"{broken_rate}%")
    advance, decline = ov.get("advance"), ov.get("decline")
    if advance is not None and decline is not None:
        add("涨跌家数", f"{advance:,}/{decline:,}")
    if ov.get("market_turnover"):
        add("两市成交", ov["market_turnover"])
    high, low = ov.get("new_high_63"), ov.get("new_low_63")
    if high is not None and low is not None:
        add("新高/新低", f"{high}/{low}")
    if ov.get("margin_balance"):
        change = ov.get("margin_change")
        suffix = f"（较前日{change:+.0f}亿）" if isinstance(change, (int, float)) else ""
        add(f"融资余额{ov.get('margin_date', '')}", f"{ov['margin_balance']}{suffix}")

    if not items:
        return ""
    # 只补充可核对的盘面事实。外源自带的“情绪温度/情绪周期”不展示，
    # 避免和本项目模型算出的 S 并列出现造成误读——温度只有一个来源。
    # 标签按实际数据来源渲染，换源后不能继续写死“连板网”。
    source = str(lianban.get("source") or "")
    if "同花顺" in source and "连板网" in source:
        source_label = "同花顺官方+连板网"
    elif "同花顺" in source:
        source_label = "同花顺官方"
    else:
        source_label = "连板网"
    return (
        f'<div class="sent-factors" style="border-top:1px solid var(--bd);padding-top:6px;margin-top:2px">'
        f'<span class="sent-factor" style="color:var(--t3)">盘面补充（{esc(source_label)}）</span>'
        f'{"".join(items)}'
        f'</div>'
    )


def render_sentiment_summary(panic: dict, lianban: dict | None = None) -> str:
    """渲染顶部市场温度卡片，展示 S、Δ1、Δ2 及全部公式输入。"""
    score = _safe_float(panic.get("score"))
    score_text = f"{score:.1f}" if score is not None else "—"
    score_width = max(0.0, min(100.0, score)) if score is not None else 0

    phase = str(panic.get("phase") or panic.get("status") or "数据获取失败")
    momentum = str(panic.get("momentum") or "动能待定")
    cycle_label = str(panic.get("cycle_label") or f"{phase}｜{momentum}")
    delta1 = panic.get("delta1")
    delta2 = panic.get("delta2")
    components = panic.get("components") or {}
    # 模型 3.2 通过 factor_display 声明自己的因子构成；旧版 11 因子面板走兼容分支。
    factor_rows = panic.get("factor_display")
    if isinstance(factor_rows, list) and factor_rows:
        factors = "".join(
            f'<span class="sent-factor">'
            f'{_format_factor(str(row.get("name")), row.get("value"), str(row.get("kind") or "raw"))}'
            f'</span>'
            for row in factor_rows if isinstance(row, dict)
        )
    else:
        factor_names = ["空间", "次高", "涨停", "跌停", "首板", "连板", "炸板率", "成交量", "红盘数", "昨连板", "昨涨停"]
        factors = "".join(
            f'<span class="sent-factor">{_format_factor(name, components.get(name))}</span>'
            for name in factor_names
        )
    formula_label = str(
        panic.get("model_label") or "11因子公式 · 百分比按小数参与 · 成交量=亿元"
    )
    data_date = panic.get("data_date") or panic.get("date") or ""
    note = panic.get("note") or ""
    note_html = f'<span class="sent-note">{esc(note)}</span>' if note else ""
    regime = str(panic.get("regime") or "")
    regime_html = ""
    if regime:
        regime_html = (
            f'<span class="sent-factor">环境 {esc(regime)}'
            f'{"·年线上" if regime == "Bull" else "·年线下"}</span>'
        )

    return f'''<div class="sent-box">
  <div class="sent-main">
    <div class="sent-lbl">市场温度 S</div>
    <div class="sent-val">{score_text}</div>
    <div class="sent-desc" style="color:{_sentiment_color(phase)}">{esc(cycle_label)}</div>
  </div>
  <div class="sent-deltas">
    <div><span>Δ1 速度</span><b>{format_delta(_safe_float(delta1))}</b></div>
    <div><span>Δ2 加速度</span><b>{format_delta(_safe_float(delta2))}</b></div>
  </div>
  <div class="sbar"><div class="sfill" style="width:{score_width:.1f}%"></div></div>
  <div class="sent-formula">{esc(formula_label)} {note_html}</div>
  <div class="sent-factors">{regime_html}{factors}</div>
  {render_lianban_strip(lianban or {})}
  <div class="sent-date">数据日期 {esc(data_date) or "—"}</div>
</div>'''


def fetch_sentiment_chart_data(panic: dict | None = None) -> tuple:
    """读取市场温度公式产生的历史序列，不再用上证涨跌幅伪造情绪分数。"""
    entries = []
    if isinstance(panic, dict):
        entries = panic.get("history", []) or []
    if not entries:
        history = load_json("sentiment_history.json")
        entries = history.get("history", []) if isinstance(history, dict) else []

    by_date = {}
    for item in entries:
        if not isinstance(item, dict) or not item.get("date"):
            continue
        score = _safe_float(item.get("score"))
        if score is not None:
            by_date[str(item["date"])] = item

    if not by_date and isinstance(panic, dict):
        score = _safe_float(panic.get("score"))
        date = panic.get("data_date") or panic.get("date")
        if score is not None and date:
            by_date[str(date)] = {
                "date": str(date),
                "score": score,
                "cycle_label": panic.get("cycle_label", ""),
            }

    selected = [by_date[key] for key in sorted(by_date)][-14:]
    scores = [round(_safe_float(item.get("score"), 0), 1) for item in selected]
    labels = [str(item.get("date", ""))[5:] for item in selected]
    phases = [item.get("cycle_label", "") for item in selected]
    return scores, labels, phases


# 情绪六阶段（A股超短情绪温度模型 3.2）：修复→升温→高潮→降温→退潮→冰点
PHASE_STAGE_ORDER = ("冰点", "退潮", "降温", "修复", "升温", "高潮")
# 柱状图阶段配色：同一红色系（报刊主色）的六级深浅——冰点最浅、高潮最深，
# 只用明度区分阶段，不再用六种色相。
PHASE_COLORS = {
    "冰点": "#f0d0c2",
    "退潮": "#e3a68f",
    "降温": "#d47a5f",
    "修复": "#bf4a32",
    "升温": "#9d2318",
    "高潮": "#76140d",
}


def stage_of_phase(label) -> str:
    """从「阶段｜动能」标签里取出六阶段名；取不到返回空串（不猜阶段）。

    只在分隔符前的片段里匹配：像「降温｜退潮加速」「退潮｜下跌收敛/退潮衰竭」这类
    标签，动能词里也带「退潮」，整串匹配会把阶段判错。
    """
    text = str(label or "")
    head = re.split(r"[｜|（(]", text)[0].strip()
    for stage in PHASE_STAGE_ORDER:
        if stage in head:
            return stage
    return ""


# ===== HTML生成辅助函数 =====

def mc_cls(chg):
    value = _safe_float(chg, 0)
    return "up" if value > 0 else "dn"

def arrow(chg):
    value = _safe_float(chg, 0)
    return "▲" if value > 0 else "▼"

def badge_cls(ntype):
    return {"利好": "br", "利空": "bo", "中性": "bbl"}.get(ntype, "bbl")

def ind_cls(industry):
    mapping = {
        "半导体": "br", "存储": "br", "AI": "bcy", "算力": "bbl",
        "光模块": "bcy", "光纤": "bcy", "PCB": "bcy", "MLCC": "bgd",
        "铜箔": "bgd", "氟化工": "bo", "券商": "bbl", "养殖": "bo",
        "风电": "bcy", "机器人": "bcy", "航天": "bbl",
    }
    return mapping.get(industry, "bbl")

def infer_industry(title):
    for kw in ["半导体", "存储", "AI", "算力", "光模块", "光纤", "PCB", "MLCC",
               "铜箔", "氟化工", "券商", "养殖", "风电", "机器人", "航天"]:
        if kw in title:
            return kw
    return "综合"


# ===== AI 总结引擎（DeepSeek / OpenAI 兼容） =====

def ai_summarize_opinions(raw_text: str, context: str = "博主观点", max_retries: int = 1) -> str:
    """
    用 LLM 对博主原始口语化内容做语义级总结提炼。
    输入：Whisper转录/跟帖原始文本（口语化、碎片化）
    输出：1-3句精炼投资观点（书面语、可读性强、含核心逻辑）

    优先使用 DeepSeek API，兜底使用 OpenAI 兼容接口。
    若 API 不可用返回空串，由调用方明确标记失败；抖音可展示带来源标签的转录摘录。
    """
    global _AI_CREDENTIAL_REJECTED

    if not raw_text or len(raw_text.strip()) < 10:
        return ""

    # 凭证已被服务端拒绝过：本进程内不再重复发起请求
    if _AI_CREDENTIAL_REJECTED:
        return ""

    if api_summary_config() is None:
        return summarize_tasks([(raw_text, context)])[0]

    prompt = f"""你是一位专业的A股投资观点提炼师。请从以下{context}原始内容中，提炼出1-3句精炼的投资观点。

输入可能是语音转写文本，存在同音错字（例如"偷看"=token、"米子"=小米、
"存主/存处"=存储、"布恩斯坦"=伯恩斯坦）。请在内部按上下文纠正转写错误，
但不要把纠错过程或错字对照写进结论。

要求：
1. 用书面语，不要口语化表达
2. 每句话必须包含具体判断（看多/看空/中性）和核心逻辑（为什么）
3. 提及的具体标的/板块用【】标注，如【半导体】【江波龙】
4. 去掉所有无信息量的口语填充（"兄弟们""怎么说呢""就是说"等）
5. 去掉互动引导（"点赞关注""评论区见"等）
6. 只使用原文确实出现过的标的与板块，不要补充原文没提到的个股
7. 如果原文确实没有投资观点，输出"无明确观点"；不要用"内容杂乱/无法提炼"之类的空话代替结论
8. 总字数控制在80字以内

原始内容：
{raw_text[:2000]}

请直接输出提炼后的观点，不要加前缀说明："""

    try:
        result = call_api_text(prompt, max_tokens=200, temperature=0.3, timeout=15)
        # 清理：去掉可能的引号包裹
        result = result.strip('"\'“”‘’')
        return normalize_ai_summary(result)
    except Exception as exc:
        message = str(exc)
        if "credentials rejected" in message:
            # 凭证无效/无权限：重试没有意义，直接指向修复动作
            _AI_CREDENTIAL_REJECTED = True
            print(
                f"  [⛔] AI凭证被拒绝：{message}\n"
                "       请更新环境变量中的 DAILY_BRIEFING_AI_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY",
                file=sys.stderr,
            )
            return ""
        print(f"  [WARN] AI总结失败: {message}", file=sys.stderr)
    return ""


def ai_summarize_yanbao(report: dict, max_retries: int = 1) -> str:
    """把研报标题 + 评级改写成一句「驱动因素 → 受益方向」的核心逻辑。

    硬约束：只能使用接口给出的字段，禁止补充任何给定信息之外的事实。
    标题本身看不出逻辑时，只做同义改写，不做推断。
    """
    global _AI_CREDENTIAL_REJECTED

    title = str(report.get("title") or "").strip()
    if len(title) < 4:
        return ""
    if _AI_CREDENTIAL_REJECTED:
        return ""

    if api_summary_config() is None:
        return summarize_tasks([(json.dumps(report, ensure_ascii=False), "机构研报正文与核心逻辑")])[0]

    rating = str(report.get("rate") or "")
    change = str(report.get("ratingChangeText") or "")
    prompt = f"""你是一位券商研报编辑。下面是一份研报的元数据，请把它的要点改写成 1-2 句书面化的核心逻辑。

硬性要求（必须遵守）：
1. 只能使用下面给出的信息，**绝对不允许**补充任何未给出的数据、订单、政策、价格、业绩数字
2. 如果标题只是口号式短语、看不出因果逻辑，就只做同义改写，不要自行推断原因
3. 句式尽量是「驱动因素 → 受益方向」，并保留评级口径
4. 总字数不超过 60 字，直接输出结果，不要任何前缀说明

机构：{report.get('org', '')}
标的：{report.get('stock', '')} {report.get('code', '')}
行业：{report.get('industry', '')}
评级：{rating}{('（' + change + '）') if change else ''}
标题：{title}
"""

    try:
        result = call_api_text(prompt, max_tokens=160, temperature=0.2, timeout=20)
        return result.strip('"\'“”‘’')
    except Exception as exc:
        message = str(exc)
        if "credentials rejected" in message:
            _AI_CREDENTIAL_REJECTED = True
            print(f"  [⛔] 研报AI凭证被拒绝：{message}", file=sys.stderr)
            return ""
        print(f"  [WARN] 研报AI失败: {message}", file=sys.stderr)
    return ""


def ai_summarize_yanbao_parallel(reports: list) -> list:
    """并发为研报生成核心逻辑；返回与输入等长的字符串列表（失败为空串）。"""
    if not reports:
        return []
    results = [""] * len(reports)
    pending = []
    for index, report in enumerate(reports):
        stored = str(report.get("logic") or "").strip()
        title = str(report.get("title") or "").strip()
        if stored and stored != title:
            results[index] = stored
        else:
            pending.append((index, report))
    if not pending:
        return results
    if api_summary_config() is None:
        generated = summarize_tasks([(json.dumps(report, ensure_ascii=False), "机构研报正文与核心逻辑") for _, report in pending])
        for (index, _), summary in zip(pending, generated):
            results[index] = summary
        return results

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(ai_summarize_yanbao, report): index
                   for index, report in pending}
        for future in concurrent.futures.as_completed(futures):
            index = futures[future]
            try:
                results[index] = future.result() or ""
            except Exception:
                results[index] = ""
    return results


def ai_summarize_blogger_batch(blogger_name: str, all_texts: list, context_type: str = "淘股吧") -> dict:
    """
    批量总结单个博主的所有内容（主帖+跟帖），返回结构化结果。
    必须使用AI总结，失败时重试最多3次，仍失败则报错停止。
    """
    combined = "\n".join(t for t in all_texts if t)

    # 提取标的（从原始文本，不受AI总结影响）
    symbols = extract_symbols_from_text(combined)

    # 判断方向（从原始文本关键词计数）
    bull_signals = sum(1 for kw in ["看多", "看涨", "利好", "乐观", "涨", "反弹", "企稳",
                      "止跌", "机会", "买入", "加仓", "首选", "强", "突破", "超预期"]
                      if kw in combined)
    bear_signals = sum(1 for kw in ["看空", "看跌", "利空", "悲观", "跌", "恐慌", "风险",
                      "回避", "减仓", "弱", "破位", "不及预期", "杀跌", "暴跌"]
                      if kw in combined)
    if bull_signals > bear_signals + 2:
        direction = "看多"
    elif bear_signals > bull_signals + 2:
        direction = "看空"
    else:
        direction = "中性"

    # AI 总结（重试最多3次）
    ai_summary = ""
    for attempt in range(3):
        ai_summary = ai_summarize_opinions(combined, context=f"{context_type}博主{blogger_name}的投资观点")
        if ai_summary:
            break
        print(f"  [WARN] AI总结失败（{context_type}/{blogger_name}），重试 {attempt+1}/3...", file=sys.stderr)

    if ai_summary:
        # 从AI总结中提取【】标注的标的，补充到symbols
        extra_symbols = re.findall(r'【([^】]+)】', ai_summary)
        for s in extra_symbols:
            if s not in symbols:
                symbols.append(s)
        summary = ai_summary
    else:
        # AI总结3次均失败，报错停止（禁止回退到正则提取或原文截断）
        print(f"  [⛔] AI总结3次均失败（{context_type}/{blogger_name}），DEEPSEEK_API_KEY可能无效或额度不足，无法生成合格简报", file=sys.stderr)
        summary = f"[AI总结失败-{blogger_name}]"

    return {
        "summary": summary,
        "symbols": symbols[:6],
        "direction": direction,
        "used_ai": bool(ai_summary),
    }


def ai_summarize_batch_parallel(tasks: list) -> list:
    """
    并发批量调用 AI 总结，避免串行拖慢编译。
    tasks: [(raw_text, context), ...]
    返回: [ai_summary_str, ...]  与 tasks 一一对应
    """
    import concurrent.futures

    if api_summary_config() is None:
        return summarize_tasks(tasks)

    def _call(task):
        raw_text, context = task
        return ai_summarize_opinions(raw_text, context)

    results = [""] * len(tasks)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_call, t): i for i, t in enumerate(tasks)}
        try:
            for future in concurrent.futures.as_completed(futures, timeout=90):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception:
                    results[idx] = ""
        except concurrent.futures.TimeoutError:
            # 服务端偶尔变慢：保留已完成的摘要，未完成的按"无摘要"处理，
            # 由调用方按既有规则标注，而不是让整次编译崩掉。
            print("  [WARN] AI批量总结超时（90s），未完成的条目按无摘要处理", file=sys.stderr)
            for future, idx in futures.items():
                if results[idx]:
                    continue
                if future.done():
                    try:
                        results[idx] = future.result()
                    except Exception:
                        results[idx] = ""
    return results


# ===== 总结提炼引擎 =====

# 繁简转换（优先使用 zhconv 库，兜底手动映射）
try:
    from zhconv import convert as _zhconv_convert
    def trad_to_simp(text: str) -> str:
        """繁体转简体（zhconv）"""
        try:
            return _zhconv_convert(text, 'zh-cn')
        except Exception:
            return text
except ImportError:
    # 兜底：手动映射（覆盖常见字）
    _SIMP_MAP = {
        '說': '说', '買': '买', '賣': '卖', '漲': '涨', '賺': '赚',
        '虧': '亏', '導': '导', '體': '体', '時': '时', '長': '长',
        '點': '点', '錢': '钱', '銀': '银', '機': '机', '構': '构',
        '產': '产', '業': '业', '電': '电', '網': '网', '絡': '络',
        '聯': '联', '數': '数', '據': '据', '設': '设', '備': '备',
        '車': '车', '場': '场', '總': '总', '結': '结', '變': '变',
        '創': '创', '開': '开', '驗': '验', '證': '证', '預': '预',
        '實': '实', '歷': '历', '經': '经', '營': '营', '費': '费',
        '務': '务', '種': '种', '廠': '厂', '質': '质', '規': '规',
        '戰': '战', '義': '义', '權': '权', '資': '资', '運': '运',
        '環': '环', '壓': '压', '額': '额', '億': '亿', '關': '关',
        '鍵': '键', '統': '统', '計': '计', '劃': '划', '還': '还',
        '過': '过', '這': '这', '裡': '里', '裏': '里', '為': '为',
        '與': '与', '對': '对', '從': '从', '來': '来', '個': '个',
        '們': '们', '會': '会', '將': '将', '應': '应', '當': '当',
        '沒': '没', '於': '于', '後': '后', '問': '问', '題': '题',
        '國': '国', '際': '际', '區': '区', '東': '东', '進': '进',
        '現': '现', '發': '发', '達': '达', '轉': '转', '單': '单',
        '讓': '让', '給': '给', '請': '请', '誰': '谁', '麼': '么',
        '嗎': '吗', '著': '着', '確': '确', '認': '认', '識': '识',
        '語': '语', '讀': '读', '論': '论', '調': '调', '試': '试',
        '極': '极', '強': '强', '優': '优', '勢': '势', '態': '态',
        '擴': '扩', '張': '张', '縮': '缩', '減': '减', '續': '续',
        '斷': '断', '獨': '独', '舊': '旧', '舉': '举', '辦': '办',
        '歲': '岁', '書': '书', '寫': '写', '學': '学', '覺': '觉',
        '見': '见', '觀': '观', '評': '评', '價': '价', '報': '报',
        '貨': '货', '幣': '币', '財': '财', '飛': '飞', '龍': '龙',
        '鐵': '铁', '鋼': '钢', '銅': '铜', '鋁': '铝', '風': '风',
        '氣': '气', '雲': '云', '歡': '欢', '樂': '乐', '驚': '惊',
        '懼': '惧', '懷': '怀', '憂': '忧', '憤': '愤', '幾': '几',
        '兩': '两', '並': '并', '亞': '亚', '僅': '仅', '擊': '击',
        '擔': '担', '擇': '择', '擁': '拥', '擴': '扩', '擾': '扰',
        '裝': '装', '處': '处', '複': '复', '雜': '杂', '穀': '谷',
        '麥': '麦', '麵': '面', '飯': '饭', '飲': '饮', '馬': '马',
        '鳥': '鸟', '魚': '鱼', '蟲': '虫', '鳳': '凤', '貧': '贫',
        '窮': '穷', '撐': '撑', '擱': '搁', '擲': '掷', '擷': '撷',
        '擺': '摆', '擼': '撸',
    }
    def trad_to_simp(text: str) -> str:
        """繁体转简体（兜底）"""
        result = []
        for ch in text:
            result.append(_SIMP_MAP.get(ch, ch))
        return "".join(result)


# ===== 标的/板块关键词库 =====
SECTOR_KEYWORDS = {
    "半导体": ["半导体", "芯片", "晶圆", "封测", "光刻", "EDA", "功率器件", "MOSFET", "IGBT",
              "国产替代", "设备", "北方华创", "中微公司", "长电科技", "通富微电", "华天科技",
              "兆易创新", "紫光", "寒武纪", "中芯国际", "长鑫"],
    "存储": ["存储", "DRAM", "NAND", "HBM", "美光", "海力士", "三星", "长鑫", "江波龙",
            "佰维存储", "德明利", "东芯", "兆易"],
    "AI算力": ["AI", "算力", "GPU", "英伟达", "NVIDIA", "Blackwell", "光模块", "1.6T",
              "中际旭创", "新易盛", "天孚通信", "光迅科技", "交换机", "交换芯片",
              "算力租赁", "IDC", "液冷", "铜缆", "沃尔"],
    "光通信": ["光通信", "光纤", "光棒", "MPO", "光连接", "特发信息", "烽火通信",
              "光芯片", "LITE", "CPO", "光子"],
    "PCB/覆铜板": ["PCB", "覆铜板", "铜箔", "东山精密", "生益科技", "诺德股份", "建滔",
                 "沪电股份", "深南电路", "兴森科技"],
    "机器人": ["机器人", "宇树", "具身智能", "人形机器人", "减速器", "伺服", "传感器",
             "CCXI", "TSLA", "特斯拉"],
    "创新药": ["创新药", "医药", "生物", "CXO", "药明", "恒瑞", "百济", "信达"],
    "新能源车": ["新能源车", "锂电池", "宁德时代", "比亚迪", "充电桩", "整车"],
    "消费/潮玩": ["消费", "潮玩", "零售", "白酒", "食品", "旅游"],
    "军工/航天": ["航天", "军工", "商业航天", "火箭", "卫星", "导弹"],
    "金融/券商": ["券商", "银行", "保险", "金融", "东方财富", "中信证券"],
    "风电": ["风电", "金风科技", "东方电缆", "海风", "叶片"],
    "MLCC/被动元件": ["MLCC", "被动元件", "风华高科", "三环集团", "电容", "电阻"],
    "氟化工": ["氟化工", "六氟磷酸锂", "多氟多", "永和股份", "配额"],
}

# 个股关键词（精确匹配）
STOCK_KEYWORDS = {
    "北方华创": "002371", "中微公司": "688012", "长电科技": "600584",
    "通富微电": "002156", "华天科技": "002185", "兆易创新": "603986",
    "中际旭创": "300308", "新易盛": "300502", "天孚通信": "300394",
    "东山精密": "002384", "生益科技": "600183", "诺德股份": "600110",
    "特发信息": "000070", "宁德时代": "300750", "比亚迪": "002594",
    "风华高科": "000636", "多氟多": "002407", "永和股份": "605020",
    "金风科技": "002202", "东方电缆": "603606", "紫光国微": "002049",
    "寒武纪": "688256", "中芯国际": "688981", "江波龙": "301308",
    "佰维存储": "688525", "雅克科技": "002409", "太极实业": "600667",
    "和远气体": "002971", "南大光电": "300346", "金海通": "603061",
    "深南电路": "002916", "沪电股份": "002463", "光迅科技": "002281",
    "烽火通信": "600498", "药明康德": "603259", "恒瑞医药": "600276",
    "东方财富": "300059", "中信证券": "600030", "三环集团": "300408",
    "兴森科技": "002436", "德明利": "001309", "长鑫科技": "688825",
}


def extract_symbols_from_text(text: str) -> list:
    """从文本中提取标的/板块关键词"""
    text = trad_to_simp(text)
    found = []
    seen = set()
    # 先匹配个股（更精确）
    for name, code in STOCK_KEYWORDS.items():
        if name in text and name not in seen:
            found.append(name)
            seen.add(name)
    # 再匹配板块
    for sector, keywords in SECTOR_KEYWORDS.items():
        if sector not in seen:
            for kw in keywords:
                if kw in text:
                    found.append(sector)
                    seen.add(sector)
                    break
    return found[:6]


# ===== 投资观点句提取 =====
# 匹配包含投资判断的句式
_OPINION_PATTERNS = [
    # 明确方向判断
    r'(?:看多|看空|看涨|看跌|偏多|偏空|乐观|悲观|利好|利空)[^。，；！？]{2,30}',
    # 趋势判断
    r'(?:趋势|方向|走势|行情|周期|阶段)[^。，；！？]{0,6}(?:向上|向下|反转|延续|加速|见底|见顶|企稳|突破)[^。，；！？]{0,20}',
    # 逻辑判断
    r'(?:因为|由于|逻辑|原因|驱动|催化)[^。，；！？]{2,40}',
    # 操作建议
    r'(?:建议|关注|重点|优先|首选|回避|警惕|注意|等待|观察)[^。，；！？]{2,30}',
    # 涨跌判断
    r'(?:涨价|降价|提价|调价|紧缺|过剩|供需|扩产|减产|产能)[^。，；！？]{2,30}',
    # 估值判断
    r'(?:估值|PE|PB|市值|低估|高估|合理|泡沫)[^。，；！？]{2,25}',
    # 业绩判断
    r'(?:业绩|营收|利润|盈利|超预期|不及预期|增长|下滑)[^。，；！？]{2,30}',
    # 市场情绪
    r'(?:恐慌|贪婪|情绪|冰点|高潮|分歧|共识|一致)[^。，；！？]{2,25}',
    # 周期位置
    r'(?:周期|位置|阶段|拐点|底部|顶部|起点|终点)[^。，；！？]{0,6}(?:到了|在|处于|接近|还没|已经)[^。，；！？]{0,20}',
]

# 噪声句式（过滤掉无信息量的口语）
_NOISE_PATTERNS = [
    r'^[嗯啊哦呀哈嘿哎吧呢么嘛]+$',  # 纯语气词
    r'^.{0,3}$',  # 太短
    r'(?:怎么说呢|反正|就是说|怎么说|你想想|你就想|说白了|说真的|说实话)',  # 口语填充
    r'(?:点击|关注|点赞|转发|收藏|订阅|评论)',  # 互动引导
    r'(?:视频|直播|节目|频道|粉丝)',  # 自我引用
]


def extract_opinion_sentences(text: str, max_sentences: int = 4) -> list:
    """从文本中提取投资观点句"""
    text = trad_to_simp(text)
    # 按标点分句
    sentences = re.split(r'[。，；！？\n]', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 4]

    results = []
    for s in sentences:
        # 跳过噪声
        if any(re.search(p, s) for p in _NOISE_PATTERNS):
            continue
        # 匹配观点句
        for pat in _OPINION_PATTERNS:
            m = re.search(pat, s)
            if m:
                opinion = m.group(0).strip()
                if len(opinion) > 6 and opinion not in [r[:len(opinion)] for r in results]:
                    results.append(opinion)
                break

    # 如果观点句不够，补充高赞/高信息量句子
    if len(results) < max_sentences:
        for s in sentences:
            if s in results or any(r in s for r in results):
                continue
            # 高信息量特征：含数字、含关键词
            has_number = bool(re.search(r'\d+\.?\d*%?', s))
            has_keyword = any(kw in s for kw in ["涨", "跌", "买", "卖", "仓", "板",
                "停", "破", "新", "高", "低", "强", "弱", "量", "价", "期", "利"])
            if has_number or has_keyword:
                results.append(s[:60])
                if len(results) >= max_sentences:
                    break

    return results[:max_sentences]


def summarize_tgb_blogger(name: str, data: dict) -> dict:
    """总结提炼淘股吧博主观点（只接受AI语义总结）。"""
    posts = data.get("posts", [])
    replies = data.get("top_replies", [])
    replies_today = data.get("replies_today", 0)

    all_text = []
    post_titles = []

    # 主帖
    for p in posts:
        title = p.get("title", "")
        if title:
            post_titles.append(title)
        content = p.get("content", "")
        if content:
            all_text.append(content)

    # 跟帖（取前10条高赞）
    for r in replies[:10]:
        content = r.get("content", "")
        if content:
            all_text.append(content)

    if not all_text:
        return {
            "name": name,
            "has_content": False,
            "post_title": "",
            "summary": "目标日无可核验内容",
            "symbols": [],
            "direction": "中性",
        }

    # 使用 AI 批量总结
    result = ai_summarize_blogger_batch(name, all_text, context_type="淘股吧")

    return {
        "name": name,
        "has_content": True,
        "post_title": post_titles[0] if post_titles else "",
        "summary": result["summary"],
        "symbols": result["symbols"],
        "direction": result["direction"],
        "replies_today": replies_today,
        "has_posts": bool(posts),
        "used_ai": result["used_ai"],
    }


def _transcript_excerpt(text: str, limit: int = 180) -> str:
    """生成明确标注的转录摘录；不把未经 AI 总结的文本伪装成观点结论。"""
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip("，。；、 ") + "…"


def summarize_douyin_video(video: dict) -> dict:
    """总结抖音视频；无 AI 时展示带来源标记的真实转录摘录。"""
    title = video.get("title", "")
    transcript = video.get("transcript", "")
    fallback_text = video.get("fallback_text", "")
    summary_raw = video.get("summary", "")
    symbols_raw = video.get("symbols", [])
    direction_raw = video.get("direction", "关注")
    warning = video.get("warning", "")

    # 转简体
    title_s = trad_to_simp(title)
    transcript_s = trad_to_simp(transcript) if transcript else ""

    # 标的可从视频标题、话题或已由采集器核验的字段提取。
    symbols = extract_symbols_from_text(f"{transcript_s} {fallback_text} {title_s}")
    for s in symbols_raw:
        if s not in symbols:
            symbols.append(s)
    symbols = symbols[:6]

    # 优先使用采集器已生成的AI摘要；没有摘要时再调用AI。
    ai_configured = semantic_summary_available()
    ai_summary = summary_raw
    if not ai_summary and ai_configured:
        ai_summary = ai_summarize_opinions(transcript_s, context="抖音博主视频观点")

    if ai_summary:
        # 从AI总结中提取【】标注的标的，补充到symbols
        extra_symbols = re.findall(r'【([^】]+)】', ai_summary)
        for s in extra_symbols:
            if s not in symbols:
                symbols.append(s)
        symbols = symbols[:6]
        summary = ai_summary
        used_ai = True
    else:
        if transcript_s:
            summary = f"转录摘录（未使用AI）：{_transcript_excerpt(transcript_s)}"
        else:
            summary = f"标题/话题线索：{fallback_text or title_s}（AI语义总结失败，未展示原始转录）"
        used_ai = False

    # 判断方向（基于转录内容重新判断）
    if transcript_s:
        bull_signals = sum(1 for kw in ["看多", "看涨", "利好", "乐观", "涨", "反弹",
                          "机会", "买入", "首选", "强", "突破", "超预期", "涨价",
                          "扩产", "紧缺", "需求", "增长"]
                          if kw in transcript_s)
        bear_signals = sum(1 for kw in ["看空", "看跌", "利空", "悲观", "跌", "恐慌",
                          "风险", "回避", "弱", "破位", "杀跌", "暴跌", "降价",
                          "过剩", "减产"]
                          if kw in transcript_s)
        if bull_signals > bear_signals + 2:
            direction = "利好"
        elif bear_signals > bull_signals + 2:
            direction = "利空"
        else:
            direction = "关注"
    else:
        direction = direction_raw

    return {
        "title": title_s[:50],
        "url": video.get("url", ""),
        "summary": summary,
        "symbols": symbols,
        "direction": direction,
        "warning": warning,
        "used_ai": used_ai,
    }


def render_survey_section(survey: dict, data_note: str = "") -> str:
    """Render the blogger survey with an honest empty/error state."""
    survey = survey if isinstance(survey, dict) else {}
    stats = survey.get("statistics") if isinstance(survey.get("statistics"), dict) else {}
    analyses = survey.get("analyses") if isinstance(survey.get("analyses"), list) else []
    status = str(survey.get("status") or "").lower()
    note = str(survey.get("note") or "").strip()
    total = int(stats.get("total_analyses", len(analyses)) or 0)
    if status in {"error", "failed", "failure"} or survey.get("error"):
        reason = note or str(survey.get("error") or "未知错误")
        return f'''<section class="sec">
<div class="sh"><span class="ico">◉</span> 博主多空统计 <span class="meta">数据获取失败</span></div>
<div class="lbox" style="color:var(--wrn)">数据获取失败：{esc(reason)}</div>
</section>'''
    if total <= 0:
        reason = note or "暂无有效观点；未使用旧缓存"
        return f'''<section class="sec">
<div class="sh"><span class="ico">◉</span> 博主多空统计 <span class="meta">0位有效观点{data_note}</span></div>
<div class="lbox" style="color:var(--t3)">暂无有效观点：{esc(reason)}</div>
</section>'''

    def count(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    market = stats.get("by_market", {}) or {}
    bull = count(market.get("bull"))
    bear = count(market.get("bear"))
    neutral = count(market.get("neutral"))
    market_total = bull + bear + neutral
    ratio = f"{bull / bear:.2f}" if bear > 0 else ("无看空样本" if bull > 0 else "暂无有效样本")
    bull_pct = bull / market_total * 100 if market_total else 0
    bear_pct = bear / market_total * 100 if market_total else 0
    neutral_pct = neutral / market_total * 100 if market_total else 0
    if bull_pct >= 60:
        gauge_color, gauge_label = "var(--up)", "偏多"
    elif bear_pct >= 40:
        gauge_color, gauge_label = "var(--dn)", "偏空"
    else:
        gauge_color, gauge_label = "var(--inf)", "分歧"

    circumference = 2 * 3.14159 * 40
    bull_dash = circumference * bull_pct / 100
    bear_dash = circumference * bear_pct / 100
    neutral_dash = circumference * neutral_pct / 100
    gauge_svg = f'''<svg viewBox="0 0 100 100">
<circle class="ring-bg" cx="50" cy="50" r="40"/>
<circle class="ring-fill bull" cx="50" cy="50" r="40" stroke-dasharray="{bull_dash} {circumference - bull_dash}"/>
<circle class="ring-fill bear" cx="50" cy="50" r="40" stroke-dasharray="{bear_dash} {circumference - bear_dash}" stroke-dashoffset="{-bull_dash}"/>
<circle class="ring-fill neutral" cx="50" cy="50" r="40" stroke-dasharray="{neutral_dash} {circumference - neutral_dash}" stroke-dashoffset="{-(bull_dash + bear_dash)}"/>
</svg>'''

    sector_bars = []
    for sector_data in (stats.get("by_sector_sorted", []) or [])[:10]:
        if not isinstance(sector_data, dict):
            continue
        sbull = count(sector_data.get("bull"))
        sbear = count(sector_data.get("bear"))
        sneutral = count(sector_data.get("neutral"))
        sector_total = max(sbull + sbear + sneutral, 1)
        labels = []
        if sbull: labels.append(f"▲{sbull}")
        if sbear: labels.append(f"▼{sbear}")
        if sneutral: labels.append(f"—{sneutral}")
        sector_bars.append(f'''<div class="survey-sector-row">
<span class="survey-sector-name">{esc(sector_data.get("sector"))}</span>
<div class="survey-sector-bar"><div class="bar-bull" style="width:{sbull / sector_total * 100:.1f}%"></div><div class="bar-bear" style="width:{sbear / sector_total * 100:.1f}%"></div><div class="bar-neutral" style="width:{sneutral / sector_total * 100:.1f}%"></div><span class="bar-label">{' / '.join(labels)}</span></div>
<span class="survey-sector-count">{count(sector_data.get('blogger_count'))}人</span></div>''')

    platform_cards = []
    for platform, pdata in (stats.get("by_platform", {}) or {}).items():
        if not isinstance(pdata, dict):
            continue
        pbull, pbear, pneutral = count(pdata.get("bull")), count(pdata.get("bear")), count(pdata.get("neutral"))
        pratio = f"{pbull / pbear:.1f}" if pbear else ("无看空样本" if pbull else "暂无有效样本")
        platform_cards.append(f'''<div class="survey-plat-card"><span class="survey-plat-name">{esc(platform)}</span><div class="survey-plat-stats"><span class="sp-bull">{pbull}</span><span class="sp-sep">/</span><span class="sp-bear">{pbear}</span><span class="sp-neutral">({pneutral})</span></div><span class="survey-plat-meta">{count(pdata.get('blogger_count'))}位博主 · 多空比 <b>{esc(pratio)}</b></span></div>''')

    conclusions = []
    if note:
        conclusions.append(note)
    top_sectors = stats.get("by_sector_sorted", []) or []
    if top_sectors and isinstance(top_sectors[0], dict):
        conclusions.append(f"最大共识方向：{top_sectors[0].get('sector', '')}（{count(top_sectors[0].get('blogger_count'))}人提及）")
    return f'''<section class="sec">
<div class="sh"><span class="ico">◉</span> 博主多空统计 <span class="meta">{total}位有效观点 · {esc(ratio)}多空比{data_note}</span></div>
<div class="survey-wrap"><div class="survey-top"><div class="survey-gauge"><span class="survey-gauge-title">A股大盘采样观点</span><div class="survey-gauge-ring">{gauge_svg}<div class="survey-gauge-center"><span class="survey-gauge-val" style="color:{gauge_color}">{gauge_label}</span><span class="survey-gauge-label">{market_total}人</span></div></div><div class="survey-gauge-legend"><span><i class="dot-bull"></i>看多{bull}</span><span><i class="dot-bear"></i>看空{bear}</span><span><i class="dot-neutral"></i>中性{neutral}</span></div><div class="survey-gauge-ratio">多空比 <b>{esc(ratio)}</b></div></div><div class="survey-sectors"><span class="survey-sectors-title">涉及赛道的样本方向</span>{''.join(sector_bars)}</div></div><div class="survey-platforms">{''.join(platform_cards)}</div><div class="lbox"><b>结论：</b>{esc('；'.join(conclusions) or '暂无额外结论')}</div></div>
</section>'''


def build_strategy_items(news: dict, events: dict, panic: dict, tgb: dict,
                         tgb_summaries: list | None = None, lianban: dict | None = None) -> dict:
    """Derive strategy watch/risk text only from the current source payloads.

    风险提示只能引用已经过 AI 语义总结的博主结论，不能把口语原文当成观点
    交付；没有可用摘要时给出明确的空状态说明。
    """
    long_items, watch_items, risk_items = [], [], []
    # 连板网的当日主线与次日观察：放在最前面，它们是当日资金的真实落点
    if isinstance(lianban, dict) and lianban.get("status") == "ok":
        for sector in (lianban.get("main_sectors") or [])[:3]:
            name = str(sector.get("sector") or "").strip()
            if not name:
                continue
            count = sector.get("limit_up_count")
            leader = str(sector.get("leader") or "").strip()
            text = f"主线·{name}"
            if count is not None:
                text += f"（涨停{count}家"
                text += f"，龙头{leader}）" if leader else "）"
            elif leader:
                text += f"（龙头{leader}）"
            long_items.append(text)
        top_leader = str(lianban.get("top_leader") or "").strip()
        if top_leader:
            long_items.append(f"总龙头 {top_leader}")
    for item in (news.get("news", []) if isinstance(news, dict) else [])[:10]:
        if item.get("type") == "利好":
            title = str(item.get("title") or "")[:50]
            stocks = "、".join(str(s) for s in (item.get("stocks") or [])[:2])
            long_items.append(f"{title}（{stocks}）" if stocks else title)
    score = _safe_float(panic.get("score")) if isinstance(panic, dict) else None
    delta1 = _safe_float(panic.get("delta1")) if isinstance(panic, dict) else None
    delta2 = _safe_float(panic.get("delta2")) if isinstance(panic, dict) else None
    cycle = str(panic.get("cycle_label") or "市场温度数据不可用") if isinstance(panic, dict) else "市场温度数据不可用"
    # 温度跟踪行放首位：观察等待卡只渲染前 5 条，别被未来事件挤掉。
    if score is not None:
        watch_items.append(f"市场温度S {score:.1f}（Δ1 {format_delta(delta1)}，Δ2 {format_delta(delta2)}）：跟踪{cycle}")
    if isinstance(lianban, dict) and lianban.get("status") == "ok":
        for item in (lianban.get("watch_next") or [])[:3]:
            name = str(item.get("name") or "").strip()
            why = str(item.get("why") or "").strip()
            if name:
                watch_items.append(f"次日观察 {name}{'：' + why[:40] if why else ''}")
    # 有次日观察名单时压缩未来事件条数，保证观察卡 6 条上限内都能显示
    has_watch = bool(
        isinstance(lianban, dict) and lianban.get("status") == "ok" and lianban.get("watch_next")
    )
    for item in (events.get("events", []) if isinstance(events, dict) else [])[:2 if has_watch else 4]:
        if item.get("date") and item.get("event"):
            watch_items.append(f"{item.get('date')}：{str(item.get('event'))[:70]}")
    risk_keywords = ["跌停", "退潮", "恐慌", "风险", "暴跌", "大跌", "亏钱", "杀跌", "回调", "破位"]
    for summary in (tgb_summaries or []):
        text = str(summary or "").strip()
        if not text or text.startswith("[AI总结"):
            continue
        for sentence in re.split(r"[；;。]", text):
            sentence = sentence.strip()
            if sentence and any(kw in sentence for kw in risk_keywords):
                risk_items.append(sentence[:60])
    if not watch_items:
        watch_items.append("暂无带明确日期的未来事件或动能信号")
    if not long_items:
        long_items.append("暂无可核验的利好新闻标的")
    if not risk_items:
        risk_items.append("当前源无带风险语义的AI总结结论；不代表不存在风险")
    return {"long": long_items, "watch": watch_items, "risk": risk_items}


def build_html(today: str, trade_date: str) -> str:
    """从数据文件编译完整HTML"""

    # 加载所有数据
    news = load_json("news_today.json")
    panic = load_json("panic_today.json")
    events = load_json("events_today.json")
    yanbao = load_json("yanbao_latest.json")
    tgb = load_json("tgb_today.json")
    douyin = load_json("douyin_today.json")
    survey = load_json("sentiment_survey_today.json")
    lhb = load_json("lhb_today.json")
    # 连板网公开概况/主线/资金：作为现有板块的补充数据源（非替代）
    lianban = load_json("lianban_today.json")
    rotation = load_json("rotation_today.json")
    node_cycle = load_json("node_cycle_today.json")

    quote_path = DATA_DIR / "quote_today.html"
    quote_html = quote_path.read_text(encoding="utf-8") if quote_path.exists() else ""
    if not quote_html.strip():
        quote_html = '''<!-- 每日金句数据状态：error -->
<section class="quote-banner">
  <div class="quote-mark">!</div>
  <div class="quote-text">每日金句数据获取失败</div>
  <div class="quote-principle">名言数据文件缺失或为空；未使用样例名言。</div>
</section>'''

    # 读取CSS模板
    template = (BASE_DIR / 'templates' / 'briefing.html').read_text(encoding='utf-8')
    css_start = template.find("<style>")
    css_end = template.find("</style>")
    css_block = template[css_start:css_end + 8]

    # 日期显示
    dt = datetime.strptime(today, "%Y-%m-%d")
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]
    today_display = f"{today.replace('-', '.')} {weekday_cn}"
    data_note = f"（{trade_date}交易数据）" if today != trade_date else ""
    news_note = section_data_note(news, today)
    lhb_note = section_data_note(lhb, trade_date, trade_date)
    yanbao_note = section_data_note(yanbao, today, trade_date)
    survey_note = section_data_note(survey, today, trade_date)
    tgb_note = section_data_note(tgb, today, trade_date)
    douyin_note = section_data_note(douyin, today, trade_date)
    events_note = section_data_note(events, today)

    # 日期对不上的缓存不许进入渲染层：整段降级为"数据获取失败"，
    # 避免出现"标题写着失败、下面却列出别的日期条目"的误导画面。
    LIST_KEYS = (
        "news", "events", "opinions", "reports", "bloggers", "analyses",
        "top_net_buy", "top_net_sell", "top_institution_buy",
        "top_hot_money_buy", "top_hot_money_sell", "hot_money_groups",
        "key_stocks_detail", "main_themes", "entries",
    )

    def _enforce_freshness(data: dict, requested: str, fallback: str | None = None) -> dict:
        if not isinstance(data, dict) or not data:
            return data if isinstance(data, dict) else {}
        if section_has_live_data(data, requested, fallback):
            return data
        state, reason = dataset_state(data, requested, fallback)
        cleared = dict(data)
        for key in LIST_KEYS:
            if key in cleared:
                cleared[key] = [] if isinstance(cleared[key], list) else {}
        cleared["total_stocks"] = 0
        cleared["status"] = "error"
        cleared["note"] = (
            f"数据获取失败：{reason or data.get('note') or '未取得目标日数据'}；未使用其它日期内容"
        )
        return cleared

    news = _enforce_freshness(news, today)
    lhb = _enforce_freshness(lhb, trade_date, trade_date)
    survey = _enforce_freshness(survey, today, trade_date)
    tgb = _enforce_freshness(tgb, today, trade_date)
    douyin = _enforce_freshness(douyin, today, trade_date)
    events = _enforce_freshness(events, today)
    yanbao = _enforce_freshness(yanbao, today, trade_date)
    # 连板网补充数据：日期对不上就整体停用，避免把别的交易日盘面混进来
    lianban = _enforce_freshness(lianban, today, trade_date) if lianban else {}
    rotation = _enforce_freshness(rotation, today, trade_date) if rotation else {}

    # 指数数据
    index_snapshot = load_json("indices_today.json")
    indices = index_snapshot.get("indices") if index_snapshot.get("date") == today else None
    if not indices:
        indices = fetch_index_data(trade_date)
    index_cards = "".join(render_index_card(name, indices.get(name)) for name in ["上证", "科创50", "纳斯达克", "KOSPI"])
    index_errors = indices.get("_errors") if isinstance(indices.get("_errors"), dict) else {}
    dated = [
        (name, indices[name].get("data_date"))
        for name in ["上证", "科创50", "纳斯达克", "KOSPI"]
        if isinstance(indices.get(name), dict) and indices[name].get("data_date")
    ]
    unique_dates = sorted({str(date) for _, date in dated})
    if not dated:
        index_note = "指数数据获取失败"
    elif len(unique_dates) == 1:
        index_note = f"指数数据截至{unique_dates[-1]}"
    else:
        index_note = "指数数据日期：" + " / ".join(f"{name} {str(date)[5:]}" for name, date in dated)
    if index_errors:
        index_note += "（" + "、".join(index_errors) + "获取失败）"

    # 市场温度历史数据（与顶部 S 使用同一套公式）
    chart_scores, chart_labels, chart_phases = fetch_sentiment_chart_data(panic)

    # 柱状图标题里的交易日跨度要跟随真实历史长度，避免标签写得比样本更大
    if chart_scores:
        span_label = f"近{len(chart_scores)}个交易日" if len(chart_scores) > 1 else "最新一日"
        css_block = css_block.replace(
            "市场温度 · 阶段柱状", f"市场温度 · 阶段柱状（{span_label}）"
        )

    # 图例只列出当期真实出现过的阶段，顺序固定为六阶段顺序
    used_stages = [s for s in PHASE_STAGE_ORDER if any(stage_of_phase(p) == s for p in chart_phases)]
    chart_legend = "".join(
        f'<span class="cl-item"><i style="background:{PHASE_COLORS[s]}"></i>{s}</span>'
        for s in used_stages
    )
    if not chart_legend:
        chart_legend = '<span class="cl-item">情绪阶段标签缺失，柱子按统一色显示</span>'

    # ===== ① HERO =====
    hero = f"""<section class="hero">
<div class="hero-row1">
  {render_sentiment_summary(panic, lianban)}
  <div class="chart-box">
    <canvas id="sentChart"></canvas>
    <div class="chart-tip" id="chartTip"><div class="v"></div><div class="d"></div></div>
    <div class="chart-legend">{chart_legend}</div>
  </div>
</div>
<div class="ms">
{index_cards}
</div>
<div class="sent-date">{esc(index_note)}</div>
</section>"""

    # ===== ② 财经新闻 =====
    news_items = news.get("news", [])[:15]
    news_rows = []
    for n in news_items:
        raw_time = str(n.get("time", "") or "")
        time_str = raw_time[11:16] if len(raw_time) >= 16 and raw_time[4] == "-" else raw_time[:5]
        ntype = esc(n.get("type", "中性"))
        title = esc(n.get("title", ""))
        source = esc(n.get("source", ""))
        if n.get('url'):
            source = f'<a href="{esc(n["url"])}" target="_blank" rel="noopener">{source}</a>'
        if n.get('direction_reason'):
            title += f'<div class="t3">{esc(n["direction_reason"])}</div>'
        stock_tags = "".join(f' <span class="tag y">{esc(s)}</span>' for s in n.get("stocks", []) if s)
        news_rows.append(f'<tr><td class="tr">{esc(time_str)}</td><td><span class="{badge_cls(n.get("type", "中性"))}">{ntype}</span></td><td class="t2">{title}{stock_tags}</td><td class="t3">{source}</td></tr>')
    if not news_rows:
        news_rows = [f'<tr><td colspan="4" class="t3" style="text-align:center">{esc(news_note or "暂无可核验新闻，未使用其他日期内容")}</td></tr>']
    news_meta = section_meta(news, today, count=len(news_items), unit="条")
    news_sec = f"""<section class="sec">
<div class="sh"><span class="ico">◉</span> 财经科技新闻 <span class="meta">{news_meta}</span></div>
<table><colgroup><col style="width:56px"><col style="width:50px"><col><col style="width:60px"></colgroup>
<tr><th>时间</th><th>类型</th><th>标题</th><th>来源</th></tr>
{"".join(news_rows)}</table></section>"""

    # ===== ③½ 龙虎榜 =====
    lhb_total = lhb.get("total_stocks", 0)
    lhb_top_buy = lhb.get("top_net_buy", [])[:10]
    lhb_top_sell = lhb.get("top_net_sell", [])[:5]
    lhb_top_inst = lhb.get("top_institution_buy", [])[:8]
    lhb_hot_buy = lhb.get("top_hot_money_buy", [])[:8]
    lhb_hot_sell = lhb.get("top_hot_money_sell", [])[:5]
    lhb_groups = lhb.get("hot_money_groups", [])
    lhb_themes = lhb.get("main_themes", [])
    lhb_signals = lhb.get("key_signals", [])

    # 净买入TOP表格
    lhb_buy_rows = []
    for i, s in enumerate(lhb_top_buy):
        chg = _safe_float(s.get("涨跌幅"), 0)
        chg_cls = "up" if chg > 0 else "dn"
        chg_text = f"+{chg:.2f}%" if chg > 0 else f"{chg:.2f}%"
        net_buy = _safe_float(s.get("净买额亿"), 0)
        reason = esc(str(s.get("上榜原因", ""))[:16])
        jiedu = esc(str(s.get("解读", "")))
        lhb_buy_rows.append(
            f'<tr><td class="t2"><span class="tag r">{esc(s.get("名称", ""))}</span></td>'
            f'<td class="{chg_cls}">{chg_text}</td>'
            f'<td class="tb">{net_buy:.2f}</td>'
            f'<td class="t3">{reason}{(" · " + jiedu[:22]) if jiedu else ""}</td></tr>'
        )

    lhb_sell_rows = []
    for s in lhb_top_sell:
        chg = _safe_float(s.get("涨跌幅"), 0)
        net_sell = _safe_float(s.get("净卖额亿"), 0)
        lhb_sell_rows.append(f'<tr><td class="t2"><span class="tag r">{esc(s.get("名称", ""))}</span></td><td class="{mc_cls(chg)}">{chg:+.2f}%</td><td class="dn">-{net_sell:.2f}</td><td class="t3">{esc(str(s.get("上榜原因", ""))[:16])}</td></tr>')

    lhb_inst_rows = []
    for s in lhb_top_inst:
        inst_net = _safe_float(s.get("机构净买入亿"), 0)
        lhb_inst_rows.append(f'<tr><td class="t2">{esc(s.get("名称", ""))}</td><td class="up">{inst_net:+.2f}</td><td class="t3">买方{esc(s.get("买方机构数", 0))}家 · 卖方{esc(s.get("卖方机构数", 0))}家</td></tr>')

    # 游资席位TOP表格
    lhb_hot_rows = []
    for s in lhb_hot_buy:
        nick = str(s.get("昵称", s.get("席位", "")[:12]))
        full_seat = str(s.get("席位", ""))
        net_val = _safe_float(s.get("净买入亿"), 0)
        stocks_str = "、".join(str(x) for x in s.get("涉及个股", [])[:3])
        lhb_hot_rows.append(
            f'<tr><td class="tb" title="{esc(full_seat)}">{esc(nick)}</td>'
            f'<td class="up">+{net_val:.2f}</td>'
            f'<td class="t3">{esc(stocks_str)}</td></tr>'
        )

    lhb_hot_sell_rows = []
    for s in lhb_hot_sell:
        nick = str(s.get("昵称", s.get("席位", "")[:12]))
        net_val = _safe_float(s.get("净卖出亿"), 0)
        stocks_str = "、".join(str(x) for x in s.get("涉及个股", [])[:3])
        lhb_hot_sell_rows.append(f'<tr><td class="tb">{esc(nick)}</td><td class="dn">-{net_val:.2f}</td><td class="t3">{esc(stocks_str)}</td></tr>')

    # 主线板块标签
    theme_tags = []
    for t in lhb_themes:
        strength = str(t.get("强度", "🔥"))
        name = str(t.get("板块", ""))
        stocks = "、".join(str(x) for x in t.get("个股", [])[:3])
        theme_tags.append(f'<span class="tag c">{esc(strength + name)}</span> <span class="t3">{esc(stocks)}</span>')
    theme_html = " ".join(theme_tags) if theme_tags else '<span class="t3">暂无明显主线</span>'

    # 关键信号
    signal_parts = []
    for sig in lhb_signals[:4]:
        signal_parts.append(esc(sig))
    signal_html = "；".join(signal_parts) if signal_parts else "暂无有效信号"

    # 游资派系
    group_parts = []
    for g in lhb_groups[:3]:
        direction = str(g.get("方向", ""))
        total = _safe_float(g.get("总净额亿"), 0)
        name = str(g.get("派系", ""))
        stocks = "、".join(str(x) for x in g.get("涉及个股", [])[:3])
        cls = "up" if total > 0 else "dn"
        group_parts.append(f'<span class="tag b">{esc(name)}</span><span class="{cls}">{esc(direction)}{abs(total):.1f}亿</span> <span class="t3">{esc(stocks)}</span>')
    group_html = " ".join(group_parts) if group_parts else ""

    lhb_empty_note = esc(lhb_note or "暂无可核验龙虎榜数据")
    lhb_sec = f"""<section class="sec">
<div class="sh"><span class="ico">◉</span> 龙虎榜 <span class="meta">{section_meta(lhb, trade_date, trade_date, count=lhb_total, unit="只")}</span></div>
<table><colgroup><col style="width:72px"><col style="width:56px"><col style="width:52px"><col></colgroup>
<tr><th>名称</th><th>涨跌</th><th>净买亿</th><th>上榜原因</th></tr>
{"".join(lhb_buy_rows) or f'<tr><td colspan="4" class="t3" style="text-align:center">{lhb_empty_note}</td></tr>'}</table>
<div style="margin-top:8px"><b style="color:var(--dn)">净卖出TOP</b></div>
<table><colgroup><col style="width:72px"><col style="width:56px"><col style="width:52px"><col></colgroup>
<tr><th>名称</th><th>涨跌</th><th>净卖亿</th><th>上榜原因</th></tr>
{"".join(lhb_sell_rows) or '<tr><td colspan="4" class="t3" style="text-align:center">暂无净卖出明细</td></tr>'}</table>
<div style="margin-top:8px"><b style="color:var(--cyn)">机构净买入TOP</b></div>
<table><colgroup><col style="width:100px"><col style="width:60px"><col></colgroup>
<tr><th>名称</th><th>净买亿</th><th>机构席位</th></tr>
{"".join(lhb_inst_rows) or '<tr><td colspan="3" class="t3" style="text-align:center">暂无机构明细</td></tr>'}</table>
<div style="margin-top:8px"><b style="color:var(--gld)">游资席位</b></div>
<table><colgroup><col style="width:140px"><col style="width:52px"><col></colgroup>
<tr><th>席位</th><th>净买亿</th><th>涉及个股</th></tr>
{"".join(lhb_hot_rows) or '<tr><td colspan="3" class="t3" style="text-align:center">暂无游资净买入明细</td></tr>'}</table>
<div style="margin-top:8px"><b style="color:var(--dn)">游资净卖出TOP</b></div>
<table><colgroup><col style="width:140px"><col style="width:52px"><col></colgroup>
<tr><th>席位</th><th>净卖亿</th><th>涉及个股</th></tr>
{"".join(lhb_hot_sell_rows) or '<tr><td colspan="3" class="t3" style="text-align:center">暂无游资净卖出明细</td></tr>'}</table>
<div style="margin-top:6px"><b style="color:var(--cyn)">主线</b> {theme_html}</div>
{f'<div style="margin-top:4px"><b style="color:var(--inf)">派系</b> {group_html}</div>' if group_html else ''}
<div class="lbox"><b>信号：</b>{signal_html}</div>
</section>"""

    # ===== ③¾ 板块轮动 =====
    # 只在真正出问题时才把说明塞进表头；正常时表头保持“15个板块 · T+5 · 日期”这种短格式
    rotation_note = ""
    if rotation:
        state, _ = dataset_state(rotation, trade_date, trade_date)
        if state != "ok" or str(rotation.get("status", "")).lower() != "ok":
            rotation_note = section_data_note(rotation, trade_date, trade_date)
    rotation_sec = render_rotation_section(rotation, rotation_note)

    # ===== ③⅞ 大小周期节点票 =====
    node_cycle_sec = render_node_cycle_section(node_cycle)

    # ===== ④ 机构研报 =====
    reports = []
    report_begin = datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=2)
    report_end = datetime.strptime(today, "%Y-%m-%d")
    for report in yanbao.get("reports", []) if isinstance(yanbao.get("reports", []), list) else []:
        try:
            published = datetime.strptime(str(report.get("publishDate", ""))[:10], "%Y-%m-%d")
        except ValueError:
            continue
        if report_begin <= published <= report_end:
            reports.append(report)
    # 研报的「核心逻辑」不能拿标题充数：用 AI 在给定字段内改写成逻辑句，
    # 拿不到就如实回到标题并标注来源，不编造因果。
    yb_logic_results = ai_summarize_yanbao_parallel(reports)
    yb_logic_failed = 0
    yb_rows = []
    for index, r in enumerate(reports):
        org = str(r.get("org", ""))[:10]
        stock = str(r.get("stock", ""))
        code = str(r.get("code", ""))
        title = str(r.get("title", ""))
        stored_logic = str(r.get("logic") or "").strip()
        ai_logic = yb_logic_results[index] if index < len(yb_logic_results) else ""
        if stored_logic and stored_logic != title:
            logic, logic_tag = stored_logic, ""
        elif ai_logic:
            logic, logic_tag = ai_logic, ' <span style="color:var(--cyn);font-size:10px">✦AI提炼</span>'
        else:
            logic, logic_tag = title, ' <span style="color:var(--t3);font-size:10px">（原始报告标题）</span>'
            yb_logic_failed += 1
        rate = str(r.get("rate", ""))
        if rate in ["买入", "增持", "推荐", "优于大市", "强烈推荐"]:
            dir_cls, dir_text = "bg_", "看多"
        elif rate in ["减持", "卖出"]:
            dir_cls, dir_text = "bo", "看空"
        else:
            dir_cls, dir_text = "bbl", "中性"
        industry = str(r.get('industry') or infer_industry(title))
        stock_display = f"{code} {stock}".strip()
        source = str(r.get("source") or "东方财富研报API")
        publish_date = str(r.get("publishDate", ""))[:10]
        source_link = f'<a href="{esc(r.get("source_url", ""))}" target="_blank" rel="noopener">{esc(source)}</a>'
        yb_rows.append(f'<tr><td class="tb">{esc(org)}</td><td><span class="{ind_cls(industry)}">{esc(industry)}</span></td><td class="t2">{esc(stock_display) or "—"}</td><td><span class="{dir_cls}">{esc(rate or "未评级")}</span></td><td class="t2">{esc(logic[:150])}{logic_tag}</td><td class="t3">{source_link} · {esc(publish_date)}</td></tr>')
    focus_tracks = []
    for report in reports:
        track = str(report.get('industry') or infer_industry(str(report.get("title", ""))))
        if track not in focus_tracks and track != "综合":
            focus_tracks.append(track)
    focus_text = "、".join(focus_tracks[:6]) if focus_tracks else "暂无足够研报样本归纳主线"
    yb_sec = f"""<section class="sec fw">
<div class="sh"><span class="ico">◉</span> 机构研报 <span class="meta">{section_meta(yanbao, today, trade_date, count=len(reports), unit="篇")}</span></div>
<table><colgroup><col style="width:74px"><col style="width:58px"><col style="width:110px"><col style="width:42px"><col><col style="width:140px"></colgroup>
<tr><th>机构</th><th>赛道</th><th>标的</th><th>方向</th><th>核心逻辑</th><th>来源</th></tr>
{"".join(yb_rows) or f'<tr><td colspan="6" class="t3" style="text-align:center">{esc(yanbao_note or "暂无目标窗口内可核验研报；未使用旧缓存")}</td></tr>'}</table>
<div class="lbox"><b>样本聚焦：</b>{esc(focus_text)}</div>
</section>"""

    # ===== ⑤½ 博主多空统计 =====
    survey_stats = survey.get("statistics", {})
    survey_analyses = survey.get("analyses", [])
    mkt = survey_stats.get("by_market", {"bull": 0, "bear": 0, "neutral": 0})
    mkt_total = mkt.get("bull", 0) + mkt.get("bear", 0) + mkt.get("neutral", 0)
    mkt_ratio = f"{mkt['bull']/mkt['bear']:.2f}" if mkt.get("bear", 0) > 0 else ("无看空样本" if mkt.get("bull", 0) > 0 else "暂无有效样本")

    # 大盘仪表盘 — SVG环形图
    bull_count = mkt.get("bull", 0)
    bear_count = mkt.get("bear", 0)
    neutral_count = mkt.get("neutral", 0)
    bull_pct = bull_count / mkt_total * 100 if mkt_total > 0 else 0
    bear_pct = bear_count / mkt_total * 100 if mkt_total > 0 else 0
    neutral_pct = neutral_count / mkt_total * 100 if mkt_total > 0 else 0

    # SVG环形参数 (半径40, 周长=2πr≈251.3)
    R = 40
    C = 2 * 3.14159 * R  # ≈251.3
    # 三个弧段：bull从0°, bear从bull结束, neutral从bear结束
    bull_dash = C * bull_pct / 100
    bear_dash = C * bear_pct / 100
    neutral_dash = C * neutral_pct / 100
    bull_offset = 0
    bear_offset = -bull_dash
    neutral_offset = -(bull_dash + bear_dash)

    # 确定主色
    if bull_pct >= 60:
        gauge_main_color = "var(--up)"
        gauge_sentiment = "偏多"
    elif bear_pct >= 40:
        gauge_main_color = "var(--dn)"
        gauge_sentiment = "偏空"
    else:
        gauge_main_color = "var(--inf)"
        gauge_sentiment = "分歧"

    gauge_svg = f"""<svg viewBox="0 0 100 100">
      <circle class="ring-bg" cx="50" cy="50" r="{R}"/>
      <circle class="ring-fill bull" cx="50" cy="50" r="{R}"
        stroke-dasharray="{bull_dash} {C - bull_dash}" stroke-dashoffset="{bull_offset}"/>
      <circle class="ring-fill bear" cx="50" cy="50" r="{R}"
        stroke-dasharray="{bear_dash} {C - bear_dash}" stroke-dashoffset="{bear_offset}"/>
      <circle class="ring-fill neutral" cx="50" cy="50" r="{R}"
        stroke-dasharray="{neutral_dash} {C - neutral_dash}" stroke-dashoffset="{neutral_offset}"/>
    </svg>"""

    # 板块热力条
    sector_bars = []
    for sd in survey_stats.get("by_sector_sorted", [])[:10]:
        sector = sd.get("sector", "")
        bull = sd.get("bull", 0)
        bear = sd.get("bear", 0)
        neutral = sd.get("neutral", 0)
        mentions = sd.get("blogger_count", 0)
        total_s = bull + bear + neutral
        if total_s == 0:
            total_s = 1
        bull_w = bull / total_s * 100
        bear_w = bear / total_s * 100
        neutral_w = neutral / total_s * 100
        # 条内标签
        bar_label_parts = []
        if bull > 0: bar_label_parts.append(f"▲{bull}")
        if bear > 0: bar_label_parts.append(f"▼{bear}")
        if neutral > 0: bar_label_parts.append(f"—{neutral}")
        bar_label = " / ".join(bar_label_parts) if bar_label_parts else ""
        sector_bars.append(f"""<div class="survey-sector-row">
  <span class="survey-sector-name">{sector}</span>
  <div class="survey-sector-bar">
    <div class="bar-bull" style="width:{bull_w}%"></div>
    <div class="bar-bear" style="width:{bear_w}%"></div>
    <div class="bar-neutral" style="width:{neutral_w}%"></div>
    <span class="bar-label">{bar_label}</span>
  </div>
  <span class="survey-sector-count">{mentions}人</span>
</div>""")

    # 平台对比卡片
    plat_cards = []
    for pname, pdata in survey_stats.get("by_platform", {}).items():
        p_bull = pdata.get("bull", 0)
        p_bear = pdata.get("bear", 0)
        p_neutral = pdata.get("neutral", 0)
        ptotal = p_bull + p_bear + p_neutral
        pratio = f"{p_bull/p_bear:.1f}" if p_bear > 0 else ("无看空样本" if p_bull > 0 else "暂无有效样本")
        plat_cards.append(f"""<div class="survey-plat-card">
  <span class="survey-plat-name">{pname}</span>
  <div class="survey-plat-stats">
    <span class="sp-bull">{p_bull}</span><span class="sp-sep">/</span><span class="sp-bear">{p_bear}</span><span class="sp-neutral">({p_neutral})</span>
  </div>
  <span class="survey-plat-meta">{pdata.get('blogger_count', ptotal)}位博主 · 多空比 <b>{pratio}</b></span>
</div>""")

    # 核心结论
    conclusions = []
    tgb_plat = survey_stats.get("by_platform", {}).get("淘股吧", {})
    xq_plat = survey_stats.get("by_platform", {}).get("雪球", {})
    tgb_r = tgb_plat.get("bull", 0) / max(tgb_plat.get("bear", 1), 1)
    xq_r = xq_plat.get("bull", 0) / max(xq_plat.get("bear", 1), 1)
    if mkt_total == 0:
        conclusions.append("暂无有效观点，未使用旧缓存或样例数据")
    elif xq_r > tgb_r + 0.5:
        conclusions.append(f"雪球偏乐观(多空比{xq_r:.1f})，淘股吧偏谨慎(多空比{tgb_r:.1f})")
    elif tgb_r > xq_r + 0.5:
        conclusions.append(f"淘股吧偏乐观(多空比{tgb_r:.1f})，雪球偏谨慎(多空比{xq_r:.1f})")
    else:
        conclusions.append(f"两平台观点接近，多空比均约{mkt_ratio}")

    if mkt_total > 0 and survey_stats.get("by_sector_sorted"):
        top_sector = survey_stats["by_sector_sorted"][0]
        conclusions.append(f"最大共识方向：{top_sector['sector']}（{top_sector['blogger_count']}人提及）")

    all_bull_sectors = [s for s in survey_stats.get("by_sector_sorted", []) if mkt_total > 0 and s.get("bear", 0) == 0 and s.get("bull", 0) >= 2]
    if all_bull_sectors:
        conclusions.append(f"一致看多：{'、'.join(s['sector'] for s in all_bull_sectors[:3])}")

    conclusion_html = "；".join(conclusions)

    survey_sec = f"""<section class="sec">
<div class="sh"><span class="ico">◉</span> 博主多空统计 <span class="meta">{survey_stats.get('total_analyses', 0)}位博主 · {mkt_ratio}多空比{data_note}</span></div>
<div class="survey-wrap">
  <div class="survey-top">
    <div class="survey-gauge">
      <span class="survey-gauge-title">大盘情绪</span>
      <div class="survey-gauge-ring">
        {gauge_svg}
        <div class="survey-gauge-center">
          <span class="survey-gauge-val" style="color:{gauge_main_color}">{gauge_sentiment}</span>
          <span class="survey-gauge-label">{mkt_total}人</span>
        </div>
      </div>
      <div class="survey-gauge-legend">
        <span><i class="dot-bull"></i>看多{bull_count}</span>
        <span><i class="dot-bear"></i>看空{bear_count}</span>
        <span><i class="dot-neutral"></i>中性{neutral_count}</span>
      </div>
      <div class="survey-gauge-ratio">多空比 <b>{mkt_ratio}</b></div>
    </div>
    <div class="survey-sectors">
      <span class="survey-sectors-title">板块多空分布</span>
      {"".join(sector_bars)}
    </div>
  </div>
  <div class="survey-platforms">
    {"".join(plat_cards)}
  </div>
  <div class="lbox"><b>结论：</b>{conclusion_html}</div>
</div>
</section>"""

    # 统一使用经过状态校验的渲染器，空数据不会出现无限比或虚构结论。
    survey_state, survey_reason = dataset_state(survey, today, trade_date)
    survey_render_data = survey
    if survey_state in {"error", "stale", "future"}:
        survey_render_data = dict(survey)
        survey_render_data["status"] = "error"
        survey_render_data["note"] = survey_note or survey_reason
    survey_data_date = _date_label(survey) if survey_state == "ok" else ""
    survey_sec = render_survey_section(
        survey_render_data,
        f"（{esc(survey_data_date)}数据）" if survey_data_date else "",
    )
    reviewed = survey.get('reviewed_samples', survey.get('analyses', []))
    audit_rows = []
    for sample in reviewed:
        platform, name = sample.get('platform', ''), sample.get('blogger', '')
        original = next((p.get('bloggers', {}).get(name, {}) for p in survey.get('raw_platforms', []) if p.get('platform') == platform), {})
        uid = original.get('uid', '')
        url = ('https://www.tgb.cn/blog/' if platform == '淘股吧' else 'https://xueqiu.com/u/') + str(uid)
        verdict = sample.get('direction', '中性') if sample.get('eligible', True) else '排除'
        audit_rows.append(f'<tr><td>{esc(platform)}</td><td><a href="{esc(url)}" target="_blank" rel="noopener">{esc(name)}</a></td><td>{esc(verdict)}</td><td>{esc(sample.get("reason", ""))}</td></tr>')
    audit_html = f'<div class="lbox">{esc(survey.get("note", ""))}<br>{esc(survey.get("sampling_method", ""))}</div><details><summary>查看{len(reviewed)}位活跃作者的判读与排除理由</summary><table><tr><th>平台</th><th>作者</th><th>判读</th><th>依据</th></tr>{"".join(audit_rows)}</table></details>'
    survey_sec = survey_sec.replace('</section>', audit_html + '</section>')

    # ===== ⑥ 淘股吧 =====
    # 先收集所有博主的原始文本，并发调用 AI 总结
    tgb_blogger_names = list(tgb.get("bloggers", {}).keys())
    tgb_ai_tasks = []  # [(raw_text, context), ...]
    tgb_raw_texts = []
    tgb_raw_data = {}  # name -> data dict

    for name in tgb_blogger_names:
        d = tgb["bloggers"][name]
        tgb_raw_data[name] = d
        combined = tgb_content_text(d)
        tgb_raw_texts.append(combined)
        if combined:
            tgb_ai_tasks.append((combined, f"淘股吧博主{name}的投资观点"))
        else:
            tgb_ai_tasks.append(("", ""))  # 无内容占位

    # 只复用同一目标日、同一来源且原文哈希一致的 AI 摘要。
    tgb_cache_path = DATA_DIR / "tgb_ai_summaries.json"
    tgb_summary_cache = load_summary_cache(tgb_cache_path)
    tgb_ai_results = [""] * len(tgb_ai_tasks)
    tgb_cache_dirty = False
    pending_indices = []
    for i, name in enumerate(tgb_blogger_names):
        raw_text = tgb_raw_texts[i]
        if not raw_text:
            continue
        cached = get_cached_summary(tgb_summary_cache, today, "tgb", name, raw_text)
        if cached is None:
            pending_indices.append(i)
        else:
            tgb_ai_results[i] = cached

    # 并发 AI 总结；已有精确缓存时无须重新请求。
    tgb_ai_configured = semantic_summary_available()
    if tgb_ai_configured and pending_indices:
        pending_results = ai_summarize_batch_parallel([tgb_ai_tasks[i] for i in pending_indices])
        for i, result in zip(pending_indices, pending_results):
            normalized = normalize_ai_summary(result)
            tgb_ai_results[i] = normalized
            if normalized:
                set_cached_summary(
                    tgb_summary_cache, today, "tgb", tgb_blogger_names[i],
                    tgb_raw_texts[i], normalized,
                )
                tgb_cache_dirty = True

    # 组装淘股吧行
    tgb_rows = []
    tgb_symbols_all = []
    tgb_directions = []
    tgb_ai_failures = []
    tgb_no_opinion_count = 0
    for i, name in enumerate(tgb_blogger_names):
        d = tgb_raw_data[name]
        ai_summary = tgb_ai_results[i] if i < len(tgb_ai_results) else ""

        # 使用 ai_summarize_blogger_batch 的逻辑（但复用已获取的 AI 结果）
        posts = d.get("posts", [])
        replies = d.get("top_replies", [])
        replies_today = d.get("replies_today", 0)
        all_text = []
        post_titles = []
        for p in posts:
            if p.get("title"): post_titles.append(p["title"])
        combined = tgb_raw_texts[i]
        if combined:
            all_text.append(combined)

        if not all_text:
            last_seen = str(d.get("last_seen_date") or "")
            if last_seen and last_seen < str(today):
                reason = f'目标日无动态（账号最后跟帖 {last_seen}，此后未更新）'
            else:
                reason = "目标日无可核验观点"
            tgb_rows.append(f'<tr><td class="tb" style="color:var(--gld)">{esc(name)}</td><td class="t2">{esc(reason)}</td></tr>')
            continue

        combined = "\n".join(all_text)
        symbols = extract_symbols_from_text(combined)

        # 方向判断
        bull_signals = sum(1 for kw in ["看多", "看涨", "利好", "乐观", "涨", "反弹", "企稳",
                          "止跌", "机会", "买入", "加仓", "首选", "强", "突破", "超预期"]
                          if kw in combined)
        bear_signals = sum(1 for kw in ["看空", "看跌", "利空", "悲观", "跌", "恐慌", "风险",
                          "回避", "减仓", "弱", "破位", "不及预期", "杀跌", "暴跌"]
                          if kw in combined)
        if bull_signals > bear_signals + 2:
            direction = "看多"
        elif bear_signals > bull_signals + 2:
            direction = "看空"
        else:
            direction = "中性"

        # 组装摘要
        used_ai = bool(ai_summary)
        if ai_summary:
            if ai_summary == NO_CLEAR_OPINION:
                direction = "中性"
                symbols = []
                tgb_no_opinion_count += 1
            else:
                extra_symbols = re.findall(r'【([^】]+)】', ai_summary)
                for s in extra_symbols:
                    if s not in symbols: symbols.append(s)
            summary = ai_summary
        else:
            if not tgb_ai_configured:
                summary = f"[AI总结不可用-{name}]"
            else:
                # AI总结失败，重试最多3次
                for retry in range(3):
                    if _AI_CREDENTIAL_REJECTED:
                        break  # 凭证被拒时重试无意义
                    ai_summary = ai_summarize_opinions(combined, context=f"淘股吧博主{name}的投资观点")
                    if ai_summary:
                        break
                    print(f"  [WARN] 淘股吧AI总结失败（{name}），重试 {retry+1}/3...", file=sys.stderr)
                if ai_summary:
                    used_ai = True
                    ai_summary = normalize_ai_summary(ai_summary)
                    if ai_summary == NO_CLEAR_OPINION:
                        direction = "中性"
                        symbols = []
                        tgb_no_opinion_count += 1
                    else:
                        extra_symbols = re.findall(r'【([^】]+)】', ai_summary)
                        for s in extra_symbols:
                            if s not in symbols: symbols.append(s)
                    summary = ai_summary
                    set_cached_summary(
                        tgb_summary_cache, today, "tgb", name, combined, ai_summary,
                    )
                    tgb_cache_dirty = True
                else:
                    # AI总结失败，禁止回退到正则提取或原文截断。
                    print(f"  [⛔] 淘股吧AI总结3次均失败（{name}），无法生成合格语义摘要", file=sys.stderr)
                    summary = f"[AI总结失败-{name}]"

        if used_ai:
            direction = summary_direction(summary)
            symbols = [s for s in re.findall(r'【([^】]+)】', summary) if s not in {'中性', '看多', '看空', '关注'}]
            for s in symbols[:5]:
                if s not in tgb_symbols_all:
                    tgb_symbols_all.append(s)
            tgb_directions.append(direction)
        else:
            # 有可核验内容却没拿到 AI 语义摘要：不允许把原始口语当观点交付
            tgb_ai_failures.append(name)
        sym_tags = " ".join(f'<span class="tag y">{esc(s)}</span>' for s in symbols[:5]) if used_ai else ""

        if not used_ai:
            dir_badge = '<span class="bbl" style="margin-right:4px">待AI总结</span>'
        elif direction == "看多":
            dir_badge = '<span class="bg_" style="margin-right:4px">看多</span>'
        elif direction == "看空":
            dir_badge = '<span class="bo" style="margin-right:4px">看空</span>'
        else:
            dir_badge = '<span class="bbl" style="margin-right:4px">中性</span>'

        title_part = ""
        if post_titles:
            title_part = f'<b>{esc(post_titles[0])}</b>：'
        elif not posts:
            title_part = '<span style="color:var(--t3);font-size:11px">仅跟帖</span> '

        ai_tag = ' <span style="color:var(--cyn);font-size:10px">✦AI提炼</span>' if used_ai else ""
        summary_html = esc(summary)
        sym_tags = " ".join(f'<span class="tag y">{esc(s)}</span>' for s in symbols[:5]) if used_ai else ""
        sources = ' '.join(f'<a href="{esc(p.get("url", ""))}" target="_blank" rel="noopener">主帖原文</a>' for p in posts)
        if replies:
            sources += f' <a href="{esc(replies[0].get("url", ""))}" target="_blank" rel="noopener">回复来源</a>'
        tgb_rows.append(f'<tr><td class="tb" style="color:var(--gld)">{esc(name)}</td><td class="t2">{dir_badge}{title_part}{summary_html}{ai_tag} {sym_tags}<div class="t3">{esc(d.get("data_date", ""))} · {sources}</div></td></tr>')

    if tgb_cache_dirty:
        try:
            save_summary_cache(tgb_summary_cache, tgb_cache_path)
        except OSError as exc:
            print(f"  [WARN] 淘股吧摘要缓存写入失败：{exc}", file=sys.stderr)

    # 淘股吧共识
    tgb_bull_count = tgb_directions.count("看多")
    tgb_bear_count = tgb_directions.count("看空")
    if tgb.get("status") == "error" or not tgb_blogger_names:
        tgb_consensus = f"数据获取失败：{tgb.get('note') or tgb.get('error') or '无可核验淘股吧内容'}"
    elif not tgb_directions:
        tgb_consensus = "未生成有效AI摘要；原始内容未冒充观点结论"
    elif tgb_bull_count == 0 and tgb_bear_count == 0 and tgb_no_opinion_count:
        tgb_consensus = f"有可核验内容，但 {tgb_no_opinion_count} 位博主未表达明确多空观点"
    elif tgb_bull_count == 0 and tgb_bear_count == 0:
        tgb_consensus = f"当前摘要方向以中性为主（{len(tgb_directions)}位）"
    elif tgb_bull_count > tgb_bear_count:
        tgb_consensus = f"整体偏多({tgb_bull_count}看多/{tgb_bear_count}看空)"
    elif tgb_bear_count > tgb_bull_count:
        tgb_consensus = f"整体偏空({tgb_bear_count}看空/{tgb_bull_count}看多)"
    else:
        tgb_consensus = f"多空分歧({tgb_bull_count}看多/{tgb_bear_count}看空)"
    if tgb_no_opinion_count and (tgb_bull_count or tgb_bear_count):
        tgb_consensus += f"；另有{tgb_no_opinion_count}位未表达明确观点"
    if tgb_symbols_all:
        top_syms = tgb_symbols_all[:4]
        tgb_consensus += f"；共同关注：{'、'.join(str(s) for s in top_syms)}"

    total_replies = sum(b.get("replies_today", 0) for b in tgb.get("bloggers", {}).values())
    total_posts = sum(b.get("posts_today", 0) for b in tgb.get("bloggers", {}).values())
    if not tgb_rows:
        tgb_rows = [f'<tr><td colspan="2" class="t3" style="text-align:center">{esc(tgb_note or "淘股吧数据获取失败")}</td></tr>']
    tgb_sec = f"""<section class="sec">
<div class="sh"><span class="ico">◉</span> 淘股吧 <span class="meta">{section_meta(tgb, today, trade_date, count=len(tgb.get("bloggers", {})), unit="位博主")} · {total_posts}主帖/{total_replies}跟帖</span></div>
<table><colgroup><col style="width:56px"><col></colgroup>
<tr><th>博主</th><th>核心观点 + 标的</th></tr>
{"".join(tgb_rows)}</table>
<div class="lbox"><b>共识：</b>{esc(tgb_consensus)}</div></section>"""

    # ===== ⑦ 抖音 =====
    # 先收集所有视频的原始文本，并发调用 AI 总结
    ai_configured = semantic_summary_available()
    dy_video_list = []  # [(blogger_idx, video_dict), ...]
    dy_ai_tasks = []

    for bi, b in enumerate(douyin.get("bloggers", [])):
        if not b.get("videos"):
            continue
        for v in b["videos"]:
            transcript = v.get("transcript", "")
            title = v.get("title", "")
            transcript_s = trad_to_simp(transcript) if transcript else ""
            title_s = trad_to_simp(title)
            raw_for_ai = transcript_s if not v.get("warning") else ""
            dy_video_list.append((bi, v, title_s, transcript_s))
            if raw_for_ai and len(raw_for_ai.strip()) >= 10:
                dy_ai_tasks.append((raw_for_ai, f"抖音博主{b['name']}视频观点"))
            else:
                dy_ai_tasks.append(("", ""))

    # The cache is bound to report date, video URL and the complete transcript.
    dy_cache_path = DATA_DIR / 'douyin_ai_summaries.json'
    dy_cache = load_summary_cache(dy_cache_path)
    dy_ai_results = [''] * len(dy_ai_tasks)
    pending = []
    for i, (_, video, _, _) in enumerate(dy_video_list):
        raw = dy_ai_tasks[i][0]
        cached = get_cached_summary(dy_cache, today, 'douyin', video.get('url', ''), raw) if raw else None
        if cached:
            dy_ai_results[i] = cached
        elif raw:
            pending.append(i)
    if ai_configured and pending:
        for i, summary in zip(pending, ai_summarize_batch_parallel([dy_ai_tasks[j] for j in pending])):
            if summary:
                dy_ai_results[i] = summary
                set_cached_summary(dy_cache, today, 'douyin', dy_video_list[i][1].get('url', ''), dy_ai_tasks[i][0], summary)
        save_summary_cache(dy_cache, dy_cache_path)

    # 组装抖音卡片
    dy_items = []
    dy_symbols_all = []
    ai_result_idx = 0
    blogger_video_started = set()  # 追踪哪些博主已有视频输出

    for bi, b in enumerate(douyin.get("bloggers", [])):
        if not b.get("videos"):
            last_seen = str(b.get("last_seen_date") or "")
            if last_seen and last_seen < str(today):
                dy_reason = f"目标日无视频（账号最后发布 {last_seen}，此后未更新）"
            else:
                dy_reason = douyin_note or "目标日无可核验视频"
            dy_items.append(f'<div class="dy"><span class="dyt">--:--</span><div><strong>{esc(b.get("name", ""))}</strong><p>{esc(dy_reason)}</p></div></div>')
            continue
        for v in b["videos"][:8]:
            title_s = trad_to_simp(v.get("title", ""))
            transcript_s = trad_to_simp(v.get("transcript", "")) if v.get("transcript") else ""
            fallback_text = trad_to_simp(v.get("fallback_text", ""))
            warning = str(v.get("warning", ""))
            symbols_raw = v.get("symbols", [])

            # 提取标的
            symbols = extract_symbols_from_text(f"{transcript_s} {fallback_text} {title_s}")
            for s in symbols_raw:
                if s not in symbols: symbols.append(s)
            symbols = symbols[:6]

            # 获取 AI 总结结果
            ai_summary = dy_ai_results[ai_result_idx] if ai_result_idx < len(dy_ai_results) else ""
            ai_result_idx += 1

            used_ai = bool(ai_summary)
            if ai_summary:
                if ai_summary == NO_CLEAR_OPINION:
                    symbols = []
                else:
                    extra_symbols = re.findall(r'【([^】]+)】', ai_summary)
                    for s in extra_symbols:
                        if s not in symbols: symbols.append(s)
                    symbols = symbols[:6]
                summary = ai_summary
            else:
                if not ai_configured:
                    if fallback_text or warning:
                        summary = f"标题/话题线索：{fallback_text or title_s}（未配置AI，未展示原始转录）"
                    elif transcript_s:
                        summary = f"转录摘录（未使用AI）：{_transcript_excerpt(transcript_s)}"
                    else:
                        summary = "未配置AI，暂无可展示的真实视频文本"
                else:
                    # 已配置AI但请求失败时，重试最多3次。
                    for retry in range(3):
                        if _AI_CREDENTIAL_REJECTED:
                            break  # 凭证被拒时重试无意义
                        ai_summary = ai_summarize_opinions(transcript_s, context=f"抖音视频{title_s[:30]}")
                        if ai_summary:
                            break
                        print(f"  [WARN] 抖音AI总结失败（{title_s[:30]}），重试 {retry+1}/3...", file=sys.stderr)
                    if ai_summary:
                        used_ai = True
                        extra_symbols = re.findall(r'【([^】]+)】', ai_summary)
                        for s in extra_symbols:
                            if s not in symbols: symbols.append(s)
                        symbols = symbols[:6]
                        summary = ai_summary
                    else:
                        # AI总结失败时不把转录伪装成AI结论，但可以展示来源明确的摘录。
                        print(f"  [⛔] 抖音AI总结3次均失败（{title_s[:30]}），保留真实转录摘录", file=sys.stderr)
                        if fallback_text or warning:
                            summary = f"标题/话题线索：{fallback_text or title_s}（AI语义总结失败，未展示原始转录）"
                        elif transcript_s:
                            summary = f"转录摘录（AI总结失败）：{_transcript_excerpt(transcript_s)}"
                        else:
                            summary = "AI语义总结失败，暂无可展示的视频文本"

            # 正式简报只交付与本次转录相符的语义结论。
            if not used_ai:
                raise RuntimeError(f'抖音视频缺少与转录相符的语义摘要：{v.get("url", "")}；未写出完整简报')
            # 方向判断
            if ai_summary == NO_CLEAR_OPINION:
                direction = "关注"
            elif transcript_s:
                bull_signals = sum(1 for kw in ["看多", "看涨", "利好", "乐观", "涨", "反弹",
                                  "机会", "买入", "首选", "强", "突破", "超预期", "涨价",
                                  "扩产", "紧缺", "需求", "增长"]
                                  if kw in transcript_s)
                bear_signals = sum(1 for kw in ["看空", "看跌", "利空", "悲观", "跌", "恐慌",
                                  "风险", "回避", "弱", "破位", "杀跌", "暴跌", "降价",
                                  "过剩", "减产"]
                                  if kw in transcript_s)
                if bull_signals > bear_signals + 2:
                    direction = "利好"
                elif bear_signals > bull_signals + 2:
                    direction = "利空"
                else:
                    direction = "关注"
            else:
                direction = v.get("direction", "关注")

            if used_ai:
                direction = {'看多': '利好', '看空': '利空'}.get(summary_direction(summary), '关注')
                symbols = [s for s in re.findall(r'【([^】]+)】', summary) if s not in {'中性', '看多', '看空', '关注'}]

            for s in symbols[:4]:
                if s not in dy_symbols_all:
                    dy_symbols_all.append(s)
            sym_tags = " ".join(f'<span class="tag y">{esc(s)}</span>' for s in symbols[:4])
            if direction == "利好":
                dir_tag = '<span class="bg_">利好</span>'
            elif direction == "利空":
                dir_tag = '<span class="bo">利空</span>'
            else:
                dir_tag = '<span class="bbl">关注</span>'
            warn_tag = ' <span style="color:var(--wrn);font-size:10px">⚠标题/话题兜底</span>' if warning else ""
            ai_tag = ' <span style="color:var(--cyn);font-size:10px">✦AI提炼</span>' if used_ai else ""
            title_note = '展示标题取自转录首句 · ' if v.get('title_source') == '转录开头' else ''
            dy_items.append(f'<div class="dy"><span class="dyt">{dir_tag}{warn_tag}{ai_tag}</span><div><strong>{esc(title_s[:50])}</strong><p>{esc(summary[:250])} {sym_tags}</p><small class="t3">{title_note}{esc(b.get("name", ""))} · {esc(v.get("created_at", ""))} · <a href="{esc(v.get("url", ""))}" target="_blank" rel="noopener">视频原文</a></small></div></div>')
    dy_name_parts = [esc(b.get("name", "")) for b in douyin.get("bloggers", []) if b.get("name")]
    dy_name = " · ".join(dy_name_parts) if dy_name_parts else "抖音博主"
    dy_lbox_symbols = " ".join(f'<span class="tag y">{esc(s)}</span>' for s in dy_symbols_all[:8])
    dy_count = sum(len(b.get("videos", [])) for b in douyin.get("bloggers", []) if isinstance(b, dict))
    if not dy_items:
        # 没有可渲染的真视频时，只说明失败原因，不给"线索汇总"这种会被误读的占位
        dy_body = f'<div class="lbox" style="color:var(--wrn)">{esc(douyin_note or "数据获取失败：目标日无可核验视频")}</div>'
    else:
        dy_body = "".join(dy_items) + (
            f'<div class="lbox"><b>线索：</b>见视频观点汇总 {dy_lbox_symbols}</div>'
        )
    dy_sec = f"""<section class="sec fw">
<div class="sh"><span class="ico">◉</span> 抖音 <span class="meta">{dy_name} · {section_meta(douyin, today, trade_date, count=dy_count, unit="条视频")}</span></div>
{dy_body}
</section>"""

    # ===== ⑨ 未来大事件 =====
    ev_rows = []
    for e in events.get("events", []):
        date = str(e.get("date", ""))
        if e.get('time') and e['time'] != '00:00':
            date += ' ' + str(e['time'])
        etype = str(e.get("type", ""))
        event = str(e.get("event", ""))[:80]
        impact = str(e.get("impact", "中性"))
        type_cls = {"宏观": "bbl", "消费": "bgd", "解禁": "bo", "PMI": "br"}.get(etype, "bbl")
        imp_cls = {"利好": "bg_", "利空": "bo", "中性": "bbl"}.get(impact, "bbl")
        source = str(e.get("source") or events.get("source") or "")
        source_html = esc(source)
        if e.get('source_url'):
            source_html = f'<a href="{esc(e["source_url"])}" target="_blank" rel="noopener">{source_html}</a>'
        ev_rows.append(f'<tr><td class="tr">{esc(date)}</td><td><span class="{type_cls}">{esc(etype)}</span></td><td class="t2">{esc(event)}{(" <span class=\"t3\">" + source_html + "</span>") if source else ""}</td><td><span class="{imp_cls}">{esc(impact)}</span></td></tr>')
    if not ev_rows:
        ev_rows = [f'<tr><td colspan="4" class="t3" style="text-align:center">{esc(events_note or "暂无带明确日期的可核验事件；未使用日期推算")}</td></tr>']
    event_meta = events.get("range", "") if str(events.get("status", "")).lower() == "ok" else (events_note or "目标窗口")
    events_sec = f"""<section class="sec">
<div class="sh"><span class="ico">◉</span> 未来大事件 <span class="meta">{esc(event_meta)}</span></div>
<table><colgroup><col style="width:64px"><col style="width:48px"><col><col style="width:48px"></colgroup>
<tr><th>时间</th><th>类型</th><th>事件</th><th>影响</th></tr>
{"".join(ev_rows)}</table></section>"""

    # ===== ⑩ 策略（基于数据动态生成摘要）=====
    strategy_items = build_strategy_items(news, events, panic, tgb, tgb_ai_results, lianban)
    long_items = strategy_items["long"]
    watch_items = strategy_items["watch"]
    risk_items = strategy_items["risk"]

    strategy_sec = f"""<section class="sec" style="margin-bottom:0">
<div class="sh"><span class="ico">◉</span> 策略 <span class="meta">全源综合{data_note}</span></div>
<div class="strat">
<div class="sc long"><h4><span class="dot"></span>进攻线索（需确认）</h4><ul>{"".join(f'<li>{esc(item)}</li>' for item in long_items[:6])}</ul></div>
<div class="sc wait"><h4><span class="dot"></span>观察等待</h4><ul>{"".join(f'<li>{esc(item)}</li>' for item in watch_items[:6])}</ul></div>
<div class="sc risk"><h4><span class="dot"></span>风险提示</h4><ul>{"".join(f'<li>{esc(item[:60])}</li>' for item in risk_items[:5])}</ul></div>
</div></section>"""

    # ===== Chart JS =====
    chart_js_data = json.dumps(chart_scores)
    chart_js_labels = json.dumps(chart_labels)
    chart_js_phases = json.dumps(chart_phases, ensure_ascii=False)
    chart_js_stage_colors = json.dumps(PHASE_COLORS, ensure_ascii=False)

    chart_js = f"""<script>
const h=document.getElementById('hdr');
window.addEventListener('scroll',()=>{{h.classList.toggle('elevated',window.scrollY>6)}},{{passive:true}});
document.querySelectorAll('.mc').forEach(c=>{{c.addEventListener('mousemove',e=>{{const r=c.getBoundingClientRect();c.style.setProperty('--mx',((e.clientX-r.left)/r.width*100)+'%');c.style.setProperty('--my',((e.clientY-r.top)/r.height*100)+'%')}})}});
(function(){{
  const canvas=document.getElementById('sentChart');const tip=document.getElementById('chartTip');if(!canvas||!tip)return;
  const data={chart_js_data};const labels={chart_js_labels};const phases={chart_js_phases};
  const stageColors={chart_js_stage_colors};const neutral='#8b8577';
  if(data.length===0){{canvas.style.display='none';return;}}
  const minV=0,maxV=100;const pad={{t:22,b:20,l:26,r:10}};const dpr=window.devicePixelRatio||1;
  let W,H,step,bw,plotTop,plotBottom,bars=[];let animProg=0,hi=-1;
  function yS(v){{return plotBottom-(v-minV)/(maxV-minV)*(plotBottom-plotTop)}}
  function stageOf(label){{const s=String(label||'');const head=s.split(/[｜|（(]/)[0];for(const k in stageColors){{if(head.indexOf(k)>=0)return k;}}return '';}}
  function size(){{const r=canvas.getBoundingClientRect();W=r.width;H=120;canvas.width=W*dpr;canvas.height=H*dpr;const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);plotTop=pad.t;plotBottom=H-pad.b;step=(W-pad.l-pad.r)/data.length;bw=Math.max(6,Math.min(26,step*0.6));bars=data.map((v,i)=>({{x:pad.l+step*i+step/2,v,i,label:labels[i]||'',phase:phases[i]||'',color:stageColors[stageOf(phases[i])]||neutral,y:yS(v)}}));}}
  function draw(prog){{const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);ctx.strokeStyle='rgba(27,25,21,.09)';ctx.lineWidth=1;[25,50,75,100].forEach(v=>{{const y=yS(v);ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(W-pad.r,y);ctx.stroke()}});ctx.strokeStyle='rgba(27,25,21,.35)';ctx.beginPath();ctx.moveTo(pad.l,plotBottom);ctx.lineTo(W-pad.r,plotBottom);ctx.stroke();ctx.fillStyle='rgba(27,25,21,.45)';ctx.font='600 9px Georgia,"Times New Roman",serif';ctx.textAlign='right';[0,50,100].forEach(v=>ctx.fillText(v,pad.l-2,yS(v)+3));bars.forEach(b=>{{const hh=Math.max(1,(plotBottom-b.y)*prog);ctx.fillStyle=b.color;ctx.fillRect(b.x-bw/2,plotBottom-hh,bw,hh);ctx.strokeStyle='rgba(27,25,21,.22)';ctx.lineWidth=1;ctx.strokeRect(b.x-bw/2+.5,plotBottom-hh+.5,Math.max(1,bw-1),Math.max(1,hh-1));if(b.i===hi){{ctx.strokeStyle='rgba(27,25,21,.85)';ctx.lineWidth=1.5;ctx.strokeRect(b.x-bw/2-1.5,plotBottom-hh-1.5,bw+3,hh+3)}}}});const every=step<26?2:1;ctx.fillStyle='rgba(27,25,21,.5)';ctx.font='600 9px Georgia,"Times New Roman",serif';ctx.textAlign='center';bars.forEach((b,i)=>{{if(b.label&&i%every===0)ctx.fillText(b.label,b.x,H-4)}});}}
  function animate(){{animProg+=0.05;if(animProg>1)animProg=1;draw(animProg);if(animProg<1)requestAnimationFrame(animate)}}size();animProg=0;animate();
  let resizeTimer;window.addEventListener('resize',()=>{{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{{size();draw(animProg)}},100)}});
  const canvasBox=canvas.parentElement;
  canvasBox.addEventListener('mousemove',e=>{{if(animProg<1)return;const rect=canvas.getBoundingClientRect();const mx=e.clientX-rect.left;const idx=Math.floor((mx-pad.l)/step);if(idx<0||idx>=bars.length){{hi=-1;tip.style.opacity='0';draw(1);return}}hi=idx;const b=bars[idx];draw(1);tip.querySelector('.v').textContent=b.v;tip.querySelector('.d').textContent=b.label+' · '+(b.phase||'阶段未知');const offX=canvas.offsetLeft,offY=canvas.offsetTop;const anchorX=b.x+offX,anchorY=b.y+offY;let left=anchorX-tip.offsetWidth/2;let top=anchorY-tip.offsetHeight-12;if(top<0){{top=anchorY+14;tip.classList.add('top')}}else{{tip.classList.remove('top')}}left=Math.max(4,Math.min(canvasBox.clientWidth-tip.offsetWidth-4,left));tip.style.left=left+'px';tip.style.top=top+'px';tip.style.opacity='1';}});
  canvasBox.addEventListener('mouseleave',()=>{{hi=-1;tip.style.opacity='0';if(animProg>=1)draw(1)}});
}})();
</script>"""

    # 大小周期节点票：缩放 + 横向拖动。单独成串，避免在内层再加一层转义。
    node_zoom_js = """<script>
(function(){
  var STEP = 0.25, MIN = 1, MAX = 4;
  document.querySelectorAll('.node-cycle').forEach(function(section){
    var box = section.querySelector('.node-zoom');
    var track = section.querySelector('.node-track');
    var scroll = section.querySelector('[data-node-scroll]');
    var label = section.querySelector('[data-node-zoom-value]');
    if(!box || !track || !label) return;
    var value = 1;
    function clamp(v){ return Math.min(MAX, Math.max(MIN, v)); }
    function render(){
      track.style.setProperty('--node-zoom', value);
      label.textContent = Math.round(value * 100) + '%';
      var outBtn = box.querySelector('[data-node-zoom="out"]');
      var inBtn = box.querySelector('[data-node-zoom="in"]');
      if(outBtn) outBtn.disabled = value <= MIN + 1e-6;
      if(inBtn) inBtn.disabled = value >= MAX - 1e-6;
    }
    function zoomTo(next, anchorRatio){
      var before = scroll ? scroll.scrollWidth : 0;
      var keepLeft = scroll ? scroll.scrollLeft : 0;
      value = clamp(next);
      render();
      if(!scroll) return;
      var after = scroll.scrollWidth;
      if(anchorRatio === null){ scroll.scrollLeft = 0; return; }
      scroll.scrollLeft = Math.max(0, anchorRatio * after - (anchorRatio * before - keepLeft));
    }
    box.addEventListener('click', function(event){
      var btn = event.target.closest('button[data-node-zoom]');
      if(!btn) return;
      var action = btn.getAttribute('data-node-zoom');
      var ratio = (scroll && scroll.scrollWidth > 0)
        ? scroll.scrollLeft / scroll.scrollWidth : 0.5;
      if(action === 'in') zoomTo(value + STEP, ratio);
      else if(action === 'out') zoomTo(value - STEP, ratio);
      else zoomTo(1, null);
    });
    render();
    if(!scroll) return;
    scroll.addEventListener('wheel', function(event){
      if(!event.ctrlKey) return;
      event.preventDefault();
      var rect = scroll.getBoundingClientRect();
      var pointer = (scroll.scrollLeft + (event.clientX - rect.left)) / Math.max(scroll.scrollWidth, 1);
      value = clamp(value + (event.deltaY < 0 ? STEP : -STEP));
      render();
      scroll.scrollLeft = Math.max(0, pointer * scroll.scrollWidth - (event.clientX - rect.left));
    }, {passive:false});
    var dragging = false, startX = 0, startLeft = 0;
    scroll.addEventListener('pointerdown', function(event){
      if(event.pointerType !== 'mouse' || event.button !== 0) return;
      if(event.target.closest('.node-bar')) return;
      dragging = true; startX = event.clientX; startLeft = scroll.scrollLeft;
      scroll.classList.add('dragging');
      if(scroll.setPointerCapture) scroll.setPointerCapture(event.pointerId);
    });
    scroll.addEventListener('pointermove', function(event){
      if(!dragging) return;
      scroll.scrollLeft = startLeft - (event.clientX - startX);
    });
    ['pointerup','pointercancel','pointerleave'].forEach(function(type){
      scroll.addEventListener(type, function(){
        dragging = false; scroll.classList.remove('dragging');
      });
    });
  });
})();
</script>"""
    chart_js = chart_js + node_zoom_js
    table_mobile_js = """<script>
document.querySelectorAll('table').forEach(function(table){
  var first=table.rows[0];if(!first)return;
  var hasHeaders=Array.prototype.some.call(first.cells,function(cell){return cell.tagName==='TH';});
  if(!hasHeaders)return;
  if(first.parentElement.tagName!=='THEAD'){
    var thead=document.createElement('thead');
    first.parentElement.insertBefore(thead,first);
    thead.appendChild(first);
  }
  Array.prototype.forEach.call(table.rows,function(row){
    if(row.parentElement.tagName==='THEAD')return;
    Array.prototype.forEach.call(row.cells,function(cell,index){
      if(cell.hasAttribute('colspan')||cell.dataset.label)return;
      var header=first.cells[index];
      if(header)cell.dataset.label=(header.textContent||'').trim();
    });
  });
});
</script>"""

    # ===== 组装完整HTML =====
    # 报头里的板块计数：真实渲染出来的板块数（含策略），不写死
    mast_sections = sum(
        1 for block in (hero, quote_html, news_sec, lhb_sec, rotation_sec, node_cycle_sec, yb_sec,
                        survey_sec, tgb_sec, dy_sec, events_sec, strategy_sec)
        if str(block).strip()
    )
    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>每日简报 — {today_display}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700;900&family=Playfair+Display:wght@600;700;900&display=swap" rel="stylesheet">
{css_block}
</head>
<body>
<header id="hdr"><span class="logo">每日简报</span><div class="hdr-right"><span class="hdr-date">{today_display}</span><span class="live-badge">每日快照</span></div></header>
<main class="c">
<div class="np-mast">
  <div class="np-mast-kicker">Daily A-Share Briefing</div>
  <h1 class="np-mast-title">每日简报</h1>
  <div class="np-mast-sub"><span>{today_display}</span><span class="sep">/</span><span>行情数据日 <b>{trade_date}</b></span><span class="sep">/</span><span>共 <b>{mast_sections}</b> 个板块</span><span class="sep">/</span><span>情绪模型 3.2</span></div>
</div>
{hero}
{node_cycle_sec}
{quote_html}
<div class="g">
{news_sec}
{lhb_sec}
{rotation_sec}
{yb_sec}
{survey_sec}
{tgb_sec}
{dy_sec}
{events_sec}
</div>
{strategy_sec}
<div class="ft">每日简报 · <span>v3.22</span> · {today_display} · 数据仅为信息整理，不构成投资建议</div>
</main>
{chart_js}
{table_mobile_js}
</body>
</html>"""

    if tgb_ai_failures:
        raise RuntimeError(
            "淘股吧有可核验内容但未取得 AI 语义摘要（"
            + "、".join(tgb_ai_failures)
            + "）。请检查 Codex CLI 登录、模型访问及语义调用时限，或确认 "
            "~/.codex/daily-briefing.env 中的 AI API Key 有效；未写出简报，避免把原始跟帖当观点交付。"
        )

    return full_html


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    today = get_date()
    trade_date = get_recent_trade_date(today)

    print(f"编译简报: {today} (交易日: {trade_date})", file=sys.stderr)

    try:
        from briefing_integrity import require_complete
        require_complete(DATA_DIR, today, trade_date)
        html = build_html(today, trade_date)
    except RuntimeError as exc:
        print(f"  [⛔] 编译已终止：{exc}", file=sys.stderr)
        raise SystemExit(3)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{today}简报.html"

    # Keep generated HTML byte-identical across Windows and Linux builds.
    with open(output_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(html)

    print(f"OK: {output_path}")
    print(f"Size: {len(html):,} chars")

    # 输出交付按钮
    abs_path = str(output_path).replace("\\", "/")
    encoded = quote(abs_path, safe="/:")
    button = f'<a href="file:///{encoded}" style="display:inline-block;padding:12px 28px;font-family:\'Microsoft YaHei\',sans-serif;font-size:15px;font-weight:700;color:#0b0f19;background:linear-gradient(135deg,#fbbf24,#f59e0b);border-radius:8px;text-decoration:none;box-shadow:0 4px 14px rgba(245,158,11,.35);border:1px solid rgba(255,255,255,.15);">📄 打开今日简报</a>'
    print(f"BUTTON:{button}")
