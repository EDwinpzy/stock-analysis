#!/usr/bin/env python3
"""查找响应中所有 create_time 字段及视频详情页时间"""
import asyncio
import json
import re
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

SHARE_URL = "https://v.douyin.com/gvHcwiTADOk/"


def find_keys(obj, target="create_time", path="", found=None):
    if found is None:
        found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f"{path}.{k}" if path else k
            if k == target:
                found.append((new_path, v))
            elif isinstance(v, (dict, list)):
                find_keys(v, target, new_path, found)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            find_keys(v, target, f"{path}[{i}]", found)
    return found


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15',
            viewport={'width': 390, 'height': 844}
        )
        page = await ctx.new_page()
        await page.goto(SHARE_URL, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(4000)
        full_url = page.url
        m = re.search(r'/user/([^/?]+)', full_url)
        sec_uid = m.group(1) if m else None

        captured = []

        async def capture(response):
            if '/web/api/v2/aweme/post' in response.url:
                try:
                    captured.append(await response.json())
                except Exception:
                    pass

        page.on('response', lambda r: asyncio.create_task(capture(r)))
        await page.goto(f'https://www.douyin.com/user/{sec_uid}', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)
        await browser.close()

        if not captured:
            print("无响应")
            return

        data = captured[0]
        found = find_keys(data, "create_time")
        print(f"找到 {len(found)} 个 create_time 字段:")
        for path, val in found[:30]:
            print(f"  {path}: {val}")

        # 取第一个视频，尝试打开详情页找时间
        aweme_list = data.get('aweme_list', [])
        if aweme_list:
            first = aweme_list[0]
            vid = first['aweme_id']
            video_url = f"https://www.douyin.com/video/{vid}"
            print(f"\n尝试获取视频详情页时间: {video_url}")
            browser2 = await p.chromium.launch(headless=True)
            ctx2 = await browser2.new_context(
                user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15',
                viewport={'width': 390, 'height': 844}
            )
            page2 = await ctx2.new_page()
            try:
                await page2.goto(video_url, wait_until='domcontentloaded', timeout=30000)
                await page2.wait_for_timeout(3000)
                html = await page2.content()
                # 查找时间相关文本
                time_patterns = [
                    r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})',
                    r'(\d{4}年\d{2}月\d{2}日)',
                    r'"create_time":\s*(\d{10,13})',
                    r'"publish_time":\s*(\d{10,13})',
                ]
                for pat in time_patterns:
                    matches = re.findall(pat, html)
                    if matches:
                        print(f"  匹配 {pat}: {matches[:5]}")
                # 查找包含发布时间的元素
                found_times = []
                for el in await page2.query_selector_all('*'):
                    text = await el.text_content() or ''
                    if '发布' in text or '小时前' in text or '分钟前' in text or '昨天' in text:
                        t = text.strip()
                        if t and len(t) < 100:
                            found_times.append(t)
                print(f"  页面时间文本: {list(set(found_times))[:10]}")
            except Exception as e:
                print(f"  详情页失败: {e}")
            await browser2.close()


if __name__ == "__main__":
    asyncio.run(main())
