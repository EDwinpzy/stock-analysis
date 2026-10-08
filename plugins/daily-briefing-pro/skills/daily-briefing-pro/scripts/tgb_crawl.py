"""淘股吧四位博主每日主帖+跟帖抓取（urllib HTTP + Cookie，无浏览器）

v2: 重写为纯HTTP请求，解决Playwright add_cookies失效导致页面跳转登录的问题。
- moreReplyMod: 跟帖页（公开需Cookie，返回完整HTML）
- moreTopic: 主帖页（公开需Cookie，但默认显示旧数据，需翻页或用日期筛选）
- 博客主页 /blog/uid: 公开可见，默认显示精华帖

输出JSON到 stdout。
用法: python tgb_crawl.py                    # 爬当天
      python tgb_crawl.py --date 2026-07-03 # 爬指定日期
"""
import json, os, re, sys, urllib.request, ssl
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from runtime_paths import get_data_dir
DATA_DIR = get_data_dir(SCRIPT_DIR.parent)

if "--date" in sys.argv:
    idx = sys.argv.index("--date")
    TODAY = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else datetime.now().strftime("%Y-%m-%d")
else:
    TODAY = datetime.now().strftime("%Y-%m-%d")

# Cookie路径：优先环境变量，其次data目录，最后用户目录
COOKIE_FILE = os.environ.get("TGB_COOKIE_PATH",
    str(DATA_DIR / "tgb_cookies.json"))
if not os.path.exists(COOKIE_FILE):
    COOKIE_FILE = os.path.expanduser("~/.codex/tgb_cookies.json")

BLOGGERS = [
    ("8580229", "东北玄"),
    ("2313082", "太阳的微笑"),
    ("7555792", "九尾北极猫"),
    ("2747572", "狼王行千里"),
]

TRASH_KW = [
    "钓鱼","空军","台球","助教","周末","老婆","菜市场","爬山","旅游",
    "大理","兄弟厉害","加油","签到","恭喜","哈哈","嗯","打卡",
]

# SSL上下文（跳过证书验证）
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


def load_cookie_string() -> str:
    """从JSON文件加载Cookie并拼接为HTTP Cookie header值"""
    if not os.path.exists(COOKIE_FILE):
        sys.stderr.write(f"[WARN] Cookie file not found: {COOKIE_FILE}\n")
        return ""
    try:
        cookies = json.load(open(COOKIE_FILE, encoding="utf-8"))
        cookie_str = "; ".join(f'{c["name"]}={c["value"]}' for c in cookies if c.get("name") and c.get("value"))
        sys.stderr.write(f"[OK] Cookies loaded: {len(cookies)} entries\n")
        return cookie_str
    except Exception as e:
        sys.stderr.write(f"[WARN] Cookie load error: {e}\n")
        return ""


def fetch_page(url: str, cookie_str: str) -> str:
    """HTTP GET请求页面，返回HTML文本"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36",
        "Cookie": cookie_str,
    })
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        sys.stderr.write(f"[ERROR] fetch {url}: {e}\n")
        return ""


def is_trash(text: str) -> bool:
    """闲聊过滤"""
    txt = text.strip()
    if len(txt) < 10:
        return True
    for kw in TRASH_KW:
        if kw in txt:
            return True
    return False


def extract_replies(html: str, today: str) -> list:
    """从moreReplyMod页面HTML提取指定日期的跟帖

    HTML结构:
    <div class="blogReply">
      <div class="blogReply-userName">用户名</div>
      <span class="blogReply-date">2026-07-08 11:18</span>
      <span class="blogReply-gray">跟帖了</span>
      <a href="/a/xxx" title="来源帖子标题">来源帖子标题</a>
      <a href="/a/xxx/回复ID" class="blogReply-subinfo">跟帖内容(赞数)</a>
      <span class="zanNums">45</span>
    </div>
    """
    replies = []

    # 按 blogReply div 切割
    reply_blocks = re.split(r'<div class="blogReply">', html)

    for block in reply_blocks[1:]:  # 跳过第一个（页面头部）
        # 提取日期
        date_m = re.search(r'<span class="blogReply-date">(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})</span>', block)
        if not date_m:
            continue
        reply_date = date_m.group(1)[:10]
        if reply_date != today:
            continue

        # 提取用户名
        user_m = re.search(r'<div class="blogReply-userName">([^<]+)</div>', block)
        user = user_m.group(1).strip() if user_m else ""

        # 提取来源帖子标题和URL
        from_m = re.search(r'<a href="(/a/[^"]+)"\s+title="([^"]+)"', block)
        from_url = from_m.group(1) if from_m else ""
        from_title = from_m.group(2) if from_m else ""

        # 提取跟帖内容（blogReply-subinfo链接）
        content = ""
        likes = 0
        content_m = re.search(
            r'<a[^>]*class="blogReply-subinfo[^"]*"[^>]*>\s*([\s\S]+?)\s*\((\d+)\)\s*</a>',
            block
        )
        if content_m:
            content = re.sub(r'<[^>]+>', '', content_m.group(1)).strip()
            # 清理 &nbsp; 等HTML实体
            content = content.replace('&nbsp;', ' ').replace('&amp;', '&')
            likes = int(content_m.group(2))
        else:
            # 备用：尝试不含赞数的内容
            content_m2 = re.search(r'class="blogReply-subinfo[^"]*"[^>]*>\s*([\s\S]+?)</a>', block)
            if content_m2:
                content = re.sub(r'<[^>]+>', '', content_m2.group(1)).strip()
                content = content.replace('&nbsp;', ' ').replace('&amp;', '&')

        # 提取赞数（从zanNums span，如果上面没取到）
        if likes == 0:
            zan_m = re.search(r'<span class="zanNums">(\d+)</span>', block)
            if zan_m:
                likes = int(zan_m.group(1))

        # 判断是否为主帖（blogReply-gray显示"发表了"而非"跟帖了"）
        is_post = "发表了" in block and "跟帖了" not in block

        replies.append({
            "date": date_m.group(1),
            "user": user,
            "from_title": from_title,
            "from_url": from_url,
            "content": content[:300],
            "likes": likes,
            "is_post": is_post,
        })

    # 按赞数排序
    replies.sort(key=lambda x: x["likes"], reverse=True)
    return replies


def latest_reply_date(html: str) -> str:
    """页面里最新的跟帖日期。用于说明某位博主是“目标日无动态”还是“已停更”。"""
    dates = re.findall(r'<span class="blogReply-date">(\d{4}-\d{2}-\d{2})', html or "")
    return max(dates) if dates else ""


def extract_posts(html: str, today: str) -> list:
    """从moreTopic页面HTML提取指定日期的主帖

    HTML结构:
    <div class="article_tittle">
      <a href="/a/xxx" title="帖子标题">帖子标题</a>
      <div class="tittle_llhf">浏览/回复</div>
      <div class="tittle_fbshijian">2026-07-08</div>
    </div>
    """
    posts = []

    # 找所有 article_tittle div
    article_blocks = re.findall(
        r'<div class="article_tittle">(.*?)<div class="clear"></div>',
        html, re.DOTALL
    )

    for block in article_blocks:
        # 提取日期
        date_m = re.search(r'<div class="tittle_fbshijian[^"]*">(\d{4}-\d{2}-\d{2})</div>', block)
        if not date_m or date_m.group(1) != today:
            continue

        # 提取标题和URL
        title_m = re.search(r'<a href="(/a/[^"]+)"[^>]*title="([^"]+)"', block)
        if not title_m:
            title_m = re.search(r'<a href="(/a/[^"]+)"[^>]*>([^<]+)</a>', block)
        url = title_m.group(1) if title_m else ""
        title = title_m.group(2).strip() if title_m else ""

        # 过滤垃圾行
        if any(kw in title for kw in ["全选", "标 题", "最新时间"]):
            continue

        # 浏览/回复
        views_m = re.search(r'<div class="tittle_llhf[^"]*">([^<]+)</div>', block)
        views = views_m.group(1).strip() if views_m else ""

        posts.append({
            "title": title,
            "url": url,
            "date": today,
            "views": views,
        })

    return posts


def extract_blog_home_posts(html: str, today: str) -> list:
    """从博客主页 /blog/uid 提取帖子（公开可见，默认显示精华帖+近期帖）

    HTML结构与moreTopic相同: article_tittle div
    """
    return extract_posts(html, today)


def crawl():
    cookie_str = load_cookie_string()
    if not cookie_str:
        sys.stderr.write("[ERROR] No cookies available, cannot fetch TGB data\n")
        return {
            "date": TODAY,
            "data_date": "",
            "bloggers": {},
            "status": "error",
            "source": "淘股吧公开页面 + 登录Cookie",
            "error": "No cookies",
            "note": f"缺少淘股吧登录Cookie：{COOKIE_FILE}；未使用旧缓存"
        }

    result = {"date": TODAY, "data_date": "", "bloggers": {}, "source": "淘股吧公开页面 + 登录Cookie"}
    used_fallback = False  # 是否使用了回退日期

    for uid, name in BLOGGERS:
        sys.stderr.write(f"[INFO] Fetching {name} (uid={uid})...\n")
        data = {"name": name, "data_date": "", "posts_today": 0, "replies_today": 0, "posts": [], "top_replies": []}

        # 尝试抓取指定日期的数据
        target_date = TODAY
        last_seen = ""
        for attempt in range(2):  # 最多尝试2天（当天 + 前一天）
            data = {"name": name, "data_date": "", "posts_today": 0, "replies_today": 0, "posts": [], "top_replies": []}

            # 1. 跟帖页（moreReplyMod）— 最可靠的数据源
            reply_url = f"https://www.tgb.cn/user/blog/moreReplyMod?userID={uid}"
            reply_html = fetch_page(reply_url, cookie_str)

            if reply_html and "登录" not in reply_html[:500]:
                seen = latest_reply_date(reply_html)
                if seen > last_seen:
                    last_seen = seen
                today_replies = extract_replies(reply_html, target_date)
                data["replies_today"] = len(today_replies)

                # 从跟帖中识别主帖（is_post=True的条目）
                post_replies = [r for r in today_replies if r.get("is_post")]
                reply_only = [r for r in today_replies if not r.get("is_post")]

                # 主帖信息
                for pr in post_replies:
                    data["posts"].append({
                        "title": pr.get("from_title", ""),
                        "url": pr.get("from_url", ""),
                    })

                # 高赞跟帖
                for r in reply_only[:10]:
                    if not is_trash(r["content"]):
                        data["top_replies"].append({
                            "content": r["content"][:200],
                            "likes": r["likes"],
                            "from_title": r.get("from_title", ""),
                        })
            else:
                sys.stderr.write(f"  [WARN] moreReplyMod returned login page or empty for {name}\n")

            # 2. 主帖页（moreTopic）— 补充主帖信息
            topic_url = f"https://www.tgb.cn/user/blog/moreTopic?userID={uid}"
            topic_html = fetch_page(topic_url, cookie_str)

            if topic_html and "登录" not in topic_html[:500]:
                today_posts = extract_posts(topic_html, target_date)
                # 合并（去重，以moreReplyMod为主）
                existing_urls = {p["url"] for p in data["posts"]}
                for tp in today_posts:
                    if tp["url"] not in existing_urls:
                        data["posts"].append({"title": tp["title"], "url": tp["url"]})
                        existing_urls.add(tp["url"])

            # 3. 博客主页（公开可见）— 最后补充
            blog_url = f"https://www.tgb.cn/blog/{uid}"
            blog_html = fetch_page(blog_url, cookie_str)

            if blog_html:
                home_posts = extract_blog_home_posts(blog_html, target_date)
                existing_urls = {p["url"] for p in data["posts"]}
                for hp in home_posts:
                    if hp["url"] not in existing_urls:
                        data["posts"].append({"title": hp["title"], "url": hp["url"]})
                        existing_urls.add(hp["url"])

            data["posts_today"] = len(data["posts"])
            if data["posts_today"] > 0 or data["replies_today"] > 0:
                data["data_date"] = target_date

            # 如果当天有数据，直接使用；否则回退到前一天
            if data["posts_today"] > 0 or data["replies_today"] > 0:
                if attempt > 0:
                    used_fallback = True
                    sys.stderr.write(f"  {name}: {target_date}找到数据（回退自{TODAY}）\n")
                else:
                    sys.stderr.write(f"  {name}: {data['posts_today']} posts, {data['replies_today']} replies\n")
                break
            elif attempt == 0:
                # 当天无数据，尝试前一天
                prev = datetime.strptime(TODAY, "%Y-%m-%d") - timedelta(days=1)
                while prev.weekday() >= 5:
                    prev -= timedelta(days=1)
                prev_date = prev.strftime("%Y-%m-%d")
                sys.stderr.write(f"  {name}: {TODAY}无数据，尝试回退到 {prev_date}...\n")
                target_date = prev_date
            else:
                sys.stderr.write(f"  {name}: {TODAY}及前一天均无数据\n")

        # 记录页面里最新的跟帖日期，便于区分“目标日无动态”和“长期停更”
        data["last_seen_date"] = last_seen
        result["bloggers"][name] = data

    if used_fallback:
        result["note"] = f"使用回退日期数据（{TODAY}无更新）"

    actual_dates = sorted({d.get("data_date") for d in result["bloggers"].values() if d.get("data_date")})
    result["data_date"] = actual_dates[-1] if len(actual_dates) == 1 else (f"{actual_dates[0]}~{actual_dates[-1]}" if actual_dates else "")
    total_activity = sum(d.get("posts_today", 0) + d.get("replies_today", 0) for d in result["bloggers"].values())
    result["status"] = "ok" if total_activity > 0 else "error"
    result["activity_count"] = total_activity
    if total_activity == 0:
        result["error"] = "No posts or replies in target date and one-workday fallback"
        result["note"] = f"{TODAY}及前一个工作日均无可核验主帖或跟帖；未使用旧缓存"

    return result


if __name__ == "__main__":
    data = crawl()
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
