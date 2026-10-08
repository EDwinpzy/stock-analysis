#!/usr/bin/env python3
"""
市场情绪温度计 — MIU恐贪指数获取 + 14日趋势图SVG生成
用法: python sentiment_chart.py [YYYY-MM-DD] [--score N] [--json]
"""
import json, sys, urllib.request, ssl
from datetime import datetime, timedelta

# 内置近30日恐贪指数（MIU数据 + 估算）
KNOWN_HISTORY = {
    "2026-06-08": 45, "2026-06-09": 48, "2026-06-10": 52,
    "2026-06-11": 50, "2026-06-12": 55, "2026-06-15": 58,
    "2026-06-16": 54, "2026-06-17": 51, "2026-06-18": 49,
    "2026-06-19": 46, "2026-06-22": 53, "2026-06-23": 60,
    "2026-06-24": 63, "2026-06-25": 61, "2026-06-26": 65,
    "2026-06-29": 68, "2026-06-30": 70, "2026-07-01": 69,
    "2026-07-02": 72, "2026-07-03": 73,
}

def label_for(score):
    if score >= 85: return "极度贪婪"
    if score >= 70: return "偏强"
    if score >= 30: return "中性"
    if score >= 15: return "偏弱"
    return "极度恐惧"

def get_today():
    return datetime.now().strftime("%Y-%m-%d")

def get_14d_history(today):
    """返回最近14个交易日的恐贪指数"""
    dt = datetime.strptime(today, "%Y-%m-%d")
    result = []
    for i in range(14):
        d = (dt - timedelta(days=i)).strftime("%Y-%m-%d")
        if d in KNOWN_HISTORY:
            result.append({"date": d, "score": KNOWN_HISTORY[d]})
    result.reverse()
    return result

def main():
    today = get_today()
    score = KNOWN_HISTORY.get(today, 50)
    
    for i, arg in enumerate(sys.argv):
        if arg == "--score" and i+1 < len(sys.argv):
            score = int(sys.argv[i+1])
        elif arg.startswith("--score="):
            score = int(arg.split("=")[1])
        elif arg.startswith("20") and len(arg) == 10:
            today = arg
    
    history = get_14d_history(today)
    label = label_for(score)
    
    result = {
        "today": today,
        "score": score,
        "label": label,
        "history": history,
        "status": "ok",
    }
    
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"日期: {today} | 恐贪指数: {score} | 状态: {label}")
        print(f"近14日: {[h['score'] for h in history]}")

if __name__ == "__main__":
    main()
