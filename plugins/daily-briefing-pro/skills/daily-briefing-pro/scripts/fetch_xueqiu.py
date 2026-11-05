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

    # Use verified accessible accounts from the documented candidate list.
    # Failed candidates are recorded separately and never counted as no posts.
    users = load_users(limit + 30)
    if not users:
        return {
            "platform": "雪球", "date": target_date, "data_date": "", "bloggers": {},
            "status": "error", "error": "缺少雪球博主名单",
            "note": "data/xueqiu_hot_users.json 不存在或为空；未使用旧缓存",
        }

    cookies = load_cookies()
    bloggers, active, complete, queried = {}, 0, 0, 0
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
            if complete >= limit:
                break
            queried += 1
            uid, name = user["uid"], user["name"]
            try:
                for retry in range(3):
                    response = await page.request.get(
                        f"https://xueqiu.com/statuses/user_timeline.json?user_id={uid}&page=1",
                        headers={"Referer": f"https://xueqiu.com/u/{uid}"},
                    )
                    if response.status == 200:
                        break
                    await page.wait_for_timeout(1000)
                if response.status != 200:
                    errors.append(f"{name}:HTTP{response.status}")
                    continue
                payload = json.loads(await response.text())
                if not isinstance(payload.get("statuses"), list):
                    raise ValueError("时间线返回错误信封")
                statuses = list(payload["statuses"])
                for number in range(2, 51):
                    if not statuses or min(int(s.get("created_at") or 0) for s in statuses) < int(datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=CN).timestamp()*1000):
                        break
                    response = await page.request.get(f"https://xueqiu.com/statuses/user_timeline.json?user_id={uid}&page={number}", headers={"Referer": f"https://xueqiu.com/u/{uid}"})
                    more = json.loads(await response.text())
                    if response.status != 200 or not isinstance(more.get("statuses"), list):
                        raise ValueError("时间线分页失败")
                    if not more["statuses"]:
                        break
                    statuses.extend(more["statuses"])
                else:
                    raise ValueError("超过50页仍未覆盖目标日")
            except Exception as exc:
                errors.append(f"{name}:{type(exc).__name__}")
                continue

            posts = []
            for status in statuses:
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
                    "content": body,
                    "id": str(status.get("id") or ""),
                    "source_url": f"https://xueqiu.com/{uid}/{status.get('id')}",
                    "created_at": moment.strftime("%Y-%m-%d %H:%M"),
                    "likes": int(status.get("like_count") or 0),
                    "retweets": int(status.get("retweet_count") or 0),
                })
            complete += 1
            if posts:
                active += 1
            bloggers[name] = {"name": name, "uid": uid, "data_date": target_date, "posts": posts}

        await browser.close()

    return {
        "platform": "雪球",
        "date": target_date,
        "data_date": target_date if active else "",
        "bloggers": bloggers,
        "status": ("partial" if active else "error") if complete < limit else ("ok" if active else "empty"),
        "coverage": {"expected_bloggers": limit, "queried_bloggers": queried, "complete_bloggers": complete, "failed_bloggers": max(0, limit-complete), "excluded_candidates": len(errors), "active_bloggers": active},
        "active_bloggers": active,
        "queried_bloggers": queried,
        "source": "雪球时间线接口（Playwright 浏览器内请求上下文）",
        "failures": errors[:10],
        "note": (
            f"候选查询{queried}位，完整核验{complete}位雪球样本，{active}位在{target_date}有发帖；排除{len(errors)}位访问失败候选（未计作无动态）"
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
