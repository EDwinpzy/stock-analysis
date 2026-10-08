#!/usr/bin/env python3
"""
市场情绪综合强度计算器（v3 开盘啦爬虫版）

基于 kaipanla-crawler 的完整数据，反推权重计算综合情绪强度。
数值越大情绪越高涨，0-100分制。

权重（反推自用户校准值 [50,91,73,92,95]，scale=0.9342, offset=32.22）:
- 赚钱效应: 40.9% (昨日涨停今表现 + 昨日连板今表现 + 昨日破板今表现)
- 涨跌比:   35.3% (上涨家数 / 下跌家数)
- 趋势强度: 18.1% (百日新高 - 大幅回撤)
- 涨停净额:  4.8% (涨停数 - 跌停数)
- 封板质量:  0.8% (1 - 破板率)
- 接力意愿:  0.3% (连板率)
- 梯队接力: 15%混合 (2026-08-25新增：原六维×0.85 + 梯队接力×0.15)
  开盘啦「昨日XX表现」细分口径——首板/二板/三板以上/连板/炸板今日表现，
  东财昨日涨停池(stock_zt_pool_previous_em)+炸板池合并今日快照计算，非ST过滤；
  打板类收盘口径与对应梯队等价不重复计，成交前十/ST首板不入指数

额外输出（供每日简报补充数据源）:
- 连板梯队详情（含题材标签）
- 涨停原因板块（含封单额/涨停时间）
- 板块强度排名
- 龙虎榜数据
- 大幅回撤个股
- 市场评价

兼容旧版 panic_today.json 格式，build_briefing.py 无需修改即可使用。
"""

import json
import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# 添加脚本目录到 path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from runtime_paths import get_data_dir

DATA_DIR = get_data_dir(Path(SCRIPT_DIR).parent)

from kaipanla_crawler import KaipanlaCrawler


# ===== 归一化工具 =====

def normalize(value, min_val, max_val, inverse=False):
    """将数值归一化到 0-100"""
    if max_val == min_val:
        return 50.0
    score = (value - min_val) / (max_val - min_val) * 100
    if inverse:
        score = 100 - score
    return max(0.0, min(100.0, score))


# ===== 各维度计算 =====

def calc_profit_effect(ladder_row):
    """赚钱效应 (40.4%) — 昨日涨停/连板/破板今表现之和"""
    yesterday_limit = ladder_row.get("昨日涨停今表现(%)", 0)
    yesterday_consecutive = ladder_row.get("昨日连板今表现(%)", 0)
    yesterday_broken = ladder_row.get("昨日破板今表现(%)", 0)
    raw = yesterday_limit + yesterday_consecutive + yesterday_broken
    # 范围: -5 ~ +18 → 0 ~ 100
    score = normalize(raw, min_val=-5, max_val=18)
    return {
        "score": round(score, 1),
        "raw": round(raw, 2),
        "yesterday_limit": yesterday_limit,
        "yesterday_consecutive": yesterday_consecutive,
        "yesterday_broken": yesterday_broken,
    }


def calc_limit_net(daily_data):
    """涨停净额 (20.0%) — 涨停数 - 跌停数"""
    limit_up = daily_data.get("涨停数", 0)
    limit_down = daily_data.get("跌停数", 0)
    raw = limit_up - limit_down
    # 范围: -80 ~ +140 → 0 ~ 100
    score = normalize(raw, min_val=-80, max_val=140)
    return {
        "score": round(score, 1),
        "raw": raw,
        "limit_up": limit_up,
        "limit_down": limit_down,
    }


def calc_up_down_ratio(daily_data):
    """涨跌比 (19.3%) — 上涨家数 / 下跌家数"""
    up = daily_data.get("上涨家数", 0)
    down = daily_data.get("下跌家数", 0)
    raw = up / down if down > 0 else 10.0
    # 范围: 0.3 ~ 7 → 0 ~ 100
    score = normalize(raw, min_val=0.3, max_val=7)
    return {
        "score": round(score, 1),
        "raw": round(raw, 2),
        "up_count": up,
        "down_count": down,
    }


def calc_lianban_rate(daily_data):
    """接力意愿 (18.3%) — 连板率"""
    raw = daily_data.get("连板率", 0)
    # 范围: 0 ~ 35 → 0 ~ 100
    score = normalize(raw, min_val=0, max_val=35)
    return {
        "score": round(score, 1),
        "raw": raw,
    }


def calc_board_quality(ladder_row):
    """封板质量 (1.0%) — 1 - 破板率"""
    broken_rate = ladder_row.get("今日涨停破板率(%)", 30)
    raw = 100 - broken_rate
    # 破板率范围: 0 ~ 55, 反转 → 0 ~ 100
    score = normalize(broken_rate, min_val=0, max_val=55, inverse=True)
    return {
        "score": round(score, 1),
        "raw": round(raw, 2),
        "broken_rate": broken_rate,
    }


def calc_trend_strength(new_high, withdrawal_count):
    """趋势强度 (1.0%) — 百日新高 - 大幅回撤"""
    raw = new_high - withdrawal_count
    # 范围: -15 ~ +15 → 0 ~ 100
    score = normalize(raw, min_val=-15, max_val=15)
    return {
        "score": round(score, 1),
        "raw": raw,
        "new_high": new_high,
        "withdrawal_count": withdrawal_count,
    }


def _prev_trade_day(date_str: str) -> str:
    """前一交易日（跳过周末）"""
    d = datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def calc_ladder_relay(actual_date: str, ladder_row: dict) -> dict:
    """梯队接力表现 — 开盘啦「昨日XX表现」细分口径（首板/二板/三板以上/连板/炸板）
    梯队数据源: 东财昨日涨停池(stock_zt_pool_previous_em，自带次日涨跌幅+昨日连板数)；
    炸板表现直接复用开盘啦连板梯队的「昨日破板今表现(%)」。
    打板类（打首板/打二板/打板）收盘口径与对应梯队表现等价，不重复计；
    昨日成交前十/昨日ST首板为边缘口径，不入指数。非ST过滤。
    """
    empty = {"score": 50.0, "sub": {}, "note": ""}
    if not actual_date:
        return {**empty, "note": "无数据日期"}
    try:
        import akshare as ak
    except ImportError:
        return {**empty, "note": "akshare未安装"}

    prev_day = _prev_trade_day(actual_date)
    ymd = prev_day.replace("-", "")
    try:
        pool = ak.stock_zt_pool_previous_em(date=ymd)
    except Exception as e:
        return {**empty, "note": f"昨日涨停池获取失败:{str(e)[:60]}"}
    if pool is None or len(pool) == 0:
        return {**empty, "note": f"昨日({prev_day})涨停池为空"}

    pool = pool[~pool["名称"].astype(str).str.contains("ST", na=False)]
    chg = pool["涨跌幅"].astype(float)
    lb = pool["昨日连板数"].astype(float)

    def _mean(mask):
        v = chg[mask]
        return round(float(v.mean()), 2) if len(v) > 0 else None

    sub_pct = {
        "首板表现": _mean(lb == 1),
        "二板表现": _mean(lb == 2),
        "三板以上表现": _mean(lb >= 3),
        "连板表现": _mean(lb >= 2),
    }
    # 炸板表现：开盘啦「昨日破板今表现(%)」（连板梯队接口已有，无需额外请求）
    try:
        zb = ladder_row.get("昨日破板今表现(%)")
        if zb is not None:
            sub_pct["炸板表现"] = round(float(zb), 2)
    except (TypeError, ValueError):
        pass

    # 各梯队表现映射0-100（高板波动大，区间更宽）
    ranges = {"首板表现": (-6, 6), "二板表现": (-8, 8), "三板以上表现": (-10, 10),
              "连板表现": (-8, 8), "炸板表现": (-6, 6)}
    weights = {"首板表现": 0.35, "二板表现": 0.25, "三板以上表现": 0.15,
               "连板表现": 0.10, "炸板表现": 0.25}
    total_w, acc = 0.0, 0.0
    sub_score = {}
    for k, v in sub_pct.items():
        if v is None:
            continue
        lo, hi = ranges[k]
        s = normalize(v, lo, hi)
        sub_score[k] = round(s, 1)
        acc += s * weights[k]
        total_w += weights[k]

    if total_w == 0:
        return {**empty, "note": "无有效梯队数据"}

    return {
        "score": round(acc / total_w, 1),
        "sub": sub_score,
        "sub_pct": sub_pct,
        "pool_count": int(len(pool)),
        "data_date": actual_date,
        "prev_day": prev_day,
        "note": "",
    }


# ===== 状态判定 =====

def get_status(score: float) -> str:
    """根据分数判断状态"""
    if score < 20:
        return "极度低迷"
    elif score < 35:
        return "偏弱"
    elif score < 50:
        return "温和偏多"
    elif score < 65:
        return "偏多活跃"
    elif score < 80:
        return "情绪高涨"
    else:
        return "极度亢奋"


def get_status_color(score: float) -> str:
    """根据分数返回CSS颜色变量"""
    if score < 25:
        return "var(--dn)"
    elif score < 45:
        return "var(--warn)"
    elif score < 55:
        return "var(--ink2)"
    else:
        return "var(--up)"


# ===== 主函数 =====

def main():
    # --date 参数支持
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        today = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else datetime.now().strftime("%Y-%m-%d")
    else:
        today = datetime.now().strftime("%Y-%m-%d")

    print(f"=== 市场情绪综合强度计算 ({today}) ===\n", file=sys.stderr)

    crawler = KaipanlaCrawler()

    # 1. 获取日度数据
    print("[1/6] 获取日度数据...", file=sys.stderr)
    try:
        daily = crawler.get_daily_data(today)
        if isinstance(daily, dict) and daily.get("涨停数", 0) == 0:
            # 可能是非交易日，尝试回退
            raise ValueError("无数据")
        daily_data = daily if hasattr(daily, '__getitem__') else {}
        if hasattr(daily, 'to_dict'):
            daily_data = daily.to_dict()
        actual_date = str(daily_data.get("日期", today))
    except Exception as e:
        print(f"  [WARN] 当日数据获取失败，尝试回退: {e}", file=sys.stderr)
        # 回退到最近交易日
        dt = datetime.strptime(today, "%Y-%m-%d")
        for _ in range(5):
            dt -= timedelta(days=1)
            while dt.weekday() >= 5:
                dt -= timedelta(days=1)
            try:
                daily = crawler.get_daily_data(dt.strftime("%Y-%m-%d"))
                if hasattr(daily, 'to_dict'):
                    daily_data = daily.to_dict()
                else:
                    daily_data = daily
                if daily_data.get("涨停数", 0) > 0:
                    actual_date = dt.strftime("%Y-%m-%d")
                    break
            except:
                continue
        else:
            daily_data = {}
            actual_date = today

    if not daily_data:
        # 完全无数据，输出默认值
        result = {
            "date": today, "data_date": today,
            "score": 50, "status": "中性",
            "comment": "", "note": "数据获取失败",
            "components": {
                "profit_effect": 50, "limit_net": 50,
                "up_down_ratio": 50, "lianban_rate": 50,
                "board_quality": 50, "trend_strength": 50,
            },
            "details": {},
            "extra": {},
        }
        print(json.dumps(result, ensure_ascii=False))
        return

    print(f"  涨停{daily_data.get('涨停数','?')}/跌停{daily_data.get('跌停数','?')} | "
          f"上涨{daily_data.get('上涨家数','?')}/下跌{daily_data.get('下跌家数','?')} | "
          f"连板率{daily_data.get('连板率','?')}% [数据日期:{actual_date}]", file=sys.stderr)

    # 2. 获取连板梯队数据
    print("[2/6] 获取连板梯队...", file=sys.stderr)
    try:
        ladder_df = crawler.get_limit_up_ladder(actual_date)
        ladder_row = ladder_df.iloc[0].to_dict() if len(ladder_df) > 0 else {}
    except Exception as e:
        print(f"  [WARN] 连板梯队获取失败: {e}", file=sys.stderr)
        ladder_row = {}

    print(f"  连板率:{ladder_row.get('连板率(%)','?')} | 破板率:{ladder_row.get('今日涨停破板率(%)','?')} | "
          f"昨日涨停今表现:{ladder_row.get('昨日涨停今表现(%)','?')}% | "
          f"市场评价:{ladder_row.get('市场评价','?')}", file=sys.stderr)

    # 3. 获取百日新高
    print("[3/6] 获取百日新高...", file=sys.stderr)
    try:
        new_high = crawler.get_new_high_data(actual_date)
        new_high = int(new_high) if new_high else 0
    except:
        new_high = 0

    # 4. 大幅回撤
    withdrawal_count = int(daily_data.get("大幅回撤家数", 0))

    # ===== 计算各维度 =====
    print("[4/6] 计算各维度分数...", file=sys.stderr)

    profit = calc_profit_effect(ladder_row)
    limit_net = calc_limit_net(daily_data)
    ratio = calc_up_down_ratio(daily_data)
    lianban = calc_lianban_rate(daily_data)
    board_q = calc_board_quality(ladder_row)
    trend = calc_trend_strength(new_high, withdrawal_count)
    relay = calc_ladder_relay(actual_date, ladder_row)

    print(f"  赚钱效应: {profit['score']} (原始:{profit['raw']})", file=sys.stderr)
    print(f"  涨停净额: {limit_net['score']} (原始:{limit_net['raw']})", file=sys.stderr)
    print(f"  涨跌比:   {ratio['score']} (原始:{ratio['raw']})", file=sys.stderr)
    print(f"  接力意愿: {lianban['score']} (原始:{lianban['raw']}%)", file=sys.stderr)
    print(f"  封板质量: {board_q['score']} (破板率:{board_q['broken_rate']}%)", file=sys.stderr)
    print(f"  趋势强度: {trend['score']} (原始:{trend['raw']})", file=sys.stderr)
    if relay.get("note"):
        print(f"  梯队接力: 50中性 ({relay['note']})", file=sys.stderr)
    else:
        print(f"  梯队接力: {relay['score']} (池{relay.get('pool_count','?')}只 {relay.get('sub_pct')})", file=sys.stderr)

    # ===== 加权综合 =====
    print("[5/6] 计算综合强度...", file=sys.stderr)

    raw_score = (
        profit["score"] * 0.4086 +
        limit_net["score"] * 0.0479 +
        ratio["score"] * 0.3527 +
        lianban["score"] * 0.0026 +
        board_q["score"] * 0.0075 +
        trend["score"] * 0.1808
    )

    # 梯队接力表现（开盘啦「昨日XX表现」细分口径：首板/二板/三板以上/炸板）
    # 混合权重15%，原六维按0.85缩放，保持 SCALE/OFFSET 校准基本不变
    raw_score = raw_score * 0.85 + relay["score"] * 0.15

    # 缩放+偏移：将原始分数映射到校准范围
    # 反推自用户校准值 [50,91,73,92,95]，scale=0.9342, offset=32.22
    SCALE = 0.9342
    OFFSET = 32.22
    total_score = raw_score * SCALE + OFFSET
    total_score = max(0, min(100, total_score))

    status = get_status(total_score)
    market_eval = ladder_row.get("市场评价", "")

    # 回退标注
    note = ""
    if actual_date != today:
        note = f"使用{actual_date}数据（{today}数据未生成，已回退）"

    # ===== 额外数据（供简报补充） =====
    print("[6/6] 获取额外数据...", file=sys.stderr)

    extra = {}

    # 连板梯队详情
    try:
        consec = crawler.get_consecutive_limit_up(actual_date)
        # 清理ladder数据：移除爬虫bug字段"连板天数"（被错误填充为大数值）
        clean_ladder = {}
        for level, stocks in consec.get("ladder", {}).items():
            clean_stocks = []
            for s in stocks:
                clean_stocks.append({
                    "股票代码": s.get("股票代码", ""),
                    "股票名称": s.get("股票名称", ""),
                    "题材": s.get("题材", ""),
                    "概念": s.get("概念", ""),
                })
            clean_ladder[level] = clean_stocks
        extra["consecutive_ladder"] = {
            "max_consecutive": consec.get("max_consecutive", 0),
            "max_consecutive_stocks": consec.get("max_consecutive_stocks", ""),
            "max_consecutive_concepts": consec.get("max_consecutive_concepts", ""),
            "ladder": clean_ladder,
        }
    except Exception as e:
        print(f"  [WARN] 连板详情获取失败: {e}", file=sys.stderr)

    # 涨停原因板块
    try:
        sector_rank = crawler.get_sector_ranking(actual_date)
        extra["limit_up_sectors"] = {
            "summary": sector_rank.get("summary", {}),
            "sectors": sector_rank.get("sectors", [])[:10],  # 取前10板块
        }
    except Exception as e:
        print(f"  [WARN] 涨停板块获取失败: {e}", file=sys.stderr)

    # 板块强度排名
    try:
        ndays = crawler.get_sector_strength_ndays(actual_date, num_days=1)
        if hasattr(ndays, 'to_dict'):
            extra["sector_strength_rank"] = ndays.head(10).to_dict(orient='records')
        else:
            extra["sector_strength_rank"] = []
    except Exception as e:
        print(f"  [WARN] 板块强度获取失败: {e}", file=sys.stderr)

    # 龙虎榜
    try:
        lhb = crawler.get_longhubang_stock_list(actual_date)
        extra["longhubang"] = {
            "total_count": lhb.get("total_count", 0),
            "stocks": lhb.get("stocks", [])[:20],  # 取前20只
        }
    except Exception as e:
        print(f"  [WARN] 龙虎榜获取失败: {e}", file=sys.stderr)

    # 大幅回撤详情
    try:
        withdrawal_df = crawler.get_sharp_withdrawal(actual_date)
        if hasattr(withdrawal_df, 'to_dict'):
            extra["sharp_withdrawal"] = withdrawal_df.to_dict(orient='records')
        else:
            extra["sharp_withdrawal"] = []
    except Exception as e:
        print(f"  [WARN] 大幅回撤详情获取失败: {e}", file=sys.stderr)

    # 综合热度排名（近5日：开盘啦涨停+龙虎榜+连板+淘股吧提及）
    print("[7/7] 计算综合热度排名...", file=sys.stderr)
    try:
        from collections import defaultdict
        # 获取近5个交易日
        dt = datetime.strptime(actual_date, "%Y-%m-%d")
        recent_dates = []
        cur = dt
        while len(recent_dates) < 5:
            if cur.weekday() < 5:
                recent_dates.append(cur.strftime("%Y-%m-%d"))
            cur -= timedelta(days=1)
        recent_dates.reverse()

        hstock = defaultdict(lambda: {
            "name": "", "kpl_zt": 0, "max_lianban": 0,
            "total_fengdan": 0, "lhb_count": 0, "lhb_buy": 0,
            "concepts": set(), "tgb_mentions": 0, "dcf_rank": None
        })

        for d in recent_dates:
            # 涨停板块
            try:
                sdata = crawler.get_sector_ranking(d)
                for sector in sdata.get("sectors", []):
                    for s in sector.get("stocks", []):
                        code = s.get("股票代码", "")
                        if not code:
                            continue
                        info = hstock[code]
                        info["name"] = s.get("股票名称", "")
                        info["kpl_zt"] += 1
                        lb = s.get("连板次数", 0)
                        if isinstance(lb, int) and lb > info["max_lianban"]:
                            info["max_lianban"] = lb
                        fd = s.get("封单额", 0)
                        if isinstance(fd, (int, float)) and fd > 0:
                            info["total_fengdan"] += fd
                        concepts = s.get("概念标签", "")
                        if concepts:
                            for c in concepts.split("、")[:3]:
                                info["concepts"].add(c.strip())
            except Exception:
                pass
            # 龙虎榜
            try:
                lhb = crawler.get_longhubang_stock_list(d)
                for s in lhb.get("stocks", []):
                    code = s.get("stock_code", "")
                    if not code:
                        continue
                    info = hstock[code]
                    info["name"] = s.get("stock_name", info["name"])
                    info["lhb_count"] += 1
                    info["lhb_buy"] += s.get("buy_amount", 0)
            except Exception:
                pass
            # 连板梯队
            try:
                consec = crawler.get_consecutive_limit_up(d)
                for level, stocks in consec.get("ladder", {}).items():
                    level_int = int(level)
                    for s in stocks:
                        code = s.get("股票代码", "")
                        if not code:
                            continue
                        info = hstock[code]
                        info["name"] = s.get("股票名称", info["name"])
                        info["max_lianban"] = max(info["max_lianban"], level_int)
                        concepts = s.get("概念", "")
                        if concepts:
                            for c in concepts.split("、")[:3]:
                                info["concepts"].add(c.strip())
            except Exception:
                pass

        # 淘股吧提及
        tgb_data = {}
        try:
            tgb_path = DATA_DIR / "tgb_today.json"
            with open(tgb_path, encoding="utf-8") as f:
                tgb_data = json.load(f)
        except Exception:
            pass
        # 常见股票关键词映射
        _STOCK_KW = {
            "传智教育":"003032","德龙汇能":"000593","豪尔赛":"002963","一鸣食品":"605179",
            "神雾节能":"000820","高争民爆":"002827","爱丽家居":"603221","美利云":"000815",
            "天娱数科":"002354","风范股份":"601700","欣天科技":"300615","中京电子":"002579",
            "科瑞技术":"002957","云南锗业":"002428","博杰股份":"002975","沃格光电":"603773",
            "高乐股份":"002348","凯撒文化":"002425","百花医药":"600721","浙江世宝":"002703",
            "大众交通":"600611","东山精密":"002384","盛视科技":"002990","利通电子":"603629",
            "百合花":"603823","汇绿生态":"001267","长飞光纤":"601869","中材科技":"002080",
            "有研新材":"600206","海星股份":"603115","普联软件":"300996","恒银科技":"603106",
            "新能股份":"000595","北方华创":"002371","中际旭创":"300308","寒武纪":"688256",
            "胜宏科技":"300476","江波龙":"301308","索菱股份":"002766","大晟文化":"600892",
            "博彦科技":"002649","冰轮环境":"000811","东材科技":"601208","华正新材":"603186",
        }
        for _, bd in tgb_data.get("bloggers", {}).items():
            all_text = ""
            for reply in bd.get("top_replies", []):
                all_text += reply.get("content", "") + " "
            for post in bd.get("posts", []):
                all_text += post.get("title", "") + " "
            for name, code in _STOCK_KW.items():
                if name in all_text:
                    info = hstock[code]
                    info["name"] = info["name"] or name
                    info["tgb_mentions"] += 1

        # 东方财富人气榜
        dcf_rank = {}  # code -> rank
        try:
            import requests as _req
            _url = "https://emappdata.eastmoney.com/stockrank/getAllCurrentList"
            _headers = {"Content-Type": "application/json",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            for _page in range(1, 4):
                _payload = {"appId": "appId01", "globalVersion": "1.0",
                            "marketType": "0", "pageNo": _page, "pageSize": 100}
                _resp = _req.post(_url, json=_payload, headers=_headers, timeout=15)
                _items = _resp.json().get("data", [])
                if not _items:
                    break
                for _item in _items:
                    raw_code = _item.get("sc", "")
                    # SH600519 -> 600519, SZ002428 -> 002428
                    if raw_code.startswith("SH") or raw_code.startswith("SZ"):
                        clean_code = raw_code[2:]
                    else:
                        clean_code = raw_code
                    rank = _item.get("rk", 999)
                    dcf_rank[clean_code] = rank
                if len(_items) < 100:
                    break
            print(f"  东方财富人气榜: {len(dcf_rank)}只", file=sys.stderr)
        except Exception as e:
            print(f"  [WARN] 东方财富人气榜获取失败: {e}", file=sys.stderr)

        # 东方财富排名靠前的个股也要加入hstock（可能不在涨停/龙虎榜中）
        for code, rank in dcf_rank.items():
            if code not in hstock and rank <= 30:
                hstock[code]["dcf_rank"] = rank

        # 标记东方财富排名
        for code, rank in dcf_rank.items():
            if code in hstock:
                hstock[code]["dcf_rank"] = rank

        # 综合热度评分
        hot_results = []
        for code, info in hstock.items():
            if not info["name"]:
                continue
            # 东方财富排名分：排名1→30分，排名100→0分
            dcf_score = max(0, 31 - info.get("dcf_rank", 999)) if info.get("dcf_rank") else 0
            score = (
                info["kpl_zt"] * 10 +
                info["max_lianban"] * 15 +
                info["lhb_count"] * 8 +
                info["lhb_buy"] / 1e8 * 2 +
                info["total_fengdan"] / 1e8 * 1 +
                info["tgb_mentions"] * 5 +
                dcf_score
            )
            if score > 0:
                hot_results.append({
                    "code": code,
                    "name": info["name"],
                    "score": round(score, 1),
                    "kpl_zt": info["kpl_zt"],
                    "max_lianban": info["max_lianban"],
                    "lhb_count": info["lhb_count"],
                    "tgb_mentions": info["tgb_mentions"],
                    "dcf_rank": info.get("dcf_rank"),
                    "concepts": ", ".join(list(info["concepts"])[:3]),
                })

        hot_results.sort(key=lambda x: x["score"], reverse=True)
        extra["hot_stocks"] = hot_results[:10]
        print(f"  综合热度TOP10: {', '.join(s['name'] for s in hot_results[:10])}", file=sys.stderr)
    except Exception as e:
        print(f"  [WARN] 综合热度计算失败: {e}", file=sys.stderr)
        extra["hot_stocks"] = []

    # ===== 输出 =====
    # 兼容旧版 panic_today.json 格式，同时扩展新字段
    result = {
        "date": today,
        "data_date": actual_date,
        "score": round(total_score, 1),
        "status": status,
        "comment": market_eval,
        "note": note,
        # 新版6维度（兼容旧版 components 字段名）
        "components": {
            "profit_effect": profit["score"],
            "limit_net": limit_net["score"],
            "up_down_ratio": ratio["score"],
            "lianban_rate": lianban["score"],
            "board_quality": board_q["score"],
            "trend_strength": trend["score"],
            "relay_score": relay["score"],
            # 旧版兼容字段（映射到最接近的新维度）
            "up_down_ratio_legacy": ratio["score"],      # 旧: 涨跌比 20%
            "lianban_rate_legacy": lianban["score"],      # 旧: 连板率 15%
            "limit_ratio": limit_net["score"],            # 旧: 涨跌停比 15%
            "sector_strength": 50,                        # 旧: 板块强度 15% (已废弃)
            "withdrawal_score": board_q["score"],         # 旧: 大幅回撤 10%
            "north_score": 50,                            # 旧: 北向资金 10% (已废弃)
            "margin_score": 50,                           # 旧: 融资余额 10% (已废弃)
            "futures_score": 50,                          # 旧: 股指期货 5% (已废弃)
        },
        "details": {
            "up_count": ratio["up_count"],
            "down_count": ratio["down_count"],
            "limit_up": limit_net["limit_up"],
            "limit_down": limit_net["limit_down"],
            "withdrawal_count": withdrawal_count,
            "new_high": new_high,
            "broken_rate": board_q["broken_rate"],
            "relay_sub_pct": relay.get("sub_pct", {}),
            "relay_sub_score": relay.get("sub", {}),
            "relay_prev_day": relay.get("prev_day", ""),
            "relay_note": relay.get("note", ""),
            "yesterday_limit_performance": profit["yesterday_limit"],
            "yesterday_consecutive_performance": profit["yesterday_consecutive"],
            "yesterday_broken_performance": profit["yesterday_broken"],
            "lianban_rate_raw": lianban["raw"],
            "market_eval": market_eval,
        },
        # 新增：各维度原始分数和权重
        "dimensions": {
            "profit_effect": {"score": profit["score"], "weight": 0.409, "raw": profit["raw"]},
            "limit_net": {"score": limit_net["score"], "weight": 0.048, "raw": limit_net["raw"]},
            "up_down_ratio": {"score": ratio["score"], "weight": 0.353, "raw": ratio["raw"]},
            "lianban_rate": {"score": lianban["score"], "weight": 0.003, "raw": lianban["raw"]},
            "board_quality": {"score": board_q["score"], "weight": 0.008, "raw": board_q["broken_rate"]},
            "trend_strength": {"score": trend["score"], "weight": 0.181, "raw": trend["raw"]},
        },
        # 新增：额外数据源
        "extra": extra,
    }

    print(f"\n综合强度: {total_score:.1f}", file=sys.stderr)
    print(f"状态: {status}", file=sys.stderr)
    if note:
        print(f"提示: {note}", file=sys.stderr)
    if market_eval:
        print(f"市场评价: {market_eval}", file=sys.stderr)

    # 输出JSON
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
