"""Require dated, usable data for every section before delivering a full brief."""
from __future__ import annotations

import json
import math
from datetime import date as calendar_date, timedelta
from pathlib import Path
from data_quality import dataset_state

MODULES = {
    'panic_today.json': ('市场温度', 'score', True),
    'lianban_today.json': ('盘面补充', 'overview', True),
    'news_today.json': ('财经新闻', 'news', False),
    'lhb_today.json': ('龙虎榜', 'top_net_buy', True),
    'rotation_today.json': ('行业轮动', 'entries', True),
    'yanbao_latest.json': ('机构研报', 'reports', False),
    'sentiment_survey_today.json': ('博主多空调查', 'analyses', True),
    'tgb_today.json': ('淘股吧', 'bloggers', True),
    'douyin_today.json': ('抖音', 'bloggers', True),
    'events_today.json': ('未来事件', 'events', False),
}


def validate_data(data: dict, date: str, trade_date: str, quote: str) -> list[str]:
    failures = []
    for filename, (name, key, allow_trade) in MODULES.items():
        item = data.get(filename, {})
        # Research uses a documented three-day publication window.
        fallback = trade_date if allow_trade else ((calendar_date.fromisoformat(date) - timedelta(days=2)).isoformat() if filename == 'yanbao_latest.json' else None)
        state, reason = dataset_state(item, date, fallback)
        if state != 'ok':
            failures.append(f'{name}：{reason}')
            continue
        value = item.get(key)
        if value is None or value == [] or value == {} or value == '':
            failures.append(f'{name}：内容为空')
        if filename == 'panic_today.json' and (not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100):
            failures.append('市场温度：分数无效')
        if filename == 'rotation_today.json' and item.get('asof') != trade_date:
            failures.append('行业轮动：模型行情未更新至最近交易日')
        if filename == 'douyin_today.json':
            videos = [v for b in item.get('bloggers', []) for v in b.get('videos', [])]
            if not videos or any(not str(v.get('transcript') or '').strip() or v.get('warning') for v in videos):
                failures.append('抖音：存在未完成转录的视频')
            if item.get('expected_video_count', len(videos)) != len(videos):
                failures.append('抖音：目标视频遗漏')
        if filename == 'tgb_today.json':
            coverage = item.get('coverage', {})
            if coverage.get('complete_bloggers', 0) < coverage.get('expected_bloggers', 4) or coverage.get('failed_bloggers'):
                failures.append('淘股吧：账号页面核验不完整')
        if filename == 'sentiment_survey_today.json':
            coverage = item.get('platform_coverage', {})
            if any(not coverage.get(p) or coverage[p].get('failed_bloggers') or coverage[p].get('complete_bloggers', 0) != coverage[p].get('expected_bloggers') for p in ('淘股吧', '雪球')):
                failures.append('博主多空调查：两个平台覆盖未完成')
            if item.get('analysis_method') != '语义核验':
                failures.append('博主多空调查：观点方向尚未经过语义核验')
        if filename == 'yanbao_latest.json' and any(not r.get('verified') or not r.get('logic') or not r.get('source_url') for r in item.get('reports', [])):
            failures.append('机构研报：原文或核心逻辑未核验')
    node = data.get('node_cycle_today.json', {})
    if node.get('status') != 'ok' or not node.get('rows') or not node.get('axis_dates') or max(node['axis_dates']) != trade_date:
        failures.append('大小周期节点：数据缺失或日期不符')
    snapshot = data.get('indices_today.json', {})
    indices = snapshot.get('indices', {})
    if snapshot.get('date') != date:
        failures.append('指数：快照日期不符')
    for name in ('上证', '科创50', '纳斯达克', 'KOSPI'):
        item = indices.get(name, {})
        change = item.get('chg')
        if not isinstance(item.get('close'), (int, float)) or not math.isfinite(item['close']) or item['close'] <= 0 or not isinstance(change, (int, float)) or not math.isfinite(change) or not item.get('data_date') or item['data_date'] > date:
            failures.append(f'指数{name}：行情缺失或无效')
    if not quote.strip() or '数据获取失败' in quote or 'https://' not in quote:
        failures.append('每日一句：数据缺失')
    return list(dict.fromkeys(failures))


def require_complete(data_dir: Path, date: str, trade_date: str) -> None:
    data = {}
    for filename in (*MODULES, 'node_cycle_today.json', 'indices_today.json'):
        try:
            data[filename] = json.loads((data_dir / filename).read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            data[filename] = {}
    try:
        quote = (data_dir / 'quote_today.html').read_text(encoding='utf-8-sig')
    except OSError:
        quote = ''
    failures = validate_data(data, date, trade_date, quote)
    if failures:
        raise RuntimeError('完整简报未通过逐模块验收：' + '；'.join(failures))
