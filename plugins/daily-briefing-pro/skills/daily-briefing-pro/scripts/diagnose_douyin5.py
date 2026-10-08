#!/usr/bin/env python3
"""单独测试口罩哥主页抓取（修复短链问题）"""
import asyncio
import json
import re
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

SHARE_URL = "https://v.douyin.com/gvHcwiTADOk/"


def ts_to_bj_str(ts) -> str:
    if not ts:
        return "unknown"
    try:
        tz_bj = timezone(timedelta(hours=8))
        return datetime.fromtimestamp(int(ts), tz=tz_bj).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


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
        print(f"短链跳转后URL: {full_url}")

        m = re.search(r'/user/([^/?]+)', full_url)
        sec_uid = m.group(1) if m else None
        print(f"sec_uid: {sec_uid}")

        if not sec_uid:
            print("未能解析 sec_uid，尝试 /home 跳转逻辑")
            await page.goto(f"https://www.douyin.com/home", wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(4000)
            full_url = page.url
            print(f"跳转后URL: {full_url}")
            m = re.search(r'/user/([^/?]+)', full_url)
            sec_uid = m.group(1) if m else None
            print(f"sec_uid: {sec_uid}")

        captured = []

        async def capture(response):
            if '/web/api/v2/aweme/post' in response.url:
                try:
                    data = await response.json()
                    min_cursor = data.get('min_cursor', 0)
                    print(f"  API返回: {len(data.get('aweme_list', []))} 条视频, min_cursor={min_cursor}, min_cursor_bj={ts_to_bj_str(min_cursor // 1000) if min_cursor else 'N/A'}")
                    captured.append(data)
                except Exception as e:
                    print(f"  JSON解析失败: {e}")

        page.on('response', lambda r: asyncio.create_task(capture(r)))

        await page.goto(f'https://www.douyin.com/user/{sec_uid}', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)
        for i in range(6):
            await page.evaluate('window.scrollBy(0, 3000)')
            await page.wait_for_timeout(2500)

        await browser.close()

        if captured:
            print(f"\n总共拦截到 {len(captured)} 个响应")
            # 取第一个响应看所有视频
            data = captured[0]
            aweme_list = data.get('aweme_list', [])
            print(f"\naweme_list 长度: {len(aweme_list)}")
            print(f"max_cursor={data.get('max_cursor', 0)}, min_cursor={data.get('min_cursor', 0)}, has_more={data.get('has_more', False)}")
            print(f"\n所有视频发布时间:")
            for item in aweme_list:
                vid = item.get('aweme_id', 'unknown')
                desc = (item.get('desc', '') or '')[:50]
                create_time = item.get('create_time', 0)
                print(f"  {vid} | create_time={create_time} | bj={ts_to_bj_str(create_time)} | {desc}")


if __name__ == "__main__":
    asyncio.run(main())
