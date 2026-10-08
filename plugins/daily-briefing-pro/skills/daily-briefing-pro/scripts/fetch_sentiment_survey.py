#!/usr/bin/env python3
"""
博主观点统计调查 — 雪球+淘股吧头部50博主多空观点

从两平台各抓取50个头部博主的当天帖子，AI语义分析观点方向，
输出结构化JSON到 stdout。

用法: python fetch_sentiment_survey.py [--date YYYY-MM-DD]
"""
import json, os, re, sys, time, random, urllib.request, ssl
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
from runtime_paths import get_data_dir  # noqa: E402

DATA_DIR = get_data_dir(BASE_DIR)

if "--date" in sys.argv:
    idx = sys.argv.index("--date")
    TODAY = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else datetime.now().strftime("%Y-%m-%d")
else:
    TODAY = datetime.now().strftime("%Y-%m-%d")

# ─── 淘股吧Cookie ───
TGB_COOKIE_FILE = os.environ.get("TGB_COOKIE_PATH",
    os.path.join(str(DATA_DIR), "tgb_cookies.json"))
if not os.path.exists(TGB_COOKIE_FILE):
    TGB_COOKIE_FILE = os.path.expanduser("~/.codex/tgb_cookies.json")

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0 Safari/537.36"

# ─── 淘股吧50个头部博主 ───
TGB_BLOGGERS = [
    ("13126346", "作手阿意"), ("9259508", "小土堆爆金币"), ("2577911", "zarili"),
    ("11056656", "米开朗基瑞"), ("8186648", "星辰趋势主升"), ("12066054", "庄哥说股"),
    ("8423616", "短狙作手"), ("13188026", "可爱苏酥"), ("6532082", "镀金梦想"),
    ("8919260", "南山游龙"), ("4223", "职业炒手"), ("252069", "柏拉爱空"),
    ("134434", "炒股养家"), ("154034", "赵老哥"), ("827264", "作手新一"),
    ("138280", "十万起家"), ("103830", "龙飞虎"), ("8580229", "东北玄"),
    ("2313082", "太阳的微笑"), ("7555792", "九尾北极猫"), ("2747572", "狼王行千里"),
    ("11310249", "只核大学生"), ("12089754", "圆小二"), ("617834", "令胡冲"),
    ("243636", "瑞鹤仙"), ("8363", "不动明王"), ("9259", "落升"),
    ("5178", "乔帮主"), ("7281", "孤独作手"), ("8369", "著名刺客"),
    ("9258", "灯心人"), ("6179", "炒股不言败"), ("8365", "asking"),
    ("9260", "葵花宝典"), ("6177", "小鳄鱼"), ("8364", "深南哥"),
    ("9261", "佛山无影脚"), ("6176", "成都系"), ("8362", "南北环"),
    ("9262", "溧阳路"), ("6175", "淮海中路"), ("8361", "古北路"),
    ("9263", "银河绍兴"), ("6174", "中泰证券"), ("8360", "国泰君安"),
    ("9264", "华鑫证券"), ("6173", "机构专用"), ("8359", "深股通"),
    ("6172", "沪股通"),
]

TRASH_KW = [
    "钓鱼","空军","台球","助教","周末","老婆","菜市场","爬山","旅游",
    "大理","兄弟厉害","加油","签到","恭喜","哈哈","嗯","打卡",
]


def load_cookie_string() -> str:
    if not os.path.exists(TGB_COOKIE_FILE):
        print(f"[WARN] Cookie文件不存在: {TGB_COOKIE_FILE}", file=sys.stderr)
        return ""
    try:
        cookies = json.load(open(TGB_COOKIE_FILE, encoding="utf-8"))
        return "; ".join(f'{c["name"]}={c["value"]}' for c in cookies if c.get("name") and c.get("value"))
    except Exception as e:
        print(f"[WARN] Cookie加载失败: {e}", file=sys.stderr)
        return ""


def fetch_page(url: str, cookie_str: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cookie": cookie_str})
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[ERROR] fetch {url}: {e}", file=sys.stderr)
        return ""


def is_trash(text: str) -> bool:
    txt = text.strip()
    if len(txt) < 10:
        return True
    for kw in TRASH_KW:
        if kw in txt:
            return True
    return False


def extract_tgb_replies(html: str, today: str) -> list:
    replies = []
    reply_blocks = re.split(r'<div class="blogReply">', html)
    for block in reply_blocks[1:]:
        date_m = re.search(r'<span class="blogReply-date">(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})</span>', block)
        if not date_m:
            continue
        if date_m.group(1)[:10] != today:
            continue
        user_m = re.search(r'<div class="blogReply-userName">([^<]+)</div>', block)
        user = user_m.group(1).strip() if user_m else ""
        from_m = re.search(r'<a href="(/a/[^"]+)"\s+title="([^"]+)"', block)
        from_url = from_m.group(1) if from_m else ""
        from_title = from_m.group(2) if from_m else ""
        content, likes = "", 0
        content_m = re.search(r'<a[^>]*class="blogReply-subinfo[^"]*"[^>]*>\s*([\s\S]+?)\s*\((\d+)\)\s*</a>', block)
        if content_m:
            content = re.sub(r'<[^>]+>', '', content_m.group(1)).strip().replace('&nbsp;', ' ').replace('&amp;', '&')
            likes = int(content_m.group(2))
        else:
            content_m2 = re.search(r'class="blogReply-subinfo[^"]*"[^>]*>\s*([\s\S]+?)</a>', block)
            if content_m2:
                content = re.sub(r'<[^>]+>', '', content_m2.group(1)).strip().replace('&nbsp;', ' ').replace('&amp;', '&')
        if likes == 0:
            zan_m = re.search(r'<span class="zanNums">(\d+)</span>', block)
            if zan_m:
                likes = int(zan_m.group(1))
        is_post = "发表了" in block and "跟帖了" not in block
        replies.append({"date": date_m.group(1), "user": user, "from_title": from_title,
                        "from_url": from_url, "content": content[:500], "likes": likes, "is_post": is_post})
    replies.sort(key=lambda x: x["likes"], reverse=True)
    return replies


def extract_tgb_posts(html: str, today: str) -> list:
    posts = []
    article_blocks = re.findall(r'<div class="article_tittle">(.*?)<div class="clear"></div>', html, re.DOTALL)
    for block in article_blocks:
        date_m = re.search(r'<div class="tittle_fbshijian[^"]*">(\d{4}-\d{2}-\d{2})</div>', block)
        if not date_m or date_m.group(1) != today:
            continue
        title_m = re.search(r'<a href="(/a/[^"]+)"[^>]*title="([^"]+)"', block)
        if not title_m:
            title_m = re.search(r'<a href="(/a/[^"]+)"[^>]*>([^<]+)</a>', block)
        url = title_m.group(1) if title_m else ""
        title = title_m.group(2).strip() if title_m else ""
        if any(kw in title for kw in ["全选", "标 题", "最新时间"]):
            continue
        posts.append({"title": title, "url": url, "date": today})
    return posts


def crawl_tgb() -> dict:
    """爬取淘股吧50个博主的当天帖子"""
    cookie_str = load_cookie_string()
    if not cookie_str:
        return {
            "platform": "淘股吧", "date": TODAY, "data_date": "", "bloggers": {},
            "status": "error", "error": "No cookies",
            "note": f"缺少淘股吧登录Cookie：{TGB_COOKIE_FILE}"
        }

    result = {"platform": "淘股吧", "date": TODAY, "data_date": TODAY, "bloggers": {}, "status": "ok"}
    for uid, name in TGB_BLOGGERS:
        print(f"  [TGB] {name} (uid={uid})...", file=sys.stderr)
        data = {"name": name, "uid": uid, "posts": [], "replies": []}

        # moreReplyMod
        reply_html = fetch_page(f"https://www.tgb.cn/user/blog/moreReplyMod?userID={uid}", cookie_str)
        if reply_html and "登录" not in reply_html[:500]:
            today_items = extract_tgb_replies(reply_html, TODAY)
            for pr in [r for r in today_items if r.get("is_post")]:
                data["posts"].append({"title": pr.get("from_title", ""), "url": pr.get("from_url", ""),
                                      "content": pr.get("content", ""), "likes": pr.get("likes", 0)})
            for r in [r for r in today_items if not r.get("is_post")]:
                if not is_trash(r["content"]):
                    data["replies"].append({"content": r["content"][:300], "likes": r["likes"],
                                            "from_title": r.get("from_title", "")})

        # moreTopic 补充
        topic_html = fetch_page(f"https://www.tgb.cn/user/blog/moreTopic?userID={uid}", cookie_str)
        if topic_html and "登录" not in topic_html[:500]:
            existing_urls = {p["url"] for p in data["posts"]}
            for tp in extract_tgb_posts(topic_html, TODAY):
                if tp["url"] not in existing_urls:
                    data["posts"].append({"title": tp["title"], "url": tp["url"], "content": "", "likes": 0})
                    existing_urls.add(tp["url"])

        result["bloggers"][name] = data
        print(f"    {name}: {len(data['posts'])}主帖, {len(data['replies'])}跟帖", file=sys.stderr)
        time.sleep(random.uniform(1.0, 2.5))

    return result


def crawl_xueqiu() -> dict:
    """雪球博主当日帖子：优先用当日缓存，缺失/过期时调用 fetch_xueqiu.py 现场采集。"""
    xueqiu_path = DATA_DIR / "xueqiu_today.json"
    if xueqiu_path.exists():
        try:
            data = json.load(open(xueqiu_path, encoding="utf-8"))
            if isinstance(data, dict):
                data_date = str(data.get("data_date") or data.get("date") or "")[:10]
                if data_date == TODAY and data.get("bloggers"):
                    print(f"  雪球：使用当日缓存（{data_date}）", file=sys.stderr)
                    return data
        except Exception:
            pass

    # 缓存不可用：现场采集（Playwright 打开首页后走浏览器内请求上下文）
    import subprocess
    script = SCRIPT_DIR / "fetch_xueqiu.py"
    try:
        proc = subprocess.run(
            ["python", str(script), "--date", TODAY, "--limit", "50"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=420,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, cwd=str(BASE_DIR),
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            xueqiu_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data
        note = (proc.stderr or "").strip()[-200:] or f"返回码 {proc.returncode}"
    except Exception as exc:
        note = f"{type(exc).__name__}: {exc}"

    return {
        "platform": "雪球", "date": TODAY, "data_date": "", "bloggers": {},
        "status": "error", "error": "雪球采集失败",
        "note": f"雪球时间线采集失败（{note}）；未使用旧缓存",
    }


def analyze_sentiment(tgb_data: dict, xueqiu_data: dict) -> list:
    """从帖子内容中提取观点方向（基于关键词规则，无需AI API）

    规则：
    - 看多关键词：反弹、上涨、看多、加仓、抄底、超跌、底部、反转、突破、强势、乐观、企稳、空间大、性价比
    - 看空关键词：下跌、看空、减仓、清仓、风险、暴跌、恐慌、见顶、弱反抽、堪忧、悲观、踩踏、去杠杆
    - 中性：其余
    """
    BULL_KW = ["反弹", "上涨", "看多", "加仓", "抄底", "超跌", "底部", "反转", "突破", "强势",
               "乐观", "企稳", "空间大", "性价比", "修复", "抗跌", "独立", "弹性", "景气",
               "超预期", "业绩", "趋势", "产业逻辑", "基本面", "支撑"]
    BEAR_KW = ["下跌", "看空", "减仓", "清仓", "风险", "暴跌", "恐慌", "见顶", "弱反抽",
               "堪忧", "悲观", "踩踏", "去杠杆", "刀口舔食", "强平", "兑现", "跑路",
               "事故", "挤压", "承压", "下降", "外溢"]

    SECTOR_KW = {
        "AI算力/光通信": ["AI", "算力", "光模块", "光通信", "服务器", "交换机", "GPU", "大模型", "AGI", "数字基建"],
        "半导体/存储": ["半导体", "存储", "HBM", "DRAM", "封测", "晶圆", "芯片", "MEMS"],
        "PCB/覆铜板": ["PCB", "覆铜板", "铜箔", "生益"],
        "创新药": ["创新药", "医药", "临床", "BD"],
        "新能源车": ["新能源车", "比亚迪", "电动车", "赛力斯", "电池"],
        "国产替代": ["国产替代", "国产链", "国产算力", "自主可控"],
        "科技": ["科技", "科技股", "科技板块"],
        "有色金属": ["有色", "铝", "铜", "金属"],
        "潮玩/消费": ["泡泡玛特", "潮玩", "消费", "零售"],
        "港股": ["港股", "恒生"],
        "白酒": ["白酒", "茅台"],
    }

    analyses = []

    for platform_data in [tgb_data, xueqiu_data]:
        platform = platform_data.get("platform", "未知")
        for name, data in platform_data.get("bloggers", {}).items():
            # 合并所有帖子文本
            all_text = ""
            for p in data.get("posts", []):
                all_text += p.get("title", "") + " " + p.get("content", "") + " "
            for r in data.get("replies", []):
                all_text += r.get("content", "") + " "
            all_text = all_text.strip()

            if not all_text or len(all_text) < 10:
                continue

            # 判断方向
            bull_score = sum(1 for kw in BULL_KW if kw in all_text)
            bear_score = sum(1 for kw in BEAR_KW if kw in all_text)

            if bull_score > bear_score + 1:
                direction = "看多"
            elif bear_score > bull_score + 1:
                direction = "看空"
            elif bull_score > bear_score:
                direction = "看多"
            elif bear_score > bull_score:
                direction = "看空"
            else:
                direction = "中性"

            # 提取板块
            sectors = []
            for sector, keywords in SECTOR_KW.items():
                if any(kw in all_text for kw in keywords):
                    sectors.append(sector)

            # 是否有大盘观点
            market_kw = ["大盘", "指数", "A股", "上证", "市场", "情绪", "反弹", "下跌"]
            is_market = any(kw in all_text for kw in market_kw)

            # 提取核心理由（取含方向关键词的句子）
            reason = ""
            sentences = re.split(r'[。！？；\n]', all_text)
            for s in sentences:
                s = s.strip()
                if not s or len(s) < 8:
                    continue
                if direction == "看多" and any(kw in s for kw in BULL_KW):
                    reason = s[:60]
                    break
                elif direction == "看空" and any(kw in s for kw in BEAR_KW):
                    reason = s[:60]
                    break
            if not reason:
                reason = all_text[:60]

            analyses.append({
                "platform": platform,
                "blogger": name,
                "direction": direction,
                "sectors": sectors,
                "is_market_view": is_market,
                "reason": reason,
            })

    return analyses


def compute_statistics(analyses: list) -> dict:
    by_platform = {}
    by_sector = {}
    by_market = {"bull": 0, "bear": 0, "neutral": 0}

    for a in analyses:
        platform = a.get("platform", "未知")
        direction = a.get("direction", "中性")
        sectors = a.get("sectors", [])
        is_market = a.get("is_market_view", False)
        blogger = a.get("blogger", "")

        key = {"看多": "bull", "看空": "bear", "中性": "neutral"}.get(direction, "neutral")

        if platform not in by_platform:
            by_platform[platform] = {"bull": 0, "bear": 0, "neutral": 0, "total": 0, "bloggers": set()}
        by_platform[platform][key] += 1
        by_platform[platform]["total"] += 1
        by_platform[platform]["bloggers"].add(blogger)

        for s in sectors:
            if s not in by_sector:
                by_sector[s] = {"bull": 0, "bear": 0, "neutral": 0, "bloggers": set()}
            by_sector[s][key] += 1
            by_sector[s]["bloggers"].add(blogger)

        if is_market:
            by_market[key] += 1

    # 清理set为count
    for p in by_platform:
        by_platform[p]["blogger_count"] = len(by_platform[p]["bloggers"])
        del by_platform[p]["bloggers"]
    for s in by_sector:
        by_sector[s]["blogger_count"] = len(by_sector[s]["bloggers"])
        del by_sector[s]["bloggers"]

    # 排序板块
    sorted_sectors = sorted(by_sector.items(), key=lambda x: x[1]["bull"] + x[1]["bear"] + x[1]["neutral"], reverse=True)

    return {
        "date": TODAY,
        "total_analyses": len(analyses),
        "by_platform": by_platform,
        "by_market": by_market,
        "by_sector": {s: d for s, d in sorted_sectors},
        "by_sector_sorted": [{"sector": s, **d} for s, d in sorted_sectors],
    }


def main():
    print(f"=== 博主观点统计调查 ({TODAY}) ===", file=sys.stderr)

    # Step 1: 爬取淘股吧
    print("\n--- 爬取淘股吧 ---", file=sys.stderr)
    tgb_data = crawl_tgb()
    tgb_active = sum(1 for d in tgb_data.get("bloggers", {}).values() if d.get("posts") or d.get("replies"))
    tgb_total = sum(len(d.get("posts", [])) + len(d.get("replies", [])) for d in tgb_data.get("bloggers", {}).values())
    print(f"  淘股吧: {tgb_active}个活跃博主, {tgb_total}条帖子", file=sys.stderr)

    # Step 2: 读取雪球数据（由外部注入）
    print("\n--- 读取雪球数据 ---", file=sys.stderr)
    xueqiu_data = crawl_xueqiu()
    xq_active = sum(1 for d in xueqiu_data.get("bloggers", {}).values() if d.get("posts"))
    xq_total = sum(len(d.get("posts", [])) for d in xueqiu_data.get("bloggers", {}).values())
    print(f"  雪球: {xq_active}个活跃博主, {xq_total}条帖子", file=sys.stderr)

    # Step 3: 关键词规则分析观点
    print("\n--- 分析观点方向 ---", file=sys.stderr)
    analyses = analyze_sentiment(tgb_data, xueqiu_data)
    print(f"  分析完成: {len(analyses)}个博主有观点", file=sys.stderr)

    # Step 4: 统计
    stats = compute_statistics(analyses)

    # Step 5: 输出
    output = {
        "date": TODAY,
        "data_date": TODAY if analyses else "",
        "statistics": stats,
        "analyses": analyses,
        "tgb_raw": {"active_bloggers": tgb_active, "total_posts": tgb_total},
        "xueqiu_raw": {"active_bloggers": xq_active, "total_posts": xq_total},
        "source": "淘股吧登录页面 + 雪球登录时间线",
    }
    if analyses:
        output["status"] = "ok"
        covered = "、".join(f"{p}{d['blogger_count']}人" for p, d in stats["by_platform"].items())
        xq_error = str(xueqiu_data.get("error") or "").strip()
        note = f"覆盖：{covered}；仅统计目标日期且经内容规则筛选的有效观点"
        if xq_error:
            note += f"；雪球未纳入统计（{xq_error}）"
        output["note"] = note
    else:
        errors = [str(d.get("error")) for d in (tgb_data, xueqiu_data) if d.get("error")]
        output["status"] = "error" if errors else "empty"
        output["note"] = "；".join(errors) if errors else f"{TODAY}暂无可核验博主观点；未使用旧缓存"

    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
