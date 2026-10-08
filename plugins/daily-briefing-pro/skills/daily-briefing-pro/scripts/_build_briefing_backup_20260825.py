#!/usr/bin/env python3
"""
每日简报HTML编译器
从 data/ 目录读取各板块JSON数据，编译为自包含HTML文件

用法: python build_briefing.py [--date YYYY-MM-DD]
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
DATA_DIR = BASE_DIR / "data"

# AI 总结 API 默认配置（讯飞 MaaS，用户可通过环境变量覆盖）
# 与 run_all.py 保持一致，确保 build_briefing.py 单独运行时 AI 总结开箱即用
# 备份实现不内置 AI 凭证；如需 AI 总结，沿用环境变量配置。

# 输出目录：固定路径，不再依赖 cwd（避免定时任务 cwd 不同导致文件存到隐蔽位置）
OUTPUT_DIR = Path(r"./outputs\每日简报")


def get_date():
    """获取日期（支持 --date 参数）"""
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return datetime.now().strftime("%Y-%m-%d")


def get_recent_trade_date(date_str: str) -> str:
    """获取最近交易日（周末回退到周五）"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    wd = dt.weekday()
    if wd >= 5:  # 周六或周日
        dt = dt - timedelta(days=wd - 4)
    return dt.strftime("%Y-%m-%d")


def load_json(filename: str) -> dict:
    """加载JSON数据文件，不存在或失败返回空dict"""
    path = DATA_DIR / filename
    if not path.exists():
        print(f"  [WARN] 数据文件缺失: {filename}", file=sys.stderr)
        return {}
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception as e:
        print(f"  [WARN] 数据文件解析失败: {filename} - {e}", file=sys.stderr)
        return {}


def fetch_index_data() -> dict:
    """获取主要指数数据（上证、科创50、纳斯达克、KOSPI）
    纳斯达克: ak.index_us_stock_sina(symbol='.IXIC')
    KOSPI: ak.index_global_hist_sina(symbol='首尔综合指数')（注意：必须用中文名，不能用'KOSPI'）
    """
    indices = {}
    try:
        import akshare as ak
        # 上证指数
        df = ak.stock_zh_index_daily(symbol="sh000001")
        if len(df) > 1:
            last = df.iloc[-1]
            prev = df.iloc[-2]
            close = float(last["close"])
            prev_close = float(prev["close"])
            chg = (close - prev_close) / prev_close * 100
            indices["上证"] = {"close": round(close, 2), "chg": round(chg, 2)}

        # 科创50
        df = ak.stock_zh_index_daily(symbol="sh000688")
        if len(df) > 1:
            last = df.iloc[-1]
            prev = df.iloc[-2]
            close = float(last["close"])
            prev_close = float(prev["close"])
            chg = (close - prev_close) / prev_close * 100
            indices["科创50"] = {"close": round(close, 2), "chg": round(chg, 2)}

        # 纳斯达克
        df = ak.index_us_stock_sina(symbol=".IXIC")
        if len(df) > 1:
            last = df.iloc[-1]
            prev = df.iloc[-2]
            close = float(last["close"])
            prev_close = float(prev["close"])
            chg = (close - prev_close) / prev_close * 100
            indices["纳斯达克"] = {"close": round(close, 0), "chg": round(chg, 2)}

        # KOSPI - 必须用中文名"首尔综合指数"，'KOSPI'会KeyError
        try:
            df = ak.index_global_hist_sina(symbol="首尔综合指数")
            if len(df) > 1:
                last = df.iloc[-1]
                prev = df.iloc[-2]
                close = float(last["close"])
                prev_close = float(prev["close"])
                chg = (close - prev_close) / prev_close * 100
                indices["KOSPI"] = {"close": round(close, 0), "chg": round(chg, 2)}
        except Exception as e:
            print(f"  [WARN] KOSPI数据获取失败: {e}", file=sys.stderr)

    except Exception as e:
        print(f"  [WARN] 指数数据获取失败: {e}", file=sys.stderr)

    return indices


def fetch_index_chart_data() -> dict:
    """获取上证指数近14个交易日收盘走势（大盘折线图数据）

    返回 {dates: [...], closes: [...], chgs: [...]}，日期为 MM-DD 格式
    """
    result = {"dates": [], "closes": [], "chgs": []}
    try:
        import akshare as ak
        df = ak.stock_zh_index_daily(symbol="sh000001")
        if df is None or len(df) < 15:
            return result
        recent = df.tail(15).copy()
        recent["chg"] = recent["close"].pct_change() * 100
        recent = recent.dropna(subset=["chg"]).tail(14)
        for _, row in recent.iterrows():
            d = str(row["date"])
            result["dates"].append(d[5:])       # MM-DD
            result["closes"].append(round(float(row["close"]), 1))
            result["chgs"].append(round(float(row["chg"]), 2))
    except Exception as e:
        print(f"  [WARN] 大盘指数折线图数据获取失败: {e}", file=sys.stderr)
    return result


def fetch_sentiment_chart_data(panic_data: dict = None) -> tuple:
    """获取近14日情绪折线图数据

    优先使用开盘啦爬虫的历史涨跌分析数据（250天），
    回退到上证指数涨跌幅代理。
    """
    scores = []
    labels = []

    # 方法1: 使用开盘啦爬虫的 get_realtime_rise_fall_analysis（250天历史）
    if panic_data:
        try:
            sys.path.insert(0, str(BASE_DIR / "scripts"))
            from kaipanla_crawler import KaipanlaCrawler
            crawler = KaipanlaCrawler()
            analysis = crawler.get_realtime_rise_fall_analysis()
            raw = analysis.get("raw_data", [])
            if raw and len(raw) >= 5:
                # raw每行: [涨停, 跌停, 破板数, 炸板数, 破板率, 昨日涨停今表现, 日期]
                # 取最近14天，用涨停数和破板率计算简易情绪分数
                for row in raw[:14]:
                    date_str = str(row[6])[5:] if len(row) > 6 else "-"
                    limit_up = row[0]
                    limit_down = row[1]
                    broken_rate = row[4]
                    yesterday_perf = row[5]
                    # 简易情绪分数: 涨停越多/破板率越低/溢价越高 → 分数越高
                    # 涨停净额归一化(0-50) + 破板率反向归一化(0-25) + 溢价归一化(0-25)
                    net_score = min(50, max(0, (limit_up - limit_down) / 1.5))
                    board_score = min(25, max(0, 25 * (1 - broken_rate / 60)))
                    perf_score = min(25, max(0, 12.5 + yesterday_perf * 0.5))
                    score = round(net_score + board_score + perf_score, 1)
                    score = max(0, min(100, score))
                    scores.append(score)
                    labels.append(date_str)
                scores.reverse()
                labels.reverse()
                return scores, labels
        except Exception as e:
            print(f"  [WARN] 开盘啦历史情绪数据获取失败: {e}", file=sys.stderr)

    # 方法2: 回退到上证指数涨跌幅代理
    try:
        import akshare as ak
        df = ak.stock_zh_index_daily(symbol="sh000001")
        recent = df.tail(20)
        recent = recent.copy()
        recent["chg"] = recent["close"].pct_change() * 100
        last_14 = recent.dropna(subset=["chg"]).tail(14)
        for _, row in last_14.iterrows():
            date_str = str(row["date"])[5:]
            score = round(50 + float(row["chg"]) * 10, 1)
            score = max(0, min(100, score))
            scores.append(score)
            labels.append(date_str)
    except Exception as e:
        print(f"  [WARN] 情绪图表数据获取失败: {e}", file=sys.stderr)
        scores = [50, 50, 50, 50, 50]
        labels = ["-", "-", "-", "-", "-"]
    return scores, labels


# ===== HTML生成辅助函数 =====

def mc_cls(chg):
    return "up" if chg > 0 else "dn"

def arrow(chg):
    return "▲" if chg > 0 else "▼"

def badge_cls(ntype):
    return {"利好": "br", "利空": "bo", "中性": "bbl"}.get(ntype, "bbl")

def ind_cls(industry):
    mapping = {
        "半导体": "br", "存储": "br", "AI": "bcy", "算力": "bbl",
        "光模块": "bcy", "光纤": "bcy", "PCB": "bcy", "MLCC": "bgd",
        "铜箔": "bgd", "氟化工": "bo", "券商": "bbl", "养殖": "bo",
        "风电": "bcy", "机器人": "bcy", "航天": "bbl",
    }
    return mapping.get(industry, "bbl")

def infer_industry(title):
    for kw, ind in [
        # (关键词, 板块)
        ("半导体", "半导体"), ("芯片", "半导体"), ("晶圆", "半导体"), ("光刻", "半导体"),
        ("存储", "存储"), ("DRAM", "存储"), ("NAND", "存储"), ("HBM", "存储"),
        ("AI", "AI算力"), ("算力", "AI算力"), ("GPU", "AI算力"), ("光模块", "AI算力"),
        ("光通信", "光通信"), ("光纤", "光通信"), ("CPO", "光通信"),
        ("PCB", "PCB/覆铜板"), ("覆铜板", "PCB/覆铜板"), ("铜箔", "PCB/覆铜板"),
        ("MLCC", "MLCC/被动元件"), ("被动元件", "MLCC/被动元件"),
        ("氟化工", "氟化工"), ("六氟磷酸锂", "氟化工"),
        ("券商", "金融/券商"), ("证券", "金融/券商"), ("银行", "金融/券商"),
        ("养殖", "养殖"), ("猪", "养殖"),
        ("风电", "风电"), ("海风", "风电"), ("叶片", "风电"),
        ("机器人", "机器人"), ("人形机器人", "机器人"), ("具身智能", "机器人"),
        ("航天", "军工/航天"), ("军工", "军工/航天"), ("卫星", "军工/航天"), ("火箭", "军工/航天"),
        ("创新药", "创新药"), ("医药", "创新药"), ("生物", "创新药"), ("临床", "创新药"),
        ("药", "创新药"), ("管线", "创新药"),
        ("航运", "航运"), ("油运", "航运"), ("船", "航运"),
        ("消费", "消费/潮玩"), ("白酒", "消费/潮玩"), ("食品", "消费/潮玩"),
        ("新能源车", "新能源车"), ("锂电", "新能源车"), ("宁德", "新能源车"), ("比亚迪", "新能源车"),
    ]:
        if kw in title:
            return ind
    return "综合"


# ===== AI 总结引擎（DeepSeek / OpenAI 兼容） =====

def ai_summarize_opinions(raw_text: str, context: str = "博主观点", max_retries: int = 1) -> str:
    """
    用 LLM 对博主原始口语化内容做语义级总结提炼。
    输入：Whisper转录/跟帖原始文本（口语化、碎片化）
    输出：1-3句精炼投资观点（书面语、可读性强、含核心逻辑）

    优先使用 DeepSeek API，兜底使用 OpenAI 兼容接口。
    若 API 不可用，回退到正则提取（extract_opinion_sentences）。
    """
    if not raw_text or len(raw_text.strip()) < 10:
        return ""

    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")

    # 优先 DeepSeek，其次 OpenAI；自动匹配对应的 base_url 和 model
    if deepseek_key:
        api_key = deepseek_key
        base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2")
        model = os.environ.get("DEEPSEEK_MODEL", "xopqwen35397b")
    elif openai_key:
        api_key = openai_key
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    else:
        print("  [INFO] 无 DEEPSEEK_API_KEY / OPENAI_API_KEY，回退正则提取", file=sys.stderr)
        return ""

    prompt = f"""你是一位顶级A股短线投研总监。请从以下{context}原始内容中，提炼出完整、可执行的投资观点。

【绝对禁止】以下类型的泛泛废话，出现即不合格：
- "市场情绪谨慎/乐观/观望"
- "资金态度分化/谨慎/积极"
- "短期震荡/整理/调整"
- "注意风险/控制仓位"
- "结构性机会/分化加剧"
- "关注后续政策/业绩验证"
- "板块轮动加快/热点散乱"
- 任何没有具体标的、没有明确方向、没有时间窗口的模糊表述

【提炼要求】
- 逐条提炼博主提到的所有重要观点，不遗漏标的和板块，每条观点独占一行
- **首条必须是【次日大盘】对下个交易日大盘指数的预期**（若原文未直接说，基于其逻辑推断），格式：【次日大盘】看多/看空/震荡 + 核心逻辑（为什么） + 验证信号（什么信号确认/证伪）
- 其余每条观点必须同时包含：
1. 具体标的或板块（用【】标注，如【半导体】【江波龙】）
2. 明确方向（看多/看空/持有/减仓/清仓）
3. 核心逻辑（为什么：订单/政策/技术突破/业绩/估值等）
4. 时间窗口（日内/今明两天/本周/本月/季度）
5. 触发/验证条件（什么信号确认或证伪该观点）
- 博主提及了多个方向时，每个方向都要提炼出来，不要只挑1个
- 若博主有明确的主线判断（如"风格切换""主线PK"），单独提炼一条

【输出标准】
- 观点必须可执行：读到后知道买什么/卖什么、什么时候买/卖、为什么
- 例1：【次日大盘】看多，M国晚间修复+日韩不跳水则明日延续修复，验证信号：今晚外盘上涨且明日A股竞价高开
- 例2：【华峰测控】看多，Q3订单确认国产ATE导入加速，今明两天若站稳220元可加仓，验证信号：盘后龙虎榜机构净买入>5000万
- 例3：【半导体设备】偏空，PE普遍>60x且年内涨幅>80%，本周若北向连续3日净流出则减仓，验证信号：华峰测控跌破200日均线
- 例4：【消费电子】中性观望，苹果链订单增速放缓但AI手机增量未兑现，等9月苹果发布会后再判断，验证信号：立讯精密Q3指引
- 每条观点60-100字，提炼3-6条，覆盖原始内容中的所有重要信息，不要遗漏

原始内容：
{raw_text[:6000]}

请直接输出提炼后的观点，每行一条，不要加前缀说明："""

    import httpx
    for attempt in range(max_retries + 1):
        try:
            resp = httpx.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 800,
                    "temperature": 0.3,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                result = resp.json()["choices"][0]["message"]["content"].strip()
                # 清理：去掉可能的引号包裹
                result = result.strip('"\'""''')
                if result and result != "无明确观点":
                    return result
                return ""
            else:
                print(f"  [WARN] AI总结API返回 {resp.status_code}: {resp.text[:100]}", file=sys.stderr)
        except Exception as e:
            if attempt < max_retries:
                continue
            print(f"  [WARN] AI总结失败: {e}", file=sys.stderr)
    return ""


# ── 财经新闻全天AI精选 ──────────────────────────────────────────
# 无关民生/天气/交通类关键词（规则预筛选排除）
_IRRELEVANT_KW = [
    "台风", "暴雨", "降雨", "洪水", "地铁", "航班", "铁路", "高速", "公路", "列车",
    "停电", "停运", "天气", "气温", "海浪", "地震", "火灾", "事故", "受伤", "遇难",
    "世界杯", "奥运", "国足", "足球", "篮球", "演唱会", "票房", "综艺", "明星",
]
# 重要性加权关键词（规则预筛选打分）
_IMPORTANT_KW = [
    (10, ["国务院", "发改委", "财政部", "央行", "证监会", "国家统计局", "商务部", "工信部",
          "金融监管总局", "外汇局", "国常会", "中央", "部委"]),
    (8, ["降准", "降息", "加息", "利率", "LPR", "MLF", "回购利率", "汇率", "人民币"]),
    (8, ["IPO", "上市", "申购", "过会", "注册制", "发行价", "募资"]),
    (7, ["制裁", "关税", "出口管制", "禁运", "反倾销", "调查", "芯片法案", "实体清单"]),
    (7, ["业绩", "财报", "预增", "预亏", "预减", "中报", "年报", "净利润", "营收"]),
    (6, ["增持", "回购", "减持", "举牌", "要约收购", "重组", "并购", "收购", "合并"]),
    (6, ["涨停", "跌停", "龙虎榜", "主力", "北向", "外资", "融资", "两融"]),
    (6, ["涨价", "降价", "调价", "提价", "价格战", "供需", "紧缺", "产能", "扩产"]),
    (5, ["签订", "中标", "订单", "合同", "采购", "招标", "供货"]),
    (5, ["获批", "获批上市", "临床", "试验", "新药", "药监局", "创新药"]),
    (5, ["量产", "投产", "下线", "交付", "出货", "发布", "首发"]),
    (4, ["协议", "合作", "合资", "投资", "项目", "开工", "落地"]),
    (4, ["AI", "芯片", "半导体", "算力", "存储", "光模块", "机器人", "新能源",
         "光伏", "电池", "汽车", "地产", "券商", "银行", "保险", "黄金", "原油", "稀土"]),
]

def rule_score_news(n: dict) -> int:
    """规则预筛选：排除无关民生新闻，按重要性关键词打分"""
    title = n.get("title", "") + n.get("content", "")
    if any(kw in title for kw in _IRRELEVANT_KW):
        return 0
    score = 0
    for w, kws in _IMPORTANT_KW:
        if any(kw in title for kw in kws):
            score += w
    # 有标的的加分（公司新闻）
    if n.get("stocks"):
        score += 2
    return score


def ai_select_top_news(news_list: list, top_n: int = 10) -> list:
    """AI从全天快讯中精选对A股影响最大的N条信息。
    返回结构化列表：[{time, title, impact(关键/重要), sector(相关板块)}]
    AI失败时回退到规则打分排序取前N条。
    """
    # 规则预筛选：排除无关，取高分候选（上限80条）
    scored = [(rule_score_news(n), n) for n in news_list]
    candidates = [n for s, n in sorted(scored, key=lambda x: -x[0]) if s >= 5][:80]
    if not candidates:
        candidates = news_list[:50]
    # 按时间倒序（新的在前）
    candidates.sort(key=lambda n: n.get("time", ""), reverse=True)

    # 候选文本压缩（标题+时间，每条一行）
    lines = []
    for n in candidates:
        t = n.get("time", "")[11:16]
        lines.append(f"{t} {n.get('title', '')[:60]}")
    sample_text = "\n".join(lines)

    prompt = f"""你是A股财经主编。以下是{len(candidates)}条当天快讯（时间+标题，已按最新在前）。
请从中挑选对A股市场影响最大的 {top_n} 条信息，排除：天气/交通/民生/体育娱乐、与A股无关的地缘碎闻、公司日常公告。

要求：
1. 优先选：宏观政策/央行货币、监管、IPO、行业涨价/制裁/订单、龙头公司业绩/重组/增持
2. 每条输出格式（严格JSON数组，不要其他文字）：
[{{"time":"HH:MM","title":"原标题","impact":"关键|重要","sector":"相关板块或标的，无则空"}}]

快讯列表：
{sample_text}"""

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2")
    model = os.environ.get("DEEPSEEK_MODEL", "xopqwen35397b")
    if api_key:
        import httpx
        try:
            resp = httpx.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model,
                      "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": 1500, "temperature": 0.3},
                timeout=30,
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"].strip()
                # 提取JSON数组（容错：AI可能输出尾随逗号/注释/代码块围栏）
                m = re.search(r'\[.*\]', content, re.S)
                if m:
                    raw = m.group(0)
                    # 移除尾随逗号（"}" 或 "]" 前的 ","）
                    raw = re.sub(r',\s*([\]}])', r'\1', raw)
                    try:
                        items = json.loads(raw)
                    except json.JSONDecodeError:
                        items = None
                    if items:
                        # 回填原始数据
                        title_map = {n.get("title", ""): n for n in news_list}
                        out = []
                        for it in items:
                            orig = title_map.get(it.get("title", ""))
                            out.append({
                                "time": it.get("time", ""),
                                "title": it.get("title", ""),
                                "impact": it.get("impact", "重要"),
                                "sector": it.get("sector", ""),
                                "type": orig.get("type", "中性") if orig else "中性",
                                "stocks": orig.get("stocks", []) if orig else [],
                            })
                        return out
            else:
                print(f"  [WARN] 新闻精选API返回 {resp.status_code}", file=sys.stderr)
        except Exception as e:
            print(f"  [WARN] 新闻精选AI失败: {e}", file=sys.stderr)

    # 兜底：规则打分取前N
    out = []
    for n in candidates[:top_n]:
        out.append({
            "time": n.get("time", "")[11:16],
            "title": n.get("title", ""),
            "impact": "关键" if rule_score_news(n) >= 8 else "重要",
            "sector": "",
            "type": n.get("type", "中性"),
            "stocks": n.get("stocks", []),
        })
    return out
    """
    批量总结单个博主的所有内容（主帖+跟帖），返回结构化结果。
    必须使用AI总结，失败时重试最多3次，仍失败则报错停止。
    """
    combined = "\n".join(t for t in all_texts if t)

    # 提取标的（从原始文本，不受AI总结影响）
    symbols = extract_symbols_from_text(combined)

    # 判断方向（从原始文本关键词计数）
    bull_signals = sum(1 for kw in ["看多", "看涨", "利好", "乐观", "涨", "反弹", "企稳",
                      "止跌", "机会", "买入", "加仓", "首选", "强", "突破", "超预期"]
                      if kw in combined)
    bear_signals = sum(1 for kw in ["看空", "看跌", "利空", "悲观", "跌", "恐慌", "风险",
                      "回避", "减仓", "弱", "破位", "不及预期", "杀跌", "暴跌"]
                      if kw in combined)
    if bull_signals > bear_signals + 2:
        direction = "看多"
    elif bear_signals > bull_signals + 2:
        direction = "看空"
    else:
        direction = "中性"

    # AI 总结（重试最多3次）
    ai_summary = ""
    for attempt in range(3):
        ai_summary = ai_summarize_opinions(combined, context=f"{context_type}博主{blogger_name}的投资观点")
        if ai_summary:
            break
        print(f"  [WARN] AI总结失败（{context_type}/{blogger_name}），重试 {attempt+1}/3...", file=sys.stderr)

    if ai_summary:
        # 从AI总结中提取【】标注的标的，补充到symbols
        extra_symbols = re.findall(r'【([^】]+)】', ai_summary)
        for s in extra_symbols:
            if s not in symbols:
                symbols.append(s)
        summary = ai_summary
    else:
        # AI总结3次均失败，报错停止（禁止回退到正则提取或原文截断）
        print(f"  [⛔] AI总结3次均失败（{context_type}/{blogger_name}），DEEPSEEK_API_KEY可能无效或额度不足，无法生成合格简报", file=sys.stderr)
        summary = f"[AI总结失败-{blogger_name}]"

    return {
        "summary": summary,
        "symbols": symbols[:6],
        "direction": direction,
        "used_ai": bool(ai_summary),
    }


def ai_summarize_batch_parallel(tasks: list) -> list:
    """
    并发批量调用 AI 总结，避免串行拖慢编译。
    tasks: [(raw_text, context), ...]
    返回: [ai_summary_str, ...]  与 tasks 一一对应
    """
    import concurrent.futures

    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not deepseek_key and not openai_key:
        return [""] * len(tasks)

    def _call(task):
        raw_text, context = task
        return ai_summarize_opinions(raw_text, context)

    results = [""] * len(tasks)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_call, t): i for i, t in enumerate(tasks)}
        for future in concurrent.futures.as_completed(futures, timeout=60):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception:
                results[idx] = ""
    return results


# ===== 总结提炼引擎 =====

# 繁简转换（优先使用 zhconv 库，兜底手动映射）
try:
    from zhconv import convert as _zhconv_convert
    def trad_to_simp(text: str) -> str:
        """繁体转简体（zhconv）"""
        try:
            return _zhconv_convert(text, 'zh-cn')
        except Exception:
            return text
except ImportError:
    # 兜底：手动映射（覆盖常见字）
    _SIMP_MAP = {
        '說': '说', '買': '买', '賣': '卖', '漲': '涨', '賺': '赚',
        '虧': '亏', '導': '导', '體': '体', '時': '时', '長': '长',
        '點': '点', '錢': '钱', '銀': '银', '機': '机', '構': '构',
        '產': '产', '業': '业', '電': '电', '網': '网', '絡': '络',
        '聯': '联', '數': '数', '據': '据', '設': '设', '備': '备',
        '車': '车', '場': '场', '總': '总', '結': '结', '變': '变',
        '創': '创', '開': '开', '驗': '验', '證': '证', '預': '预',
        '實': '实', '歷': '历', '經': '经', '營': '营', '費': '费',
        '務': '务', '種': '种', '廠': '厂', '質': '质', '規': '规',
        '戰': '战', '義': '义', '權': '权', '資': '资', '運': '运',
        '環': '环', '壓': '压', '額': '额', '億': '亿', '關': '关',
        '鍵': '键', '統': '统', '計': '计', '劃': '划', '還': '还',
        '過': '过', '這': '这', '裡': '里', '裏': '里', '為': '为',
        '與': '与', '對': '对', '從': '从', '來': '来', '個': '个',
        '們': '们', '會': '会', '將': '将', '應': '应', '當': '当',
        '沒': '没', '於': '于', '後': '后', '問': '问', '題': '题',
        '國': '国', '際': '际', '區': '区', '東': '东', '進': '进',
        '現': '现', '發': '发', '達': '达', '轉': '转', '單': '单',
        '讓': '让', '給': '给', '請': '请', '誰': '谁', '麼': '么',
        '嗎': '吗', '著': '着', '確': '确', '認': '认', '識': '识',
        '語': '语', '讀': '读', '論': '论', '調': '调', '試': '试',
        '極': '极', '強': '强', '優': '优', '勢': '势', '態': '态',
        '擴': '扩', '張': '张', '縮': '缩', '減': '减', '續': '续',
        '斷': '断', '獨': '独', '舊': '旧', '舉': '举', '辦': '办',
        '歲': '岁', '書': '书', '寫': '写', '學': '学', '覺': '觉',
        '見': '见', '觀': '观', '評': '评', '價': '价', '報': '报',
        '貨': '货', '幣': '币', '財': '财', '飛': '飞', '龍': '龙',
        '鐵': '铁', '鋼': '钢', '銅': '铜', '鋁': '铝', '風': '风',
        '氣': '气', '雲': '云', '歡': '欢', '樂': '乐', '驚': '惊',
        '懼': '惧', '懷': '怀', '憂': '忧', '憤': '愤', '幾': '几',
        '兩': '两', '並': '并', '亞': '亚', '僅': '仅', '擊': '击',
        '擔': '担', '擇': '择', '擁': '拥', '擴': '扩', '擾': '扰',
        '裝': '装', '處': '处', '複': '复', '雜': '杂', '穀': '谷',
        '麥': '麦', '麵': '面', '飯': '饭', '飲': '饮', '馬': '马',
        '鳥': '鸟', '魚': '鱼', '蟲': '虫', '鳳': '凤', '貧': '贫',
        '窮': '穷', '撐': '撑', '擱': '搁', '擲': '掷', '擷': '撷',
        '擺': '摆', '擼': '撸',
    }
    def trad_to_simp(text: str) -> str:
        """繁体转简体（兜底）"""
        result = []
        for ch in text:
            result.append(_SIMP_MAP.get(ch, ch))
        return "".join(result)


# ===== 标的/板块关键词库 =====
SECTOR_KEYWORDS = {
    "半导体": ["半导体", "芯片", "晶圆", "封测", "光刻", "EDA", "功率器件", "MOSFET", "IGBT",
              "国产替代", "设备", "北方华创", "中微公司", "长电科技", "通富微电", "华天科技",
              "兆易创新", "紫光", "寒武纪", "中芯国际", "长鑫"],
    "存储": ["存储", "DRAM", "NAND", "HBM", "美光", "海力士", "三星", "长鑫", "江波龙",
            "佰维存储", "德明利", "东芯", "兆易"],
    "AI算力": ["AI", "算力", "GPU", "英伟达", "NVIDIA", "Blackwell", "光模块", "1.6T",
              "中际旭创", "新易盛", "天孚通信", "光迅科技", "交换机", "交换芯片",
              "算力租赁", "IDC", "液冷", "铜缆", "沃尔"],
    "光通信": ["光通信", "光纤", "光棒", "MPO", "光连接", "特发信息", "烽火通信",
              "光芯片", "LITE", "CPO", "光子"],
    "PCB/覆铜板": ["PCB", "覆铜板", "铜箔", "东山精密", "生益科技", "诺德股份", "建滔",
                 "沪电股份", "深南电路", "兴森科技"],
    "机器人": ["机器人", "宇树", "具身智能", "人形机器人", "减速器", "伺服", "传感器",
             "CCXI", "TSLA", "特斯拉"],
    "创新药": ["创新药", "医药", "生物", "CXO", "药明", "恒瑞", "百济", "信达"],
    "新能源车": ["新能源车", "锂电池", "宁德时代", "比亚迪", "充电桩", "整车"],
    "消费/潮玩": ["消费", "潮玩", "零售", "白酒", "食品", "旅游"],
    "军工/航天": ["航天", "军工", "商业航天", "火箭", "卫星", "导弹"],
    "金融/券商": ["券商", "银行", "保险", "金融", "东方财富", "中信证券"],
    "风电": ["风电", "金风科技", "东方电缆", "海风", "叶片"],
    "MLCC/被动元件": ["MLCC", "被动元件", "风华高科", "三环集团", "电容", "电阻"],
    "氟化工": ["氟化工", "六氟磷酸锂", "多氟多", "永和股份", "配额"],
    "稀土/稀有金属": ["稀土", "中国稀土", "北方稀土", "盛和资源", "翔鹭钨业", "钨", "盛达资源",
                 "稀有金属", "磁材", "金力永磁", "华宏科技", "中科三环"],
    "电力/能源": ["电力", "华银电力", "华电", "大唐", "绿电", "火电", "核电", "煤炭",
                "能源", "天然气", "广汇能源"],
    "民爆": ["民爆", "高争民爆", "易普力", "保利联合", "爆破"],
    "光模块/CPO": ["光模块", "CPO", "共封装", "光迅科技", "中际旭创", "新易盛", "天孚通信"],
    "PCB": ["PCB", "红板科技", "中京电子", "沪电股份", "深南电路", "兴森科技", "覆铜板", "贤丰控股"],
    "光伏": ["光伏", "福莱特", "隆基", "通威", "阳光电源", "组件", "硅料", "胶膜"],
    "环保/生态": ["环保", "汇绿生态", "园林", "生态", "水处理", "固废"],
    "有色": ["有色", "铜", "铝", "锌", "黄金", "紫金矿业", "江西铜业", "云铝股份"],
    "医疗器械": ["医疗器械", "医疗", "美好医疗", "脑机接口", "体外诊断", "IVD", "齿科", "眼科"],
    "量子计算": ["量子", "量子计算", "罗普特", "伊辛机", "本源量子", "国盾"],
}

# 个股关键词（精确匹配）
STOCK_KEYWORDS = {
    "北方华创": "002371", "中微公司": "688012", "长电科技": "600584",
    "通富微电": "002156", "华天科技": "002185", "兆易创新": "603986",
    "中际旭创": "300308", "新易盛": "300502", "天孚通信": "300394",
    "东山精密": "002384", "生益科技": "600183", "诺德股份": "600110",
    "特发信息": "000070", "宁德时代": "300750", "比亚迪": "002594",
    "风华高科": "000636", "多氟多": "002407", "永和股份": "605020",
    "金风科技": "002202", "东方电缆": "603606", "紫光国微": "002049",
    "寒武纪": "688256", "中芯国际": "688981", "江波龙": "301308",
    "佰维存储": "688525", "雅克科技": "002409", "太极实业": "600667",
    "和远气体": "002971", "南大光电": "300346", "金海通": "603061",
    "深南电路": "002916", "沪电股份": "002463", "光迅科技": "002281",
    "烽火通信": "600498", "药明康德": "603259", "恒瑞医药": "600276",
    "东方财富": "300059", "中信证券": "600030", "三环集团": "300408",
    "兴森科技": "002436", "德明利": "001309", "长鑫科技": "688825",
}

# 个股名 → 板块/概念 反向映射（做多方向只显示板块概念，不显示个股）
def stock_to_sector(stock_name: str) -> str:
    """将个股名映射为所属板块/概念，未匹配返回空字符串"""
    if not stock_name:
        return ""
    for sector, kws in SECTOR_KEYWORDS.items():
        if stock_name in kws:
            return sector
    # 模糊匹配：个股名包含于关键词或关键词包含于个股名
    for sector, kws in SECTOR_KEYWORDS.items():
        for kw in kws:
            if kw and (kw in stock_name or stock_name in kw):
                return sector
    return ""


def extract_symbols_from_text(text: str) -> list:
    """从文本中提取标的/板块关键词"""
    text = trad_to_simp(text)
    found = []
    seen = set()
    # 先匹配个股（更精确）
    for name, code in STOCK_KEYWORDS.items():
        if name in text and name not in seen:
            found.append(name)
            seen.add(name)
    # 再匹配板块
    for sector, keywords in SECTOR_KEYWORDS.items():
        if sector not in seen:
            for kw in keywords:
                if kw in text:
                    found.append(sector)
                    seen.add(sector)
                    break
    return found[:6]


# ===== 投资观点句提取 =====
# 匹配包含投资判断的句式
_OPINION_PATTERNS = [
    # 明确方向判断
    r'(?:看多|看空|看涨|看跌|偏多|偏空|乐观|悲观|利好|利空)[^。，；！？]{2,30}',
    # 趋势判断
    r'(?:趋势|方向|走势|行情|周期|阶段)[^。，；！？]{0,6}(?:向上|向下|反转|延续|加速|见底|见顶|企稳|突破)[^。，；！？]{0,20}',
    # 逻辑判断
    r'(?:因为|由于|逻辑|原因|驱动|催化)[^。，；！？]{2,40}',
    # 操作建议
    r'(?:建议|关注|重点|优先|首选|回避|警惕|注意|等待|观察)[^。，；！？]{2,30}',
    # 涨跌判断
    r'(?:涨价|降价|提价|调价|紧缺|过剩|供需|扩产|减产|产能)[^。，；！？]{2,30}',
    # 估值判断
    r'(?:估值|PE|PB|市值|低估|高估|合理|泡沫)[^。，；！？]{2,25}',
    # 业绩判断
    r'(?:业绩|营收|利润|盈利|超预期|不及预期|增长|下滑)[^。，；！？]{2,30}',
    # 市场情绪
    r'(?:恐慌|贪婪|情绪|冰点|高潮|分歧|共识|一致)[^。，；！？]{2,25}',
    # 周期位置
    r'(?:周期|位置|阶段|拐点|底部|顶部|起点|终点)[^。，；！？]{0,6}(?:到了|在|处于|接近|还没|已经)[^。，；！？]{0,20}',
]

# 噪声句式（过滤掉无信息量的口语）
_NOISE_PATTERNS = [
    r'^[嗯啊哦呀哈嘿哎吧呢么嘛]+$',  # 纯语气词
    r'^.{0,3}$',  # 太短
    r'(?:怎么说呢|反正|就是说|怎么说|你想想|你就想|说白了|说真的|说实话)',  # 口语填充
    r'(?:点击|关注|点赞|转发|收藏|订阅|评论)',  # 互动引导
    r'(?:视频|直播|节目|频道|粉丝)',  # 自我引用
]


def extract_opinion_sentences(text: str, max_sentences: int = 4) -> list:
    """从文本中提取投资观点句"""
    text = trad_to_simp(text)
    # 按标点分句
    sentences = re.split(r'[。，；！？\n]', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 4]

    results = []
    for s in sentences:
        # 跳过噪声
        if any(re.search(p, s) for p in _NOISE_PATTERNS):
            continue
        # 匹配观点句
        for pat in _OPINION_PATTERNS:
            m = re.search(pat, s)
            if m:
                opinion = m.group(0).strip()
                if len(opinion) > 6 and opinion not in [r[:len(opinion)] for r in results]:
                    results.append(opinion)
                break

    # 如果观点句不够，补充高赞/高信息量句子
    if len(results) < max_sentences:
        for s in sentences:
            if s in results or any(r in s for r in results):
                continue
            # 高信息量特征：含数字、含关键词
            has_number = bool(re.search(r'\d+\.?\d*%?', s))
            has_keyword = any(kw in s for kw in ["涨", "跌", "买", "卖", "仓", "板",
                "停", "破", "新", "高", "低", "强", "弱", "量", "价", "期", "利"])
            if has_number or has_keyword:
                results.append(s[:60])
                if len(results) >= max_sentences:
                    break

    return results[:max_sentences]


def summarize_tgb_blogger(name: str, data: dict) -> dict:
    """总结提炼淘股吧博主观点（优先AI总结，回退正则提取）"""
    posts = data.get("posts", [])
    replies = data.get("top_replies", [])
    replies_today = data.get("replies_today", 0)

    all_text = []
    post_titles = []

    # 主帖
    for p in posts:
        title = p.get("title", "")
        if title:
            post_titles.append(title)
        content = p.get("content", "")
        if content:
            all_text.append(content)

    # 跟帖（取前10条高赞）
    for r in replies[:10]:
        content = r.get("content", "")
        if content:
            all_text.append(content)

    if not all_text:
        return {
            "name": name,
            "has_content": False,
            "post_title": "",
            "summary": "今日无动态",
            "symbols": [],
            "direction": "中性",
        }

    # 使用 AI 批量总结
    result = ai_summarize_blogger_batch(name, all_text, context_type="淘股吧")

    return {
        "name": name,
        "has_content": True,
        "post_title": post_titles[0] if post_titles else "",
        "summary": result["summary"],
        "symbols": result["symbols"],
        "direction": result["direction"],
        "replies_today": replies_today,
        "has_posts": bool(posts),
        "used_ai": result["used_ai"],
    }


def douyin_fallback_summary(text: str) -> str:
    """抖音观点精炼兜底：AI总结失败时从文本提取含投资关键词的核心句（不允许原文截断/失败标记）
    对"视频 7670xxx"这类无意义标题/转录，返回提示而非垃圾内容"""
    if not text:
        return ""
    text = text.strip()
    # 清洗旧版兜底前缀"视频标题：xxx。话题标签：..."
    text = re.sub(r'^视频标题：', '', text)
    text = re.sub(r'。?话题标签：', ' / ', text)
    # 无意义标题（纯视频ID），无有效投资信息
    if re.fullmatch(r'视频\s*\d{10,}', text):
        return "（视频未提供标题，转录受限）"
    if len(text) <= 60 or "【" in text:
        return text[:60]
    kw = re.findall(r'[^。；！？\n]{0,12}(?:存储|半导体|芯片|AI|算力|涨价|降价|扩产|需求|订单|业绩|财报|降息|加息|国产|替代|英伟达|苹果|特斯拉|AMD|美光|HBM|DRAM|NAND|光模块|机器人|铜|黄金)[^。；！？\n]{0,20}', text)
    if kw:
        return kw[0][:60]
    return text[:60] + "…"


def summarize_douyin_video(video: dict) -> dict:
    """总结提炼抖音视频观点（优先AI总结，失败时精炼兜底，禁止原文截断/失败标记）"""
    title = video.get("title", "")
    transcript = video.get("transcript", "")
    summary_raw = video.get("summary", "")
    symbols_raw = video.get("symbols", [])
    direction_raw = video.get("direction", "关注")
    warning = video.get("warning", "")

    # 转简体
    title_s = trad_to_simp(title)
    transcript_s = trad_to_simp(transcript) if transcript else ""

    # 提取标的（优先从转录提取，补充原始标的）
    symbols = extract_symbols_from_text(transcript_s or title_s)
    for s in symbols_raw:
        if s not in symbols:
            symbols.append(s)
    symbols = symbols[:6]

    # AI 总结（优先使用转录文本，标题兜底）
    raw_for_ai = transcript_s or title_s
    ai_summary = ai_summarize_opinions(raw_for_ai, context="抖音博主视频观点")

    if ai_summary:
        # 从AI总结中提取【】标注的标的，补充到symbols
        extra_symbols = re.findall(r'【([^】]+)】', ai_summary)
        for s in extra_symbols:
            if s not in symbols:
                symbols.append(s)
        symbols = symbols[:6]
        summary = ai_summary
        used_ai = True
    else:
        # 精炼兜底：从转录/标题提取含投资关键词的核心句（不输出原文截断或失败标记）
        summary = douyin_fallback_summary(transcript_s or title_s)
        if not summary:
            summary = title_s[:60]
        used_ai = False

    # 判断方向（基于转录内容重新判断）
    if transcript_s:
        bull_signals = sum(1 for kw in ["看多", "看涨", "利好", "乐观", "涨", "反弹",
                          "机会", "买入", "首选", "强", "突破", "超预期", "涨价",
                          "扩产", "紧缺", "需求", "增长"]
                          if kw in transcript_s)
        bear_signals = sum(1 for kw in ["看空", "看跌", "利空", "悲观", "跌", "恐慌",
                          "风险", "回避", "弱", "破位", "杀跌", "暴跌", "降价",
                          "过剩", "减产"]
                          if kw in transcript_s)
        if bull_signals > bear_signals + 2:
            direction = "利好"
        elif bear_signals > bull_signals + 2:
            direction = "利空"
        else:
            direction = "关注"
    else:
        direction = direction_raw

    return {
        "title": title_s[:50],
        "url": video.get("url", ""),
        "summary": summary,
        "symbols": symbols,
        "direction": direction,
        "warning": warning,
        "used_ai": used_ai,
    }


def build_html(today: str, trade_date: str) -> str:
    """从数据文件编译完整HTML（报刊风格·浅色新闻纸）"""

    # 加载所有数据
    news = load_json("news_today.json")
    panic = load_json("panic_today.json")
    selfstock = load_json("selfstock_today.json")
    events = load_json("events_today.json")
    yanbao = load_json("yanbao_latest.json")
    tgb = load_json("tgb_today.json")
    douyin = load_json("douyin_today.json")
    survey = load_json("sentiment_survey_today.json")
    lhb = load_json("lhb_today.json")
    serenity = load_json("serenity_today.json")
    cycle = load_json("langwang_cycle.json")

    # 每日一句（读取名言HTML，移除引号装饰 <div class="quote-mark">❝</div>）
    quote_path = DATA_DIR / "quote_today.html"
    quote_html = ""
    if quote_path.exists():
        quote_html = open(quote_path, encoding="utf-8").read()
        # 移除引号装饰元素（用户要求去掉双引号 ❝）
        quote_html = re.sub(r'<div class="quote-mark">[^<]*</div>', '', quote_html)
        quote_html = re.sub(r'\n\s*\n', '\n', quote_html).strip()

    # 读取CSS模板（跳过文件开头的HTML注释，定位真正的 <style> 标签）
    template = open(BASE_DIR / "templates" / "briefing.html", encoding="utf-8").read()
    css_end = template.rfind("</style>")
    css_start = template.rfind("<style>", 0, css_end)
    css_block = template[css_start:css_end + 8]

    # 日期显示
    dt = datetime.strptime(today, "%Y-%m-%d")
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][dt.weekday()]
    today_display = f"{today.replace('-', '.')} {weekday_cn}"
    data_note = f"（{trade_date}数据）" if today != trade_date else ""

    # 博主板块统一日期标注：从各数据源提取实际数据日期（考虑回退场景），格式 MM/DD
    def blogger_date_label(data: dict) -> str:
        """从博主数据JSON提取实际数据日期，返回 '8/6' 格式；优先解析note中的回退日期"""
        ds = data.get("date", "")
        note = data.get("note", "") or ""
        # 从note解析"使用YYYY-MM-DD数据"（回退场景）
        m = re.search(r'使用(\d{4})-(\d{2})-(\d{2})数据', note)
        if m:
            ds = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        if ds and len(ds) >= 10:
            try:
                d = datetime.strptime(ds[:10], "%Y-%m-%d")
                return f"{d.month}/{d.day}"
            except ValueError:
                pass
        return today[5:].replace("-", "/")

    # 指数数据
    indices = fetch_index_data()
    idx_sh = indices.get("上证", {"close": 3900, "chg": 0})
    idx_kc50 = indices.get("科创50", {"close": 2000, "chg": 0})
    idx_nasdaq = indices.get("纳斯达克", {"close": 26000, "chg": 0})
    idx_kospi = indices.get("KOSPI", {"close": 2600, "chg": 0})

    # 情绪图表数据
    chart_scores, chart_labels = fetch_sentiment_chart_data(panic)

    # ===== 狼王行千里情绪周期阶段（叠加到情绪折线图）=====
    # cycle.by_date: {date: {stage,color,note}}；按情绪图的labels日期对齐
    cycle_by_date = cycle.get("by_date", {}) if isinstance(cycle, dict) else {}
    cycle_cur = cycle.get("current", {}) if isinstance(cycle, dict) else {}
    cycle_legend_colors = {"up": "#C0392B", "dn": "#1E7E34", "warn": "#9C640C", "blue": "#1B4F72"}
    # 每个交易日对应的阶段（按labels中的MM-DD匹配 year-08-xx）
    cycle_daily = []
    year = str(dt.year)
    for lab in chart_labels:
        day = f"{year}-{lab}" if lab and len(lab) == 5 else ""
        st = cycle_by_date.get(day, {}) if day else {}
        cycle_daily.append({
            "stage": st.get("stage", ""),
            "color": cycle_legend_colors.get(st.get("color", ""), "#6B6555"),
            "note": st.get("note", ""),
        })
    cycle_cur_html = ""
    if cycle_cur:
        cst = cycle_cur.get("stage", "")
        ccl = cycle_legend_colors.get(cycle_cur.get("color", ""), "#6B6555")
        cnote = cycle_cur.get("note", "")
        cdate = cycle_cur.get("date", "")
        cycle_cur_html = f'<div class="cycle-cur" style="background:{ccl}" title="{cnote}">狼王·{cst} <small>{cdate}</small></div>'
    chart_js_cycle = json.dumps(cycle_daily)

    # ===== 大盘指数折线图（上证近14日）=====
    idx_chart = fetch_index_chart_data()
    idx_map = {d: c for d, c in zip(idx_chart.get("dates", []), idx_chart.get("closes", []))}
    # 合并：以情绪图日期为主轴，上证按日期匹配（缺失用前值填充避免断线）
    merged_chart = []
    last_idx = None
    for i, lab in enumerate(chart_labels):
        day = f"{year}-{lab}" if lab and len(lab) == 5 else ""
        st = cycle_by_date.get(day, {}) if day else {}
        idx_v = idx_map.get(lab)
        if idx_v is not None:
            last_idx = idx_v
        merged_chart.append({
            "date": lab,
            "sent": chart_scores[i],
            "idx": last_idx,
            "stage": st.get("stage", ""),
            "color": cycle_legend_colors.get(st.get("color", ""), "#6B6555"),
            "note": st.get("note", ""),
        })
    chart_js_merged = json.dumps(merged_chart)

    # ===== ① 报头 Masthead =====
    masthead = f"""<div class="masthead">
<div class="kicker">DAILY MARKET BRIEFING</div>
<h1>每日简报</h1>
<div class="dateline">
<span>第 {today.replace('-','')} 期</span>
<span class="center">{dt.year}年{dt.month}月{dt.day}日 · {weekday_cn}</span>
<span>{data_note.strip("（）") or "收盘数据"}</span>
</div>
</div>"""

    # ===== ② 头版头条（情绪 + 指数 + 折线图）=====
    score = panic.get("score", 50)
    status = panic.get("status", "中性")
    score_pct = int(score)
    if score < 25:
        sent_color = "var(--dn)"
    elif score < 45:
        sent_color = "var(--warn)"
    elif score < 55:
        sent_color = "var(--ink2)"
    elif score < 75:
        sent_color = "var(--up)"
    else:
        sent_color = "var(--up)"

    # 新版情绪维度数据
    dims = panic.get("dimensions", {})
    details = panic.get("details", {})
    market_eval = details.get("market_eval", "")
    extra = panic.get("extra", {})

    # 构建维度小标签
    dim_tags = []
    dim_labels = {
        "profit_effect": ("赚钱效应", "💰"),
        "limit_net": ("涨停净额", "🔥"),
        "up_down_ratio": ("涨跌比", "📊"),
        "lianban_rate": ("接力意愿", "🔗"),
        "board_quality": ("封板质量", "🛡"),
        "trend_strength": ("趋势强度", "📈"),
    }
    for dim_key, (dim_name, dim_emoji) in dim_labels.items():
        dim_info = dims.get(dim_key, {})
        dim_score = dim_info.get("score", 50)
        dim_tags.append(f'<span class="dim-tag" title="{dim_name} {dim_score}分">{dim_emoji}{dim_name}<b>{dim_score:.0f}</b></span>')
    dim_tags_html = " ".join(dim_tags)

    # 连板梯队摘要
    ladder_info = extra.get("consecutive_ladder", {})
    max_consec = ladder_info.get("max_consecutive", 0)
    max_consec_stock = ladder_info.get("max_consecutive_stocks", "")
    max_consec_concept = ladder_info.get("max_consecutive_concepts", "")
    ladder_summary = f"最高板{max_consec}连板·{max_consec_stock}" if max_consec > 0 else ""

    # 涨停板块摘要（前3个）
    limit_sectors = extra.get("limit_up_sectors", {}).get("sectors", [])[:3]
    sector_summary = " | ".join(f"{s['sector_name']}{s['stock_count']}只" for s in limit_sectors) if limit_sectors else ""

    # 副标题
    lead_sub_parts = [f"赚钱效应{dims.get('profit_effect',{}).get('score',50):.0f}分主导，"
                      f"连板率{details.get('lianban_rate_raw',0):.1f}%，"
                      f"破板率{details.get('broken_rate',0):.1f}%"]
    if market_eval:
        lead_sub_parts.append(f"开盘啦评价：{market_eval}")
    if ladder_summary:
        lead_sub_parts.append(ladder_summary)
    lead_sub_text = "。".join(lead_sub_parts) + "。"

    def idx_html(name, d):
        chg = d["chg"]
        cls = "up" if chg > 0 else "dn"
        arr = "▲" if chg > 0 else "▼"
        return f'<div class="idx"><div class="nm">{name}</div><div class="vl">{d["close"]:,.0f}</div><div class="cg {cls}">{arr}{abs(chg):.2f}%</div></div>'

    # 综合热度TOP10
    hot_stocks = extra.get("hot_stocks", [])
    hot_rows_html = ""
    if hot_stocks:
        for i, hs in enumerate(hot_stocks[:10], 1):
            name = hs.get("name", "")
            code = hs.get("code", "")
            lb = hs.get("max_lianban", 0)
            lhb_cnt = hs.get("lhb_count", 0)
            tgb_cnt = hs.get("tgb_mentions", 0)
            dcf_rank = hs.get("dcf_rank")
            concepts = hs.get("concepts", "")
            lb_tag = f'<span class="lb">{lb}连板</span>' if lb > 1 else ""
            lhb_tag = f'<span class="lhb">龙虎榜</span>' if lhb_cnt > 0 else ""
            tgb_tag = f'<span class="tgb">TGB×{tgb_cnt}</span>' if tgb_cnt > 0 else ""
            dcf_tag = f'<span class="dcf">东财#{dcf_rank}</span>' if dcf_rank and dcf_rank <= 30 else ""
            concept_tag = f'<span class="cpt">{concepts}</span>' if concepts else ""
            hot_rows_html += f'<div class="hrow"><span class="hr">{i}</span><span class="hn">{name}</span><span class="hc">{code}</span><span class="htags">{lb_tag}{lhb_tag}{tgb_tag}{dcf_tag}{concept_tag}</span></div>\n'

    hot_section = f"""<div class="hot-stocks">
<div class="hot-title">🔥 近5日综合热度 TOP10</div>
<div class="hot-rows">
{hot_rows_html}
</div>
</div>""" if hot_stocks else ""

    lead = f"""<section class="lead">
<div class="lead-sent">
<div class="sent-kicker">情绪强度</div>
<div class="sent-val" style="color:{sent_color}">{score_pct}</div>
<div class="sent-status" style="color:{sent_color}">{status}</div>
<div class="sent-bar"><div class="fill" style="width:{score_pct}%"></div></div>
<div class="dim-tags">{dim_tags_html}</div>
</div>
<div class="lead-main">
<div class="lead-headline">情绪指数 <span class="em">{score_pct}</span> {status}，{"赚钱效应强劲" if score>=65 else "情绪偏弱" if score<35 else "多空博弈继续"}</div>
<div class="lead-sub">{lead_sub_text}{"🔥" + sector_summary if sector_summary else ""}</div>
<div class="chart-box">
<div class="chart-head">
<span class="clbl">近14日情绪 · 上证走势 · 情绪周期阶段</span>
<div class="chart-toggle">
<span class="tg on" data-k="sent" id="tgSent" title="点击隐藏/显示情绪折线"><i class="dot" style="background:var(--up)"></i>情绪</span>
<span class="tg on" data-k="idx" id="tgIdx" title="点击隐藏/显示上证折线"><i class="dot" style="background:var(--blue)"></i>上证</span>
</div>
</div>
<canvas id="sentChart"></canvas>
<div class="cycle-strip" id="cycleStrip"></div>
{cycle_cur_html}
<div class="cycle-legend"><span class="cy"><i style="background:var(--up)"></i>主升</span><span class="cy"><i style="background:var(--dn)"></i>退潮</span><span class="cy"><i style="background:var(--warn)"></i>混沌</span><span class="cy"><i style="background:var(--blue)"></i>节点</span></div>
<div class="chart-tip" id="chartTip"><div class="v"></div><div class="d"></div></div>
</div>
<div class="lead-indices">
{idx_html("上证", idx_sh)}
{idx_html("科创50", idx_kc50)}
{idx_html("纳斯达克", idx_nasdaq)}
{idx_html("KOSPI", idx_kospi)}
</div>
</div>
{hot_section}
</section>"""

    # ===== ③ 财经新闻（全天汇总 + AI精选最重要信息）=====
    all_news = news.get("news", [])
    # 规则预筛选：排除无关民生新闻，保留重要性候选
    scored_news = [(rule_score_news(n), n) for n in all_news]
    valid_news = [n for s, n in sorted(scored_news, key=lambda x: -x[0]) if s >= 3]
    if not valid_news:
        valid_news = all_news
    # 策略研判用 top 候选（保留旧接口）
    news_items = valid_news[:10]
    # AI 精选最重要的 N 条
    top_news = ai_select_top_news(all_news, top_n=10)
    news_rows = []
    for it in top_news:
        time_str = it.get("time", "")[:5] if it.get("time") else ""
        ntype = it.get("type", "中性")
        impact = it.get("impact", "重要")
        sector = it.get("sector", "")
        title = it.get("title", "")
        # 过滤无效代码标签（90.BKxxxx 板块代码、0.xxx 浮点噪声等），只保留真实股票/板块名
        valid_stocks = [s for s in it.get("stocks", []) if s and not re.match(r'^[0-9.]*\.?BK?[0-9]*$', s) and not re.match(r'^\d+\.\d+$', s)]
        stock_tags = "".join(f' <span class="tag r">{s}</span>' for s in valid_stocks)
        impact_tag = f'<span class="imp {"imp-k" if impact=="关键" else "imp-b"}">{impact}</span>'
        sector_tag = f'<span class="tag y">{sector}</span>' if sector else ""
        news_rows.append(f'<tr><td class="t2">{title}{sector_tag}{stock_tags}</td></tr>')
    if not news_rows:
        news_rows = ['<tr><td class="t3" style="text-align:center">全天无重要财经信息</td></tr>']
    news_sec = f"""<section class="sec">
<div class="sh"><span class="num">01</span> 财经新闻 <span class="meta">全天{len(all_news)}条 · AI精选{len(top_news)}条{data_note}</span></div>
<table>
<tr><th>今日要闻</th></tr>
{"".join(news_rows)}</table></section>"""

    # ===== ④ 自选股新闻 =====
    ss_news = selfstock.get("news", [])
    if ss_news:
        ss_rows = []
        for n in ss_news[:15]:
            ntype = n.get("type", "中性")
            title = n.get("title", "")
            source = n.get("source", "")
            ss_rows.append(f'<tr><td><span class="{badge_cls(ntype)}">{ntype}</span></td><td class="t2">{title}</td></tr>')
        ss_count = len(ss_news)
    else:
        ss_rows = ['<tr><td colspan="2" class="t3" style="text-align:center">暂无自选股相关新闻</td></tr>']
        ss_count = 0
    ss_sec = f"""<section class="sec">
<div class="sh"><span class="num">02</span> 自选股动态 <span class="meta">{ss_count}条{data_note}</span></div>
<table><colgroup><col style="width:46px"><col></colgroup>
<tr><th>类型</th><th>标题</th></tr>
{"".join(ss_rows)}</table></section>"""

    # ===== ⑤ 龙虎榜 =====
    lhb_total = lhb.get("total_stocks", 0)
    lhb_top_buy = lhb.get("top_net_buy", [])[:10]
    lhb_hot_buy = lhb.get("top_hot_money_buy", [])[:8]
    lhb_groups = lhb.get("hot_money_groups", [])
    lhb_themes = lhb.get("main_themes", [])
    lhb_signals = lhb.get("key_signals", [])

    lhb_buy_rows = []
    # 建立名称到detail的映射（含买入/卖出席位信息）
    lhb_detail_map = {d.get("名称", ""): d for d in lhb.get("key_stocks_detail", [])}
    for s in lhb_top_buy:
        chg = s.get("涨跌幅", 0)
        chg_cls = "up" if chg > 0 else "dn"
        chg_text = f"+{chg:.2f}%" if chg > 0 else f"{chg:.2f}%"
        net_buy = s.get("净买额亿", 0)
        buy_val = s.get("买入额亿", 0)
        sell_val = s.get("卖出额亿", 0)
        # 获取游资席位名称
        name = s.get("名称", "")
        detail = lhb_detail_map.get(name, {})
        buy_seats = detail.get("买入席位", [])
        sell_seats = detail.get("卖出席位", [])
        buy_names = "、".join(b.get("席位", "")[:6] for b in buy_seats[:2]) if buy_seats else ""
        sell_names = "、".join(b.get("席位", "")[:6] for b in sell_seats[:2]) if sell_seats else ""
        buy_part = f"买{buy_val:.2f}"
        sell_part = f"卖{sell_val:.2f}"
        if buy_names:
            buy_part += f"<small style='color:var(--ink3)'> ({buy_names})</small>"
        if sell_names:
            sell_part += f"<small style='color:var(--ink3)'> ({sell_names})</small>"
        lhb_buy_rows.append(
            f'<tr><td class="t2"><span class="tag r">{name}</span></td>'
            f'<td class="{chg_cls}">{chg_text}</td>'
            f'<td class="tb">{net_buy:.2f}</td>'
            f'<td class="t2">{buy_part} / <small style="color:var(--ink3)">{sell_part}</small></td></tr>'
        )

    lhb_hot_rows = []
    for s in lhb_hot_buy:
        nick = s.get("昵称", s.get("席位", "")[:12])
        full_seat = s.get("席位", "")
        net_val = s.get("净买入亿", 0)
        stocks_str = "、".join(s.get("涉及个股", [])[:3])
        lhb_hot_rows.append(
            f'<tr><td class="tb" title="{full_seat}">{nick}</td>'
            f'<td class="up">+{net_val:.2f}</td>'
            f'<td class="t3">{stocks_str}</td></tr>'
        )

    theme_tags = []
    for t in lhb_themes:
        strength = t.get("强度", "🔥")
        name = t.get("板块", "")
        stocks = "、".join(t.get("个股", [])[:3])
        theme_tags.append(f'<span class="tag c">{strength}{name}</span> <span class="t3">{stocks}</span>')
    theme_html = " ".join(theme_tags) if theme_tags else '<span class="t3">暂无明显主线</span>'

    signal_parts = [sig for sig in lhb_signals[:4]]
    signal_html = "；".join(signal_parts) if signal_parts else "暂无"

    group_parts = []
    for g in lhb_groups[:3]:
        direction = g.get("方向", "")
        total = g.get("总净额亿", 0)
        name = g.get("派系", "")
        stocks = "、".join(g.get("涉及个股", [])[:3])
        cls = "up" if total > 0 else "dn"
        group_parts.append(f'<span class="tag b">{name}</span><span class="{cls}">{direction}{abs(total):.1f}亿</span> <span class="t3">{stocks}</span>')
    group_html = " ".join(group_parts) if group_parts else ""

    lhb_sec = f"""<section class="sec">
<div class="sh"><span class="num">03</span> 龙虎榜 <span class="meta">{lhb_total}只{data_note}</span></div>
<table><colgroup><col style="width:72px"><col style="width:52px"><col style="width:48px"><col></colgroup>
<tr><th>名称</th><th>涨跌</th><th>净买亿</th><th>买入 / 卖出</th></tr>
{"" .join(lhb_buy_rows)}</table>
<div style="margin-top:5px;font-size:11px"><b style="color:var(--cyan)">主线</b> {theme_html}</div>
{f'<div style="margin-top:3px;font-size:11px"><b style="color:var(--blue)">派系</b> {group_html}</div>' if group_html else ''}
<div class="lbox"><b>信号：</b>{signal_html}</div>
</section>"""

    # ===== ④ 机构研报（只保留最近3天）=====
    reports = yanbao.get("reports", [])
    # 筛选最近3天（含当天），按 publishDate 过滤
    try:
        dt_today = datetime.strptime(trade_date, "%Y-%m-%d")
        cutoff = (dt_today - timedelta(days=3)).strftime("%Y-%m-%d")
    except ValueError:
        cutoff = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    reports_3d = []
    reports_skipped = 0
    for r in reports:
        pd_ = r.get("publishDate", "")
        if pd_ and pd_ >= cutoff:
            reports_3d.append(r)
        elif pd_:
            reports_skipped += 1
    # 若3天过滤后为空（如周末无新研报），放宽到最近5天
    if not reports_3d and reports:
        reports_3d = reports[:15]
        reports_skipped = 0
    reports = reports_3d[:20]
    # 构建行数据，按机构分组用于合并单元格
    yb_rows_data = []
    for r in reports:
        org = r.get("org", "")[:6]
        stock = r.get("stock", "")
        title = r.get("title", "")
        rate = r.get("rate", "")
        if rate in ["买入", "增持", "推荐"]:
            dir_cls, dir_text = "bg_", "看多"
        elif rate in ["减持", "卖出"]:
            dir_cls, dir_text = "bo", "看空"
        else:
            dir_cls, dir_text = "bbl", "中性"
        industry = infer_industry(title)
        stock_tag = f'<span class="tag r">{stock}</span>' if stock else ""
        source = r.get("publishDate", "")[5:10] if r.get("publishDate") else ""
        ind_dir = f'<span class="{ind_cls(industry)}">{industry}</span> <span class="{dir_cls}">{dir_text}</span>'
        yb_rows_data.append({"org": org, "date": source, "ind_dir": ind_dir, "body": f'{title} {stock_tag}'})

    # 相同机构全局合并第一列（rowspan），机构按首次出现顺序分组，组内按日期排序
    org_groups = []
    org_index = {}
    for rd in yb_rows_data:
        if rd["org"] not in org_index:
            org_index[rd["org"]] = len(org_groups)
            org_groups.append([])
        org_groups[org_index[rd["org"]]].append(rd)

    yb_rows = []
    for group in org_groups:
        group = sorted(group, key=lambda x: x["date"], reverse=True)
        span = len(group)
        # 日期合并（去重）
        dates = []
        for g in group:
            if g["date"] and g["date"] not in dates:
                dates.append(g["date"])
        date_str = "、".join(dates) if dates else ""
        org = group[0]["org"]
        org_date = f'{org}<br><small style="color:var(--ink3);font-size:10px">{date_str}</small>' if date_str else org
        rowspan_attr = f' rowspan="{span}"' if span > 1 else ""
        yb_rows.append(
            f'<tr><td class="tb"{rowspan_attr}>{org_date}</td><td>{group[0]["ind_dir"]}</td><td class="t2">{group[0]["body"]}</td></tr>'
        )
        # 后续行只输出赛道+核心逻辑
        for g in group[1:]:
            yb_rows.append(f'<tr><td>{g["ind_dir"]}</td><td class="t2">{g["body"]}</td></tr>')
    yb_meta = f"{len(reports)}篇 · 最近3天"
    if reports_skipped:
        yb_meta += f"（过滤{reports_skipped}篇>3天）"
    yb_sec = f"""<section class="sec">
<div class="sh"><span class="num">04</span> 机构研报 <span class="meta">{yb_meta} · {yanbao.get("data_date", trade_date)}</span></div>
<table><colgroup><col style="width:62px"><col style="width:72px"><col></colgroup>
<tr><th>机构 / 日期</th><th>赛道 / 方向</th><th>核心逻辑</th></tr>
{"".join(yb_rows)}</table></section>"""

    # ===== ⑦ Serenity =====
    serenity_opinions = serenity.get("opinions", [])
    serenity_rows = []
    if serenity.get("has_data") and serenity_opinions:
        for op in serenity_opinions:
            direction = op.get("direction", "")
            dir_cls = {"看多": "up", "看空": "dn", "中性": "bbl", "观察": "bbl"}.get(direction, "bbl")
            summary = op.get("summary", "")
            symbols = op.get("symbols", [])
            sym_tags = "".join(f'<span class="tag y">{s}</span>' for s in symbols[:3])
            likes = op.get("likes", 0)
            likes_text = f"🔥{likes}" if likes > 50 else f"{likes}赞"
            # 方向列允许换行（覆盖徽章 .bbl 的 white-space:nowrap，长方向文本不撑宽列）
            serenity_rows.append(
                f'<tr><td style="vertical-align:middle"><span class="{dir_cls}" style="white-space:normal;word-break:break-word;display:inline-block">{direction}</span></td>'
                f'<td class="t2">{summary}{sym_tags}</td></tr>'
            )
    else:
        serenity_rows.append('<tr><td colspan="2" class="t3" style="text-align:center">暂无新观点</td></tr>')

    serenity_sec = f"""<section class="sec">
<div class="sh"><span class="num">05</span> Serenity观点 <span class="meta">{blogger_date_label(serenity)} · @aleabitoreddit</span></div>
<table><colgroup><col style="width:96px"><col></colgroup>
<tr><th>方向</th><th>核心观点 + 标的</th></tr>
{"" .join(serenity_rows)}</table></section>"""

    # ===== ⑧ 博主多空统计 =====
    survey_stats = survey.get("statistics", {})
    mkt = survey_stats.get("by_market", {"bull": 0, "bear": 0, "neutral": 0})
    mkt_total = mkt.get("bull", 0) + mkt.get("bear", 0) + mkt.get("neutral", 0)
    mkt_ratio = f"{mkt['bull']/max(mkt['bear'],1):.2f}" if mkt.get("bear", 0) > 0 else "∞"

    bull_count = mkt.get("bull", 0)
    bear_count = mkt.get("bear", 0)
    neutral_count = mkt.get("neutral", 0)
    bull_pct = bull_count / mkt_total * 100 if mkt_total > 0 else 0
    bear_pct = bear_count / mkt_total * 100 if mkt_total > 0 else 0
    neutral_pct = neutral_count / mkt_total * 100 if mkt_total > 0 else 0

    R = 40
    C = 2 * 3.14159 * R
    bull_dash = C * bull_pct / 100
    bear_dash = C * bear_pct / 100
    neutral_dash = C * neutral_pct / 100
    bull_offset = 0
    bear_offset = -bull_dash
    neutral_offset = -(bull_dash + bear_dash)

    if bull_pct >= 60:
        gauge_main_color = "var(--up)"; gauge_sentiment = "偏多"
    elif bear_pct >= 40:
        gauge_main_color = "var(--dn)"; gauge_sentiment = "偏空"
    else:
        gauge_main_color = "var(--blue)"; gauge_sentiment = "分歧"

    gauge_svg = f"""<svg viewBox="0 0 100 100">
      <circle class="ring-bg" cx="50" cy="50" r="{R}"/>
      <circle class="ring-fill bull" cx="50" cy="50" r="{R}" stroke-dasharray="{bull_dash} {C - bull_dash}" stroke-dashoffset="{bull_offset}"/>
      <circle class="ring-fill bear" cx="50" cy="50" r="{R}" stroke-dasharray="{bear_dash} {C - bear_dash}" stroke-dashoffset="{bear_offset}"/>
      <circle class="ring-fill neutral" cx="50" cy="50" r="{R}" stroke-dasharray="{neutral_dash} {C - neutral_dash}" stroke-dashoffset="{neutral_offset}"/>
    </svg>"""

    sector_bars = []
    for sd in survey_stats.get("by_sector_sorted", [])[:10]:
        sector = sd.get("sector", "")
        bull = sd.get("bull", 0); bear = sd.get("bear", 0); neutral = sd.get("neutral", 0)
        mentions = sd.get("blogger_count", 0)
        total_s = max(bull + bear + neutral, 1)
        bull_w = bull / total_s * 100; bear_w = bear / total_s * 100; neutral_w = neutral / total_s * 100
        parts = []
        if bull > 0: parts.append(f"▲{bull}")
        if bear > 0: parts.append(f"▼{bear}")
        if neutral > 0: parts.append(f"-{neutral}")
        bar_label = " / ".join(parts)
        sector_bars.append(f'<div class="survey-sector-row"><span class="survey-sector-name">{sector}</span><div class="survey-sector-bar"><div class="bar-bull" style="width:{bull_w}%"></div><div class="bar-bear" style="width:{bear_w}%"></div><div class="bar-neutral" style="width:{neutral_w}%"></div><span class="bar-label">{bar_label}</span></div><span class="survey-sector-count">{mentions}人</span></div>')

    plat_cards = []
    for pname, pdata in survey_stats.get("by_platform", {}).items():
        p_bull = pdata.get("bull", 0); p_bear = pdata.get("bear", 0); p_neutral = pdata.get("neutral", 0)
        ptotal = p_bull + p_bear + p_neutral
        pratio = f"{p_bull/max(p_bear,1):.1f}" if p_bear > 0 else "∞"
        plat_cls = "tgb" if "淘股" in pname else "xq" if "雪球" in pname else ""
        plat_cards.append(f'<div class="survey-plat-card {plat_cls}"><span class="survey-plat-name">{pname}</span><div class="survey-plat-stats"><span class="sp-bull">{p_bull}</span><span class="sp-sep">/</span><span class="sp-bear">{p_bear}</span><span class="sp-neutral">({p_neutral})</span></div><span class="survey-plat-meta">{pdata.get("blogger_count", ptotal)}位博主 · 多空比 <b>{pratio}</b></span></div>')

    conclusions = []
    tgb_plat = survey_stats.get("by_platform", {}).get("淘股吧", {})
    xq_plat = survey_stats.get("by_platform", {}).get("雪球", {})
    tgb_r = tgb_plat.get("bull", 0) / max(tgb_plat.get("bear", 1), 1)
    xq_r = xq_plat.get("bull", 0) / max(xq_plat.get("bear", 1), 1)
    if xq_r > tgb_r + 0.5:
        conclusions.append(f"雪球游资系偏乐观(多空比{xq_r:.1f})，淘股吧短线客偏谨慎(多空比{tgb_r:.1f})——说明大资金在布局，散户在观望，跟随大资金方向")
    elif tgb_r > xq_r + 0.5:
        conclusions.append(f"淘股吧短线客积极(多空比{tgb_r:.1f})，雪球游资系谨慎(多空比{xq_r:.1f})——说明散户情绪高涨但大资金未跟进，需防追高风险")
    else:
        if tgb_r > 2:
            conclusions.append(f"两平台同步看多(多空比{mkt_ratio})，短线共识强，但一致性过高往往意味着短期顶部")
        elif tgb_r < 0.5:
            conclusions.append(f"两平台同步看空(多空比{mkt_ratio})，避险情绪一致，等待冰点后的反弹信号")
        else:
            conclusions.append(f"两平台多空均衡(多空比{mkt_ratio})，市场分歧大，结构性机会为主，重个股轻指数")

    by_sector = survey_stats.get("by_sector_sorted", [])
    if by_sector:
        top = by_sector[0]
        bull_ratio = top.get("bull", 0) / max(top.get("bear", 1), 1)
        if bull_ratio >= 3:
            conclusions.append(f"【{top['sector']}】一致看多(▲{top.get('bull', 0)}▼{top.get('bear', 0)})，短线最强主线，重点跟踪龙头")
        elif bull_ratio >= 1.5:
            conclusions.append(f"【{top['sector']}】偏多(▲{top.get('bull', 0)}▼{top.get('bear', 0)})，资金关注度高，等分歧低吸机会")
        elif bull_ratio <= 0.5:
            conclusions.append(f"【{top['sector']}】一致看空(▲{top.get('bull', 0)}▼{top.get('bear', 0)})，回避为主，等利空消化")
        else:
            conclusions.append(f"【{top['sector']}】多空分歧(▲{top.get('bull', 0)}▼{top.get('bear', 0)})，方向未定，观望")

    all_bull_sectors = [s for s in by_sector if s.get("bear", 0) == 0 and s.get("bull", 0) >= 2]
    if all_bull_sectors:
        names = "、".join(s['sector'] for s in all_bull_sectors[:3])
        conclusions.append(f"【{names}】零看空一致看多——极端共识往往意味着短期顶部，不建议追高，持有者可考虑减仓")

    all_bear_sectors = [s for s in by_sector if s.get("bull", 0) == 0 and s.get("bear", 0) >= 2]
    if all_bear_sectors:
        names = "、".join(s['sector'] for s in all_bear_sectors[:3])
        conclusions.append(f"【{names}】零看多一致看空——极端悲观往往酝酿反弹，可纳入观察名单等冰点信号")

    conclusion_html = "；".join(conclusions)

    survey_sec = f"""<section class="sec">
<div class="sh"><span class="num">06</span> 博主多空统计 <span class="meta">{survey_stats.get('total_analyses', 0)}位博主 · {mkt_ratio}多空比{data_note}</span></div>
<div class="survey-wrap">
  <div class="survey-top">
    <div class="survey-gauge">
      <span class="survey-gauge-title">大盘情绪</span>
      <div class="survey-gauge-ring">{gauge_svg}<div class="survey-gauge-center"><span class="survey-gauge-val" style="color:{gauge_main_color}">{gauge_sentiment}</span><span class="survey-gauge-label">{mkt_total}人</span></div></div>
      <div class="survey-gauge-legend"><span><i class="dot-bull"></i>看多{bull_count}</span><span><i class="dot-bear"></i>看空{bear_count}</span><span><i class="dot-neutral"></i>中性{neutral_count}</span></div>
      <div class="survey-gauge-ratio">多空比 <b>{mkt_ratio}</b></div>
    </div>
    <div class="survey-sectors"><span class="survey-sectors-title">板块多空分布</span>{"".join(sector_bars)}</div>
  </div>
  <div class="survey-platforms">{"".join(plat_cards)}</div>
  <div class="lbox"><b>结论：</b>{conclusion_html}</div>
</div>
</section>"""

    # ===== ⑨ 淘股吧 =====
    tgb_blogger_names = list(tgb.get("bloggers", {}).keys())
    tgb_ai_tasks = []
    tgb_raw_data = {}
    for name in tgb_blogger_names:
        d = tgb["bloggers"][name]
        tgb_raw_data[name] = d
        posts = d.get("posts", [])
        replies = d.get("top_replies", [])
        all_text = [p["content"] for p in posts if p.get("content")]
        all_text += [r["content"] for r in replies[:15] if r.get("content")]
        if all_text:
            tgb_ai_tasks.append(("\n".join(all_text), f"淘股吧博主{name}的投资观点"))
        else:
            tgb_ai_tasks.append(("", ""))

    tgb_ai_results = ai_summarize_batch_parallel(tgb_ai_tasks)

    tgb_rows = []
    tgb_symbols_all = set()
    tgb_directions = []
    for i, name in enumerate(tgb_blogger_names):
        d = tgb_raw_data[name]
        ai_summary = tgb_ai_results[i] if i < len(tgb_ai_results) else ""
        posts = d.get("posts", [])
        replies = d.get("top_replies", [])
        all_text = [p["content"] for p in posts if p.get("content")]
        all_text += [r["content"] for r in replies[:15] if r.get("content")]
        post_titles = [p["title"] for p in posts if p.get("title")]

        if not all_text:
            tgb_rows.append(f'<tr><td class="tb" style="color:var(--gold)">{name}</td><td class="t2">今日无动态</td></tr>')
            continue

        combined = "\n".join(all_text)
        symbols = extract_symbols_from_text(combined)
        bull_signals = sum(1 for kw in ["看多","看涨","利好","乐观","涨","反弹","企稳","止跌","机会","买入","加仓","首选","强","突破","超预期"] if kw in combined)
        bear_signals = sum(1 for kw in ["看空","看跌","利空","悲观","跌","恐慌","风险","回避","减仓","弱","破位","不及预期","杀跌","暴跌"] if kw in combined)
        direction = "看多" if bull_signals > bear_signals + 2 else "看空" if bear_signals > bull_signals + 2 else "中性"

        used_ai = bool(ai_summary)
        if not ai_summary:
            for retry in range(3):
                ai_summary = ai_summarize_opinions(combined, context=f"淘股吧博主{name}的投资观点")
                if ai_summary: break
                print(f"  [WARN] 淘股吧AI总结失败（{name}），重试 {retry+1}/3...", file=sys.stderr)
        if ai_summary:
            used_ai = True
            for s in re.findall(r'【([^】]+)】', ai_summary):
                if s in ("次日大盘", "大盘", "指数", "A股", "市场", "大盘指数"):
                    continue
                if s not in symbols: symbols.append(s)
            summary = ai_summary
        else:
            print(f"  [⛔] 淘股吧AI总结3次均失败（{name}）", file=sys.stderr)
            summary = f"[AI总结失败-{name}]"

        for s in symbols[:5]: tgb_symbols_all.add(s)
        sym_tags = " ".join(f'<span class="tag y">{s}</span>' for s in symbols[:5])
        tgb_directions.append(direction)
        dir_badge = '<span class="bg_">看多</span>' if direction == "看多" else '<span class="bo">看空</span>' if direction == "看空" else '<span class="bbl">中性</span>'
        # 方向徽章 + 仅跟帖标记移到博主名称下方（博主列整体居中）
        name_meta = f'<span style="display:block;margin-top:4px">{dir_badge}</span>'
        if not posts:
            name_meta += '<span style="display:block;color:var(--ink3);font-size:10px;margin-top:3px">仅跟帖</span>'
        title_part = f'<b>{post_titles[0]}</b>：' if post_titles else ''
        # 将多个观点按【xxx】拆分，每条观点独立成行，过滤空观点
        opinion_parts = re.split(r'(?=【)', summary.strip())
        opinion_parts = [p.strip() for p in opinion_parts if p.strip() and len(p.strip()) > 8]
        # 拆分次日大盘观点（首条次日预期用醒目样式高亮；兼容【次日大盘】/【大盘指数】/【明日大盘】等变体标签）
        nd_tag_pat = r'【(次日大盘|大盘指数|明日大盘|大盘预期|大盘)】'
        next_day_html = ""
        rest_parts = opinion_parts
        if opinion_parts and re.match(nd_tag_pat, opinion_parts[0]):
            nd_first = re.sub(nd_tag_pat, '【次日大盘】', opinion_parts[0], count=1)
            next_day_html = f'<div class="opinion nd">{nd_first}</div>'
            rest_parts = opinion_parts[1:]
        if len(rest_parts) > 1:
            opinion_html = "".join(
                f'<div class="opinion">{p}</div>'
                for p in rest_parts
            )
        elif rest_parts:
            opinion_html = f'<div class="opinion">{rest_parts[0]}</div>'
        else:
            opinion_html = ""
        tgb_rows.append(f'<tr><td class="tb" style="color:var(--gold);text-align:center">{name}{name_meta}</td><td class="t2">{title_part}{next_day_html}{opinion_html} {sym_tags}</td></tr>')

    tgb_bull_count = tgb_directions.count("看多")
    tgb_bear_count = tgb_directions.count("看空")
    # ===== 次日大盘预期汇总 =====
    nd_tag_pat = r'【(?:次日大盘|大盘指数|明日大盘|大盘预期|大盘)】'
    next_day_views = []
    for i, name in enumerate(tgb_blogger_names):
        ai_summary = tgb_ai_results[i] if i < len(tgb_ai_results) else ""
        if not ai_summary:
            continue
        nd_m = re.search(nd_tag_pat + r'([^【]*)', ai_summary)
        if nd_m:
            nd_txt = nd_m.group(1).strip()
            if "看空" in nd_txt or "看跌" in nd_txt or "偏空" in nd_txt:
                nd_dir = "看空"
            elif "看多" in nd_txt or "看涨" in nd_txt or "偏多" in nd_txt:
                nd_dir = "看多"
            else:
                nd_dir = "震荡"
            next_day_views.append((name, nd_dir, nd_txt[:60]))
    if next_day_views:
        nd_bull = sum(1 for _, d, _ in next_day_views if d == "看多")
        nd_bear = sum(1 for _, d, _ in next_day_views if d == "看空")
        nd_flat = sum(1 for _, d, _ in next_day_views if d == "震荡")
        if nd_bull > nd_bear and nd_bull >= nd_flat:
            nd_consensus = f"多数看多({nd_bull}多/{nd_bear}空/{nd_flat}震荡)"
        elif nd_bear > nd_bull and nd_bear >= nd_flat:
            nd_consensus = f"多数看空({nd_bull}多/{nd_bear}空/{nd_flat}震荡)"
        elif nd_flat >= max(nd_bull, nd_bear):
            nd_consensus = f"偏震荡({nd_bull}多/{nd_bear}空/{nd_flat}震荡)"
        else:
            nd_consensus = f"分歧({nd_bull}多/{nd_bear}空/{nd_flat}震荡)"
        nd_details = "；".join(f"{n}:{d}" for n, d, _ in next_day_views[:5])
        nd_consensus += f"（{nd_details}）"
    else:
        nd_consensus = "暂无博主明确预期"

    if tgb_bull_count > tgb_bear_count:
        tgb_consensus = f"整体偏多({tgb_bull_count}看多/{tgb_bear_count}看空)"
    elif tgb_bear_count > tgb_bull_count:
        tgb_consensus = f"整体偏空({tgb_bear_count}看空/{tgb_bull_count}看多)"
    else:
        tgb_consensus = f"多空分歧({tgb_bull_count}看多/{tgb_bear_count}看空)"
    if tgb_symbols_all:
        tgb_consensus += f"；共同关注：{'、'.join(list(tgb_symbols_all)[:4])}"

    total_replies = sum(b.get("replies_today", 0) for b in tgb.get("bloggers", {}).values())
    tgb_sec = f"""<section class="sec">
<div class="sh"><span class="num">07</span> 淘股吧博主 <span class="meta">{blogger_date_label(tgb)} · {len(tgb.get("bloggers", {}))}位 · {total_replies}条跟帖{data_note}</span></div>
<table><colgroup><col style="width:64px"><col></colgroup>
<tr><th>博主</th><th>核心观点 + 标的</th></tr>
{"".join(tgb_rows)}</table>
<div class="lbox"><b>次日大盘：</b>{nd_consensus}</div>
<div class="lbox"><b>共识：</b>{tgb_consensus}</div></section>"""

    # ===== ⑩ 抖音 =====
    dy_ai_tasks = []
    dy_video_list = []
    for bi, b in enumerate(douyin.get("bloggers", [])):
        if not b.get("videos"): continue
        for v in b["videos"][:8]:
            transcript = v.get("transcript", "")
            title = v.get("title", "")
            transcript_s = trad_to_simp(transcript) if transcript else ""
            title_s = trad_to_simp(title)
            raw_for_ai = transcript_s or title_s
            dy_video_list.append((bi, v, title_s, transcript_s))
            dy_ai_tasks.append((raw_for_ai, f"抖音博主{b['name']}视频观点") if raw_for_ai and len(raw_for_ai.strip()) >= 10 else ("", ""))

    dy_ai_results = ai_summarize_batch_parallel(dy_ai_tasks)
    dy_items = []
    dy_symbols_all = set()
    ai_result_idx = 0

    def _dy_opinion_html(summary: str) -> str:
        """将AI总结的多个观点按【】拆分，每条观点带序号独立成行，过滤空观点和转录受限废话"""
        # 过滤转录受限/AI无法总结的废话（无条件过滤，无论长度）
        _junk_patterns = [
            "转录受限", "未提供标题", "无法凭空捏造", "原始内容中明确标注",
            "由于您提供", "缺失了", "无法具体分析", "内容过于简短",
            "仅表达了", "请提供", "需要更多信息", "无法在遵守",
            "请补充", "我将立即", "严苛标准",
        ]
        if any(j in summary for j in _junk_patterns):
            return ""
        parts = re.split(r'(?=【)', summary.strip())
        parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 8]
        if len(parts) > 1:
            return "".join(
                f'<span class="opinion">{p}</span>'
                for p in parts
            )
        if summary.strip() and len(summary.strip()) > 8:
            return f'<span class="opinion">{summary.strip()}</span>'
        return ""

    for bi, b in enumerate(douyin.get("bloggers", [])):
        if not b.get("videos"):
            dy_items.append(f'<div class="dy-empty">{b["name"]}：无今日视频更新</div>')
            continue
        for v in b["videos"][:8]:
            title_s = trad_to_simp(v.get("title", ""))
            transcript_s = trad_to_simp(v.get("transcript", "")) if v.get("transcript") else ""
            warning = v.get("warning", "")
            symbols_raw = v.get("symbols", [])
            symbols = extract_symbols_from_text(transcript_s or title_s)
            for s in symbols_raw:
                if s not in symbols: symbols.append(s)
            symbols = symbols[:6]

            ai_summary = dy_ai_results[ai_result_idx] if ai_result_idx < len(dy_ai_results) else ""
            ai_result_idx += 1
            used_ai = bool(ai_summary)
            if not ai_summary:
                for retry in range(3):
                    ai_summary = ai_summarize_opinions(transcript_s or title_s, context=f"抖音视频{title_s[:30]}")
                    if ai_summary: break
                    print(f"  [WARN] 抖音AI总结失败（{title_s[:30]}），重试 {retry+1}/3...", file=sys.stderr)
            if ai_summary:
                used_ai = True
                for s in re.findall(r'【([^】]+)】', ai_summary):
                    if s not in symbols: symbols.append(s)
                symbols = symbols[:6]
                summary = ai_summary
            else:
                # 精炼兜底：不允许输出"[AI总结失败]"或原文截断，提取含投资关键词的核心句
                print(f"  [WARN] 抖音AI总结3次失败，使用精炼兜底（{title_s[:30]}）", file=sys.stderr)
                summary = douyin_fallback_summary(transcript_s or title_s) or title_s[:60]

            if transcript_s:
                bull_signals = sum(1 for kw in ["看多","看涨","利好","乐观","涨","反弹","机会","买入","首选","强","突破","超预期","涨价","扩产","紧缺","需求","增长"] if kw in transcript_s)
                bear_signals = sum(1 for kw in ["看空","看跌","利空","悲观","跌","恐慌","风险","回避","弱","破位","杀跌","暴跌","降价","过剩","减产"] if kw in transcript_s)
                direction = "利好" if bull_signals > bear_signals + 2 else "利空" if bear_signals > bull_signals + 2 else "关注"
            else:
                direction = v.get("direction", "关注")

            for s in symbols[:4]: dy_symbols_all.add(s)
            # 方向徽章：只保留利好/利空，"关注"不显示徽章
            dir_tag = '<span class="bg_">利好</span>' if direction == "利好" else '<span class="bo">利空</span>' if direction == "利空" else ""
            # 无意义标题（纯视频ID）不显示，避免占用版面
            display_title = title_s[:50] if not re.fullmatch(r'视频\s*\d{10,}', title_s.strip()) else ""
            title_html = f'<strong>{display_title}</strong>' if display_title else ""
            tag_spans = "".join(f'<span class="tag y">{s}</span>' for s in symbols[:4])
            sym_tags_html = f'<div class="dy-tags">{tag_spans}</div>' if symbols else ""
            # 观点为空（转录受限被过滤）时整条视频不显示，避免空块
            opinion_html = _dy_opinion_html(summary)
            if not opinion_html:
                continue
            dy_items.append(
                f'<div class="dy">'
                f'<div class="dy-head"><span class="dyt">{dir_tag}</span>{title_html}</div>'
                f'<p>{opinion_html}</p>'
                f'{sym_tags_html}'
                f'</div>'
            )

    dy_name_parts = [b["name"] for b in douyin.get("bloggers", []) if b.get("videos")]
    dy_name = " · ".join(dy_name_parts) if dy_name_parts else "抖音博主"
    dy_lbox_symbols = " ".join(f'<span class="tag y">{s}</span>' for s in list(dy_symbols_all)[:8])
    dy_sec = f"""<section class="sec">
<div class="sh"><span class="num">08</span> 抖音博主 <span class="meta">{blogger_date_label(douyin)} · {dy_name}{data_note}</span></div>
{"".join(dy_items)}
<div class="lbox"><b>线索：</b>见视频观点汇总 {dy_lbox_symbols}</div>
</section>"""

    # ===== ⑪ 未来大事件（时间轴布局 v4.6.0）=====
    ev_events = events.get("events", [])
    # 按日期分组，同一日期的事件聚合到一个时间节点
    ev_by_date = {}
    for e in ev_events:
        date = e.get("date", "")
        ev_by_date.setdefault(date, []).append(e)

    ev_timeline = []
    for date, date_events in ev_by_date.items():
        # 节点标题：日期 + 当天事件数
        date_items = []
        for e in date_events:
            etype = e.get("type", "")
            event_full = e.get("description", "") or e.get("event", "")
            importance = e.get("importance", "一般")
            country = e.get("country", "")
            type_cls = {"宏观": "bbl", "消费": "bgd", "解禁": "bo", "PMI": "br", "央行": "br",
                        "通胀": "bo", "就业": "bgd", "货币": "br", "外汇": "bbl", "原油": "bbl",
                        "业绩": "br", "IPO": "bgd", "会议": "bbl", "产品": "bcy", "政策": "br",
                        "财报": "br", "定期": "bbl"}.get(etype, "bbl")
            country_flag = "🇨🇳" if country == "中国" else "🌍"
            etime = e.get("time", "")
            time_str = f'<span class="tl-t">{etime}</span>' if etime else ""
            date_items.append(
                f'<div class="tl-item">'
                f'<span class="tl-type {type_cls}">{etype}</span>'
                f'{time_str}'
                f'<span class="tl-ev">{country_flag} {event_full}</span>'
                f'</div>'
            )
        date_label = date.replace("/", ".")
        ev_timeline.append(
            f'<div class="tl-node">'
            f'<div class="tl-date"><span class="tl-dot"></span><b>{date_label}</b><em>{len(date_events)}件</em></div>'
            f'<div class="tl-body">{"".join(date_items)}</div>'
            f'</div>'
        )

    # range按实际入选事件日期计算（重磅发布会可超出7天窗口，JSON里的range可能滞后）
    ev_dates_full = sorted(e.get("date_full", "") for e in ev_events if e.get("date_full"))
    if ev_dates_full:
        ev_range_label = f"{ev_dates_full[0]} ~ {ev_dates_full[-1]}"
    else:
        ev_range_label = events.get("range", "")

    events_sec = f"""<section class="sec">
<div class="sh"><span class="num">09</span> 未来大事件 <span class="meta">{ev_range_label}</span></div>
<div class="timeline">
{''.join(ev_timeline) if ev_timeline else '<div class="t3" style="padding:8px 0">暂无未来事件数据</div>'}
</div></section>"""

    # ===== ⑫ 策略研判（结构化投资逻辑）=====
    long_items = []
    watch_items = []
    risk_items = []

    # 做多逻辑：新闻利好 + 龙虎榜资金 + 机构推荐（只显示板块/概念，不显示个股）
    def _sector_label(stocks_list, title=""):
        """将个股列表映射为板块/概念标签，返回【板块A/板块B】格式"""
        sectors = []
        for s in stocks_list:
            sec = stock_to_sector(s)
            if sec and sec not in sectors:
                sectors.append(sec)
        if sectors:
            return f"【{'/'.join(sectors)}】"
        # 兜底：从标题推断行业
        ind = infer_industry(title)
        return f"【{ind}】" if ind != "综合" else ""

    for n in news_items[:10]:
        if n.get("type") == "利好" and n.get("stocks"):
            title_s = n['title'][:40]
            label = _sector_label(n.get("stocks", [])[:3], title_s)
            long_items.append(f"{label}看多，催化：{title_s}")
    # 补充龙虎榜买入标的（只显示板块）
    for s in lhb_top_buy[:3]:
        name = s.get("名称", "")
        net_buy = s.get("净买额亿", 0)
        buy_val = s.get("买入额亿", 0)
        if net_buy > 1.0 and buy_val > 2.0:  # 大单介入
            label = _sector_label([name])
            long_items.append(f"{label}看多，龙虎榜净买{net_buy:.1f}亿，游资大买{buy_val:.1f}亿")
    # 补充机构推荐（只显示板块）
    for r in reports[:3]:
        stock = r.get("stock", "")
        rate = r.get("rate", "")
        if rate in ["买入", "增持", "推荐"] and stock:
            label = _sector_label([stock], r.get('title', ''))
            long_items.append(f"{label}看多，机构{rate}，{r.get('title', '')[:30]}")
    if not long_items:
        long_items = ["暂无明确做多信号，等待催化出现"]

    # 观察等待：待验证事件 + 板块异动 + 情绪拐点
    # 从未来事件提取
    for e in events.get("events", [])[:3]:
        date = e.get("date", "")
        event = e.get("event", "")[:30]
        impact = e.get("impact", "中性")
        if impact in ["利好", "利空"]:
            watch_items.append(f"{date} {event}（{impact}，待验证）")
    # 从情绪拐点
    if chart_scores and len(chart_scores) >= 3:
        recent_trend = chart_scores[-1] - chart_scores[-3]
        if recent_trend > 10:
            watch_items.append(f"情绪快速回升+{recent_trend:.0f}，等确认持续性再动")
        elif recent_trend < -10:
            watch_items.append(f"情绪快速下滑{recent_trend:.0f}，等企稳信号")
    # 从板块多空
    if survey_stats.get("by_sector_sorted"):
        top = survey_stats["by_sector_sorted"][0]
        watch_items.append(f"【{top['sector']}】多空分歧大（▲{top.get('bull',0)}▼{top.get('bear',0)}），等方向确认")
    if len(watch_items) < 2:
        watch_items.append("暂无重大事件，保持仓位观察")

    # ===== 风险提示：多源融合（情绪极端 + 监管 + 共识见顶 + 利空 + 大卖）=====
    # ① 极端情绪：恐慌贪婪指数 ≥75（极度亢奋）或 ≤25（极度恐慌）均构成风险
    p_score = panic.get("score", 50)
    p_status = panic.get("status", "中性")
    if p_score >= 75:
        risk_items.append(f"情绪指数{p_score:.0f}（{p_status}），短线过热追高回撤风险大，持有强势股可考虑逢高减仓")
    elif p_score <= 25:
        risk_items.append(f"情绪指数{p_score:.0f}（{p_status}），恐慌杀跌尚未见底，勿盲目抄底")
    # ② 零看空极端共识：某板块看多≥3且零看空且参与者≥4 → 一致性看多见顶信号
    #    只保留前2个代表板块，避免多条重复共识挤占版面
    _consensus_count = 0
    for sd in survey_stats.get("by_sector_sorted", [])[:10]:
        sector = sd.get("sector", "")
        bull = sd.get("bull", 0)
        bear = sd.get("bear", 0)
        bloggers = sd.get("blogger_count", 0)
        if bull >= 3 and bear == 0 and bloggers >= 4:
            risk_items.append(f"【{sector}】{bull}人看多0人看空，极端共识往往预示短期顶部，勿追高，持有者可减仓")
            _consensus_count += 1
            if _consensus_count >= 2:
                break
    # ③ 高位股监管风险：新闻标题命中停牌/暂停/核查/异常交易/监管/问询/处罚
    #    ⚠️ 必须扫描全量新闻（valid_news 仅前10条精选，监管新闻常排不进去）
    #    ⚠️ 排除外交/国际类"暂停"（如"暂停与伊朗接触/贸易往来"），只留A股监管信号
    _reg_kw = ["停牌", "暂停", "核查", "异常交易", "监管", "问询", "处罚", "关注函", "警示函"]
    _reg_excl = ["伊朗", "贸易往来", "外交", "以色列", "巴勒斯坦", "谈判", "关税", "美联储", "欧洲"]
    _reg_found = 0
    for n in all_news:
        t = n.get("title", "")
        if any(k in t for k in _reg_kw) and not any(e in t for e in _reg_excl) \
                and ("利空" in n.get("type", "") or "中性" in n.get("type", "")):
            stocks_str = ", ".join([s for s in n.get("stocks", [])[:2] if not s.startswith("90.")])
            risk_items.append(f"监管信号：{t[:44]}" + (f"（{stocks_str}）" if stocks_str else ""))
            _reg_found += 1
            if _reg_found >= 4:  # 监管类最多取4条，防止全量扫描冗余
                break
    # ④ 打板接力恶化：连板率极低 或 破板率高 与高情绪背离
    p_comp = panic.get("components", {})
    lianban_rate = p_comp.get("lianban_rate", 50)
    broken_rate = (panic.get("details", {}) or {}).get("broken_rate", 0)
    if lianban_rate <= 10 and broken_rate >= 25:
        risk_items.append(f"接力意愿弱：连板率{lianban_rate:.0f}%且破板率{broken_rate:.0f}%，高位接力情绪恶化，谨防补涨龙跌停引发踩踏")
    elif lianban_rate <= 10:
        risk_items.append(f"接力意愿弱：连板率仅{lianban_rate:.0f}%，高位股缺乏承接，谨防补涨龙跌停引发踩踏")
    # ⑤ 结构化看空观点（博主多空统计 analyses，淘股吧+雪球）
    for a in survey.get("analyses", [])[:10]:
        if a.get("direction") == "看空":
            blogger = a.get("blogger", "")
            reason = (a.get("reason") or "")[:40]
            if reason:
                risk_items.append(f"【{blogger}】看空：{reason}")
    # ⑥ 利空新闻（带个股，前10条）
    for n in news_items[:10]:
        if n.get("type") == "利空" and n.get("stocks"):
            stocks_str = ", ".join([s for s in n.get("stocks", [])[:2] if not s.startswith("90.")])
            risk_items.append(f"【{stocks_str or '市场'}】看空，{n['title'][:40]}")
    # ⑦ 龙虎榜游资大卖
    for s in lhb_top_buy[-3:]:
        net_buy = s.get("净买额亿", 0)
        sell_val = s.get("卖出额亿", 0)
        if net_buy < -0.5 and sell_val > 2.0:
            risk_items.append(f"【{s.get('名称','')}】游资大卖{sell_val:.1f}亿，净卖{abs(net_buy):.1f}亿")
    # ⑧ Serenity看空
    for s in serenity.get("opinions", [])[:2]:
        if s.get("direction") == "看空":
            risk_items.append(f"【{s.get('symbol','')}】Serenity看空：{s.get('summary','')[:40]}")
    # 去重（保留顺序）
    seen = set()
    deduped = []
    for it in risk_items:
        if it not in seen:
            seen.add(it)
            deduped.append(it)
    risk_items = deduped
    # 风险按优先级排序：情绪 > 接力 > 共识 > 监管 > 个股类（博主看空/大卖）
    def _risk_rank(it):
        if it.startswith("情绪指数"):
            return 0
        if it.startswith("接力意愿"):
            return 1
        if it.startswith("【") and "极端共识" in it:
            return 2
        if it.startswith("监管信号"):
            return 3
        return 4
    risk_items.sort(key=_risk_rank)
    if not risk_items:
        risk_items = ["暂无明确风险信号，保持常规风控"]

    strategy_sec = f"""<section class="sec" style="margin-bottom:0">
<div class="sh"><span class="num">10</span> 策略研判 <span class="meta">全源综合{data_note}</span></div>
<div class="strat">
<div class="sc long"><h4><span class="dot"></span>做多方向</h4><ul>{"".join(f'<li>{item}</li>' for item in long_items[:5])}</ul></div>
<div class="sc wait"><h4><span class="dot"></span>观察等待</h4><ul>{"".join(f'<li>{item}</li>' for item in watch_items[:5])}</ul></div>
<div class="sc risk"><h4><span class="dot"></span>风险提示</h4><ul>{"".join(f'<li>{item[:80]}</li>' for item in risk_items[:7])}</ul></div>
</div></section>"""

    # ===== Chart JS（纸感配色，单图双线：情绪 + 上证，可切换显隐）=====
    chart_js_data = json.dumps(chart_scores)
    chart_js_labels = json.dumps(chart_labels)

    chart_js = f"""<script>
(function(){{
  const canvas=document.getElementById('sentChart');const tip=document.getElementById('chartTip');if(!canvas||!tip)return;
  const strip=document.getElementById('cycleStrip');
  const data={chart_js_merged};const labels=data.map(d=>d.date);
  const cyc=data.map(d=>({{stage:d.stage,color:d.color,note:d.note}}));
  const dpr=window.devicePixelRatio||1;const pad={{t:26,b:38,l:28,r:40}};
  let W,H,xStep,animProg=0,showSent=true,showIdx=true;
  // 上证动态y轴范围（在数据里取有效idx）
  const idxVals=data.map(d=>d.idx).filter(v=>v!=null);
  let iMin=Math.min.apply(null,idxVals),iMax=Math.max.apply(null,idxVals);const iSpan=(iMax-iMin)||1;
  iMin=iMin-iSpan*0.15;iMax=iMax+iSpan*0.15;
  function yS(v,minV,maxV){{return pad.t+(H-pad.t-pad.b)*(1-(v-minV)/(maxV-minV))}}
  function buildStrip(){{if(!strip)return;strip.innerHTML='';const cw=canvas.getBoundingClientRect().width;const x0=pad.l,x1=cw-pad.r;const step=(x1-x0)/(data.length-1);cyc.forEach((c,i)=>{{if(!c.stage)return;const seg=document.createElement('div');seg.className='seg';seg.style.background=c.color;seg.style.width=(step+1)+'px';seg.textContent=c.stage;strip.appendChild(seg)}});}}
  function size(){{const r=canvas.getBoundingClientRect();W=r.width;H=200;canvas.width=W*dpr;canvas.height=H*dpr;const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);xStep=(W-pad.l-pad.r)/(data.length-1);buildStrip();}}
  function drawLine(ctx,key,minV,maxV,color,fill,dotColor,prog,lastColor){{const vals=data.map(d=>d[key]);const pts=[];data.forEach((d,i)=>{{if(d[key]==null)return;pts.push({{x:pad.l+i*xStep,y:yS(d[key],minV,maxV),v:d[key],i}})}});if(!pts.length)return;const n=Math.max(1,Math.ceil(pts.length*prog));const arr=pts.slice(0,n);ctx.beginPath();ctx.moveTo(arr[0].x,arr[0].y);arr.forEach(p=>ctx.lineTo(p.x,p.y));ctx.strokeStyle=color;ctx.lineWidth=2;ctx.lineJoin='round';ctx.lineCap='round';ctx.stroke();arr.slice(0,-1).forEach(p=>{{ctx.beginPath();ctx.arc(p.x,p.y,2.5,0,Math.PI*2);ctx.fillStyle=dotColor;ctx.fill()}});const lp=arr[arr.length-1];if(lp){{ctx.beginPath();ctx.arc(lp.x,lp.y,6,0,Math.PI*2);ctx.fillStyle=dotColor;ctx.fill();ctx.beginPath();ctx.arc(lp.x,lp.y,3,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();}}}}
  function draw(prog){{const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);ctx.strokeStyle='rgba(140,132,115,.2)';ctx.lineWidth=1;
    // 左轴（情绪0-100）网格
    if(showSent){{[0,25,50,75,100].forEach(v=>{{const y=yS(v,0,100);ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(W-pad.r,y);ctx.stroke()}});ctx.fillStyle='rgba(107,101,85,.5)';ctx.font='500 8px "JetBrains Mono"';ctx.textAlign='right';[0,50,100].forEach(v=>{{const y=yS(v,0,100);ctx.fillText(v,pad.l-2,y+3)}})}}
    // 右轴（上证范围）网格
    if(showIdx){{[0.25,0.5,0.75].forEach(f=>{{const v=iMin+(iMax-iMin)*f;const y=yS(v,iMin,iMax);ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(W-pad.r,y);ctx.stroke()}});ctx.fillStyle='rgba(27,79,114,.6)';ctx.font='500 8px "JetBrains Mono"';ctx.textAlign='left';[0.25,0.5,0.75].forEach(f=>{{const v=iMin+(iMax-iMin)*f;const y=yS(v,iMin,iMax);ctx.fillText(Math.round(v),W-pad.r+4,y+3)}});}}
    if(showSent)drawLine(ctx,'sent',0,100,'#C0392B','rgba(192,57,43,.15)','rgba(192,57,43,.4)',prog,'#C0392B');
    if(showIdx)drawLine(ctx,'idx',iMin,iMax,'#1B4F72','rgba(27,79,114,.15)','rgba(27,79,114,.4)',prog,'#1B4F72');
    if(prog>=1){{ctx.fillStyle='rgba(107,101,85,.5)';ctx.font='500 8px "JetBrains Mono"';ctx.textAlign='center';labels.forEach((l,i)=>{{if(l)ctx.fillText(l,pad.l+i*xStep,H-26)}})}}}}
  function animate(){{animProg+=0.025;if(animProg>1)animProg=1;draw(animProg);if(animProg<1)requestAnimationFrame(animate)}}size();animProg=0;animate();
  let resizeTimer;window.addEventListener('resize',()=>{{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{{size();draw(animProg)}},100)}});
  // ===== 切换显隐 =====
  const tgSent=document.getElementById('tgSent'),tgIdx=document.getElementById('tgIdx');
  function toggle(tg,k){{if(k==='sent')showSent=!showSent;else showIdx=!showIdx;tg.classList.toggle('off',!(k==='sent'?showSent:showIdx));draw(animProg);}}
  if(tgSent)tgSent.addEventListener('click',()=>toggle(tgSent,'sent'));
  if(tgIdx)tgIdx.addEventListener('click',()=>toggle(tgIdx,'idx'));
  // ===== tooltip =====
  const canvasBox=canvas.parentElement;
  canvasBox.addEventListener('mousemove',e=>{{if(animProg<1)return;const rect=canvas.getBoundingClientRect();const mx=e.clientX-rect.left;let closest=null,minDist=Infinity;data.forEach((d,i)=>{{const x=pad.l+i*xStep;const dist=Math.abs(x-mx);if(dist<minDist){{minDist=dist;closest={{d,i}}}}}});if(!closest||minDist>30){{tip.style.opacity='0';return}}const p=closest.d;let vs=[];if(showSent&&p.sent!=null)vs.push('情绪'+Math.round(p.sent));if(showIdx&&p.idx!=null)vs.push('上证'+p.idx.toFixed(1));tip.querySelector('.v').textContent=vs.join(' · ')||'-';tip.querySelector('.d').textContent=p.date+(p.stage?' · '+p.stage:'');const tx=pad.l+closest.i*xStep;let ty=pad.t+(H-pad.t-pad.b)*(1-(showSent?p.sent:50)/100);if(!showSent)ty=pad.t+(H-pad.t-pad.b)*0.5;ty-=tip.offsetHeight+10;if(ty<2)ty=pad.t+2;if(ty>H-tip.offsetHeight-2)ty=H-tip.offsetHeight-2;tip.style.left=Math.max(4,Math.min(W-tip.offsetWidth-4,tx))+'px';tip.style.top=ty+'px';tip.style.opacity='1';draw(animProg);const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.strokeStyle='rgba(140,132,115,.25)';ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(pad.l+closest.i*xStep,pad.t);ctx.lineTo(pad.l+closest.i*xStep,H-pad.b);ctx.stroke();ctx.setLineDash([]);}});
  canvasBox.addEventListener('mouseleave',()=>{{tip.style.opacity='0';if(animProg>=1)draw(1)}});
}})();
</script>"""

    # ===== 组装完整HTML（报刊版式）=====
    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>每日简报 - {today_display}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;600;700;900&family=Noto+Sans+SC:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
{css_block}
</head>
<body>
<div class="page">
{masthead}
{lead}
{quote_html}
<div class="cols">
{news_sec}
{lhb_sec}
{ss_sec}
{serenity_sec}
{tgb_sec}
{dy_sec}
{yb_sec}
{survey_sec}
<div class="fw">
{events_sec}
</div>
<div class="fw">
{strategy_sec}
</div>
</div>
<div class="ft">每日简报 · <span>报刊版</span> · {today_display}</div>
</div>
{chart_js}
</body>
</html>"""

    return full_html


if __name__ == "__main__":
    today = get_date()
    trade_date = get_recent_trade_date(today)

    print(f"编译简报: {today} (交易日: {trade_date})", file=sys.stderr)

    html = build_html(today, trade_date)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{today}简报.html"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"OK: {output_path}")
    print(f"Size: {len(html):,} chars")

    # 输出交付按钮
    abs_path = str(output_path).replace("\\", "/")
    encoded = quote(abs_path, safe="/:")
    button = f'<a href="file:///{encoded}" style="display:inline-block;padding:12px 28px;font-family:\'Microsoft YaHei\',sans-serif;font-size:15px;font-weight:700;color:#0b0f19;background:linear-gradient(135deg,#fbbf24,#f59e0b);border-radius:8px;text-decoration:none;box-shadow:0 4px 14px rgba(245,158,11,.35);border:1px solid rgba(255,255,255,.15);">📄 打开今日简报</a>'
    print(f"BUTTON:{button}")
