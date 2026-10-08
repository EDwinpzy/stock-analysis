#!/usr/bin/env python3
"""
每日简报HTML生成器
后台整合各数据源，生成自包含HTML文件
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
# 输出到当前工作区的 reports/每日简报
# 如果从 skill 目录内部运行，自动定位到用户工作空间
_cwd = Path(os.getcwd())
if ".agents" in _cwd.parts and "skills" in _cwd.parts:
    WORKSPACE_ROOT = Path.cwd()
else:
    WORKSPACE_ROOT = _cwd
OUTPUT_DIR = Path.cwd() / "reports" / "每日简报"


def run_script(script_name, *args, timeout=60):
    """后台调用脚本并解析JSON输出"""
    try:
        result = subprocess.run(
            ["python", str(SCRIPT_DIR / script_name), *args],
            capture_output=True, text=True, cwd=str(BASE_DIR), timeout=timeout
        )
        stdout_text = result.stdout.strip()
        if result.returncode != 0:
            print(f"警告: {script_name} 返回码 {result.returncode}", file=sys.stderr)
            if result.stderr.strip():
                print(f"  错误: {result.stderr.strip()[:200]}", file=sys.stderr)
            return {}

        if not stdout_text:
            return {}

        # 先尝试将整个输出作为JSON解析
        try:
            return json.loads(stdout_text)
        except json.JSONDecodeError:
            pass

        # 若整体解析失败，逐行逆向查找有效的JSON对象/数组
        lines = stdout_text.split("\n")
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    return obj
                if isinstance(obj, list):
                    return {"items": obj}
            except json.JSONDecodeError:
                continue

        print(f"警告: {script_name} 未输出有效JSON", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print(f"警告: {script_name} 执行超时", file=sys.stderr)
    except Exception as e:
        print(f"警告: {script_name} 执行失败: {e}", file=sys.stderr)
    return {}


def get_today_str():
    return datetime.now().strftime("%Y.%m.%d")


def get_weekday():
    return ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][datetime.now().weekday()]


def generate_briefing(data: dict) -> str:
    """生成HTML简报"""
    date_str = get_today_str()
    weekday = get_weekday()

    pg_score = data.get("panic_greed", {}).get("score", 50)
    pg_status = data.get("panic_greed", {}).get("status", "中性")
    weekend = datetime.now().weekday() >= 5

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>每日简报 — {date_str} {weekday}</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{margin:0;padding:0;box-sizing:border-box}}
:root{{
--bg:#0b0f19;--bg2:rgba(17,24,39,.68);--bg3:#0f172a;--bg4:#1a2332;
--a:#f59e0b;--a2:#fbbf24;
--up:#ef4444;--up-bg:rgba(239,68,68,.1);--up-glow:rgba(239,68,68,.3);
--dn:#22c55e;--dn-bg:rgba(34,197,94,.1);--dn-glow:rgba(34,197,94,.3);
--inf:#3b82f6;--inf-bg:rgba(59,130,246,.1);
--cyn:#38bdf8;--cyn-bg:rgba(56,189,248,.1);
--gld:#fbbf24;--gld-bg:rgba(251,191,36,.1);
--wrn:#f97316;--wrn-bg:rgba(249,115,22,.1);
--t1:#f3f4f6;--t2:#9ca3af;--t3:#6b7280;
--bd:rgba(255,255,255,.055);--bd2:rgba(255,255,255,.1);
--display:'Space Grotesk','Inter',system-ui,sans-serif;
--sans:'Inter',-apple-system,BlinkMacSystemFont,system-ui,sans-serif;
--mono:'JetBrains Mono','Cascadia Code',monospace;
}}
body{{background:var(--bg);color:var(--t1);font-family:var(--sans);font-size:15px;line-height:1.7;min-height:100vh}}
header{{backdrop-filter:blur(32px);background:rgba(8,8,13,.75);border-bottom:1px solid var(--bd);padding:0 24px;height:54px;display:flex;align-items:center;gap:14px;position:sticky;top:0;z-index:100}}
.logo{{font-family:var(--display);font-size:20px;font-weight:700;letter-spacing:-.03em;background:linear-gradient(135deg,var(--a),var(--a2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.hdr-right{{margin-left:auto;display:flex;align-items:center;gap:12px}}
.hdr-date{{font-size:13px;color:var(--t2);font-family:var(--mono);font-weight:500}}
.live-badge{{display:inline-flex;align-items:center;gap:5px;font-size:10px;font-weight:700;color:var(--up);font-family:var(--mono);text-transform:uppercase;letter-spacing:.08em;padding:3px 10px;background:var(--up-bg);border-radius:20px;border:1px solid rgba(239,68,68,.18)}}
.live-dot{{width:5px;height:5px;border-radius:50%;background:var(--up);animation:lp 2s ease-in-out infinite;box-shadow:0 0 8px var(--up-glow)}}
@keyframes lp{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.35;transform:scale(.65)}}}}
.c{{padding:24px 32px 52px}}
.hero{{display:flex;gap:12px;margin-bottom:14px}}
.sent-box{{backdrop-filter:blur(20px);background:var(--bg2);border:1px solid var(--bd);border-radius:12px;padding:14px 18px;display:flex;align-items:center;gap:16px}}
.sent-val{{font-family:var(--display);font-size:36px;font-weight:700;line-height:1;background:linear-gradient(135deg,var(--up),var(--cyn));-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.sent-lbl{{font-size:12px;color:var(--t3);font-weight:600;text-transform:uppercase;letter-spacing:.08em}}
.sent-desc{{font-size:14px;font-weight:600;color:var(--up)}}
.sbar{{width:110px;height:5px;background:var(--bg4);border-radius:3px;position:relative;overflow:visible}}
.sfill{{height:100%;border-radius:2px;background:linear-gradient(90deg,var(--dn),var(--wrn) 35%,var(--up) 100%);position:relative}}
.sfill::after{{content:'';position:absolute;right:-5px;top:50%;transform:translateY(-50%);width:10px;height:10px;border-radius:50%;background:var(--up);box-shadow:0 0 10px var(--up-glow)}}
.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(480px,1fr));gap:14px;margin-bottom:14px}}
.g .fw{{grid-column:1/-1}}
.sec{{backdrop-filter:blur(16px);background:var(--bg2);border:1px solid var(--bd);border-radius:10px;overflow:hidden;display:flex;flex-direction:column}}
.sh{{padding:12px 18px;border-bottom:1px solid var(--bd);font-family:var(--display);font-size:14px;font-weight:600;color:var(--t2);display:flex;align-items:center;gap:8px}}
.sh .ico{{color:var(--a);font-size:13px}}
.sh .meta{{margin-left:auto;font-size:11px;color:var(--t3);font-weight:400}}
table{{width:100%;border-collapse:collapse}}
th{{font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;padding:8px 16px;text-align:left;border-bottom:1px solid var(--bd);color:var(--t3);background:rgba(255,255,255,.015)}}
td{{padding:8px 16px;border-bottom:1px solid rgba(255,255,255,.03);font-size:13.5px;vertical-align:middle}}
tr:hover td{{background:rgba(255,255,255,.02)}}
.tr{{font-family:var(--mono);color:var(--t2);font-size:12px;white-space:nowrap}}
.t2{{color:var(--t1);font-weight:500}}
.t3{{color:var(--t3);font-size:12px}}
.tb{{color:var(--inf);font-weight:600;white-space:nowrap}}
.br,.bo,.bbl,.bg_,.bcy,.bgd{{display:inline-block;min-width:34px;text-align:center;padding:2px 8px;border-radius:5px;font-size:10.5px;font-weight:700;letter-spacing:.03em;white-space:nowrap}}
.br{{background:rgba(239,68,68,.1);color:var(--up)}}
.bo{{background:var(--wrn-bg);color:var(--wrn)}}
.bbl{{background:var(--inf-bg);color:var(--inf)}}
.bg_{{background:var(--up-bg);color:var(--up)}}
.bcy{{background:var(--cyn-bg);color:var(--cyn)}}
.bgd{{background:var(--gld-bg);color:var(--gld)}}
.tag{{display:inline-block;font-size:11px;padding:1px 6px;border-radius:4px;margin:0 2px;white-space:nowrap;font-weight:600;line-height:1.6}}
.tag.r{{background:rgba(239,68,68,.12);color:var(--up)}}
.tag.b{{background:var(--inf-bg);color:var(--inf)}}
.tag.y{{background:var(--gld-bg);color:var(--gld)}}
.tag.c{{background:var(--cyn-bg);color:var(--cyn)}}
.tag.g{{background:var(--dn-bg);color:var(--dn)}}
.weekend-note{{background:rgba(249,115,22,.08);border:1px solid rgba(249,115,22,.2);border-radius:8px;padding:10px 16px;margin:10px 16px;font-size:12px;color:var(--wrn);display:flex;align-items:center;gap:8px}}
.weekend-note::before{{content:'⚠';font-size:14px}}
.ft{{text-align:center;padding:20px;font-size:12px;color:var(--t3)}}
.ft span{{color:var(--a);font-weight:600}}
@media(max-width:960px){{.g{{grid-template-columns:1fr}}.hero{{flex-wrap:wrap}}}}
</style>
</head>
<body>
<header><span class="logo">每日简报</span><div class="hdr-right"><span class="hdr-date">{date_str}</span><span class="live-badge"><span class="live-dot"></span>{'WEEKEND' if weekend else 'LIVE'}</span></div></header>
<main class="c">

<!-- HERO -->
<section class="hero">
<div class="sent-box">
  <div><div class="sent-lbl">情绪</div><div class="sent-val">{pg_score:.0f}</div><div class="sent-desc">{pg_status}</div></div>
  <div class="sbar"><div class="sfill" style="width:{pg_score}%"></div></div>
</div>
</section>

<!-- 自动流网格 -->
<div class="g">
'''

    # 财经新闻
    news = data.get("news", [])
    if news:
        html += '''<section class="sec fw">
<div class="sh"><span class="ico">◉</span> 财经科技新闻 <span class="meta">''' + str(len(news)) + '''条</span></div>
<table>
<tr><th>时间</th><th>类型</th><th>标题</th><th>来源</th></tr>
'''
        for item in news[:15]:
            time_str = item.get("time", "")[11:16] if item.get("time") else item.get("time", "")
            title = item.get("title", "")[:80]
            source = item.get("source", "")
            news_type = item.get("type", "中性")
            type_class = "bg_" if news_type == "利好" else "bo" if news_type == "利空" else "bbl"
            html += f'''<tr><td class="tr">{time_str}</td><td><span class="{type_class}">{news_type}</span></td><td class="t2">{title}</td><td class="t3">{source}</td></tr>\n'''
        html += '''</table></section>\n'''

    # 自选股新闻
    ss_news = data.get("selfstock_news", {})
    ss_list = ss_news.get("news", [])
    ss_meta = ss_news.get("data_date", get_today_str())
    if ss_list:
        html += f'''<section class="sec">
<div class="sh"><span class="ico">◉</span> 自选股新闻 <span class="meta">{len(ss_list)}条 · {ss_meta.replace('-','/')}数据</span></div>
<table>
<tr><th>时间</th><th>类型</th><th>标题</th><th>来源</th></tr>
'''
        for item in ss_list[:15]:
            time_str = item.get("time", "") or "—"
            title = item.get("title", "")[:80]
            source = item.get("source", "")
            news_type = item.get("type", "中性")
            codes = item.get("related_codes", [])
            code_tags = "".join(f'<span class="tag r">{c}</span>' for c in codes[:3])
            type_class = "bg_" if news_type == "利好" else "bo" if news_type == "利空" else "bbl"
            html += f'''<tr><td class="tr">{time_str}</td><td><span class="{type_class}">{news_type}</span></td><td class="t2">{title} {code_tags}</td><td class="t3">{source}</td></tr>\n'''
        html += '''</table></section>\n'''
    else:
        note = ss_news.get("note", "最近3天内暂无自选股相关新闻")
        html += f'''<section class="sec">
<div class="sh"><span class="ico">◉</span> 自选股新闻 <span class="meta">{ss_meta.replace('-','/')}数据</span></div>
<div class="weekend-note">{note}</div>
<table>
<tr><th>时间</th><th>类型</th><th>标题</th><th>来源</th></tr>
<tr><td class="tr">—</td><td><span class="bbl">中性</span></td><td class="t2">暂无相关新闻</td><td class="t3">—</td></tr>
</table>
</section>\n'''

    # Serenity观点
    serenity = data.get("serenity", {})
    if serenity:
        html += '''<section class="sec">
<div class="sh"><span class="ico">◉</span> Serenity观点 <span class="meta">@aleabitoreddit</span></div>
<table>
<tr><th>标的</th><th>提及次数</th><th>核心观点</th></tr>
'''
        for sym, info in list(serenity.items())[:10]:
            count = info.get("count", 0)
            direction = info.get("direction", "")
            html += f'''<tr><td class="tb"><span class="tag r">${sym}</span></td><td>{count}次</td><td class="t2">{direction[:50]}</td></tr>\n'''
        html += '''</table></section>\n'''

    # 淘股吧博主
    tgb = data.get("tgb", {})
    tgb_bloggers = tgb.get("bloggers", {})
    if tgb_bloggers:
        html += '''<section class="sec">
<div class="sh"><span class="ico">◉</span> 淘股吧 <span class="meta">''' + str(len(tgb_bloggers)) + '''位博主 · ''' + tgb.get("date", get_today_str()) + '''</span></div>
<table>
<tr><th>博主</th><th>核心观点 + 标的</th></tr>
'''
        for name, info in tgb_bloggers.items():
            posts = info.get("posts", [])
            replies = info.get("top_replies", [])
            content_parts = []
            if posts:
                for post in posts[:1]:
                    title = post.get("title", "")
                    body = post.get("content", "")[:80]
                    content_parts.append(f"<b>{title}</b>：{body}")
            elif replies:
                r = replies[0]
                content_parts.append(f"<span style='color:var(--t3);font-size:11px'>仅跟帖</span> <b>{r.get('content','')[:60]}</b>")
            else:
                content_parts.append("今日无动态")
            html += f'''<tr><td class="tb" style="color:var(--gld)">{name}</td><td class="t2">{"".join(content_parts)}</td></tr>\n'''
        html += '''</table></section>\n'''

    # 抖音博主观点
    douyin = data.get("douyin", {})
    douyin_bloggers = douyin.get("bloggers", [])
    if douyin_bloggers:
        total_videos = sum(len(b.get("videos", [])) for b in douyin_bloggers)
        html += f'''<section class="sec fw">
<div class="sh"><span class="ico">◉</span> 抖音 <span class="meta">{len(douyin_bloggers)}位博主 · {total_videos}条视频 · 本地Whisper转录</span></div>
<table>
<tr><th>博主</th><th>视频</th><th>核心观点</th><th>标的</th><th>方向</th></tr>
'''
        for blogger in douyin_bloggers:
            name = blogger.get("name", "")
            videos = blogger.get("videos", [])
            for v in videos:
                title = v.get("title", "")[:40]
                summary = v.get("summary", "")[:90]
                symbols = " ".join(f'<span class="tag y">{s}</span>' for s in v.get("symbols", []))
                direction = v.get("direction", "关注")
                dir_class = "bg_" if direction == "利好" else "bo" if direction == "利空" else "bbl"
                html += f'''<tr><td class="tb" style="color:var(--gld)">{name}</td><td class="t2">{title}</td><td class="t2">{summary}</td><td>{symbols}</td><td><span class="{dir_class}">{direction}</span></td></tr>\n'''
        html += '''</table></section>\n'''
    else:
        note = douyin.get("note", "抖音数据获取失败或未配置博主")
        html += f'''<section class="sec fw">
<div class="sh"><span class="ico">◉</span> 抖音 <span class="meta">{note}</span></div>
<div class="weekend-note">抖音博主观点抓取未返回数据，请检查网络或博主链接是否可用</div>
</section>\n'''

    # 未来大事件
    future = data.get("future_events", {})
    events = future.get("events", [])
    if events:
        html += f'''<section class="sec">
<div class="sh"><span class="ico">◉</span> 未来大事件 <span class="meta">{future.get('range','').replace('-','/')} · {len(events)}条</span></div>
<table>
<tr><th>时间</th><th>类型</th><th>事件</th><th>影响</th></tr>
'''
        for item in events[:15]:
            date_str_ev = item.get("date", "")
            time_str_ev = item.get("time", "")
            time_display = f"{date_str_ev} {time_str_ev}".strip() if time_str_ev else date_str_ev
            ev_type = item.get("type", "宏观")
            event = item.get("event", "")[:70]
            impact = item.get("impact", "中性")
            type_class = "bg_" if impact == "利好" else "bo" if impact == "利空" else "bbl"
            html += f'''<tr><td class="tr">{time_display}</td><td><span class="bbl">{ev_type}</span></td><td class="t2">{event}</td><td><span class="{type_class}">{impact}</span></td></tr>\n'''
        html += '''</table></section>\n'''
    else:
        html += '''<section class="sec">
<div class="sh"><span class="ico">◉</span> 未来大事件 <span class="meta">数据获取失败</span></div>
<div class="weekend-note">未来大事件数据获取失败，请检查网络或数据源可用性</div>
<table>
<tr><th>时间</th><th>类型</th><th>事件</th><th>影响</th></tr>
<tr><td class="tr">—</td><td><span class="bbl">宏观</span></td><td class="t2">暂无数据</td><td><span class="bbl">中性</span></td></tr>
</table>
</section>\n'''

    html += '''</div><!-- .g end -->'''

    # 页脚
    html += f'''
<div class="ft">每日简报 · <span>v4</span> · {date_str} {weekday}</div>
</main>
</body>
</html>'''

    return html


def main():
    """主函数：后台整合数据并生成HTML"""
    data = {
        "panic_greed": {},
        "news": [],
        "serenity": {},
        "selfstock_news": {},
        "future_events": {}
    }

    # 1. 恐慌贪婪指数
    data["panic_greed"] = run_script("panic_greed_index_enhanced.py")

    # 2. 财经新闻
    news_data = run_script("fetch_news.py", "--source", "eastmoney", "--limit", "15")
    data["news"] = news_data.get("news", [])

    # 3. 自选股新闻（后台HTTP，无浏览器）
    data["selfstock_news"] = run_script("fetch_selfstock_news.py")

    # 4. 未来大事件（后台HTTP，无浏览器）
    data["future_events"] = run_script("fetch_future_events.py")

    # 5. Serenity观点（可选，网络HTTP）
    serenity_data = run_script("serenity_crawler.py", "--symbols")
    if not serenity_data:
        # serenity_crawler.py 默认输出文本，这里不做解析
        data["serenity"] = {}

    # 6. 淘股吧博主
    data["tgb"] = run_script("tgb_crawl.py")

    # 7. 抖音博主观点（本地Whisper兜底，耗时较长）
    data["douyin"] = run_script("fetch_douyin.py", timeout=600)

    # 生成HTML
    html = generate_briefing(data)

    # 确保输出目录存在
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 保存文件：reports/每日简报/YYYY-MM-DD简报.html
    today = datetime.now().strftime("%Y-%m-%d")
    output_path = OUTPUT_DIR / f"{today}简报.html"

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    # URL编码的Markdown链接
    abs_path = str(output_path).replace("\\", "/")
    encoded = quote(abs_path, safe="/:")
    print(f"\n📄 [{today}简报.html](file:///{encoded})")

    # JSON摘要输出到stderr，不污染链接
    summary = {
        "date": today,
        "panic_greed_score": data["panic_greed"].get("score", 0),
        "panic_greed_status": data["panic_greed"].get("status", ""),
        "news_count": len(data["news"]),
        "selfstock_news_count": data["selfstock_news"].get("news_count", 0),
        "future_events_count": data["future_events"].get("event_count", 0),
        "output_file": str(output_path)
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)


if __name__ == "__main__":
    main()
