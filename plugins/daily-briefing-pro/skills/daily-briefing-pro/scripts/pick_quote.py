#!/usr/bin/env python3
"""
每日一句投资名言 — 去重选取器

从 data/investment_quotes.json 随机选取一条当天未用过的名言，
写入 data/used_quotes.json 记录已用ID。
当所有名言用完时自动重置列表。

用法：
    python scripts/pick_quote.py              # 输出JSON到stdout
    python scripts/pick_quote.py --html       # 输出HTML片段
"""

import json
import random
import os
import sys
from datetime import datetime
from html import escape

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
from runtime_paths import get_data_dir

DATA_DIR = str(get_data_dir(os.path.abspath(SKILL_DIR)))

QUOTES_FILE = os.path.join(SKILL_DIR, "data", "investment_quotes.json")
USED_FILE = os.path.join(DATA_DIR, "used_quotes.json")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def pick_quote():
    quotes = [q for q in load_json(QUOTES_FILE) if q.get('verified') and q.get('source_url')]
    if not quotes:
        raise ValueError('没有已核验原始出处的名言')
    used = load_json(USED_FILE) if os.path.exists(USED_FILE) else {}
    target_date = datetime.now().strftime('%Y-%m-%d')
    if '--date' in sys.argv:
        target_date = sys.argv[sys.argv.index('--date') + 1]
    selections = used.setdefault('selections', {})
    previous = next((q for q in quotes if q['id'] == selections.get(target_date)), None)
    if previous:
        return previous, len({q['id'] for q in quotes} - set(used.get('used_ids', [])))

    used_ids = set(used.get("used_ids", []))
    all_ids = {q["id"] for q in quotes}

    available = all_ids - used_ids

    # 全部用完 → 重置
    if not available:
        print("// [pick_quote] 所有名言已用完，自动重置", file=sys.stderr)
        used_ids = set()
        available = all_ids

    chosen_id = random.choice(list(available))
    chosen = next(q for q in quotes if q["id"] == chosen_id)
    selections[target_date] = chosen_id

    # 更新已用列表
    used_ids.add(chosen_id)
    used["used_ids"] = sorted(used_ids)
    # --date 支持（仅影响 last_updated 时间戳）
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        used["last_updated"] = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else datetime.now().strftime("%Y-%m-%d %H:%M")
    else:
        used["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_json(USED_FILE, used)

    return chosen, len(available) - 1  # remaining count after this pick


def to_html(quote_data, remaining):
    """生成每日一句HTML"""
    q = quote_data
    return f"""<!-- ⑪ 每日一句 -->
<section class="quote-banner">
  <div class="quote-mark">❝</div>
  <div class="quote-text">{q['quote']}</div>
  <div class="quote-author">
    —— <strong>{q['author']}</strong>
    <span class="quote-title">{q['author_title']}</span>
  </div>
  <div class="quote-principle">
    <span class="quote-icon">💡</span> {q['principle']}
  </div>
  <div class="quote-tags">
    {" ".join(f'<span class="quote-tag">{t}</span>' for t in q['tags'])}
  </div>
  <div class="quote-meta">今日金句 · 剩余 {remaining} 条未用</div>
  <div class="quote-meta"><a href="{escape(q['source_url'], quote=True)}" target="_blank" rel="noopener">{escape(q.get('source_title', '原始出处'))}</a></div>
</section>"""


def to_json_output(quote_data, remaining):
    """输出JSON格式（供generate_briefing.py解析）"""
    return json.dumps({
        "status": "ok",
        "quote": quote_data,
        "remaining": remaining
    }, ensure_ascii=False)


def error_html(message):
    """Render an explicit failure card; never substitute a made-up quote."""
    safe = str(message).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'''<!-- 每日金句数据状态：error -->
<section class="quote-banner">
  <div class="quote-mark">!</div>
  <div class="quote-text">每日金句数据获取失败</div>
  <div class="quote-principle">{safe}</div>
</section>'''


if __name__ == "__main__":
    try:
        quote, remaining = pick_quote()
    except Exception as e:
        print(f"// [pick_quote] ERROR: {e}", file=sys.stderr)
        if "--html" in sys.argv:
            print(error_html(e))
        else:
            print(json.dumps({"status": "error", "error": str(e), "quote": None}, ensure_ascii=False))
        raise SystemExit(0)

    if "--html" in sys.argv:
        print(to_html(quote, remaining))
    elif "--json" in sys.argv:
        print(to_json_output(quote, remaining))
    else:
        # 默认输出JSON
        print(to_json_output(quote, remaining))
