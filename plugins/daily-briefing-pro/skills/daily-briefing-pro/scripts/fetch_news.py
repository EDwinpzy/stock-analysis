#!/usr/bin/env python3
"""
财经新闻抓取器 - 东方财富API
用法: python fetch_news.py --source eastmoney --limit 15
"""

import json
import urllib.request
import urllib.parse
import ssl
from datetime import datetime
import sys
import re


_FETCH_ERROR = ""
_THS_ERROR = ""


def _item_date(item: dict) -> str:
    """Return the calendar date carried by a fast-news item."""
    value = item.get("showTime") or item.get("time") or item.get("publishTime") or item.get("date") or ""
    match = re.search(r"(\d{4}-\d{2}-\d{2})", str(value))
    return match.group(1) if match else ""


def filter_news_by_date(items: list, target_date: str) -> list:
    """Keep only items whose source timestamp is on ``target_date``.

    The Eastmoney endpoint can return the latest news regardless of the
    requested report date.  Filtering here prevents a weekend report from
    silently mixing a different day's headlines into a dated snapshot.
    Items without a parseable timestamp are discarded rather than guessed.
    """
    return [item for item in items if isinstance(item, dict) and _item_date(item) == target_date]


def _normalise_stock_list(value) -> list:
    """Return only real six-digit stock codes/names from API metadata.

    The endpoint also labels sectors and valuation figures as ``stockList``
    values (for example ``90.BK0437`` and ``0.161032``).  Those are not
    investable symbols and must not be rendered as stock tags.
    """
    values = value if isinstance(value, list) else []
    result = []
    seen = set()
    for item in values:
        if isinstance(item, dict):
            candidates = [item.get("code"), item.get("stockCode"), item.get("name"), item.get("stockName")]
        else:
            candidates = [item]
        for candidate in candidates:
            text = str(candidate or "").strip()
            if re.fullmatch(r"\d{6}", text) or (text and not re.search(r"[.\s]", text) and len(text) <= 12 and re.search(r"[\u4e00-\u9fffA-Za-z]", text)):
                if text not in seen:
                    seen.add(text)
                    result.append(text)
                break
    return result[:8]


def fetch_eastmoney_news(limit: int = 15, target_date: str | None = None) -> list:
    """从东方财富获取财经快讯"""
    global _FETCH_ERROR
    _FETCH_ERROR = ""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    # 东方财富快讯API - 使用正确的参数
    url = "https://np-listapi.eastmoney.com/comm/web/getFastNewsList"
    params = {
        "client": "web",
        "biz": "web_724",
        "fastColumn": "102",
        "sortEnd": "",
        "pageSize": str(limit),
        "req_trace": "1"
    }
    
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        full_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.eastmoney.com/"
        }
    )
    
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        _FETCH_ERROR = str(e)
        print(f"东方财富快讯获取失败: {e}", file=sys.stderr)
        return []
    
    # 东方财富API返回code=1表示成功
    if "data" not in data:
        _FETCH_ERROR = f"API返回异常：{data}"
        print(f"API返回异常: {data}", file=sys.stderr)
        return []
    
    raw_items = data["data"].get("fastNewsList", [])
    if target_date:
        raw_items = filter_news_by_date(raw_items, target_date)

    news_list = []
    for item in raw_items:
        news = {
            "title": item.get("title", ""),
            "content": item.get("summary", item.get("content", "")),
            "time": item.get("showTime", ""),
            "source": "东方财富",
            "url": f"https://finance.eastmoney.com/a/{item.get('code', '')}.html",
            "type": classify_news(item.get("title", "") + item.get("summary", "")),
            "stocks": _normalise_stock_list(item.get("stockList", []))
        }
        news_list.append(news)
    
    return news_list


def classify_news(text: str) -> str:
    """简单分类新闻"""
    text = text.lower()
    
    # 利好关键词
    bullish_kw = ["利好", "增长", "上涨", "突破", "盈利", "中标", "回购", "增持", 
                  "大涨", "翻倍", "新高", "超预期", "订单", "业绩预增"]
    # 利空关键词
    bearish_kw = ["利空", "下跌", "亏损", "减持", "暴雷", "调查", "处罚", "风险",
                  "下调", "违约", "退市", "破产", "诉讼", "暴跌"]
    # 行业关键词
    industry_kw = ["半导体", "芯片", "新能源", "光伏", "锂电池", "AI", "人工智能",
                   "医药", "医疗", "消费", "白酒", "汽车", "地产", "银行", "券商"]
    
    is_bullish = any(kw in text for kw in bullish_kw)
    is_bearish = any(kw in text for kw in bearish_kw)
    
    # 提取标的关键词
    symbols = []
    if "半导体" in text or "芯片" in text:
        symbols.append("半导体")
    if "新能源" in text or "光伏" in text:
        symbols.append("新能源")
    if "AI" in text or "人工智能" in text:
        symbols.append("AI")
    if "医药" in text or "医疗" in text:
        symbols.append("医药")
    
    if is_bullish:
        return "利好"
    elif is_bearish:
        return "利空"
    else:
        return "中性"


def fetch_global_tech_news(limit: int = 10) -> list:
    """获取国际科技新闻"""
    global _THS_ERROR
    _THS_ERROR = ""
    # 尝试使用其他新闻源
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    # 使用同花顺7x24快讯API作为补充
    url = "https://news.10jqka.com.cn/realtimenews.html"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://news.10jqka.com.cn/"
        }
    )
    
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            html = resp.read().decode('utf-8')
            # 简单解析
            import re
            news_list = []
            # 提取新闻条目
            items = re.findall(r'<li[^>]*>.*?</li>', html[:50000], re.DOTALL)[:limit]
            for item in items:
                title_match = re.search(r'title="([^"]+)"', item)
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', item)
                time_match = re.search(r'(\d{2}:\d{2})', item)
                if title_match:
                    shown_time = time_match.group(1) if time_match else ""
                    if date_match and shown_time:
                        shown_time = f"{date_match.group(1)} {shown_time}"
                    news_list.append({
                        "title": title_match.group(1),
                        "content": "",
                        "time": shown_time,
                        "source": "同花顺",
                        "url": "",
                        "type": classify_news(title_match.group(1))
                    })
            return news_list
    except Exception as e:
        _THS_ERROR = str(e)
        print(f"同花顺快讯获取失败: {e}", file=sys.stderr)
        return []


def main():
    import argparse
    parser = argparse.ArgumentParser(description="财经新闻抓取器")
    parser.add_argument("--source", choices=["eastmoney", "ths", "all"], default="eastmoney")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--date", type=str, default=None, help="指定日期 YYYY-MM-DD，默认今天")
    args = parser.parse_args()
    
    date_str = args.date if args.date else datetime.now().strftime("%Y-%m-%d")
    result = {
        "date": date_str,
        "fetch_time": datetime.now().strftime("%H:%M:%S"),
        "data_date": date_str,
        "source": "东方财富快讯API",
        "news": []
    }
    
    if args.source in ["eastmoney", "all"]:
        print("[1/2] 获取东方财富快讯...", file=sys.stderr)
        em_news = fetch_eastmoney_news(args.limit, target_date=date_str)
        result["news"].extend(em_news)
        print(f"  获取 {len(em_news)} 条", file=sys.stderr)
    
    if args.source in ["ths", "all"]:
        print("[2/2] 获取同花顺快讯...", file=sys.stderr)
        ths_news = fetch_global_tech_news(args.limit)
        result["news"].extend(ths_news)
        print(f"  获取 {len(ths_news)} 条", file=sys.stderr)
    
    # 所有来源都必须带有明确的目标日期；只有时分而没有日期的页面条目不能
    # 被放进带日期的简报，避免把实时抓取结果误当成历史数据。
    result["news"] = [n for n in result["news"] if _item_date(n) == date_str]
    fetch_error = _FETCH_ERROR or (_THS_ERROR if args.source in ["ths", "all"] and not result["news"] else "")
    if fetch_error:
        result["status"] = "error"
        result["data_date"] = ""
        result["note"] = f"数据获取失败：{fetch_error}"
    elif result["news"]:
        actual_dates = sorted({_item_date(n) for n in result["news"] if _item_date(n)})
        result["data_date"] = actual_dates[-1] if actual_dates else date_str
        result["status"] = "ok"
        result["note"] = f"仅保留{date_str}当日有明确时间戳的新闻"
    else:
        result["status"] = "empty"
        result["data_date"] = ""
        result["note"] = f"{date_str}暂无可核验新闻；未使用其他日期内容"

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
