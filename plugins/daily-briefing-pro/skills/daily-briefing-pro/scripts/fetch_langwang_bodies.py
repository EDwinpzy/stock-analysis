"""抓取狼王行千里复盘帖正文，提取周期阶段表述

输出 data/langwang_cycle_raw.json: {date, title, id, cycle_text, raw}
用法: python fetch_langwang_bodies.py [--days 60] [--out data/langwang_cycle_raw.json]
"""
import json, os, re, sys, urllib.request, ssl, time
from pathlib import Path

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from runtime_paths import get_data_dir

DATA_ROOT = get_data_dir(Path(BASE))
COOKIE_FILE = os.environ.get("TGB_COOKIE_PATH", str(DATA_ROOT / "tgb_cookies.json"))
if not os.path.exists(COOKIE_FILE):
    COOKIE_FILE = os.path.expanduser("~/.codex/tgb_cookies.json")
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# 复盘帖标题特征
REVIEW_KW = ["主观周期复盘贴", "客观数据复盘贴", "复盘贴"]


def load_cookie_string():
    if not os.path.exists(COOKIE_FILE):
        return ""
    cookies = json.load(open(COOKIE_FILE, encoding="utf-8"))
    return "; ".join(f'{c["name"]}={c["value"]}' for c in cookies if c.get("name") and c.get("value"))


def fetch_post_body(post_id, cookie_str):
    url = f"https://www.tgb.cn/a/{post_id}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36",
        "Cookie": cookie_str,
    })
    html = urllib.request.urlopen(req, context=ctx, timeout=25).read().decode("utf-8", errors="ignore")
    # 去标签
    text = re.sub(r"<script[\s\S]*?</script>", "", html)
    text = re.sub(r"<style[\s\S]*?</style>", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
    text = re.sub(r"\s+", " ", text)
    return text


def extract_cycle(pid, title, text):
    """从正文提取周期阶段表述"""
    result = {
        "id": pid,
        "title": title,
        "cycle_section": "",
        "cycle_mentions": [],
    }
    # 找"情绪周期"段落到"题材周期"段落之间
    em = re.search(r"情绪周期\s*([\s\S]{0,120}?)(?:题材周期|A型|B型|逻辑梳理|公开的|淘股吧)", text)
    if em:
        result["cycle_section"] = re.sub(r"\s+", " ", em.group(1)).strip()[:200]
    # 收集所有含阶段关键词的句子
    stage_kw = ["主升一", "主升二", "主升三", "主升", "退潮", "混沌", "冰点",
                "一周期", "二周期", "三周期", "下跌一", "衰竭", "修复", "启动"]
    for m in re.finditer(r"[^。；;]{0,40}(?:主升[一二三]?|退潮|混沌|冰点|下跌一|衰竭)[^。；;]{0,50}", text):
        s = re.sub(r"\s+", " ", m.group(0)).strip()
        if len(s) > 8 and "周期" in s or any(k in s for k in stage_kw):
            result["cycle_mentions"].append(s[:120])
    return result


def main():
    days = 60
    out = DATA_ROOT / "langwang" / "langwang_cycle_raw.json"
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])
    if "--out" in sys.argv:
        output_arg = Path(sys.argv[sys.argv.index("--out") + 1]).expanduser()
        if output_arg.is_absolute():
            out = output_arg
        else:
            parts = output_arg.parts[1:] if output_arg.parts[:1] == ("data",) else output_arg.parts
            out = DATA_ROOT.joinpath(*parts)

    posts = json.load(open(DATA_ROOT / "langwang" / "langwang_posts.json", encoding="utf-8"))["posts"]
    # 只保留最近N天的复盘帖
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    reviews = [p for p in posts if p["date"] >= cutoff and
               any(k in p["title"] for k in REVIEW_KW)]
    reviews.sort(key=lambda p: p["date"])
    sys.stderr.write(f"reviews in {days} days: {len(reviews)}\n")

    cookie_str = load_cookie_string()
    result = []
    for p in reviews:
        try:
            text = fetch_post_body(p["id"], cookie_str)
            cyc = extract_cycle(p["id"], p["title"], text)
            cyc["date"] = p["date"]
            result.append(cyc)
            sys.stderr.write(f"[{p['date']}] {p['title'][:30]} -> {len(cyc['cycle_mentions'])} mentions\n")
            time.sleep(0.4)
        except Exception as e:
            sys.stderr.write(f"[{p['date']}] ERR {e}\n")

    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(result, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"count": len(result)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
