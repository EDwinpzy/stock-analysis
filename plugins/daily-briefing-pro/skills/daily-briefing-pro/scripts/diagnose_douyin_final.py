#!/usr/bin/env python3
"""完整诊断：短链→主页→API，输出min_cursor"""
import asyncio
import re
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright


async def main():
    share_url = "https://v.douyin.com/gvHcwiTADOk/"
    print(f"短链: {share_url}\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15',
            viewport={'width': 390, 'height': 844}
        )
        page = await ctx.new_page()

        await page.goto(share_url, wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(4000)
        full_url = page.url
        print(f"1. 短链跳转: {full_url}")

        m = re.search(r'/user/([^/?]+)', full_url)
        sec_uid = m.group(1) if m else None
        print(f"2. sec_uid: {sec_uid}\n")

        captured = []

        async def capture(response):
            url = response.url
            if '/web/api/v2/aweme/post' in url:
                print(f"3. 拦截API: {url[:120]}")
                try:
                    data = await response.json()
                    min_cursor = data.get('min_cursor', 0)
                    max_cursor = data.get('max_cursor', 0)
                    has_more = data.get('has_more', False)
                    count = len(data.get('aweme_list', []))
                    print(f"   - aweme_list数量: {count}")
                    print(f"   - min_cursor(毫秒): {min_cursor}")
                    if min_cursor:
                        min_cursor_sec = min_cursor // 1000
                        print(f"   - min_cursor(秒): {min_cursor_sec}")
                        from datetime import datetime, timezone, timedelta
                        tz_bj = timezone(timedelta(hours=8))
                        dt = datetime.fromtimestamp(min_cursor_sec, tz=tz_bj)
                        print(f"   - min_cursor北京时间: {dt.strftime('%Y-%m-%d %H:%M')}")
                    print(f"   - max_cursor: {max_cursor}, has_more: {has_more}")
                    captured.append(data)
                except Exception as e:
                    print(f"   - JSON解析失败: {e}")

        page.on('response', lambda r: asyncio.create_task(capture(r)))

        await page.goto(f'https://www.douyin.com/user/{sec_uid}', wait_until='domcontentloaded', timeout=30000)
        await page.wait_for_timeout(3000)
        for i in range(6):
            await page.evaluate('window.scrollBy(0, 3000)')
            await page.wait_for_timeout(2500)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
