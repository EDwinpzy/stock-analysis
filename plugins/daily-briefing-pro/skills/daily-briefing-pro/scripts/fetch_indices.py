"""Persist a source dated snapshot of all four index cards."""
import json
import sys
from datetime import datetime, timezone, timedelta
from build_briefing import fetch_index_data
from trading_date import get_recent_trade_date

date = sys.argv[sys.argv.index('--date')+1] if '--date' in sys.argv else datetime.now(timezone(timedelta(hours=8))).date().isoformat()
indices = fetch_index_data(get_recent_trade_date(date))
print(json.dumps({'date': date, 'indices': indices, 'source': 'AkShare：新浪日线；KOSPI东方财富备用日线', 'status': 'error' if indices.get('_errors') else 'ok'}, ensure_ascii=False, indent=2))
