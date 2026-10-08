#!/usr/bin/env python3
"""探测抖音视频详情API"""
import asyncio
import json
import re
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

VID = "7659870209783952070"


def ts_to_bj(ts) -> str:
    try:
        dt = datetime.fromtimestamp(int(ts), tz=timezone(timedelta(hours=8)))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        return str(e)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15',
            viewport={'width': 390, 'height': 844}
        )
        page = await ctx.new_page()

        captured = []

        async def capture(response):
            url = response.url
            if 'aweme' in url and ('detail' in url or '/aweme/' in url):
                print(f"  拦截: {url[:150]}")
                try:
                    captured.append((url, await response.json()))
                except Exception as e:
                    print(f"    JSON解析失败: {e}")

        page.on('response', lambda r: asyncio.create_task(capture(r)))

        video_url = f"https://www.douyin.com/video/{VID}"
        print(f"打开视频详情页: {video_url}")
        await page.goto(video_url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(4000)

        html = await page.content()
        # 从HTML提取create_time
        m = re.search(r'"create_time":\s*(\d{10,13})', html)
        if m:
            print(f"HTML create_time: {m.group(1)} -> {ts_to_bj(m.group(1))}")

        print(f"\n拦截到 {len(captured)} 个响应")
        for url, data in captured:
            print(f"\nURL: {url[:120]}")
            if isinstance(data, dict):
                print(f"顶层键: {list(data.keys())}")
                if 'aweme_detail' in data:
                    detail = data['aweme_detail']
                    print(f"aweme_detail 键: {list(detail.keys())}")
                    if 'create_time' in detail:
                        print(f"create_time: {detail['create_time']} -> {ts_to_bj(detail['create_time'])}")
                elif 'data' in data:
                    print(f"data 键: {list(data['data'].keys()) if isinstance(data['data'], dict) else type(data['data'])}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
