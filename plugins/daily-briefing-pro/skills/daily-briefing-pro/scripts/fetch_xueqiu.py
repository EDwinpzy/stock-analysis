#!/usr/bin/env python3
"""雪球头部博主当日帖子采集（Playwright + 浏览器内请求上下文）。

关键点：雪球对裸 HTTP 请求和外部浏览器指纹会下发阿里云 WAF 滑动验证，
但**用 Playwright 打开 xueqiu.com 之后，再用同一个页面的 request 上下文**
去请求 ``/statuses/user_timeline.json`` 就能正常返回真实 JSON。
（注意是 ``/statuses/...``，``/v4/statuses/...`` 仍会被 WAF 拦截。）

输出结构与 fetch_sentiment_survey.crawl_xueqiu() 约定一致：
    {platform, date, data_date, bloggers: {name: {posts: [...]}}, status, source}

用法: python fetch_xueqiu.py [--date YYYY-MM-DD] [--limit 50]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
from runtime_paths import get_data_dir

DATA_DIR = get_data_dir(BASE_DIR)
PACKAGE_DATA_DIR = BASE_DIR / "data"

CN = timezone(timedelta(hours=8))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

COOKIE_CANDIDATES = [
    DATA_DIR / "xueqiu_cookies.json",
    Path(os.path.expanduser("~/.codex/xueqiu_cookies.json")),
]


def load_cookies() -> list:
    for path in COOKIE_CANDIDATES:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except Exception as exc:
                print(f"[WARN] 雪球Cookie解析失败 {path}: {exc}", file=sys.stderr)
    return []


def load_users(limit: int) -> list:
    path = PACKAGE_DATA_DIR / "xueqiu_hot_users.json"
    if not path.exists():
        return []
    users = json.loads(path.read_text(encoding="utf-8"))
    seen, out = set(), []
    for item in users:
        uid = item.get("uid")
        if not uid or uid in seen:
            continue
        seen.add(uid)
        out.append({"uid": uid, "name": item.get("name") or str(uid)})
        if len(out) >= limit:
            break
    return out


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", text).strip()


async def collect(target_date: str, limit: int) -> dict:
    from playwright.async_api import async_playwright

    users = load_users(limit)
    if not users:
        return {
            "platform": "雪球", "date": target_date, "data_date": "", "bloggers": {},
            "status": "error", "error": "缺少雪球博主名单",
            "note": "data/xueqiu_hot_users.json 不存在或为空；未使用旧缓存",
        }

    cookies = load_cookies()
    bloggers, active = {}, 0
    errors = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=UA)
        if cookies:
            try:
                await context.add_cookies(cookies)
            except Exception as exc:
                print(f"[WARN] 雪球Cookie注入失败: {exc}", file=sys.stderr)
        page = await context.new_page()
        # 先访问首页，让浏览器自己过掉 WAF 并拿到 __utm 等通行 Cookie
        await page.goto("https://xueqiu.com/", wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(4000)

        for user in users:
            uid, name = user["uid"], user["name"]
            try:
                response = await page.request.get(
                    f"https://xueqiu.com/statuses/user_timeline.json?user_id={uid}&page=1",
                    headers={"Referer": f"https://xueqiu.com/u/{uid}"},
                )
                if response.status != 200:
                    errors.append(f"{name}:HTTP{response.status}")
                    continue
                payload = json.loads(await response.text())
            except Exception as exc:
                errors.append(f"{name}:{type(exc).__name__}")
                continue

            posts = []
            for status in payload.get("statuses") or []:
                created = status.get("created_at")
                if not created:
                    continue
                try:
                    moment = datetime.fromtimestamp(int(created) / 1000, CN)
                except (TypeError, ValueError):
                    continue
                if moment.strftime("%Y-%m-%d") != target_date:
                    continue
                body = _clean(status.get("description") or status.get("text") or "")
                title = _clean(status.get("title") or "")
                posts.append({
                    "title": title,
                    "content": body[:600],
                    "created_at": moment.strftime("%Y-%m-%d %H:%M"),
                    "likes": int(status.get("like_count") or 0),
                    "retweets": int(status.get("retweet_count") or 0),
                })
            if posts:
                active += 1
                bloggers[name] = {"name": name, "uid": uid, "data_date": target_date, "posts": posts}

        await browser.close()

    return {
        "platform": "雪球",
        "date": target_date,
        "data_date": target_date if active else "",
        "bloggers": bloggers,
        "status": "ok" if active else "empty",
        "active_bloggers": active,
        "queried_bloggers": len(users),
        "source": "雪球时间线接口（Playwright 浏览器内请求上下文）",
        "failures": errors[:10],
        "note": (
            f"查询{len(users)}位雪球博主，{active}位在{target_date}有发帖"
            if active else f"查询{len(users)}位雪球博主，{target_date}均无发帖"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(CN).strftime("%Y-%m-%d"))
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    result = asyncio.run(collect(args.date, args.limit))
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
