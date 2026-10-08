#!/usr/bin/env python3
"""深度诊断：查找 aweme_item 中的时间字段与分页参数"""
import asyncio
import json
import re
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

SHARE_URL = "https://v.douyin.com/gvHcwiTADOk/"


def ts_to_bj(ts) -> str:
    if not ts:
        return "无"
    try:
        tz_bj = timezone(timedelta(hours=8))
        return datetime.fromtimestamp(int(ts), tz=tz_bj).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


def find_time_fields(obj, path="", found=None, max_depth=6):
    """递归查找对象中可能是时间戳的数字字段"""
    if found is None:
        found = []
    if len(found) > 20 or len(path) > max_depth:
        return found
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f"{path}.{k}" if path else k
            if isinstance(v, (int, float)) and 1_000_000_000 < v < 2_000_000_000:
                found.append((new_path, v, ts_to_bj(v)))
            elif isinstance(v, str) and re.match(r"^\d{10}$", v):
                found.append((new_path, v, ts_to_bj(int(v))))
            elif isinstance(v, (dict, list)):
                find_time_fields(v, new_path, found, max_depth)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            find_time_fields(v, f"{path}[{i}]", found, max_depth)
    return found


async def main():
    print(f"诊断短链: {SHARE_URL}")
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
        print(f"sec_uid: {sec_uid}")

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
            print("未拦截到任何响应")
            return

        data = captured[0]
        print("\n=== 顶层键 ===")
        print(list(data.keys()))

        aweme_list = data.get('aweme_list', [])
        print(f"\naweme_list 长度: {len(aweme_list)}")

        if aweme_list:
            first = aweme_list[0]
            print("\n=== 第一个 aweme 的顶层键 ===")
            print(list(first.keys()))
            print("\n=== 可能是时间戳的字段 ===")
            times = find_time_fields(first)
            for path, val, bj in times:
                print(f"  {path}: {val} -> {bj}")

            print("\n=== 第一个 aweme 完整 JSON（前2000字符）===")
            print(json.dumps(first, ensure_ascii=False, indent=2)[:2000])

        print("\n=== 分页参数 ===")
        for k in ['max_cursor', 'min_cursor', 'has_more', 'status_code', 'home_page']:
            if k in data:
                print(f"  {k}: {data[k]}")


if __name__ == "__main__":
    asyncio.run(main())
