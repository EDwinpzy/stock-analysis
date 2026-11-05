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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from runtime_paths import get_data_dir
from summary_cache import (
    get_cached_summary,
    load_summary_cache,
    save_summary_cache,
    set_cached_summary,
)

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
                        'logic': '',
                        'infoCode': item.get('infoCode', ''),
                        'source': '东方财富研报API',
                        'source_url': f"https://data.eastmoney.com/report/info/{item.get('infoCode', '')}.html"
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


def attach_report_body(report: dict) -> dict:
    """Bind each report to its original text and validate the stock association."""
    import requests
    from bs4 import BeautifulSoup
    result = dict(report)
    try:
        session = requests.Session()
        session.trust_env = False
        response = session.get(result['source_url'], timeout=25)
        response.raise_for_status()
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        body = soup.select_one('.ctx-content')
        if body is None or len(body.get_text(strip=True)) < 40:
            raise ValueError('研报正文缺失')
        result['content'] = body.get_text(' ', strip=True)
        result['verified'] = True
        code = str(result.get('code') or '')
        if code and code not in result['content'][:160]:
            result['api_stock_tag'] = {'stock': result.get('stock'), 'code': code}
            result['stock'], result['code'] = '', ''
        pdf = soup.find('a', href=re.compile(r'pdf', re.I))
        if pdf:
            result['pdf_url'] = urllib.parse.urljoin(result['source_url'], pdf['href'])
    except Exception as exc:
        result['verified'] = False
        result['verification_error'] = type(exc).__name__
    return result


def _codex_summary_functions():
    """Load the authenticated local semantic summarizer when available."""
    try:
        from codex_summary_cli import semantic_summary_available, summarize_tasks
    except ImportError:
        return None, None
    return semantic_summary_available, summarize_tasks


def _usable_report_logic(value: str) -> bool:
    normalized = str(value or "").strip()
    return bool(normalized and normalized not in {"无明确观点", "无明确投资观点"})


def enrich_report_logic(
    reports: list[dict],
    target_date: str,
    cache_path: Path,
    *,
    available_fn=None,
    summarize_fn=None,
) -> dict:
    """Summarize verified report bodies and cache only date/hash-bound results."""
    cache_path = Path(cache_path)
    cache = load_summary_cache(cache_path)
    pending: list[tuple[int, str, str, str]] = []

    for index, report in enumerate(reports):
        report["logic"] = ""
        report["logic_status"] = "unverified_source"
        content = str(report.get("content") or "").strip()
        if not report.get("verified") or not content:
            continue
        source_key = str(report.get("infoCode") or report.get("source_url") or "").strip()
        if not source_key:
            report["logic_status"] = "missing_source_identity"
            continue
        cached = get_cached_summary(cache, target_date, "yanbao", source_key, content)
        if cached and _usable_report_logic(cached):
            report["logic"] = cached
            report["logic_status"] = "semantic_cached"
            continue
        context = (
            "任务：概括这篇机构研报的投资逻辑。仅依据经过核验的正文；标题、机构、行业、评级等元数据"
            "只用于定位，不得作为正文没有表达的事实或因果依据。尽可能说明正文明确给出的驱动因素、"
            "传导路径和受益/受损标的。若正文未提供清晰因果链，直接说明资料未提供，不要推断。"
        )
        pending.append((index, source_key, content, context))

    generated = 0
    generation_error = ""
    if pending:
        if available_fn is None or summarize_fn is None:
            default_available, default_summarize = _codex_summary_functions()
            available_fn = available_fn or default_available
            summarize_fn = summarize_fn or default_summarize
        try:
            if not available_fn or not available_fn():
                raise RuntimeError("semantic summarizer unavailable")
            summaries = summarize_fn([(content, context) for _, _, content, context in pending])
            if not isinstance(summaries, list) or len(summaries) != len(pending):
                raise RuntimeError("semantic summarizer returned an incomplete result")
            for (index, source_key, content, _), summary in zip(pending, summaries):
                if not isinstance(summary, str) or not _usable_report_logic(summary):
                    reports[index]["logic_status"] = "semantic_summary_missing"
                    continue
                summary = summary.strip()
                reports[index]["logic"] = summary
                reports[index]["logic_status"] = "semantic_generated"
                set_cached_summary(cache, target_date, "yanbao", source_key, content, summary)
                generated += 1
        except Exception as exc:
            generation_error = type(exc).__name__
            for index, _, _, _ in pending:
                reports[index]["logic_status"] = "semantic_generation_failed"

    if generated:
        save_summary_cache(cache, cache_path)
    verified = [report for report in reports if report.get("verified") and str(report.get("content") or "").strip()]
    missing = sum(not _usable_report_logic(report.get("logic")) for report in verified)
    return {
        "verified_reports": len(verified),
        "summarized_reports": len(verified) - missing,
        "missing_summaries": missing,
        "generation_error": generation_error,
    }


def main():
    today = get_date()
    print(f"=== 机构研报抓取（最近3天，截止{today}）===\n", file=sys.stderr)

    reports = filter_reports_by_date(fetch_reports(today, days=3), today, days=3)
    with ThreadPoolExecutor(max_workers=4) as executor:
        reports = list(executor.map(attach_report_body, reports))
    semantic = enrich_report_logic(
        reports,
        today,
        get_data_dir(Path(__file__).parent.parent) / 'yanbao_ai_summaries.json',
    )
    print(f"  获取到 {len(reports)} 篇研报（最近3天）", file=sys.stderr)

    fetch_note = f"数据获取失败：{_FETCH_ERROR}" if _FETCH_ERROR and not reports else ""
    if _FETCH_ERROR and reports:
        fetch_note = f"研报分页采集不完整：{_FETCH_ERROR}"
    if semantic["missing_summaries"]:
        semantic_note = f"{semantic['missing_summaries']}篇研报缺少基于核验正文的语义逻辑"
        if semantic["generation_error"]:
            semantic_note += f"（{semantic['generation_error']}）"
    else:
        semantic_note = ""
    notes = [note for note in (fetch_note, semantic_note) if note]
    status = (
        "error" if not reports and (_FETCH_ERROR or semantic["generation_error"])
        else "empty" if not reports
        else "partial" if _FETCH_ERROR or semantic["missing_summaries"]
        else "ok"
    )

    result = {
        "date": today,
        "data_date": report_date_range(reports),
        "count": len(reports),
        "reports": reports,
        "verified_count": sum(bool(r.get('verified')) for r in reports),
        "source": "东方财富研报API",
        "semantic_summary": semantic,
        "status": status,
        "note": "；".join(notes) or (
            "东方财富研报API · 目标日前3天窗口（不含未来或过期报告）"
            if reports else f"{today}前3天暂无可核验研报；未使用旧缓存"
        ),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
