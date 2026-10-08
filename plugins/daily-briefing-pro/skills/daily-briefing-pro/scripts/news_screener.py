#!/usr/bin/env python3
"""
News Screener API — 新闻抓取筛选功能 API 接口

提供标准的 REST-like 调用接口：
  python main.py health              # 健康检查
  python main.py tasks               # 获取搜索任务清单
  python main.py stocks              # 获取自选股列表
  python main.py stocks --codes      # 仅输出代码列表
  python main.py stocks --full-codes # 输出完整代码列表
  python main.py summary             # 输出完整摘要（含任务+股票+使用说明）

输出格式：JSON（可通过 --format text 切换为纯文本）
"""

import json
import os
import sys
import argparse
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from parse_selfstock import parse_selfstock, get_selfstock_codes, get_selfstock_fullcodes


def get_today_str():
    """获取今天的日期字符串"""
    return datetime.now().strftime("%Y-%m-%d")


def build_finance_news_queries():
    """构建财经科技新闻搜索查询列表"""
    return [
        {"type": "财联社", "query": "财联社快讯 加红 重要新闻 今天", "priority": 1},
        {"type": "财联社", "query": "财联社 电报 加红 重大新闻 今日", "priority": 1},
        {"type": "财联社", "query": "财联社 快讯 红色标记 重要 今日", "priority": 1},
        {"type": "国内", "query": "财经新闻 科技新闻 A股 最新 今天", "priority": 2},
        {"type": "国内", "query": "国内财经要闻 科技 产业 最新动态", "priority": 2},
        {"type": "国内", "query": "中国 金融 科技 头条新闻 今日", "priority": 2},
        {"type": "国际", "query": "global finance news today tech stocks market", "priority": 3},
        {"type": "国际", "query": "Wall Street tech AI semiconductor latest news", "priority": 3},
        {"type": "国际", "query": "international finance technology breaking news", "priority": 3},
    ]


def build_selfstock_queries(stocks, max_batch=20):
    """构建自选股搜索查询列表"""
    codes = [s["code"] for s in stocks]
    if not codes:
        return []

    queries = []

    for i in range(0, len(codes), max_batch):
        batch = codes[i:i + max_batch]
        batch_str = " ".join(batch)
        queries.append({
            "type": "自选股新闻",
            "query": f"{batch_str} 新闻 公告 今日",
            "codes": batch,
            "priority": 1,
        })

    important = codes[:10]
    if important:
        imp_str = " ".join(important)
        queries.append({
            "type": "重点股公告",
            "query": f"{imp_str} 重大公告 利好 利空",
            "codes": important,
            "priority": 1,
        })

    for i in range(0, min(len(codes), 20), max_batch):
        batch = codes[i:i + max_batch]
        batch_str = " ".join(batch)
        queries.append({
            "type": "龙虎榜",
            "query": f"龙虎榜 今日 {batch_str}",
            "codes": batch,
            "priority": 2,
        })

    queries.append({
        "type": "龙虎榜汇总",
        "query": "东方财富 龙虎榜 最新",
        "codes": [],
        "priority": 2,
    })

    return queries


def cmd_health(_args=None):
    """健康检查 API: health"""
    result = {
        "status": "ok",
        "service": "daily-briefing-news-filter",
        "version": "2.0.0",
        "timestamp": get_today_str(),
        "dependencies": {
            "parse_selfstock": "ok" if os.path.exists(os.path.join(SCRIPT_DIR, "parse_selfstock.py")) else "missing",
            "web_search": "available",
        }
    }
    return result


def cmd_tasks(_args=None):
    """任务清单 API: tasks"""
    self_stocks = parse_selfstock()
    finance_queries = build_finance_news_queries()
    selfstock_queries = build_selfstock_queries(self_stocks) if self_stocks else []

    return {
        "date": get_today_str(),
        "selfstock_count": len(self_stocks),
        "selfstock_codes_preview": [s["code"] for s in self_stocks[:5]],
        "tasks": {
            "finance_news": {
                "description": "国内国际财经+科技新闻（≤15条）",
                "query_count": len(finance_queries),
                "queries": finance_queries,
            },
            "selfstock_news": {
                "description": "自选股新闻/公告/龙虎榜（≤15条）",
                "query_count": len(selfstock_queries),
                "queries": selfstock_queries,
            },
        },
        "total_queries": len(finance_queries) + len(selfstock_queries),
    }


def cmd_stocks(args):
    """自选股列表 API: stocks"""
    self_stocks = parse_selfstock()

    if getattr(args, 'codes', False):
        return {"codes": get_selfstock_codes()}
    elif getattr(args, 'full_codes', False):
        return {"full_codes": get_selfstock_fullcodes()}
    else:
        return {
            "count": len(self_stocks),
            "stocks": self_stocks,
            "source_file": "C:\\应用\\同花顺\\mo_4aknfs5zs\\SelfStockInfo.json",
        }


def cmd_summary(_args=None):
    """完整摘要 API: summary"""
    stocks_result = cmd_stocks(argparse.Namespace(codes=False, full_codes=False))
    tasks_result = cmd_tasks()
    health_result = cmd_health()

    return {
        "health": health_result,
        "stocks": stocks_result,
        "tasks": tasks_result,
        "usage_notes": {
            "finance_news_limit": 15,
            "selfstock_news_limit": 15,
            "batch_size": 20,
            "output_format": "plain_text",
            "priority_order": ["政策/监管", "行业重大", "公司/业绩", "国际", "资金面"],
        }
    }


def main():
    parser = argparse.ArgumentParser(description="News Screener API")
    parser.add_argument("command", choices=["health", "tasks", "stocks", "summary"],
                       help="API command to execute")
    parser.add_argument("--codes", action="store_true", help="仅输出自选股代码列表（stocks命令）")
    parser.add_argument("--full-codes", action="store_true", help="输出完整代码列表（stocks命令）")

    args = parser.parse_args()

    commands = {
        "health": cmd_health,
        "tasks": cmd_tasks,
        "stocks": cmd_stocks,
        "summary": cmd_summary,
    }

    result = commands[args.command](args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
