#!/usr/bin/env python3
"""通过Playwright直接提取视频发布时间"""
import asyncio
import re
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright


def ts_to_bj_str(ts):
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

        aid = '7654802871703547045'
        url = f"https://www.douyin.com/video/{aid}"
        print(f"检查视频: {aid} ({url})")
        print("---")

        await page.goto(url, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(3000)

        # 获取页面文本
        text = await page.content()

        # 查找时间文本
        import re
        patterns = [
            r'(\d{4}年\d{2}月\d{2}日\d{2}:\d{2})',
            r'(\d+小时前)',
            r'(\d+分钟前)',
            r'(\d+秒前)',
            r'(昨天)',
            r'(^\d{1,2}\s*[时:]\s*\d{2})',
        ]

        print("=== 页面时间文本 ===")
        for pat in patterns:
            matches = re.findall(pat, text)
            if matches:
                print(f"{pat}: {matches[:5]}")

        # 查找包含时间描述的文本
        lines = text.split('\\n')
        for line in lines[:100]:
            if '发布' in line or '小时' in line or '分钟' in line or '昨天' in line:
                print(f"找到: {line.strip()[:200]}")

        # 查找 JSON 片段
        print("\\n=== JSON 片段 ===")
        for m in re.finditer(r'\{[^}]*publish[^}]*\}', text):
            snippet = m.group(0)[:300]
            print(f"发现: {snippet}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
