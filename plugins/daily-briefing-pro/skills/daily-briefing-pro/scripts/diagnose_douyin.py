#!/usr/bin/env python3
"""抖音抓取诊断脚本：输出博主主页API响应结构与视频日期分布"""
import asyncio
import json
import re
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

BLOGGERS = [
    ("口罩哥", "https://v.douyin.com/gvHcwiTADOk/"),
    ("机构一手调研（福总）", "https://v.douyin.com/0ijdyeSWSSs/"),
]


def ts_to_bj(ts: int) -> str:
    if not ts:
        return "无时间"
    tz_bj = timezone(timedelta(hours=8))
    return datetime.fromtimestamp(int(ts), tz=tz_bj).strftime("%Y-%m-%d %H:%M")


async def diagnose(name: str, share_url: str):
    print(f"\n=== 诊断: {name} ===")
    print(f"短链: {share_url}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15',
            viewport={'width': 390, 'height': 844}
        )
        page = await ctx.new_page()
        try:
            await page.goto(share_url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(4000)
        except Exception as e:
            print(f"  打开短链失败: {e}")
            await browser.close()
            return

        full_url = page.url
        print(f"  跳转后URL: {full_url}")
        m = re.search(r'/user/([^/?]+)', full_url)
        sec_uid = m.group(1) if m else None
        print(f"  sec_uid: {sec_uid}")
        if not sec_uid:
            await browser.close()
            return

        captured = []
        url_patterns = ['/web/api/v2/aweme/post', '/aweme/v1/web/aweme/post', '/api/v2/aweme/post']

        async def capture(response):
            for pat in url_patterns:
                if pat in response.url:
                    print(f"  拦截API: {response.url[:120]}...")
                    try:
                        captured.append(await response.json())
                    except Exception as e:
                        print(f"    解析JSON失败: {e}")

        page.on('response', lambda r: asyncio.create_task(capture(r)))

        try:
            await page.goto(f'https://www.douyin.com/user/{sec_uid}', wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(3000)
            for i in range(6):
                await page.evaluate('window.scrollBy(0, 2500)')
                await page.wait_for_timeout(2500)
                print(f"  滚动 {i+1}/6")
        except Exception as e:
            print(f"  加载主页失败: {e}")
        finally:
            await browser.close()

        total_items = 0
        today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        today_count = 0
        dates = []
        for data in captured:
            aweme_list = data.get('aweme_list', []) if isinstance(data, dict) else []
            print(f"  响应中 aweme_list 数量: {len(aweme_list)}")
            for item in aweme_list:
                total_items += 1
                vid = item.get('aweme_id', 'unknown')
                desc = (item.get('desc', '') or '')[:40]
                create_time = item.get('create_time', 0)
                dt_bj = ts_to_bj(create_time)
                dates.append(dt_bj)
                is_today = dt_bj.startswith(today)
                if is_today:
                    today_count += 1
                print(f"    {vid} | {dt_bj} | 今日:{is_today} | {desc}")

        print(f"\n  汇总: 总视频 {total_items}, 今日 {today_count}, 拦截响应 {len(captured)}")
        print(f"  日期分布: {sorted(set(dates))}")


async def main():
    for name, url in BLOGGERS:
        await diagnose(name, url)


if __name__ == "__main__":
    asyncio.run(main())
