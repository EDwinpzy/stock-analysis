#!/usr/bin/env python3
"""
个股深度分析 - 数据采集脚本
基于 thsdk 一次性获取全部分析所需数据，输出 JSON

用法: python fetch_stock_data.py <股票名称或代码>
示例: python fetch_stock_data.py 梦百合
      python fetch_stock_data.py 603313
"""

import sys
import json
import time
import traceback
import io
import os
import re
from datetime import datetime

# 强制stdout为UTF-8，避免Windows编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ─── 动态年份推导 ───
_now = datetime.now()
_CUR_YEAR = _now.year
_PREV_YEAR = _CUR_YEAR - 1
_PREV2_YEAR = _CUR_YEAR - 2
_PREV3_YEAR = _CUR_YEAR - 3
# 最近4个年报年份（当年年报可能未出，取前4年确保至少3年有数据）
_ANNUAL_YEARS = [_PREV3_YEAR, _PREV2_YEAR, _PREV_YEAR, _CUR_YEAR]
# 最近一季年份（当年Q1或去年Q4）
_Q_YEAR = _CUR_YEAR if _now.month >= 5 else _PREV_YEAR  # 5月起Q1报告基本披露完毕

# wencai查询间限流间隔（秒）
_API_DELAY = 0.5

# 大单方向码映射
_BIG_ORDER_DIR_MAP = {
    "1": "大单买入", "-1": "大单卖出",
    "2": "中单买入", "-2": "中单卖出",
    "3": "小单买入", "-3": "小单卖出",
    "4": "特大单买入", "-4": "特大单卖出",
}


def resolve_code(ths, name_or_code):
    """解析股票名称/代码为THSCODE"""
    code_str = str(name_or_code).strip()
    if code_str.isdigit() and len(code_str) == 6:
        if code_str.startswith("6"):
            prefix = "USHA"
        elif code_str.startswith("9"):
            prefix = "USTM"
        elif code_str.startswith("43") or code_str.startswith("87"):
            prefix = "USTA"
        elif code_str.startswith("83") or code_str.startswith("82"):
            # 82xxxx/83xxxx 绝大部分为新三板，少数为北交所
            # 北交所920xxx已单独处理，83/82开头优先按新三板处理
            # thsdk会根据实际市场返回正确数据
            prefix = "USTA"
        elif code_str.startswith("8"):
            # 80/81/84-89xxxx 其他8开头
            prefix = "USTM"
        else:
            # 00xxxx/30xxxx 深市
            prefix = "USZA"
        return f"{prefix}{code_str}", code_str, name_or_code
    
    # 名称搜索
    resp = ths.search_symbols(code_str)
    df = resp.df
    if df is None or len(df) == 0:
        return None, None, code_str
    
    # 优先选A股
    a_stocks = df[df['MarketDisplay'].str.contains('沪A|深A|北A', na=False)]
    if len(a_stocks) > 0:
        row = a_stocks.iloc[0]
    else:
        row = df.iloc[0]
    
    thscode = row['THSCODE']
    pure_code = row['Code']
    name = row['Name']
    return thscode, pure_code, name


def _extract_industry(finance_raw):
    """从财务原始数据中提取行业分类"""
    if not isinstance(finance_raw, dict) or "error" in finance_raw:
        return "暂无"
    for key in finance_raw:
        if "行业" in key and "所属" in key:
            return finance_raw[key]
    for key in finance_raw:
        if "行业" in key:
            return finance_raw[key]
    return "暂无"


def _build_search_keywords(stock_name, pure_code, industry):
    """构建博主观点搜索关键词列表"""
    keywords = [stock_name]
    if pure_code and pure_code != "暂无":
        keywords.append(pure_code)
    if industry != "暂无":
        parts = str(industry).split("-")
        if len(parts) >= 2:
            keywords.append(parts[-1])   # 末级分类
            keywords.append(parts[-2])   # 中级分类
    return [kw for kw in keywords if kw and kw != "暂无"]


def _safe_col(raw_dict, col_name, default="暂无"):
    """安全获取原始数据中的列值，NaN返回default"""
    val = raw_dict.get(col_name)
    if val is None:
        return default
    if isinstance(val, float) and val != val:  # NaN
        return default
    return val


def _parse_holders_string(raw_val):
    """将管道分隔的股东字符串解析为列表"""
    if not raw_val or raw_val == "暂无":
        return []
    return [h.strip() for h in str(raw_val).split("||") if h.strip()]


def _timestamp_to_date(ts_str):
    """将unix时间戳字符串转为可读日期"""
    try:
        ts = int(float(ts_str))
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError, OSError):
        return ts_str


def _map_big_order_direction(dir_code):
    """将大单方向码映射为中文"""
    return _BIG_ORDER_DIR_MAP.get(str(dir_code), str(dir_code))


def _search_blogger_cache(cache_dir, today_str, search_keywords, platform):
    """从每日缓存的博主数据中筛选提及目标股票的帖子
    
    Args:
        cache_dir: 缓存数据目录路径
        today_str: 今日日期字符串 YYYY-MM-DD
        search_keywords: 搜索关键词列表
        platform: "tgb" 或 "xueqiu"
    
    Returns:
        list: 匹配的博主观点列表
    """
    mentions = []
    
    if platform == "tgb":
        cache_file = os.path.join(cache_dir, f"tgb_posts_{today_str}.json")
        if not os.path.exists(cache_file):
            print(f"  淘股吧: 未找到今日缓存数据 ({cache_file})", file=sys.stderr)
            return mentions
        
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for blogger_name, blogger_data in data.get("bloggers", {}).items():
            # 搜索主帖
            for post in blogger_data.get("posts", []):
                text = (post.get("title", "") + " " + post.get("content", "")).lower()
                if any(kw.lower() in text for kw in search_keywords):
                    mentions.append({
                        "platform": "淘股吧",
                        "blogger": blogger_name,
                        "type": "主帖",
                        "title": post.get("title", "")[:100],
                        "content": post.get("content", "")[:300],
                        "likes": post.get("likes", 0),
                        "url": post.get("url", ""),
                    })
            # 搜索跟帖
            for reply in blogger_data.get("replies", []):
                text = (reply.get("content", "") + " " + reply.get("from_title", "")).lower()
                if any(kw.lower() in text for kw in search_keywords):
                    mentions.append({
                        "platform": "淘股吧",
                        "blogger": blogger_name,
                        "type": "跟帖",
                        "title": reply.get("from_title", "")[:100],
                        "content": reply.get("content", "")[:300],
                        "likes": reply.get("likes", 0),
                        "url": "",
                    })
    
    elif platform == "xueqiu":
        cache_file = os.path.join(cache_dir, f"xueqiu_posts_{today_str}.json")
        if not os.path.exists(cache_file):
            print(f"  雪球: 未找到今日缓存数据 ({cache_file})", file=sys.stderr)
            return mentions
        
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 雪球数据可能是列表或字典
        items = data if isinstance(data, list) else data.get("posts", [])
        for item in items:
            if not isinstance(item, dict):
                continue
            text = (item.get("text", "") + " " + item.get("title", "") + " " + item.get("content", "")).lower()
            blogger = item.get("blogger", item.get("user", item.get("name", "未知")))
            if any(kw.lower() in text for kw in search_keywords):
                mentions.append({
                    "platform": "雪球",
                    "blogger": blogger,
                    "type": item.get("type", "帖子"),
                    "title": item.get("title", "")[:100],
                    "content": item.get("text", item.get("content", ""))[:300],
                    "likes": item.get("likes", item.get("retweet_count", 0)),
                    "url": item.get("url", item.get("target", "")),
                })
    
    mentions.sort(key=lambda x: x.get("likes", 0), reverse=True)
    return mentions[:20]


def _search_tgb_direct(stock_name, pure_code, search_keywords):
    """直接调用淘股吧爬虫脚本获取博主观点（回退方案）
    
    当没有每日缓存数据时，尝试运行 tgb_crawl.py 获取当天数据
    """
    mentions = []
    skill_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    tgb_script = os.path.join(skill_root, "scripts", "tgb_crawl.py")
    
    if not os.path.exists(tgb_script):
        print(f"  淘股吧爬虫脚本不存在: {tgb_script}", file=sys.stderr)
        return mentions
    
    print(f"  尝试直接运行淘股吧爬虫...", file=sys.stderr)
    try:
        import subprocess
        proc = subprocess.run(
            [sys.executable, tgb_script],
            capture_output=True, text=True, timeout=60, encoding='utf-8'
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            for blogger_name, blogger_data in data.get("bloggers", {}).items():
                for post in blogger_data.get("posts", []):
                    text = (post.get("title", "")).lower()
                    if any(kw.lower() in text for kw in search_keywords):
                        mentions.append({
                            "platform": "淘股吧",
                            "blogger": blogger_name,
                            "type": "主帖",
                            "title": post.get("title", "")[:100],
                            "content": "",
                            "likes": 0,
                            "url": post.get("url", ""),
                        })
                for reply in blogger_data.get("top_replies", []):
                    text = reply.get("content", "").lower()
                    if any(kw.lower() in text for kw in search_keywords):
                        mentions.append({
                            "platform": "淘股吧",
                            "blogger": blogger_name,
                            "type": "跟帖",
                            "title": "",
                            "content": reply.get("content", "")[:300],
                            "likes": reply.get("likes", 0),
                            "url": "",
                        })
            mentions.sort(key=lambda x: x.get("likes", 0), reverse=True)
            print(f"  淘股吧直接爬取: 找到 {len(mentions)} 条提及", file=sys.stderr)
        else:
            print(f"  淘股吧爬虫执行失败: {proc.stderr[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"  淘股吧直接爬取异常: {e}", file=sys.stderr)
    
    return mentions[:20]


def _search_serenity(search_keywords, stock_name):
    """从Serenity观点数据中搜索AI半导体相关标的提及（回退方案）"""
    mentions = []
    skill_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    serenity_script = os.path.join(skill_root, "scripts", "serenity_crawler.py")
    
    if not os.path.exists(serenity_script):
        return mentions
    
    print(f"  尝试搜索Serenity观点...", file=sys.stderr)
    try:
        # 导入serenity_crawler的fetch函数
        import importlib.util
        spec = importlib.util.spec_from_file_location("serenity_crawler", serenity_script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        
        if hasattr(mod, 'fetch_serenity_data'):
            tweets = mod.fetch_serenity_data()
            today_str = datetime.now().strftime('%Y-%m-%d')
            for t in tweets:
                # 检查是否为今天的推文
                created = t.get("created_at", "")
                if today_str not in str(created):
                    continue
                text = (t.get("content", "") + " " + t.get("ai_summary", "")).lower()
                symbols = t.get("symbols", [])
                # 检查关键词或A股对应的美股标的
                if any(kw.lower() in text for kw in search_keywords):
                    mentions.append({
                        "platform": "Serenity(X)",
                        "blogger": "Serenity",
                        "type": "推文",
                        "title": t.get("ai_direction", "")[:100],
                        "content": t.get("ai_summary", "")[:300],
                        "likes": t.get("likes", 0),
                        "url": f"https://x.com/aleabitoreddit/status/{t.get('tweet_id', '')}",
                        "direction": t.get("ai_direction", ""),
                        "symbols": symbols,
                    })
            if mentions:
                print(f"  Serenity: 找到 {len(mentions)} 条提及", file=sys.stderr)
    except Exception as e:
        print(f"  Serenity搜索异常: {e}", file=sys.stderr)
    
    return mentions[:10]


def _fetch_research_reports(stock_name, pure_code, search_keywords):
    """获取机构研报观点（东方财富 + 研报客双源）
    
    从两个API获取研报数据，按股票名称/代码/行业关键词过滤，
    返回与该股票相关的研报列表。
    
    Args:
        stock_name: 股票名称（如"科瑞技术"）
        pure_code: 股票代码（如"002957"）
        search_keywords: 搜索关键词列表（含股票名、代码、行业末级分类）
    
    Returns:
        dict: {"reports": [...], "summary": {"total": N, "sources": [...]}}
    """
    import urllib.request
    import urllib.parse
    import ssl
    
    result = {"reports": [], "summary": {"total": 0, "sources": []}}
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_compact = today_str.replace('-', '')
    sources_found = []
    all_reports = []
    
    # ─── 源1: 东方财富研报API ───
    print(f"  东方财富研报...", file=sys.stderr)
    try:
        # 先用股票代码精确查询
        em_params = {
            'cb': 'datatable',
            'pageNo': '1',
            'pageSize': '50',
            'code': pure_code or '',
            'industryCode': '*',
            'qType': '0',
            'beginTime': today_compact,
            'endTime': today_compact,
            'lastUpdateTime': ''
        }
        em_url = f"https://reportapi.eastmoney.com/report/list?{urllib.parse.urlencode(em_params)}"
        em_req = urllib.request.Request(
            em_url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
                'Referer': 'https://data.eastmoney.com/report/'
            }
        )
        
        with urllib.request.urlopen(em_req, context=ctx, timeout=15) as response:
            text = response.read().decode('utf-8')
            start = text.find('(')
            end = text.rfind(')')
            if start > 0 and end > start:
                json_str = text[start+1:end]
                data = json.loads(json_str)
                if data.get('data'):
                    for item in data['data']:
                        all_reports.append({
                            'source': '东方财富',
                            'title': item.get('title', ''),
                            'org': item.get('orgSName', '') or item.get('orgName', '未知'),
                            'date': str(item.get('publishDate', ''))[:10],
                            'stock': item.get('stockName', ''),
                            'rating': item.get('emRatingName', ''),  # 评级：买入/增持/中性等
                            'target_price': item.get('predictNextTwoYearPe', ''),  # 目标价相关
                            'content': '',
                        })
                    sources_found.append(f"东方财富({len(data['data'])}份)")
                    print(f"    东方财富: {len(data['data'])}份", file=sys.stderr)
        
        # 如果精确查询结果少，扩大到近7天
        if len([r for r in all_reports if r['source'] == '东方财富']) < 3:
            from datetime import timedelta
            for days_back in [3, 7]:
                past_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y%m%d')
                em_params['beginTime'] = past_date
                em_params['code'] = pure_code or ''
                em_url2 = f"https://reportapi.eastmoney.com/report/list?{urllib.parse.urlencode(em_params)}"
                em_req2 = urllib.request.Request(em_url2, headers=em_req.headers)
                try:
                    with urllib.request.urlopen(em_req2, context=ctx, timeout=15) as resp2:
                        text2 = resp2.read().decode('utf-8')
                        s2, e2 = text2.find('('), text2.rfind(')')
                        if s2 > 0 and e2 > s2:
                            data2 = json.loads(text2[s2+1:e2])
                            if data2.get('data'):
                                added = 0
                                for item in data2['data']:
                                    # 去重：按标题前30字符
                                    title_key = item.get('title', '')[:30]
                                    if not any(r['title'][:30] == title_key for r in all_reports):
                                        all_reports.append({
                                            'source': '东方财富',
                                            'title': item.get('title', ''),
                                            'org': item.get('orgSName', '') or item.get('orgName', '未知'),
                                            'date': str(item.get('publishDate', ''))[:10],
                                            'stock': item.get('stockName', ''),
                                            'rating': item.get('emRatingName', ''),
                                            'target_price': item.get('predictNextTwoYearPe', ''),
                                            'content': '',
                                        })
                                        added += 1
                                if added > 0:
                                    print(f"    东方财富(近{days_back}天): +{added}份", file=sys.stderr)
                except Exception:
                    pass
            # 更新source计数
            em_count = len([r for r in all_reports if r['source'] == '东方财富'])
            if em_count > 0:
                sources_found = [s for s in sources_found if not s.startswith('东方财富')]
                sources_found.append(f"东方财富({em_count}份)")
    
    except Exception as e:
        print(f"    东方财富研报失败: {str(e)[:50]}", file=sys.stderr)
    
    # ─── 源2: 研报客API（按股票名称搜索） ───
    print(f"  研报客...", file=sys.stderr)
    try:
        # 用股票名称作为关键词搜索
        search_terms = [stock_name]
        if pure_code:
            search_terms.append(pure_code)
        # 加入行业末级分类关键词（如果有）
        for kw in search_keywords:
            if kw != stock_name and kw != pure_code and len(kw) >= 2:
                search_terms.append(kw)
        
        for kw in search_terms[:3]:  # 最多搜3个关键词，避免API限流
            try:
                yb_params = urllib.parse.urlencode({
                    'keyword': kw,
                    'size': '20',
                    'search_type': 'title',
                    'startdate': today_str,
                    'enddate': today_str,
                })
                yb_url = f'https://api.yanbaoke.cn/skills/search_report?{yb_params}'
                yb_req = urllib.request.Request(
                    yb_url,
                    headers={
                        'User-Agent': 'Mozilla/5.0',
                        'X-Skill-Version': '2.1.0',
                        'X-Skill-ID': 'yanbaoke-research-report-download'
                    }
                )
                
                with urllib.request.urlopen(yb_req, context=ctx, timeout=15) as yb_resp:
                    yb_data = json.loads(yb_resp.read().decode('utf-8'))
                    
                    if yb_data.get('success') and yb_data.get('data'):
                        added = 0
                        for item in yb_data['data']:
                            title_key = item.get('title', '')[:30]
                            # 去重
                            if any(r['title'][:30] == title_key for r in all_reports):
                                continue
                            # 提取机构名
                            org = item.get('org_name', '')
                            if not org:
                                title = item.get('title', '')
                                for known_org in ['海通国际', '中国银河', '浙商证券', '华泰证券', 
                                                  '中金公司', '东吴证券', '开源证券', '中信证券', 
                                                  '国泰君安', '招商证券', '广发证券', '兴业证券',
                                                  '天风证券', '长江证券', '安信证券', '国盛证券']:
                                    if known_org in title:
                                        org = known_org
                                        break
                            if not org:
                                org = '研报'
                            
                            all_reports.append({
                                'source': '研报客',
                                'title': item.get('title', ''),
                                'org': org,
                                'date': item.get('time', today_str),
                                'stock': item.get('stock_name', ''),
                                'rating': '',
                                'target_price': '',
                                'content': item.get('content', '')[:200],
                            })
                            added += 1
                        if added > 0:
                            print(f"    研报客[{kw}]: +{added}份", file=sys.stderr)
                
                time.sleep(0.3)  # 避免限流
                
            except Exception as e:
                print(f"    研报客[{kw}]失败: {str(e)[:30]}", file=sys.stderr)
        
        yb_count = len([r for r in all_reports if r['source'] == '研报客'])
        if yb_count > 0:
            sources_found.append(f"研报客({yb_count}份)")
    
    except Exception as e:
        print(f"    研报客整体失败: {str(e)[:50]}", file=sys.stderr)
    
    # ─── 过滤：只保留与目标股票相关的研报 ───
    stock_related = []
    other_reports = []
    
    for r in all_reports:
        text = (r.get('title', '') + ' ' + r.get('stock', '') + ' ' + r.get('content', '')).lower()
        # 精确匹配：股票名称或代码出现在标题/股票字段
        is_related = False
        if stock_name and stock_name.lower() in text:
            is_related = True
        if pure_code and pure_code in text:
            is_related = True
        if r.get('stock', '') and stock_name and stock_name in r.get('stock', ''):
            is_related = True
        
        if is_related:
            stock_related.append(r)
        else:
            other_reports.append(r)
    
    # 相关研报全部保留，其他研报按相关性排序保留前10条（行业相关）
    # 对other_reports做行业关键词匹配
    industry_related = []
    for r in other_reports:
        text = (r.get('title', '') + ' ' + r.get('content', '')).lower()
        for kw in search_keywords:
            if kw.lower() in text and kw != stock_name and kw != pure_code:
                industry_related.append(r)
                break
    
    final_reports = stock_related + industry_related[:10]
    
    # 按日期倒序排列
    final_reports.sort(key=lambda x: x.get('date', ''), reverse=True)
    
    result['reports'] = final_reports[:20]  # 最多20条
    result['summary']['total'] = len(final_reports)
    result['summary']['stock_related'] = len(stock_related)
    result['summary']['industry_related'] = len(industry_related[:10])
    result['summary']['sources'] = sources_found
    
    print(f"  研报汇总: 相关{len(stock_related)}份 + 行业{len(industry_related[:10])}份 (来源: {', '.join(sources_found) or '无'})", file=sys.stderr)
    
    return result


def fetch_all_data(ths, thscode, pure_code, stock_name):
    """一次性获取全部数据"""
    result = {
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stock_name": stock_name,
        "stock_code": pure_code,
        "thscode": thscode,
    }
    
    # ========== 1. 实时行情 ==========
    print(f"[1/11] 获取实时行情: {thscode}", file=sys.stderr)
    try:
        resp = ths.market_data_cn(thscode, "汇总")
        qdf = resp.df
        if qdf is not None and len(qdf) > 0:
            q = qdf.iloc[0]
            result["quote"] = {
                "price": q.get("价格", "暂无"),
                "change_pct": q.get("涨幅", "暂无"),
                "change_amt": q.get("涨跌", "暂无"),
                "volume": q.get("成交量", "暂无"),
                "amount": q.get("总金额", "暂无"),
                "market_cap": q.get("总市值", "暂无"),
                "circulating_cap": q.get("流通市值", "暂无"),
                "pe_ttm": q.get("市盈率TTM", "暂无"),
                "turnover_rate": q.get("换手率", "暂无"),
                "amplitude": q.get("振幅", "暂无"),
                "main_net_inflow": q.get("主力净流入", "暂无"),
                "main_net_pct": q.get("主力净量", "暂无"),
                "high": q.get("最高价", "暂无"),
                "low": q.get("最低价", "暂无"),
                "open_change": q.get("开盘涨幅", "暂无"),
                "prev_close": q.get("昨收价", "暂无"),
                "limit_up": q.get("涨停价", "暂无"),
                "limit_down": q.get("跌停价", "暂无"),
                "name": q.get("名称", "暂无"),
                "5d_change": q.get("5日涨幅", "暂无"),
            }
        else:
            result["quote"] = {"error": "无行情数据"}
    except Exception as e:
        result["quote"] = {"error": str(e)}
    
    time.sleep(_API_DELAY)
    
    # ========== 2. 财务数据（wencai_nlp 一次查询） ==========
    print(f"[2/11] 获取财务数据: {stock_name}", file=sys.stderr)
    try:
        y = _ANNUAL_YEARS
        finance_query = (
            f'{stock_name}，'
            f'{y[0]}年营业收入，{y[1]}年营业收入，{y[2]}年营业收入，{y[3]}年营业收入，'
            f'{y[0]}年归属于母公司所有者的净利润，{y[1]}年，{y[2]}年，{y[3]}年，'
            f'{y[0]}年扣除非经常性损益后的净利润，{y[1]}年，{y[2]}年，{y[3]}年，'
            f'{y[0]}年净资产收益率ROE，{y[1]}年，{y[2]}年，{y[3]}年，'
            f'{y[0]}年销售毛利率，{y[1]}年，{y[2]}年，{y[3]}年，'
            f'{y[0]}年资产负债率，{y[1]}年，{y[2]}年，{y[3]}年，'
            f'{_PREV_YEAR}年每股净资产，{_PREV_YEAR}年每股经营现金流，'
            f'{_Q_YEAR}年一季度营业收入，{_Q_YEAR}年一季度归属于母公司所有者的净利润，'
            f'{_Q_YEAR}年一季度销售毛利率，{_Q_YEAR}年一季度资产负债率，'
            f'{_Q_YEAR}年一季度每股净资产，{_Q_YEAR}年一季度净资产收益率ROE，'
            f'注册地，实际控制人，控股股东，所属行业，上市时间，'
            f'公司全称，主营业务'
        )
        resp = ths.wencai_nlp(finance_query)
        fdf = resp.df
        if fdf is not None and len(fdf) > 0:
            f = fdf.iloc[0]
            cols = list(fdf.columns)
            result["finance_columns"] = cols
            raw = {}
            for col in cols:
                val = f.get(col)
                if val is not None and not (isinstance(val, float) and val != val):
                    raw[col] = str(val)
                elif col in raw:
                    pass  # 保留已有值
                else:
                    # NaN/None → 标记为"暂无"，但保留key存在（区分"无数据"和"值为0"）
                    raw[col] = "暂无"
            result["finance_raw"] = raw
        else:
            result["finance_raw"] = {}
            result["finance_columns"] = []
    except Exception as e:
        result["finance_raw"] = {"error": str(e)}
        result["finance_columns"] = []
    
    # 提取行业分类（供Step3同业对比和Step9博主观点使用）
    industry = _extract_industry(result.get("finance_raw", {}))
    
    time.sleep(_API_DELAY)
    
    # ========== 3. 同业对比（动态发现同行业公司） ==========
    print(f"[3/11] 获取同业对比数据", file=sys.stderr)
    try:
        if industry != "暂无" and len(str(industry)) > 2:
            industry_parts = str(industry).split("-")
            industry_leaf = industry_parts[-1] if industry_parts else str(industry)
            peer_query = (
                f'{industry_leaf}行业，'
                f'市盈率，总市值，市净率，净资产收益率ROE，'
                f'{_PREV_YEAR}年营业收入，{_PREV_YEAR}年销售毛利率，{_PREV_YEAR}年销售净利率，'
                f'股息率'
            )
            print(f"  行业分类: {industry}，使用末级分类查询同行: {industry_leaf}", file=sys.stderr)
        else:
            # 无行业信息时降级：查询目标股票 + 同概念股
            peer_query = (
                f'{stock_name}，'
                f'市盈率，总市值，市净率，净资产收益率ROE，'
                f'{_PREV_YEAR}年营业收入，{_PREV_YEAR}年销售毛利率，{_PREV_YEAR}年销售净利率，'
                f'股息率'
            )
            print(f"  未获取到行业分类，仅查询目标股票", file=sys.stderr)

        resp = ths.wencai_nlp(peer_query)
        pdf = resp.df
        if pdf is not None and len(pdf) > 0:
            peers = []
            for i in range(len(pdf)):
                row_data = {}
                for col in pdf.columns:
                    val = pdf.iloc[i].get(col)
                    if val is not None and not (isinstance(val, float) and val != val):
                        row_data[col] = str(val)
                peers.append(row_data)
            result["peers_raw"] = peers
            result["peers_columns"] = list(pdf.columns)
        else:
            result["peers_raw"] = []
            result["peers_columns"] = []
    except Exception as e:
        result["peers_raw"] = []
        result["peers_columns"] = []
        print(f"  同业对比异常: {e}", file=sys.stderr)
    
    time.sleep(_API_DELAY)
    
    # ========== 4. 十大流通股东 + 北向资金 ==========
    print(f"[4/11] 获取股东数据", file=sys.stderr)
    try:
        holder_query = (
            f'{stock_name}，'
            f'十大流通股东，北向资金持股比例，'
            f'股东户数变化，机构持股比例'
        )
        resp = ths.wencai_nlp(holder_query)
        hdf = resp.df
        if hdf is not None and len(hdf) > 0:
            raw = {}
            for col in hdf.columns:
                val = hdf.iloc[0].get(col)
                if val is not None and not (isinstance(val, float) and val != val):
                    raw[col] = str(val)
                else:
                    # 保留key存在但标记"暂无"，区分"无数据"和"值为0"
                    raw[col] = "暂无"
            result["holders_raw"] = raw
            result["holders_columns"] = list(hdf.columns)
            
            # 解析管道分隔的股东名字为列表
            for key in list(raw.keys()):
                if "股东" in key and "名称" in key:
                    result["holders_parsed"] = _parse_holders_string(raw[key])
                    break
        else:
            result["holders_raw"] = {}
            result["holders_columns"] = []
            result["holders_parsed"] = []
    except Exception as e:
        result["holders_raw"] = {"error": str(e)}
        result["holders_columns"] = []
        result["holders_parsed"] = []
    
    time.sleep(_API_DELAY)
    
    # ========== 5. 大单流向 ==========
    print(f"[5/11] 获取大单流向", file=sys.stderr)
    try:
        resp = ths.big_order_flow(thscode)
        bdf = resp.df
        if bdf is not None and len(bdf) > 0:
            recent = bdf.tail(10)
            orders = []
            for i in range(len(recent)):
                row_data = {}
                for col in recent.columns:
                    val = recent.iloc[i].get(col)
                    if val is not None and not (isinstance(val, float) and val != val):
                        # 特殊处理：时间戳转换
                        if col in ("时间", "日期", "date", "time"):
                            row_data[col] = _timestamp_to_date(str(val))
                        # 特殊处理：方向码映射
                        elif col in ("方向", "类型", "direction", "type"):
                            row_data[col] = _map_big_order_direction(str(val))
                            row_data[f"{col}_code"] = str(val)  # 保留原始码
                        else:
                            row_data[col] = str(val)
                orders.append(row_data)
            result["big_orders"] = orders
            result["big_orders_columns"] = list(bdf.columns)
            # 附加方向码说明
            result["big_orders_direction_legend"] = _BIG_ORDER_DIR_MAP
        else:
            result["big_orders"] = []
            result["big_orders_columns"] = []
            result["big_orders_direction_legend"] = _BIG_ORDER_DIR_MAP
    except Exception as e:
        result["big_orders"] = []
        result["big_orders_columns"] = []
        result["big_orders_direction_legend"] = _BIG_ORDER_DIR_MAP
        print(f"  大单流向异常: {e}", file=sys.stderr)
    
    time.sleep(_API_DELAY)
    
    # ========== 6. 近期新闻 ==========
    print(f"[6/11] 获取近期新闻", file=sys.stderr)
    try:
        resp = ths.news(thscode)
        ndf = resp.df
        if ndf is not None and len(ndf) > 0:
            recent = ndf.head(15)
            news_list = []
            for i in range(len(recent)):
                row_data = {}
                for col in recent.columns:
                    val = recent.iloc[i].get(col)
                    if val is not None and not (isinstance(val, float) and val != val):
                        row_data[col] = str(val)
                news_list.append(row_data)
            result["news"] = news_list
            result["news_columns"] = list(ndf.columns)
        else:
            result["news"] = []
            result["news_columns"] = []
            print(f"  ths.news返回空，尝试wencai补充", file=sys.stderr)
            # 回退方案：用wencai查询新闻/公告
            try:
                news_resp = ths.wencai_nlp(f'{stock_name} 最新新闻 最新公告')
                if news_resp.df is not None and len(news_resp.df) > 0:
                    news_list = []
                    for i in range(min(len(news_resp.df), 15)):
                        row_data = {}
                        for col in news_resp.df.columns:
                            val = news_resp.df.iloc[i].get(col)
                            if val is not None and not (isinstance(val, float) and val != val):
                                row_data[col] = str(val)
                        news_list.append(row_data)
                    result["news"] = news_list
                    result["news_columns"] = list(news_resp.df.columns)
                    print(f"  wencai新闻回退: 获取到 {len(news_list)} 条", file=sys.stderr)
            except Exception as e2:
                print(f"  wencai新闻回退也失败: {e2}", file=sys.stderr)
    except Exception as e:
        result["news"] = []
        result["news_columns"] = []
        print(f"  近期新闻异常: {e}", file=sys.stderr)
    
    time.sleep(_API_DELAY)
    
    # ========== 7. 产品/业务结构 ==========
    print(f"[7/11] 获取产品业务数据", file=sys.stderr)
    try:
        # 优化查询：分开两个查询提高命中率
        # 查询1：主营构成
        product_query1 = (
            f'{stock_name}，'
            f'主营业务构成，'
            f'产品类型'
        )
        resp1 = ths.wencai_nlp(product_query1)
        raw1 = {}
        cols1 = []
        if resp1.df is not None and len(resp1.df) > 0:
            for col in resp1.df.columns:
                val = resp1.df.iloc[0].get(col)
                if val is not None and not (isinstance(val, float) and val != val):
                    raw1[col] = str(val)
            cols1 = list(resp1.df.columns)
        
        time.sleep(_API_DELAY)
        
        # 查询2：境内外收入
        product_query2 = (
            f'{stock_name}，'
            f'境外收入占比，境内收入占比，'
            f'{_PREV_YEAR}年境外营业收入，{_PREV_YEAR}年境内营业收入'
        )
        resp2 = ths.wencai_nlp(product_query2)
        raw2 = {}
        cols2 = []
        if resp2.df is not None and len(resp2.df) > 0:
            for col in resp2.df.columns:
                val = resp2.df.iloc[0].get(col)
                if val is not None and not (isinstance(val, float) and val != val):
                    raw2[col] = str(val)
            cols2 = list(resp2.df.columns)
        
        # 合并两次查询结果
        merged = {**raw2, **raw1}  # raw1优先（主营构成更关键）
        result["product_raw"] = merged if merged else {}
        result["product_columns"] = list(set(cols1 + cols2))
    except Exception as e:
        result["product_raw"] = {}
        result["product_columns"] = []
        print(f"  产品业务异常: {e}", file=sys.stderr)
    
    # ========== 8. 筹码结构数据 ==========
    print(f"[8/11] 获取筹码结构数据", file=sys.stderr)
    # 预填充默认值，防止key缺失
    chip_defaults = {
        'holder_count_trend': {},
        'share_structure': {},
        'unlock_data': {},
        'concentration': {},
        'margin': {},
    }
    chip_result = dict(chip_defaults)
    
    try:
        # 8a. 股东户数历史趋势
        holder_periods = []
        for y in _ANNUAL_YEARS:
            holder_periods.append(f"股东户数[{y}1231]")
            if y < _CUR_YEAR:
                holder_periods.append(f"股东户数[{y}0630]")
        if _now.month >= 5:
            holder_periods.append(f"股东户数[{_CUR_YEAR}0331]")
        
        time.sleep(_API_DELAY)
        resp = ths.wencai_nlp(f'{stock_name} {" ".join(holder_periods)}')
        if resp.df is not None and len(resp.df) > 0:
            trend = {}
            for col in resp.df.columns:
                val = resp.df.iloc[0].get(col)
                if val is not None and not (isinstance(val, float) and val != val):
                    trend[col] = str(val)
            chip_result['holder_count_trend'] = trend if trend else {}
        
        # 8b. 股本结构
        time.sleep(_API_DELAY)
        resp = ths.wencai_nlp(f'{stock_name} 总股本 流通a股 限售a股')
        if resp.df is not None and len(resp.df) > 0:
            structure = {}
            for col in resp.df.columns:
                val = resp.df.iloc[0].get(col)
                if val is not None and not (isinstance(val, float) and val != val):
                    structure[col] = str(val)
            chip_result['share_structure'] = structure if structure else {}
        
        # 8c. 解禁数据
        time.sleep(_API_DELAY)
        resp = ths.wencai_nlp(
            f'{stock_name} 下次解禁日期 下次解禁数量 '
            f'下次解禁股数占流通股比例 下次解禁金额 解禁股类型'
        )
        if resp.df is not None and len(resp.df) > 0:
            unlock = {}
            for col in resp.df.columns:
                val = resp.df.iloc[0].get(col)
                if val is not None and not (isinstance(val, float) and val != val):
                    unlock[col] = str(val)
            chip_result['unlock_data'] = unlock if unlock else {}
        
        # 8d. 持股集中度
        time.sleep(_API_DELAY)
        resp = ths.wencai_nlp(
            f'{stock_name} 前十大股东持股比例合计 '
            f'第一大股东持股比例 第一大股东名称 '
            f'户均持股数量 户均持股市值'
        )
        if resp.df is not None and len(resp.df) > 0:
            concentration = {}
            for col in resp.df.columns:
                val = resp.df.iloc[0].get(col)
                if val is not None and not (isinstance(val, float) and val != val):
                    concentration[col] = str(val)
            chip_result['concentration'] = concentration if concentration else {}
        
        # 8e. 融资余额
        time.sleep(_API_DELAY)
        resp = ths.wencai_nlp(f'{stock_name} 融资余额 融资余额占流通市值比')
        if resp.df is not None and len(resp.df) > 0:
            margin = {}
            for col in resp.df.columns:
                val = resp.df.iloc[0].get(col)
                if val is not None and not (isinstance(val, float) and val != val):
                    margin[col] = str(val)
            chip_result['margin'] = margin if margin else {}
        
    except Exception as e:
        chip_result['error'] = str(e)
    
    result['chip_structure'] = chip_result
    
    # ========== 9. 博主观点（多数据源 + 多回退） ==========
    print(f"[9/11] 获取博主观点数据", file=sys.stderr)
    blogger_result = {
        "tgb": [], "xueqiu": [], "serenity": [],
        "summary": {"total_mentions": 0, "sources": []}
    }
    try:
        search_keywords = _build_search_keywords(stock_name, pure_code, industry)
        today_str = datetime.now().strftime('%Y-%m-%d')
        sources_found = []
        
        # 9a. 淘股吧 — 优先从缓存读取，缓存不存在则直接爬取
        # 缓存目录1：统一简报目录下的市场情绪调查数据
        cache_dirs = [
            os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")), "data"),
        ]
        
        tgb_mentions = []
        for cache_dir in cache_dirs:
            if os.path.isdir(cache_dir):
                tgb_mentions = _search_blogger_cache(cache_dir, today_str, search_keywords, "tgb")
                if tgb_mentions:
                    sources_found.append(f"淘股吧缓存({os.path.basename(cache_dir)})")
                    break
        
        if not tgb_mentions:
            # 回退：直接调用淘股吧爬虫
            tgb_mentions = _search_tgb_direct(stock_name, pure_code, search_keywords)
            if tgb_mentions:
                sources_found.append("淘股吧直接爬取")
        
        blogger_result["tgb"] = tgb_mentions
        
        # 9b. 雪球 — 从缓存读取
        xq_mentions = []
        for cache_dir in cache_dirs:
            if os.path.isdir(cache_dir):
                xq_mentions = _search_blogger_cache(cache_dir, today_str, search_keywords, "xueqiu")
                if xq_mentions:
                    sources_found.append(f"雪球缓存({os.path.basename(cache_dir)})")
                    break
        
        blogger_result["xueqiu"] = xq_mentions
        
        # 9c. Serenity观点（AI半导体领域，补充美股视角）
        serenity_mentions = _search_serenity(search_keywords, stock_name)
        if serenity_mentions:
            blogger_result["serenity"] = serenity_mentions
            sources_found.append("Serenity(X)")
        
        # 9d. 汇总
        total = len(tgb_mentions) + len(xq_mentions) + len(serenity_mentions)
        blogger_result["summary"]["total_mentions"] = total
        blogger_result["summary"]["sources"] = sources_found
        
        if total == 0:
            print(f"  博主观点: 今日暂无博主提及该股（搜索词: {search_keywords}）", file=sys.stderr)
        else:
            print(f"  博主观点: 共 {total} 条提及（来源: {', '.join(sources_found)}）", file=sys.stderr)
        
    except Exception as e:
        blogger_result["error"] = str(e)
        print(f"  博主观点采集异常: {e}", file=sys.stderr)
    
    result['blogger_opinions'] = blogger_result
    
    # ========== 10. 壁垒数据（研发专利 + 市场地位） ==========
    print(f"[10/11] 获取壁垒相关数据", file=sys.stderr)
    barrier_result = {"rd_raw": {}, "market_position_raw": {}}
    try:
        # 10a. 研发+专利数据
        time.sleep(_API_DELAY)
        rd_query = (
            f'{stock_name}，'
            f'研发费用，研发费用占营业收入比，'
            f'专利数量，发明专利数量，实用新型专利数量，'
            f'{_PREV_YEAR}年研发费用，{_PREV_YEAR}年研发费用占营业收入比'
        )
        resp = ths.wencai_nlp(rd_query)
        if resp.df is not None and len(resp.df) > 0:
            rd_raw = {}
            for col in resp.df.columns:
                val = resp.df.iloc[0].get(col)
                if val is not None and not (isinstance(val, float) and val != val):
                    rd_raw[col] = str(val)
                else:
                    rd_raw[col] = "暂无"
            barrier_result["rd_raw"] = rd_raw
        else:
            print(f"  研发专利数据: wencai返回空", file=sys.stderr)
        
        # 10b. 市场地位+客户集中度
        time.sleep(_API_DELAY)
        market_query = (
            f'{stock_name}，'
            f'市场占有率，前五大客户收入占比，供应商集中度，'
            f'品牌价值，特许经营权，'
            f'{_PREV_YEAR}年前五大客户合计收入占比'
        )
        resp = ths.wencai_nlp(market_query)
        if resp.df is not None and len(resp.df) > 0:
            market_raw = {}
            for col in resp.df.columns:
                val = resp.df.iloc[0].get(col)
                if val is not None and not (isinstance(val, float) and val != val):
                    market_raw[col] = str(val)
                else:
                    market_raw[col] = "暂无"
            barrier_result["market_position_raw"] = market_raw
        else:
            print(f"  市场地位数据: wencai返回空", file=sys.stderr)
        
        rd_count = len([k for k in barrier_result["rd_raw"] if k != "暂无"])
        mp_count = len([k for k in barrier_result["market_position_raw"] if k != "暂无"])
        print(f"  壁垒数据: 研发专利{rd_count}项, 市场地位{mp_count}项", file=sys.stderr)
        
    except Exception as e:
        barrier_result["error"] = str(e)
        print(f"  壁垒数据采集异常: {e}", file=sys.stderr)
    
    result['barrier_data'] = barrier_result
    
    # ========== 11. 机构研报观点（东方财富 + 研报客） ==========
    print(f"[11/11] 获取机构研报观点", file=sys.stderr)
    try:
        search_keywords = _build_search_keywords(stock_name, pure_code, industry)
        research_result = _fetch_research_reports(stock_name, pure_code, search_keywords)
        result['research_reports'] = research_result
    except Exception as e:
        result['research_reports'] = {
            "reports": [], 
            "summary": {"total": 0, "stock_related": 0, "industry_related": 0, "sources": [], "error": str(e)}
        }
        print(f"  机构研报采集异常: {e}", file=sys.stderr)
    
    return result


def main():
    if len(sys.argv) < 2:
        print("用法: python fetch_stock_data.py <股票名称或代码>", file=sys.stderr)
        sys.exit(1)
    
    stock_input = sys.argv[1]
    start_time = time.time()
    
    # JSON输出文件路径 — 使用股票代码区分，避免旧缓存被误读
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    
    try:
        from thsdk import THS
    except ImportError:
        # thsdk未安装时，输出错误到固定文件
        output_file = os.path.join(scripts_dir, "_fetch_result.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({"error": "thsdk未安装，请运行: pip install thsdk"}, f, ensure_ascii=False)
        print("ERROR: thsdk未安装", file=sys.stderr)
        sys.exit(1)
    
    try:
        with THS() as ths:
            # 解析代码
            print(f"解析股票: {stock_input}", file=sys.stderr)
            thscode, pure_code, stock_name = resolve_code(ths, stock_input)
            
            if thscode is None:
                output_file = os.path.join(scripts_dir, "_fetch_result.json")
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump({"error": f"未找到股票: {stock_input}"}, f, ensure_ascii=False)
                print(output_file)
                sys.exit(1)
            
            print(f"已解析: {stock_name}({pure_code}) → {thscode}", file=sys.stderr)
            
            # 使用股票代码作为文件名一部分，避免不同股票的缓存互相覆盖
            safe_code = re.sub(r'[^\w]', '_', pure_code or stock_input)
            output_file = os.path.join(scripts_dir, f"_fetch_result_{safe_code}.json")
            
            # 先删除旧文件，防止脚本崩溃时主Agent读到旧数据
            try:
                if os.path.exists(output_file):
                    os.remove(output_file)
            except Exception:
                pass
            
            # 批量获取数据
            result = fetch_all_data(ths, thscode, pure_code, stock_name)
            
            elapsed = time.time() - start_time
            result["elapsed_seconds"] = round(elapsed, 1)
            print(f"数据采集完成，耗时 {elapsed:.1f}秒", file=sys.stderr)
            
            # 写入文件（非stdout，避免thsdk污染）
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, default=str)
            
            # stdout只输出文件路径，供主Agent读取
            print(output_file)
    
    except Exception as e:
        elapsed = time.time() - start_time
        error_result = {
            "error": str(e),
            "traceback": traceback.format_exc(),
            "elapsed_seconds": round(elapsed, 1)
        }
        # 写错误结果到固定文件
        output_file = os.path.join(scripts_dir, "_fetch_result.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(error_result, f, ensure_ascii=False, default=str)
        print(output_file)
        sys.exit(1)


if __name__ == "__main__":
    main()
