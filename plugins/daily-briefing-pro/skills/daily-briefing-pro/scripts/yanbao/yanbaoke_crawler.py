#!/usr/bin/env python3
"""
每日研报观点提炼 - 多源版
支持：东方财富研报、研报客API
"""

import urllib.request
import urllib.parse
import ssl
import json
import re
import sys
from datetime import datetime

# ========== 东方财富研报API ==========
EASTMONEY_REPORT_API = 'https://reportapi.eastmoney.com/report/list'

def fetch_eastmoney_reports(date):
    """从东方财富获取研报"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    reports = []
    
    begin_date = date.replace('-', '')
    end_date = date.replace('-', '')
    
    try:
        params = {
            'cb': 'datatable',
            'pageNo': '1',
            'pageSize': '50',
            'code': '',
            'industryCode': '*',
            'qType': '0',
            'beginTime': begin_date,
            'endTime': end_date,
            'lastUpdateTime': ''
        }
        
        url = f"{EASTMONEY_REPORT_API}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
                'Referer': 'https://data.eastmoney.com/report/'
            }
        )
        
        with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
            text = response.read().decode('utf-8')
            
            # JSONP格式: datatable({...})
            start = text.find('(')
            end = text.rfind(')')
            if start > 0 and end > start:
                json_str = text[start+1:end]
                data = json.loads(json_str)
                
                if data.get('data'):
                    for item in data['data']:
                        reports.append({
                            'source': '东方财富',
                            'title': item.get('title', ''),
                            'org': item.get('orgSName', '') or item.get('orgName', '未知'),
                            'date': item.get('publishDate', '')[:10],
                            'stock': item.get('stockName', ''),
                            'content': ''
                        })
    except Exception as e:
        print(f"  [WARN] 东方财富研报失败: {e}", file=sys.stderr)
    
    return reports


# ========== 研报客API (官方) ==========
YANBAOKE_API = 'https://api.yanbaoke.cn/skills/search_report'
YANBAOKE_VERSION = '2.1.0'
YANBAOKE_SKILL_ID = 'yanbaoke-research-report-download'

def fetch_yanbaoke_reports(date):
    """从研报客获取研报 (官方API)"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    reports = []
    keywords = ['人工智能', '半导体', '新能源', '策略', '金股', '消费', '医药', '机器人']
    
    for kw in keywords:
        try:
            params = urllib.parse.urlencode({
                'keyword': kw,
                'size': '20',
                'search_type': 'title',
                'startdate': date,
                'enddate': date
            })
            
            url = f'{YANBAOKE_API}?{params}'
            req = urllib.request.Request(
                url,
                headers={
                    'User-Agent': 'Mozilla/5.0',
                    'X-Skill-Version': YANBAOKE_VERSION,
                    'X-Skill-ID': YANBAOKE_SKILL_ID
                }
            )
            
            with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                if data.get('success') and data.get('data'):
                    for item in data['data']:
                        # 从标题提取机构名
                        org = item.get('org_name', '')
                        if not org:
                            title = item.get('title', '')
                            for known_org in ['海通国际', '中国银河', '浙商证券', '华泰证券', '中金公司', '东吴证券', '开源证券', '中信证券', '国泰君安']:
                                if known_org in title:
                                    org = known_org
                                    break
                        if not org:
                            org = '研报'
                        
                        reports.append({
                            'source': '研报客',
                            'title': item.get('title', ''),
                            'org': org,
                            'date': item.get('time', date),
                            'stock': item.get('stock_name', ''),
                            'uuid': item.get('uuid', ''),
                            'url': item.get('url', ''),
                            'content': item.get('content', '')[:200]
                        })
        except Exception as e:
            print(f"  [WARN] 研报客 [{kw}] 失败: {str(e)[:30]}", file=sys.stderr)
    
    return reports


def clean_title(title):
    """清洗标题"""
    import re
    
    # 移除完整日期 (20260704, 20260703)
    title = re.sub(r'\b202[0-9]{5}\b', '', title)
    # 移除年份 (2026年, 2025年, 2026)
    title = re.sub(r'20[0-9]{2}年?', '', title)
    # 移除月份
    title = re.sub(r'\d{1,2}月', '', title)
    # 移除页数和数字
    title = re.sub(r'\s*\d+页\s*', '', title)
    title = re.sub(r'\s+\d+\s*$', '', title)
    # 移除文件大小
    title = re.sub(r'\s*\d+\.?\d*\s*[kmg]?b\s*', '', title, flags=re.IGNORECASE)
    # 移除机构名
    for org in ['华泰证券', '中金公司', '浙商证券', '东吴证券', '海通国际', '中国银河', '华金证券', '亿欧智库', '安永', '开源证券']:
        title = title.replace(org, '')
    # 移除股票代码和乱码
    title = re.sub(r'\d{6}\.(BJ|SH|SZ)', '', title)
    title = re.sub(r'\s+[A-Z]\s+', ' ', title)
    # 去重连续相同的词
    words = title.split()
    seen = set()
    unique_words = []
    for w in words:
        if w not in seen or len(w) < 3:
            seen.add(w)
            unique_words.append(w)
    title = ' '.join(unique_words)
    # 移除常见前缀和括号内容
    for word in ['深度报告', '研究报告', '新股覆盖研究：', '华泰研究', '中金研究', '本周精选', '鼎智科技 ']:
        title = title.replace(word, '')
    # 移除括号及其内容
    title = re.sub(r'[（(][^）)]*[）)]', '', title)
    # 移除"第X期"
    title = re.sub(r'第\d+期', '', title)
    # 清理符号和空格
    title = title.replace('_', ' ').replace('-', ' ').replace(',', ' ').strip()
    title = re.sub(r'\s+', ' ', title)
    
    return title[:38].strip()


def extract_symbols(title, content='', stock=''):
    """提取标的或板块"""
    # 如果API返回了明确的stock_name
    if stock and stock != 'N/A':
        return stock
    
    # 从标题和内容中提取
    text = title + ' ' + content
    
    # 常见股票名称
    stocks = {
        '宁德时代': '宁德时代', '比亚迪': '比亚迪', '茅台': '贵州茅台', 
        '中际旭创': '中际旭创', '天孚通信': '天孚通信', '隆基绿能': '隆基绿能',
        '通威股份': '通威股份', '阳光电源': '阳光电源', '华为': '华为',
        '腾讯': '腾讯', '阿里': '阿里巴巴', '美团': '美团', '字节': '字节跳动',
        '小米': '小米', '百度': '百度', '京东': '京东', '拼多多': '拼多多',
        '网易': '网易', '快手': '快手', '哔哩': '哔哩哔哩', 'B站': '哔哩哔哩',
        '美的': '美的集团', '格力': '格力电器', '海尔': '海尔智家',
        '三一': '三一重工', '潍柴': '潍柴动力', '徐工': '徐工机械',
        '招商银行': '招商银行', '平安银行': '平安银行', '宁波银行': '宁波银行',
        '中信证券': '中信证券', '华泰证券': '华泰证券', '东方财富': '东方财富',
        '药明康德': '药明康德', '恒瑞医药': '恒瑞医药', '迈瑞医疗': '迈瑞医疗',
        '长春高新': '长春高新', '智飞生物': '智飞生物', '沃森生物': '沃森生物',
        '兆易创新': '兆易创新', '韦尔股份': '韦尔股份', '澜起科技': '澜起科技',
        '北方华创': '北方华创', '中微公司': '中微公司', '华大九天': '华大九天',
        '鼎智科技': '鼎智科技', '永励精密': '永励精密', '康美特': '康美特',
        '英伟达': 'NVDA', '特斯拉': 'TSLA', '苹果': 'AAPL', '微软': 'MSFT',
        '亚马逊': 'AMZN', '谷歌': 'GOOGL', 'Meta': 'META', 'AMD': 'AMD',
        '台积电': '台积电', '三星': '三星', '英特尔': '英特尔',
        '美光': '美光', 'SK海力士': 'SK海力士',
    }
    
    for name, symbol in stocks.items():
        if name in text:
            return symbol
    
    # 如果没找到具体标的，返回板块
    return extract_sector(title)


def deduplicate(reports):
    """去重"""
    seen = set()
    unique = []
    for r in reports:
        key = r['title'][:30]
        if key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


def extract_sector(title):
    """推断板块"""
    sectors = {
        '人工智能': 'AI', 'AI': 'AI', '半导体': '半导体', '芯片': '半导体',
        '光模块': '光通信', '新能源': '新能源', '光伏': '光伏', '锂电': '锂电',
        '储能': '储能', '机器人': '机器人', '汽车': '汽车', '医药': '医药',
        '消费': '消费', '白酒': '白酒', '银行': '银行', '券商': '券商',
        '军工': '军工', '化工': '化工', '有色': '有色', '铜箔': '铜箔',
        '策略': '策略', '金股': '金股', '资产管理': '资管', '基金': '基金',
        '旅游': '旅游', 'ESG': 'ESG', '债市': '债券', '氢氟酸': '化工',
        '电子级': '电子化学品', '水电': '水电', '医疗': '医药', '教育': '教育',
        '功率': '功率半导体', '涨价': '半导体'
    }
    for kw, sec in sectors.items():
        if kw in title:
            return sec
    return '综合'


def format_date(date_str):
    """格式化日期为简短格式 (07-04)"""
    if not date_str:
        return ''
    # 提取月日
    if len(date_str) >= 10:
        return date_str[5:10]  # 2026-07-04 -> 07-04
    return date_str


def clean_viewpoint(content, title):
    """清理并提取核心观点"""
    if content and len(content) > 30:
        content = content.replace('\n', ' ').replace('\r', ' ')
        content = re.sub(r'[A-Za-z]+', '', content)
        content = re.sub(r'[\d%]+', '', content)
        content = content.replace('/', '').replace('\\', '').replace('|', '')
        content = re.sub(r'\d{4}年\d{1,2}月\d{1,2}日', '', content)
        content = content.replace('年月日', '').replace('年 月', '').replace('（ 年 月）', '')
        content = content.replace('报告日期：', '').replace('中金研究', '').replace('华泰研究', '')
        content = content.replace('开源北交所', '').replace('工业互联网大厦', '')
        content = content.replace('本周精选：', '').replace('本周精选', '')
        content = content.replace('中金点睛', '').replace('栏目将带您回顾', '')
        content = content.replace('汇集本周最受读者欢迎的研究报告', '')
        content = content.replace('点击下方标题可查阅全文', '').replace('点击图片查看全文', '')
        content = content.replace('安全研究所', '').replace('目录', '').replace('一、研究背景', '')
        content = re.sub(r'【.*?】', '', content)
        content = re.sub(r'\(.*?\)', '', content)
        content = re.sub(r'[\-\—:：><]+', ' ', content)
        content = re.sub(r'\"+', '', content)
        content = re.sub(r'[\,\.\s]{3,}', ' ', content)
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r'^[月\s]+', '', content)
        content = content.strip()
        
        if len(content) > 15 and not content.startswith('...') and not content.startswith(','):
            # 增加到80字符，让观点更详细
            return content[:80] + '...' if len(content) > 80 else content
    
    # 用标题作为观点
    title_clean = clean_title(title)
    return title_clean[:80] + '...' if len(title_clean) > 80 else title_clean


def format_output(reports, date):
    """格式化输出"""
    if not reports:
        return f"⚠️ {date} 暂无研报\n"
    
    lines = [f"\n📊 每日研报观点提炼 ({date})", f"共 {len(reports)} 份", ""]
    lines.append("| 来源 | 日期 | 核心观点 | 标的/板块 | 方向 |")
    lines.append("|------|------|----------|----------|------|")
    
    for r in reports[:12]:
        org = (r['org'] or '研报')[:6]
        rpt_date = format_date(r.get('date', date))
        title = r['title']
        content = r.get('content', '')
        
        # 提取核心观点（详细版）
        viewpoint = clean_viewpoint(content, title)
        # 确保观点不为空
        if not viewpoint or viewpoint.strip() == '' or viewpoint.strip() == '|':
            viewpoint = clean_title(title)
        if not viewpoint:
            viewpoint = '观点待补充'
        
        # 提取标的或板块
        stock = r.get('stock', '')
        symbol = extract_symbols(title, content, stock)
        
        direction = '看好'
        if any(w in title for w in ['风险', '谨慎', '下调']):
            direction = '谨慎'
        elif any(w in title for w in ['利空', '下跌']):
            direction = '利空'
        
        lines.append(f"| {org} | {rpt_date} | {viewpoint} | {symbol} | {direction} |")
    
    return '\n'.join(lines)
    
    return '\n'.join(lines)


def main():
    date = datetime.now().strftime('%Y-%m-%d')
    
    if '--date' in sys.argv:
        idx = sys.argv.index('--date')
        date = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else date
    
    print(f"\n📊 每日研报观点提炼 ({date})", file=sys.stderr)
    
    print("🔍 东方财富研报...", file=sys.stderr)
    em = fetch_eastmoney_reports(date)
    print(f"   {len(em)} 份", file=sys.stderr)
    
    print("🔍 研报客...", file=sys.stderr)
    yb = fetch_yanbaoke_reports(date)
    print(f"   {len(yb)} 份", file=sys.stderr)
    
    all_reports = deduplicate(em + yb)
    print(f"\n📋 总计 {len(all_reports)} 份", file=sys.stderr)
    
    print(format_output(all_reports, date))


if __name__ == '__main__':
    main()