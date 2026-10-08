#!/usr/bin/env python3
"""
Serenity观点抓取 + AI总结
输出JSON供build_briefing.py使用
"""
import json
import os
import re
import ssl
import sys
import urllib.request
from datetime import datetime, timedelta

import env_config  # noqa: F401  注入本机凭证（~/.codex/daily-briefing.env）


def fetch_serenity_data():
    """抓取 serenitysaid.com 全部推文数据"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        'https://serenitysaid.com/',
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )

    with urllib.request.urlopen(req, context=ctx, timeout=20) as response:
        html = response.read().decode('utf-8')

    # 提取 tweets JSON
    pattern = 'tweets\\":['
    idx = html.find(pattern)
    if idx == -1:
        for p in ['tweets":', '"tweets":']:
            idx = html.find(p)
            if idx != -1:
                pattern = p
                break

    if idx == -1:
        raise ValueError("未找到tweets数据")

    array_start = idx + len(pattern) - 1
    depth = 0
    in_string = False
    end = array_start

    for i, c in enumerate(html[array_start:], start=array_start):
        if c == '[' and not in_string:
            depth += 1
        elif c == ']' and not in_string:
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        elif c == '"' and (i == 0 or html[i-1] != '\\'):
            in_string = not in_string

    json_str = html[array_start:end]
    json_str = json_str.replace('\\"', '"').replace('\\\\', '\\')

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        import codecs
        json_str = codecs.decode(json_str, 'unicode_escape')
        data = json.loads(json_str)

    return data


def get_target_date():
    """获取目标日期（支持--date参数；Serenity专项严格按目标日）"""
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            raw = sys.argv[idx + 1]
        else:
            raw = datetime.now().strftime("%Y-%m-%d")
    else:
        raw = datetime.now().strftime("%Y-%m-%d")

    datetime.strptime(raw, "%Y-%m-%d")
    return raw, raw


def ai_summarize(content: str, symbols: list, tweet_id: str) -> dict:
    """用DeepSeek API总结Serenity推文观点"""
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    if not deepseek_key:
        return {"summary": "", "direction": "", "error": "no_api_key"}

    import urllib.request

    symbols_str = ", ".join(symbols) if symbols else "未提及具体标的"
    prompt = f"""你是一位资深美股/A股投研分析师，正在阅读Serenity(@aleabitoreddit)的推文。

推文内容：
{content[:2000]}

已提取标的：{symbols_str}

【严格输出规则】
1. 用一句话总结Serenity的核心观点（40字以内）
2. 必须明确方向：看多/看空/中性/观察
3. 必须包含具体标的和逻辑（为什么看多/看空）
4. 禁止输出："市场情绪谨慎"、"资金态度分化"、"维持震荡"、"需观察"等泛泛之词
5. 禁止输出："中长期看好"、"短期波动"、"结构性机会"等空洞短语
6. 格式：【方向】标的 + 具体逻辑 + 时间节点/触发条件

输出示例：
看空【英伟达】AI芯片需求增速放缓，Q3指引不及预期，目标价下调至100美元
看多【特斯拉】FSD V12北美全面推送，Robotaxi即将发布，短期催化密集

请严格按上述格式输出："""

    payload = {
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": "你是专业投研分析师，擅长提取推文中可执行的投资观点。输出必须具体、 actionable，禁止泛泛而谈。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 200
    }

    req = urllib.request.Request(
        f"{os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {deepseek_key}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            summary = result["choices"][0]["message"]["content"].strip()

            # 提取方向
            direction = "中性"
            if "看多" in summary or "看涨" in summary or "买入" in summary:
                direction = "看多"
            elif "看空" in summary or "看跌" in summary or "卖出" in summary:
                direction = "看空"
            elif "观察" in summary or "等待" in summary:
                direction = "观察"

            return {"summary": summary, "direction": direction}
    except Exception as e:
        print(f"  [WARN] Serenity AI总结失败 ({tweet_id}): {e}", file=sys.stderr)
        return {"summary": "", "direction": "", "error": str(e)}


def main():
    target_date, raw_date = get_target_date()
    print(f"Serenity抓取: 目标日期={target_date} (原始={raw_date})", file=sys.stderr)

    try:
        all_tweets = fetch_serenity_data()
    except Exception as e:
        print(f"  [ERROR] Serenity抓取失败: {e}", file=sys.stderr)
        print(json.dumps({
            "date": target_date,
            "raw_date": raw_date,
            "data_date": "",
            "opinions": [],
            "status": "error",
            "source": "serenitysaid.com",
            "error": str(e),
            "note": "Serenity抓取失败；未使用旧帖补齐"
        }, ensure_ascii=False))
        return

    # 只过滤目标日期（当天）推文，不回退历史；异常响应不应被当作空列表吞掉。
    if not isinstance(all_tweets, list):
        message = "Serenity返回的数据结构异常"
        print(f"  [ERROR] {message}", file=sys.stderr)
        print(json.dumps({
            "date": target_date,
            "raw_date": raw_date,
            "data_date": "",
            "opinions": [],
            "status": "error",
            "source": "serenitysaid.com",
            "error": message,
            "note": "Serenity返回结构异常；未使用旧帖补齐"
        }, ensure_ascii=False))
        return
    today_tweets = [
        t for t in all_tweets
        if isinstance(t, dict) and str(t.get("created_at", "")).startswith(target_date)
    ]

    if not today_tweets:
        print(f"  [INFO] Serenity {target_date}无推文（博主当天未更新）", file=sys.stderr)

    opinions = []
    for t in today_tweets:
        content = t.get("content", "")
        symbols = t.get("symbols", [])
        tweet_id = str(t.get("id", ""))
        likes = t.get("likes", 0)

        # 优先使用已有的ai_summary
        ai_summary = t.get("ai_summary", "")
        ai_direction = t.get("ai_direction", "")

        if not ai_summary and content:
            # 调用AI总结
            result = ai_summarize(content, symbols, tweet_id)
            ai_summary = result.get("summary", "")
            ai_direction = result.get("direction", ai_direction)

        # 从总结中提取标的
        extracted_symbols = re.findall(r'【([^】]+)】', ai_summary)
        all_symbols = list(dict.fromkeys(symbols + extracted_symbols))[:4]

        if ai_summary:
            opinions.append({
                "id": tweet_id,
                "content_preview": content[:100] if content else "",
                "summary": ai_summary,
                "direction": ai_direction,
                "symbols": all_symbols,
                "likes": likes,
                "created_at": t.get("created_at", ""),
            })

    # 按likes排序，取前5条
    opinions.sort(key=lambda x: x["likes"], reverse=True)
    opinions = opinions[:5]

    result = {
        "date": target_date,
        "raw_date": raw_date,
        "data_date": target_date if today_tweets else "",
        "total_tweets": len(today_tweets),
        "opinions": opinions,
        "has_data": len(opinions) > 0,
        "status": "ok" if opinions else "empty",
        "source": "serenitysaid.com",
        "note": (
            f"{target_date}暂无公开推文；严格按目标日过滤，未使用旧帖"
            if not today_tweets else
            (f"{target_date}有{len(today_tweets)}条公开推文，但暂无有效AI观点；未展示原文"
             if not opinions else "仅展示目标日公开推文的AI语义摘要")
        ),
    }

    print(json.dumps(result, ensure_ascii=False))
    print(f"  [OK] Serenity: {len(opinions)}条观点", file=sys.stderr)


if __name__ == "__main__":
    main()
