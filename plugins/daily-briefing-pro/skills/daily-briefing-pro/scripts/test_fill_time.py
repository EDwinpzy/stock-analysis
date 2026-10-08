#!/usr/bin/env python3
"""测试补全视频时间的函数"""
import asyncio
import httpx
import re
from datetime import datetime, timezone, timedelta


def ts_to_bj_str(ts):
    if not ts:
        return "unknown"
    try:
        tz_bj = timezone(timedelta(hours=8))
        return datetime.fromtimestamp(int(ts), tz=tz_bj).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


def bj_now_str():
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


async def fetch_video_create_time(aweme_id: str, timeout: int = 15) -> int:
    """通过视频详情页 HTML 提取 create_time（秒级时间戳）"""
    url = f"https://www.douyin.com/video/{aweme_id}"
    try:
        async with httpx.AsyncClient(http2=True, follow_redirects=True, timeout=timeout) as client:
            resp = await client.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            })
            resp.raise_for_status()
            text = resp.text
            m = re.search(r'"create_time"\s*:\s*(\d{10,13})', text)
            if m:
                ts = int(m.group(1))
                if ts > 1_000_000_000_000:
                    ts = ts // 1000
                print(f"  成功提取: {ts} -> {ts_to_bj_str(ts)}")
                return ts
    except Exception as e:
        print(f"  失败: {e}")
    return 0


async def main():
    aweme_ids = [
        "7654802871703547045",  # 福总最新的
        "7648873308021157989",
        "7648039399406775673",
    ]

    videos = []
    for aid in aweme_ids:
        video = {
            'aweme_id': aid,
            'title': '测试视频',
            'url': f"https://www.douyin.com/video/{aid}",
            'create_time': 0,
        }
        videos.append(video)

    print(f"补全前 create_time: {videos[0]['create_time']}")
    filled = await fill_create_times(videos, max_concurrent=3)
    print(f"补全后:")
    for i, v in enumerate(videos):
        ct = filled[i] if i < len(filled) else 0
        print(f"  {v['aweme_id']}: {ct} -> {ts_to_bj_str(ct)}")


async def fill_create_times(videos: list, max_concurrent: int = 5) -> list:
    """并发补全视频 create_time"""
    if not videos:
        return videos
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_one(aweme_id: str) -> int:
        async with semaphore:
            return await fetch_video_create_time(aweme_id)

    async with httpx.AsyncClient(http2=True, follow_redirects=True) as client:
        tasks = [fetch_one(v['aweme_id']) for v in videos]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    filled = []
    for r in results:
        if isinstance(r, Exception):
            print(f"  异常: {r}")
            filled.append(0)
        else:
            filled.append(r)
    return filled


if __name__ == "__main__":
    asyncio.run(main())
