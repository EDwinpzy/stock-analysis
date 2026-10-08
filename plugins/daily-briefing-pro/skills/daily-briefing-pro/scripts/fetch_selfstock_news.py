#!/usr/bin/env python3
"""
自选股新闻抓取器 - 无浏览器后台HTTP请求
按自选股逐个抓取东方财富个股新闻/公告，输出JSON

用法:
    python scripts/fetch_selfstock_news.py [--date YYYY-MM-DD]
"""

import json
import os
import sys
from datetime import datetime, timedelta
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from parse_selfstock import get_selfstock_codes


_FETCH_ERROR = ""
_FETCH_FAILED_CODES = []


def get_today_str():
    """获取今天的日期字符串（支持 --date 覆盖）"""
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return datetime.now().strftime("%Y-%m-%d")


def get_recent_trade_date():
    """获取最近交易日（周末回退到周五，支持 --date 覆盖）"""
    date_str = get_today_str()
    today = datetime.strptime(date_str, "%Y-%m-%d")
    wd = today.weekday()
    if wd >= 5:  # 周六或周日
        days_back = wd - 4  # 周六=2天，周日=3天
        today = today - timedelta(days=days_back)
    return today.strftime("%Y-%m-%d")


def fetch_stock_news(code, per_stock=20):
    """按个股抓取东方财富新闻/公告（后台HTTP，经 AkShare 封装）。

    通用快讯流几乎不会点名小市值自选股，所以必须逐个股票查询；
    抓取失败时如实记录原因，不用其它日期的内容顶替。
    """
    global _FETCH_ERROR
    try:
        import akshare as ak
    except Exception as e:  # akshare 缺失属环境问题，必须显式暴露
        _FETCH_ERROR = f"akshare 不可用：{e}"
        return []

    try:
        frame = ak.stock_news_em(symbol=code)
    except Exception as e:
        _FETCH_FAILED_CODES.append(code)
        print(f"[WARN] {code} 个股新闻获取失败: {e}", file=sys.stderr)
        return []

    try:
        rows = frame.to_dict("records")
    except Exception:
        return []

    items = []
    for row in rows[:per_stock]:
        items.append({
            "title": str(row.get("新闻标题") or "").strip(),
            "content": str(row.get("新闻内容") or "").strip(),
            "publish_time": str(row.get("发布时间") or "").strip(),
            "source": str(row.get("文章来源") or "东方财富").strip(),
            "url": str(row.get("新闻链接") or "").strip(),
        })
    return items


def classify_news(text):
    """简单分类新闻为利好/利空/中性"""
    text = text.lower()
    bullish = [
        "利好", "增长", "上涨", "突破", "盈利", "中标", "回购", "增持",
        "大涨", "翻倍", "新高", "超预期", "订单", "业绩预增", "签约",
        "合作", "扩产", "投产", "获批", "通过", "中标", "预增"
    ]
    bearish = [
        "利空", "下跌", "亏损", "减持", "暴雷", "调查", "处罚", "风险",
        "下调", "违约", "退市", "破产", "诉讼", "暴跌", "解禁", "问询",
        "立案", "违规", "下降", "下滑"
    ]
    is_bullish = any(kw in text for kw in bullish)
    is_bearish = any(kw in text for kw in bearish)
    if is_bullish and not is_bearish:
        return "利好"
    if is_bearish and not is_bullish:
        return "利空"
    return "中性"


def parse_news_time(time_str):
    """解析新闻时间，返回(date, time)"""
    if not time_str:
        # Missing timestamps cannot prove the item belongs to the target
        # window; do not guess the report date.
        return "", ""
    # 处理 '2026-07-06 12:01:00' 或 '2026-07-06 12:01'
    parts = time_str.split(" ")
    if len(parts) >= 2:
        date_part = parts[0]
        time_part = parts[1][:5] if len(parts[1]) >= 5 else parts[1]
        return date_part, time_part
    if len(time_str) >= 10:
        date_part = time_str[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_part):
            try:
                datetime.strptime(date_part, "%Y-%m-%d")
                return date_part, ""
            except ValueError:
                pass
    return "", ""


def date_range_label(dates):
    values = sorted({d for d in dates if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d))})
    if not values:
        return ""
    return values[0] if values[0] == values[-1] else f"{values[0]}~{values[-1]}"


def main():
    target_date = get_today_str()
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    self_codes = set(get_selfstock_codes())
    if not self_codes:
        print(json.dumps({
            "date": target_date,
            "data_date": "",
            "selfstock_count": 0,
            "news_count": 0,
            "news": [],
            "status": "empty",
            "source": "东方财富个股新闻API (AkShare)",
            "note": "未找到自选股，请检查 THS_SELFSTOCK_PATH 环境变量或 SelfStockInfo.json"
        }, ensure_ascii=False, indent=2))
        return

    filtered = []
    seen_titles = set()
    cutoff = target_dt - timedelta(days=2)  # 目标日前3个自然日，含目标日

    # 逐只自选股抓取个股新闻/公告（后台HTTP）
    for code in sorted(self_codes):
        for item in fetch_stock_news(code):
            title = item["title"]
            full_text = title + item["content"]
            if not title or title in seen_titles:
                continue

            date_str, time_str = parse_news_time(item["publish_time"])
            try:
                news_dt = datetime.strptime(date_str, "%Y-%m-%d")
                if news_dt < cutoff or news_dt > target_dt:
                    continue
            except Exception:
                continue

            seen_titles.add(title)
            filtered.append({
                "time": time_str,
                "date": date_str,
                "type": classify_news(full_text),
                "title": title[:90],
                "source": item["source"] or "东方财富",
                "url": item["url"],
                "related_codes": [code],
            })

    # 按日期+时间倒序，取前15条
    filtered.sort(key=lambda x: (x["date"], x["time"]), reverse=True)
    filtered = filtered[:15]

    result = {
        "date": target_date,
        "data_date": date_range_label([n["date"] for n in filtered]),
        "selfstock_count": len(self_codes),
        "news_count": len(filtered),
        "news": filtered,
        "status": "error" if _FETCH_ERROR else ("ok" if filtered else "empty"),
        "source": "东方财富个股新闻API (AkShare)",
    }
    if _FETCH_ERROR:
        result["data_date"] = ""
    failed_note = (
        f"；{len(_FETCH_FAILED_CODES)}只个股接口失败（{','.join(_FETCH_FAILED_CODES[:5])}…）"
        if _FETCH_FAILED_CODES else ""
    )
    if not filtered:
        result["note"] = (
            f"数据获取失败：{_FETCH_ERROR}" if _FETCH_ERROR
            else f"{target_date}前3天内{len(self_codes)}只自选股均无个股新闻/公告{failed_note}"
        )
    else:
        result["note"] = (
            f"逐只自选股查询东方财富个股新闻，仅保留{target_date}前3天内且不晚于目标日的条目{failed_note}"
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
