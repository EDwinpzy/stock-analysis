#!/usr/bin/env python3
"""
机构研报抓取（每日简报Pro专用）
从东方财富研报API获取最近3天的研报数据（只保留最近3天，含当天）

用法: python fetch_yanbao.py [--date YYYY-MM-DD]
输出: JSON 到 stdout（run_all.py 会保存为 data/yanbao_latest.json）

数据源: https://reportapi.eastmoney.com/report/list
"""
import json
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
import re

EASTMONEY_REPORT_API = 'https://reportapi.eastmoney.com/report/list'
_FETCH_ERROR = ""


def get_date():
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return datetime.now().strftime("%Y-%m-%d")


def _publish_date(report: dict) -> str:
    value = str(report.get("publishDate") or report.get("publish_time") or "")
    match = re.search(r"(\d{4}-\d{2}-\d{2})", value)
    return match.group(1) if match else ""


def filter_reports_by_date(reports: list, target_date: str, days: int = 3) -> list:
    """Keep reports in the inclusive window ending on ``target_date``.

    The API occasionally returns records outside the requested range.  Do
    the final date check locally so an old cache or a future record can never
    enter the briefing.
    """
    try:
        end = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        return []
    begin = end - timedelta(days=max(1, days) - 1)
    result = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        try:
            published = datetime.strptime(_publish_date(report), "%Y-%m-%d").date()
        except ValueError:
            continue
        if begin <= published <= end:
            result.append(report)
    return result


def report_date_range(reports: list) -> str:
    dates = sorted({_publish_date(report) for report in reports if isinstance(report, dict) and _publish_date(report)})
    if not dates:
        return ""
    if dates[0] == dates[-1]:
        return dates[0]
    return f"{dates[0]}~{dates[-1]}"


def fetch_reports(date: str, days: int = 3) -> list:
    """从东方财富获取最近 days 天的研报"""
    global _FETCH_ERROR
    _FETCH_ERROR = ""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    target = datetime.strptime(date, "%Y-%m-%d")
    begin = (target - timedelta(days=days - 1)).strftime("%Y%m%d")
    end = target.strftime("%Y%m%d")

    reports = []
    page = 1
    while page <= 3:  # 最多3页
        try:
            params = {
                'cb': 'datatable',
                'pageNo': str(page),
                'pageSize': '100',
                'code': '',
                'industryCode': '*',
                'qType': '0',
                'beginTime': begin,
                'endTime': end,
                'lastUpdateTime': ''
            }
            url = f"{EASTMONEY_REPORT_API}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
                    'Referer': 'https://data.eastmoney.com/report/'
                }
            )
            with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
                text = response.read().decode('utf-8')
            start = text.find('(')
            end_pos = text.rfind(')')
            if start > 0 and end_pos > start:
                json_str = text[start + 1:end_pos]
                data = json.loads(json_str)
            else:
                break

            items = data.get('data', [])
            if isinstance(items, dict):
                total = items.get('total', 0)
                items = items.get('list', [])
            else:
                total = 0
            if not items:
                break
            for item in items:
                pd_ = (item.get('publishDate', '') or '')[:10]
                if pd_ and pd_ >= begin[:4] + '-' + begin[4:6] + '-' + begin[6:] and pd_ <= end[:4] + '-' + end[4:6] + '-' + end[6:]:
                    reports.append({
                        'org': item.get('orgSName', '') or '未知机构',
                        'title': item.get('title', ''),
                        'stock': item.get('stockName', ''),
                        'code': item.get('stockCode', ''),
                        'rate': item.get('emRatingName', ''),
                        'publishDate': pd_,
                        'industry': item.get('industryName', '') or item.get('indvInduName', '') or '',
                        'logic': item.get('title', ''),
                        'source': '东方财富研报API',
                        'source_url': 'https://data.eastmoney.com/report/'
                    })
            # 不足一页则退出
            if len(items) < 100:
                break
            page += 1
        except Exception as e:
            _FETCH_ERROR = str(e)
            print(f"  [WARN] 研报抓取失败(第{page}页): {e}", file=sys.stderr)
            break

    # 按发布日期倒序，去重（标题+机构相同视为重复）
    seen = set()
    unique = []
    for r in sorted(reports, key=lambda x: x.get('publishDate', ''), reverse=True):
        key = f"{r['org']}|{r['title']}"
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def main():
    today = get_date()
    print(f"=== 机构研报抓取（最近3天，截止{today}）===\n", file=sys.stderr)

    reports = filter_reports_by_date(fetch_reports(today, days=3), today, days=3)
    print(f"  获取到 {len(reports)} 篇研报（最近3天）", file=sys.stderr)

    result = {
        "date": today,
        "data_date": report_date_range(reports),
        "count": len(reports),
        "reports": reports,
        "source": "东方财富研报API",
        "status": "error" if _FETCH_ERROR and not reports else ("ok" if reports else "empty"),
        "note": (f"数据获取失败：{_FETCH_ERROR}" if _FETCH_ERROR and not reports else
                 ("东方财富研报API · 目标日前3天窗口（不含未来或过期报告）" if reports else f"{today}前3天暂无可核验研报；未使用旧缓存")),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
