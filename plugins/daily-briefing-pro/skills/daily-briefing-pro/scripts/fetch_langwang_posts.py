"""抓取狼王行千里全部主帖标题列表（POST翻页），输出JSON

用法: python fetch_langwang_posts.py [--out data/langwang_posts.json]
"""
import json, os, re, sys, urllib.request, urllib.parse, ssl, time

COOKIE_FILE = os.path.expanduser("~/.codex/tgb_cookies.json")
BASE = "https://www.tgb.cn/user/blog/moreTopic"
UID = "2747572"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def load_cookie_string():
    if not os.path.exists(COOKIE_FILE):
        sys.stderr.write("[WARN] Cookie file not found\n")
        return ""
    cookies = json.load(open(COOKIE_FILE, encoding="utf-8"))
    return "; ".join(f'{c["name"]}={c["value"]}' for c in cookies if c.get("name") and c.get("value"))


def fetch_page(page_no, cookie_str):
    url = f"{BASE}?userID={UID}&pageNo={page_no}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36",
        "Cookie": cookie_str,
    })
    with urllib.request.urlopen(req, context=ctx, timeout=25) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_rows(html):
    rows = re.findall(r'<tr[^>]*class="(?:suh|alt1)"[^>]*>(.*?)</tr>', html, re.DOTALL)
    posts = []
    for r in rows:
        tds = re.findall(r'<td[^>]*>(.*?)</td>', r, re.DOTALL)
        if len(tds) < 8:
            continue
        # 帖子标题在td[1]的<a>标签
        a_m = re.search(r'<a[^>]*href="(/a/[^"]+)"[^>]*title="([^"]*)"', tds[1])
        title = ""
        post_id = ""
        if a_m:
            post_id = a_m.group(1).split("/")[-1]
            title = re.sub(r'<[^>]+>', '', a_m.group(2)).replace('&nbsp;', ' ').strip()
        # 发布日期在td[7]
        date = re.sub(r'<[^>]+>', '', tds[7]).replace('\xa0', ' ').strip()
        if not title or not re.match(r'\d{4}-\d{2}-\d{2}', date):
            continue
        # 回帖/浏览
        hv = re.sub(r'<[^>]+>', '', tds[4]).replace('&nbsp;', ' ').replace('\xa0', ' ').strip()
        posts.append({"id": post_id, "title": title, "date": date, "replies_views": hv})
    return posts


def main():
    cookie_str = load_cookie_string()
    all_posts = []
    pages = int(sys.argv[sys.argv.index("--pages") + 1]) if "--pages" in sys.argv else 38
    total_pages = min(pages, 38)
    for pno in range(1, total_pages + 1):
        html = fetch_page(pno, cookie_str)
        posts = parse_rows(html)
        sys.stderr.write(f"[page {pno}] {len(posts)} posts\n")
        if not posts:
            # 最后一页可能为空，提前结束
            break
        all_posts.extend(posts)
        time.sleep(0.4)
    # 去重（按id）
    seen = set()
    dedup = []
    for p in all_posts:
        if p["id"] and p["id"] in seen:
            continue
        seen.add(p["id"])
        dedup.append(p)

    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "langwang", "langwang_posts.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"count": len(dedup), "posts": dedup}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"count": len(dedup), "first": dedup[0] if dedup else None,
                      "last": dedup[-1] if dedup else None}, ensure_ascii=False))


if __name__ == "__main__":
    main()
