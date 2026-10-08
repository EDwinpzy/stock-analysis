#!/usr/bin/env python3
"""从东方财富财经日历接口读取目标日起 14 天内的未来事件。

数据源为东方财富网财经日历（https://data.eastmoney.com/cjrl/）的公开报表接口
``RPT_CPH_FECALENDAR``。只输出接口中带明确 ``START_DATE`` 的条目：过去的事件和
没有日期的条目一律丢弃，不做任何日期推算。
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta


API_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
REPORT_NAME = "RPT_CPH_FECALENDAR"
COLUMNS = "START_DATE,END_DATE,FE_CODE,FE_NAME,FE_TYPE,STD_TYPE_CODE,SPONSOR_NAME,CITY,CONTENT"
SOURCE_PAGE = "https://data.eastmoney.com/cjrl/"
WINDOW_DAYS = 14

_FETCH_ERROR = ""


def get_today_str():
    if "--date" in sys.argv:
        index = sys.argv.index("--date")
        if index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return datetime.now().strftime("%Y-%m-%d")


def get_today_dt():
    try:
        return datetime.strptime(get_today_str(), "%Y-%m-%d")
    except ValueError:
        return datetime.now()


def get_offset_date_str(days, base=None):
    return ((base or get_today_dt()) + timedelta(days=days)).strftime("%Y-%m-%d")


IMPORTANT_KEYWORDS = [
    "利率", "CPI", "PPI", "GDP", "FOMC", "央行", "降息", "加息",
    "非农", "LPR", "MLF", "PMI", "通胀", "美联储",
]

DOMESTIC_MARKERS = ["中国", "国内", "A股", "沪", "深", "央行", "发改委", "工信部"]


def build_calendar_filter(target_date: str, days: int = WINDOW_DAYS) -> str:
    """构造接口过滤条件：目标日当天起至窗口结束的日历条目。"""
    end_exclusive = (
        datetime.strptime(target_date, "%Y-%m-%d") + timedelta(days=days + 1)
    ).strftime("%Y-%m-%d")
    return f"(END_DATE>='{target_date}')(START_DATE<'{end_exclusive}')"


def fetch_calendar(target_date: str, days: int = WINDOW_DAYS, page_size: int = 200):
    """后台 HTTP 读取财经日历，失败时记录原因并返回空列表。"""
    global _FETCH_ERROR
    _FETCH_ERROR = ""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    params = {
        "reportName": REPORT_NAME,
        "columns": COLUMNS,
        "pageNumber": "1",
        "pageSize": str(page_size),
        "sortColumns": "START_DATE",
        "sortTypes": "1",
        "filter": build_calendar_filter(target_date, days),
        "source": "WEB",
        "client": "WEB",
    }
    request = urllib.request.Request(
        f"{API_URL}?{urllib.parse.urlencode(params)}",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": SOURCE_PAGE,
        },
    )
    try:
        with urllib.request.urlopen(request, context=context, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        _FETCH_ERROR = str(exc)
        print(f"财经日历获取失败: {exc}", file=sys.stderr)
        return []

    if not payload.get("success"):
        _FETCH_ERROR = str(payload.get("message") or "接口返回失败")
        print(f"财经日历接口返回失败: {_FETCH_ERROR}", file=sys.stderr)
        return []

    rows = (payload.get("result") or {}).get("data") or []
    if not isinstance(rows, list):
        _FETCH_ERROR = "接口返回的数据结构异常"
        return []
    return rows


def _event_type(fe_type: str, text: str) -> str:
    mapping = {
        "经济数据": "宏观",
        "高峰论坛": "会议",
        "行业会议": "会议",
        "其他会议": "会议",
        "休市安排": "休市",
        "新股申购": "IPO",
        "新股上市": "IPO",
        "解禁": "解禁",
        "财报发布": "业绩",
    }
    if fe_type in mapping:
        return mapping[fe_type]
    for keyword, label in [
        ("CPI", "通胀"), ("PPI", "通胀"), ("PMI", "PMI"), ("GDP", "宏观"),
        ("解禁", "解禁"), ("上市", "IPO"), ("峰会", "会议"), ("论坛", "会议"),
    ]:
        if keyword in text:
            return label
    return "宏观"


def _country(city: str, text: str) -> str:
    for marker in DOMESTIC_MARKERS:
        if marker in city or marker in text:
            return "中国"
    return "国际"


def build_future_events(rows, target_date: str, days: int = WINDOW_DAYS) -> list:
    """把日历原始行规范化为简报事件列表，丢弃过去/无日期/越窗条目。"""
    try:
        start = datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        return []
    end = start + timedelta(days=days)

    events, seen = [], set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        raw_start = str(row.get("START_DATE") or "")
        try:
            event_dt = datetime.strptime(raw_start[:10], "%Y-%m-%d")
        except ValueError:
            continue  # 没有明确日期就不猜
        if event_dt < start or event_dt > end:
            continue

        name = str(row.get("FE_NAME") or "").strip()
        if not name:
            continue
        content = str(row.get("CONTENT") or "").strip()
        sponsor = str(row.get("SPONSOR_NAME") or "").strip()
        city = str(row.get("CITY") or "").strip()
        fe_type = str(row.get("FE_TYPE") or "").strip()
        text = f"{name}{content}{sponsor}{city}"

        date_label = event_dt.strftime("%m/%d")
        key = f"{date_label}-{name[:40]}"
        if key in seen:
            continue
        seen.add(key)

        importance = "重要" if any(kw in text for kw in IMPORTANT_KEYWORDS) else "中等"
        event_time = raw_start[11:16] if len(raw_start) >= 16 else ""
        events.append({
            "date": date_label,
            "time": event_time,
            "country": _country(city, name),
            "type": _event_type(fe_type, text),
            "event": name[:80],
            "forecast": "",
            "previous": "",
            "importance": importance,
            "impact": "中性",
            "description": (content or name)[:120],
            "sponsor": sponsor,
            "source": "东方财富财经日历",
            "source_url": SOURCE_PAGE,
            # 同一天先排重要事件，便于选取时保留关键宏观数据
            "_sort": (event_dt, 0 if importance == "重要" else 1, event_time, name),
        })

    events.sort(key=lambda item: item["_sort"])
    for item in events:
        item.pop("_sort", None)
    return events


def select_events(events, total_limit: int = 20, per_day_limit: int = 3) -> list:
    """限制单日条数，避免日历接口把窗口填满成同一天的流水账。"""
    per_day = {}
    selected = []
    for item in events:
        day = item.get("date", "")
        if per_day.get(day, 0) >= per_day_limit:
            continue
        per_day[day] = per_day.get(day, 0) + 1
        selected.append(item)
        if len(selected) >= total_limit:
            break
    return selected


def main():
    target = get_today_str()
    events = build_future_events(fetch_calendar(target), target)
    selected = select_events(events)
    if _FETCH_ERROR:
        status = "error"
        data_date = ""
        note = f"数据获取失败：东方财富财经日历：{_FETCH_ERROR}"
    elif selected:
        status = "ok"
        data_date = target
        note = "取自东方财富财经日历接口，仅保留带明确日期且在窗口内的事件"
    else:
        status = "empty"
        data_date = ""
        note = "目标窗口暂无带明确日期的可核验事件；未使用日期推算"
    print(json.dumps({
        "date": target,
        "data_date": data_date,
        "range": f"{target} ~ {get_offset_date_str(WINDOW_DAYS)}",
        "event_count": len(selected),
        "events": selected,
        "source": "东方财富财经日历",
        "status": status,
        "note": note,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
