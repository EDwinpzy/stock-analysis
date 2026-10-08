"""狼王行千里情绪周期阶段提取（可增量刷新）

读取 langwang_posts.json（全部主帖）+ langwang_cycle_raw.json（复盘帖正文提取），
结合规则提取 + 手工权威映射，生成每日情绪周期阶段序列，供 build_briefing.py
叠加到情绪折线图上。

阶段体系（狼王行千里 情绪周期理论）：
- 周期层级：季度 → 一周期/二周期/三周期 → 主升一/二/三阶段 → 退潮下跌一/下跌二 → 衰竭
- 周期间：混沌期（旧周期退潮结束、新周期未开启的迷茫阶段）
- 冰点：情绪最低点

输出 data/langwang_cycle.json:
{
  "source": "狼王行千里",
  "blog_url": "https://www.tgb.cn/blog/2747572",
  "current": {"date":"2026-08-21","stage":"混沌期","note":"..."},
  "by_date": {"2026-08-20": {"stage":"退潮衰竭→混沌","color":"warn","note":"...","src":"8.20主观周期复盘贴"}}
}

用法:
  python langwang_cycle.py              # 只用现有缓存生成
  python langwang_cycle.py --refresh    # 增量抓最新帖子+复盘正文后重新生成
"""
import json, os, re, subprocess, sys
from datetime import datetime
from pathlib import Path

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from runtime_paths import get_data_dir

DATA_ROOT = get_data_dir(Path(BASE))
DATA_DIR = DATA_ROOT / "langwang"
os.makedirs(DATA_DIR, exist_ok=True)
POSTS_PATH = DATA_DIR / "langwang_posts.json"
RAW_PATH = DATA_DIR / "langwang_cycle_raw.json"
OUT_PATH = DATA_ROOT / "langwang_cycle.json"

# ===== 手工权威映射（基于已抓取复盘帖正文逐日核对）=====
# 每个交易日的周期阶段。规则提取会以这里的映射为准（人工核对 > 正则猜测）
# stage: 显示名；color: up红(主升)/dn绿(退潮)/warn橙(混沌)/blue蓝(节点)
MANUAL_MAP = {
    # ---- 第二季末期 → 第三季开启 ----
    "2026-07-20": {"stage": "退潮期", "color": "dn", "note": "第二季一二三周期共振退潮", "src": "7.20主观周期复盘贴"},
    "2026-07-21": {"stage": "退潮期", "color": "dn", "note": "第二季共振退潮延续", "src": "7.21主观周期复盘贴"},
    "2026-07-23": {"stage": "混沌期", "color": "warn", "note": "退潮尾声，混沌待启", "src": "7.23主观周期复盘贴"},
    "2026-07-24": {"stage": "混沌期", "color": "warn", "note": "混沌轮动，无主线", "src": "7.24主观周期复盘贴"},
    "2026-07-31": {"stage": "混沌期", "color": "warn", "note": "第二季退潮后混沌，第三季一周期酝酿", "src": "7.31客观数据复盘贴"},
    "2026-08-03": {"stage": "混沌期", "color": "warn", "note": "第三季一周期先于题材在酝酿", "src": "8.3主观周期复盘贴"},
    # ---- 第三季一周期开启 ----
    "2026-08-04": {"stage": "周期节点", "color": "blue", "note": "08.04周期节点：第三季一周期开启", "src": "8.4主观周期复盘贴"},
    "2026-08-05": {"stage": "主升一", "color": "up", "note": "第三季情绪主升开启", "src": "8.5主观周期复盘贴"},
    "2026-08-06": {"stage": "主升一", "color": "up", "note": "反弹韧性超预期，主升结构", "src": "8.6主观周期复盘贴"},
    "2026-08-07": {"stage": "主升一→二", "color": "up", "note": "连板趋势化，趋势连板化", "src": "8.7主观周期复盘贴"},
    # ---- 主升二（切三分歧）----
    "2026-08-10": {"stage": "主升二·切三", "color": "up", "note": "二切三的分歧过程中，等转三一致", "src": "8.10午盘"},
    "2026-08-11": {"stage": "主升二", "color": "up", "note": "主线PK轮动看戏，分歧不来", "src": "8.11午盘"},
    "2026-08-12": {"stage": "主升二", "color": "up", "note": "迟到的太晚易演变成退潮", "src": "8.12午盘"},
    "2026-08-13": {"stage": "主升二→三", "color": "up", "note": "二阶段补涨穿越，扛过二切三分歧", "src": "8.13午盘"},
    "2026-08-14": {"stage": "主升三", "color": "up", "note": "一周期二切三分歧，三阶段补涨预期", "src": "8.14午盘"},
    "2026-08-15": {"stage": "主升三", "color": "up", "note": "机构行情买行业龙头，游资买情绪龙头", "src": "8.15客观数据复盘贴"},
    # ---- 主升三 ----
    "2026-08-17": {"stage": "主升三", "color": "up", "note": "一周期主升三阶段第一天", "src": "8.17主观周期复盘贴"},
    "2026-08-18": {"stage": "主升三", "color": "up", "note": "主升三阶段第二天，需K佐证", "src": "8.18主观周期复盘贴"},
    # ---- 退潮 ----
    "2026-08-19": {"stage": "退潮预警", "color": "warn", "note": "一周期大概率要退潮，周期不完美", "src": "8.19主观周期复盘贴"},
    "2026-08-20": {"stage": "退潮衰竭", "color": "dn", "note": "一周期退潮下跌一衰竭", "src": "8.20主观周期复盘贴"},
    # ---- 当前 ----
    "2026-08-21": {"stage": "混沌期", "color": "warn", "note": "一周期退潮后、二周期开启前的混沌阶段：迷茫+神经病不讲理", "src": "8.21午盘"},
}

# ===== 规则提取（补充手工映射未覆盖的日期）=====
RULE_STAGES = [
    (r"主升三", "主升三", "up"),
    (r"主升", "主升期", "up"),
    (r"退潮", "退潮期", "dn"),
    (r"冰点", "冰点", "blue"),
    (r"混沌", "混沌期", "warn"),
]


def rule_extract(text: str):
    """从正文/标题提取周期阶段（弱规则，仅兜底）"""
    for pat, stage, color in RULE_STAGES:
        if re.search(pat, text):
            return {"stage": stage, "color": color, "note": text[:60], "src": "规则提取"}
    return None


def load_json(path):
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    return None


def refresh_posts():
    """增量抓取：抓最新2页帖子，与缓存合并"""
    posts = load_json(POSTS_PATH) or {"posts": []}
    old_ids = {p["id"] for p in posts["posts"]}
    try:
        r = subprocess.run(
            [sys.executable, os.path.join(BASE, "scripts", "fetch_langwang_posts.py"),
             "--out", POSTS_PATH, "--pages", "2"],
            capture_output=True, text=True, timeout=120, encoding="utf-8")
        sys.stderr.write(r.stderr or "")
        fresh = load_json(POSTS_PATH) or {"posts": []}
        new_cnt = sum(1 for p in fresh["posts"] if p["id"] not in old_ids)
        sys.stderr.write(f"[refresh] new posts: {new_cnt}\n")
    except Exception as e:
        sys.stderr.write(f"[WARN] refresh posts failed: {e}\n")


def refresh_bodies():
    """增量抓取：抓缓存中缺失日期的复盘帖正文"""
    raw = load_json(RAW_PATH) or []
    posts = load_json(POSTS_PATH) or {"posts": []}
    review_kw = ["主观周期复盘贴", "客观数据复盘贴", "复盘贴"]
    reviews = [p for p in posts["posts"] if any(k in p["title"] for k in review_kw)]
    have_dates = {r.get("date") for r in raw}
    missing = [p for p in reviews if p["date"] not in have_dates]
    if not missing:
        sys.stderr.write("[refresh] no missing review bodies\n")
        return
    try:
        r = subprocess.run(
            [sys.executable, os.path.join(BASE, "scripts", "fetch_langwang_bodies.py"),
             "--days", "600", "--out", RAW_PATH],
            capture_output=True, text=True, timeout=300, encoding="utf-8")
        sys.stderr.write(r.stderr or "")
        sys.stderr.write(f"[refresh] bodies updated: {len(missing)} missing\n")
    except Exception as e:
        sys.stderr.write(f"[WARN] refresh bodies failed: {e}\n")


def main():
    if "--refresh" in sys.argv:
        sys.stderr.write("=== 增量刷新狼王帖子/复盘正文 ===\n")
        refresh_posts()
        refresh_bodies()

    # 1. 加载已抓数据
    posts = load_json(POSTS_PATH) or {"posts": []}
    raw = load_json(RAW_PATH) or []

    # 2. 从 raw 提取每日周期段落
    raw_by_date = {r["date"]: r for r in raw if r.get("date")}

    # 3. 组装 by_date：优先手工映射，其次规则提取
    by_date = {}
    for d, v in MANUAL_MAP.items():
        by_date[d] = v

    # 规则兜底：raw中手工未覆盖的日期
    for d, r in raw_by_date.items():
        if d in by_date:
            continue
        text = (r.get("cycle_section", "") + " " + " ".join(r.get("cycle_mentions", [])))
        if text.strip():
            ext = rule_extract(text)
            if ext:
                by_date[d] = ext

    # 4. 当前阶段 = 最新一个交易日
    current_date = max(by_date.keys())
    current = by_date[current_date]

    out = {
        "source": "狼王行千里",
        "blog_url": "https://www.tgb.cn/blog/2747572",
        "current": {"date": current_date, **current},
        "by_date": dict(sorted(by_date.items())),
    }
    json.dump(out, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[OK] langwang_cycle.json written ({len(by_date)} days)")
    print(f"[CURRENT] {current_date} → {current['stage']} ({current.get('note','')[:40]})")
    return out


if __name__ == "__main__":
    main()
