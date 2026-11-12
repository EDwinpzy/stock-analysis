#!/usr/bin/env python3
"""龙虎榜数据采集脚本 — 每日简报Pro

主数据源：同花顺官方金融数据服务（hithink-finance CLI → special dragon-tiger）
  · 个股榜：净买额 / 涨跌幅 / 概念标签 / 连续上榜天数
  · 机构榜：机构净买额与买卖机构家数
  · 游资派系榜：派系名称、净额、涉及个股
降级数据源：akshare（东方财富龙虎榜API）。仅当同花顺不可用时启用，输出结构保持一致。

输出：JSON到stdout，进度信息到stderr

用法：
    python fetch_longhubang.py --date 2026-07-31
"""

import argparse
import json
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _hithink  # noqa: E402
from trading_date import get_recent_trade_date  # noqa: E402

try:  # 同花顺路径不依赖 akshare/pandas，缺它们只影响降级路径
    import akshare as ak
    import pandas as pd
except ImportError:  # pragma: no cover
    ak = None
    pd = None


# ── 游资席位昵称映射 ──────────────────────────────────────────
# key=营业部全名中的关键匹配子串, value=市场熟知昵称
# 匹配逻辑：key in full_name，所以用全名中实际出现的子串
HOT_MONEY_NICKNAMES = {
    # ── 国泰海通系（原国泰君安，2025合并更名）──
    "南京太平南路": "南京太平南",
    "上海长宁区江苏路": "上海江苏路",
    "上海松江区中山东路": "松江中山东路",
    "武汉紫阳东路": "紫阳东路",
    "广州珠江新城": "珠江新城",
    "自贸试验区第二分公司": "自贸区二",
    "九江甘棠路": "九江甘棠路",
    "河源越王大道": "河源越王",
    "昆明北京路": "昆明北京路",
    "湛江万豪世家": "湛江万豪",
    "上海静安区新闸路": "新闸路",
    # ── 中信系 ──
    "中信建投北京知春路": "知春路",
    "中信建投证券股份有限公司北京知春路": "知春路",
    "深圳深南中路中信大厦": "深南中路",
    # ── 开源系 ──
    "西安太华路": "太华路",
    "西安高新成章路": "高新成章路",
    "开源证券上海浦东南路": "开源浦东南路",
    # ── 拉萨天团（东方财富）──
    "拉萨金融城南环路": "拉萨南环路",
    "拉萨东环路第二": "拉萨东二",
    "拉萨东环路第一": "拉萨东一",
    "拉萨团结路第一": "拉萨团结一",
    "拉萨团结路第二": "拉萨团结二",
    "山南香曲东路": "香曲东路",
    # ── 华泰系 ──
    "上海浦东新区世纪大道": "华泰世纪大道",
    "华泰证券北京西三环": "华泰西三环",
    # ── 其他知名游资 ──
    "深圳泰然九路": "泰然九路",
    "浙江互联网分公司": "国信浙江",
    "长江证券上海分公司": "长江上海",
    "上海徐汇区天钥桥路": "天钥桥路",
    "东北证券佛山分公司": "东北佛山",
    "华源证券江苏分公司": "华源江苏",
    "金融街证券上海第二分公司": "金融街上海二",
    "东莞证券南京分公司": "东莞南京",
    "东亚前海证券有限责任公司深圳分公司": "东亚前海深圳",
    "东亚前海证券有限责任公司浙江分公司": "东亚前海浙江",
    "宁波中山东路": "宁波中山东路",
    "深圳益田路免税商务大厦": "益田路",
    "上海虹口区杨树浦路": "杨树浦路",
    "庄河世纪大街": "银河庄河",
    "北京安贞门": "银河安贞门",
    "瑞银证券有限责任公司上海花园石桥路": "瑞银花园石桥",
    "高盛(中国)证券有限责任公司上海浦东新区世纪大道": "高盛世纪大道",
    "摩根大通证券(中国)有限公司上海银城中路": "摩根大通银城",
    "华鑫证券深圳益田路": "华鑫益田路",
    "华安证券北京东三环中路": "华安东三环",
    "信达证券上海浦东新区源深路": "信达源深路",
    "万联证券宁波镇明路": "万联镇明路",
    "南京洪武北路": "中银洪武北路",
    "广发证券湖南分公司": "广发湖南",
    "广发证券上海南泉北路": "广发南泉北路",
    "苏州龙西路": "申万龙西路",
    "国金证券北京崇文门外大街": "国金崇文门",
    "国金证券杭州利一路": "国金利一路",
    "平安证券杭州曙光路": "平安曙光路",
    "平安证券浙江分公司": "平安浙江",
    "天风证券上海龙翔路": "天风龙翔路",
    "苏州工业园区扬富路": "东吴扬富路",
    "甬兴证券有限公司宁波和源路": "甬兴和源路",
    "北京建国门外大街": "中金建国门",
    "国新证券海南分公司": "国新海南",
    "麦高证券有限责任公司北京分公司": "麦高北京",
    "南平广场西路": "华福广场西路",
    "汕头金砂东路": "方正金砂东",
    "广州兴民路": "兴业兴民路",
    "上海徐汇区云锦路": "华鑫云锦路",
    "深圳招商证券大厦": "招商大厦",
    "深圳深南东路罗湖商务中心": "平安深南东",
    # ── 长江证券 ──
    "长江证券股份有限公司上海分公司": "长江上海",
    # ── 东北证券 ──
    "东北证券股份有限公司佛山分公司": "东北佛山",
    # ── 华源证券 ──
    "华源证券股份有限公司江苏分公司": "华源江苏",
    # ── 东莞证券 ──
    "东莞证券股份有限公司南京分公司": "东莞南京",
    # ── 华安证券 ──
    "华安证券股份有限公司北京东三环中路": "华安东三环",
    # ── 万联证券 ──
    "万联证券股份有限公司宁波镇明路": "万联镇明路",
    # ── 国新证券 ──
    "国新证券股份有限公司海南分公司": "国新海南",
    # ── 国投证券 ──
    "国投证券股份有限公司上海虹口区杨树浦路": "杨树浦路",
    # ── 中国银河 ──
    "中国银河证券股份有限公司庄河世纪大街": "银河庄河",
    "中国银河证券股份有限公司北京安贞门": "银河安贞门",
    # ── 招商证券 ──
    "招商证券股份有限公司宁波中山东路": "宁波中山东路",
    # ── 国金证券 ──
    "国金证券股份有限公司北京崇文门外大街": "国金崇文门",
    # ── 中银国际 ──
    "中银国际证券股份有限公司南京洪武北路": "中银洪武北路",
    # ── 申万宏源 ──
    "申万宏源证券有限公司苏州龙西路": "申万龙西路",
    # ── 平安证券 ──
    "平安证券股份有限公司杭州曙光路": "平安曙光路",
    # ── 天风证券 ──
    "天风证券股份有限公司上海龙翔路": "天风龙翔路",
    # ── 东吴证券 ──
    "东吴证券股份有限公司苏州工业园区扬富路": "东吴扬富路",
    # ── 广发证券 ──
    "广发证券股份有限公司湖南分公司": "广发湖南",
    "广发证券股份有限公司上海南泉北路": "广发南泉北路",
    # ── 兴业证券 ──
    "兴业证券股份有限公司广州兴民路": "兴业兴民路",
    # ── 华鑫证券 ──
    "华鑫证券有限责任公司深圳益田路": "华鑫益田路",
    "华鑫证券有限责任公司上海徐汇区云锦路": "华鑫云锦路",
    # ── 信达证券 ──
    "信达证券股份有限公司上海浦东新区源深路": "信达源深路",
    # ── 方正证券 ──
    "方正证券股份有限公司汕头金砂东路": "方正金砂东",
    # ── 华福证券 ──
    "华福证券股份有限公司南平广场西路": "华福广场西路",
    # ── 甬兴证券 ──
    "甬兴证券有限公司宁波和源路": "甬兴和源路",
    # ── 麦高证券 ──
    "麦高证券有限责任公司北京分公司": "麦高北京",
    # ── 中金 ──
    "中国国际金融股份有限公司北京建国门外大街": "中金建国门",
    "中国国际金融股份有限公司上海分公司": "中金上海",
    # ── 国信证券 ──
    "国信证券股份有限公司深圳泰然九路": "泰然九路",
    "国信证券股份有限公司浙江互联网分公司": "国信浙江",
    # ── 中信上海分公司（需精确匹配，避免误匹配其他中信席位）──
    "中信证券股份有限公司上海分公司": "中信上海",
    # ── 华泰上海分公司 ──
    "华泰证券股份有限公司上海分公司": "华泰上海",
    # ── 华泰总部 ──
    "华泰证券股份有限公司总部": "华泰总部",
    # ── 国泰海通总部 ──
    "国泰海通证券股份有限公司总部": "海通总部",
    # ── 国泰海通上海分公司 ──
    "国泰海通证券股份有限公司上海分公司": "海通上海",
    # ── 招商证券深圳益田路 ──
    "招商证券股份有限公司深圳益田路": "招商益田路",
}


def nickname_seat(full_name):
    """将营业部全名转换为市场熟知昵称"""
    if not full_name:
        return full_name
    # 按key长度降序匹配，优先匹配更具体的
    for key, nick in sorted(HOT_MONEY_NICKNAMES.items(), key=lambda x: -len(x[0])):
        if key in full_name:
            return nick
    # 未匹配：提取公司简称+地址关键词
    if "证券" in full_name:
        parts = full_name.split("证券")
        company = parts[0].replace("股份有限公司", "").replace("有限责任公司", "")
        if len(parts) > 1 and parts[1]:
            rest = parts[1].replace("证券营业部", "").replace("营业部", "").replace("分公司", "")
            # 提取路名/地名
            import re
            road_match = re.search(r"[\u4e00-\u9fff]+路", rest)
            if road_match:
                return company[:4] + road_match.group()
            # 提取区名
            district_match = re.search(r"[\u4e00-\u9fff]+区", rest)
            if district_match:
                return company[:4] + district_match.group()
            # 最后一段
            segs = [x for x in rest.split("区") if x]
            if segs:
                return company[:4] + segs[-1][:4]
        return company[:6]
    return full_name[:10]


def get_date():
    """解析命令行日期参数，默认今天"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="日期 YYYY-MM-DD")
    args, _ = parser.parse_known_args()
    if args.date:
        return args.date
    return datetime.now().strftime("%Y-%m-%d")


def safe_float(val, default=0.0):
    """安全转换为float"""
    try:
        if pd.isna(val):
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def fetch_lhb_detail(date_str):
    """获取龙虎榜总览数据"""
    print("[1/4] 获取龙虎榜总览...", file=sys.stderr)
    try:
        df = ak.stock_lhb_detail_em(start_date=date_str, end_date=date_str)
        if df is None or df.empty:
            print("  龙虎榜无数据", file=sys.stderr)
            return pd.DataFrame()
        print(f"  获取到 {len(df)} 条记录", file=sys.stderr)
        return df
    except Exception as e:
        print(f"  龙虎榜总览获取失败: {e}", file=sys.stderr)
        return pd.DataFrame()


def fetch_institution_stats(date_str):
    """获取机构买卖统计"""
    print("[2/4] 获取机构买卖统计...", file=sys.stderr)
    try:
        df = ak.stock_lhb_jgmmtj_em(start_date=date_str, end_date=date_str)
        if df is None or df.empty:
            print("  机构统计无数据", file=sys.stderr)
            return pd.DataFrame()
        print(f"  获取到 {len(df)} 条记录", file=sys.stderr)
        return df
    except Exception as e:
        print(f"  机构统计获取失败: {e}", file=sys.stderr)
        return pd.DataFrame()


def fetch_stock_seats(code, date_str):
    """获取个股买卖席位明细"""
    all_records = []
    for flag in ["买入", "卖出"]:
        try:
            df = ak.stock_lhb_stock_detail_em(symbol=code, date=date_str, flag=flag)
            if df is not None and not df.empty:
                df["股票代码"] = code
                all_records.append(df)
        except Exception:
            pass
    if all_records:
        return pd.concat(all_records, ignore_index=True).drop_duplicates(
            subset=["交易营业部名称", "股票代码", "净额"]
        )
    return pd.DataFrame()


def fetch_hot_money_seats(date_str, detail_df):
    """获取重点个股的游资席位明细"""
    print("[3/4] 获取游资席位明细...", file=sys.stderr)

    # 选取净买入额最大的前15只个股（排除可转债）
    if detail_df.empty:
        return pd.DataFrame()

    stocks_df = detail_df[~detail_df["代码"].str.startswith(("11", "12"))].copy()
    stocks_df = stocks_df.sort_values("龙虎榜净买额", ascending=False)

    # 去重取唯一代码
    seen = set()
    top_codes = []
    for _, row in stocks_df.iterrows():
        code = row["代码"]
        if code not in seen:
            seen.add(code)
            top_codes.append(code)
        if len(top_codes) >= 15:
            break

    all_seats = []
    for i, code in enumerate(top_codes):
        try:
            df = fetch_stock_seats(code, date_str)
            if not df.empty:
                # 补充股票名称
                name_row = stocks_df[stocks_df["代码"] == code].iloc[0]
                df["股票名称"] = name_row["名称"]
                all_seats.append(df)
            print(f"  [{i+1}/{len(top_codes)}] {code} 席位获取完成", file=sys.stderr)
        except Exception as e:
            print(f"  [{i+1}/{len(top_codes)}] {code} 席位获取失败: {e}", file=sys.stderr)

    if all_seats:
        return pd.concat(all_seats, ignore_index=True)
    return pd.DataFrame()


def identify_hot_money_groups(seats_df):
    """识别游资派系"""
    if seats_df.empty:
        return []

    # 排除机构专用和股通
    df = seats_df[~seats_df["交易营业部名称"].str.contains("机构专用|股通专用")].copy()
    df["净买入亿"] = df["净额"].apply(safe_float) / 1e8

    # 按营业部汇总
    summary = df.groupby("交易营业部名称").agg(
        操作个股数=("股票代码", "nunique"),
        总净买入亿=("净买入亿", "sum"),
        涉及个股=("股票名称", lambda x: list(sorted(set(x)))),
    ).reset_index().sort_values("总净买入亿", ascending=False)

    # 识别派系
    groups = []

    # 国泰海通系
    gtht_mask = summary["交易营业部名称"].str.contains("国泰海通")
    gtht = summary[gtht_mask]
    if not gtht.empty:
        total = gtht["总净买入亿"].sum()
        all_stocks = list(sorted(set(s for lst in gtht["涉及个股"] for s in lst)))
        direction = "净买入" if total > 0 else "净卖出"
        groups.append({
            "派系": "国泰海通系",
            "方向": direction,
            "总净额亿": round(total, 2),
            "席位数": len(gtht),
            "涉及个股": all_stocks[:8],
            "核心席位": gtht.iloc[0]["交易营业部名称"][:20] if len(gtht) > 0 else "",
        })

    # 开源证券系
    ky_mask = summary["交易营业部名称"].str.contains("开源证券")
    ky = summary[ky_mask]
    if not ky.empty:
        total = ky["总净买入亿"].sum()
        all_stocks = list(sorted(set(s for lst in ky["涉及个股"] for s in lst)))
        direction = "净买入" if total > 0 else "净卖出"
        groups.append({
            "派系": "开源证券系",
            "方向": direction,
            "总净额亿": round(total, 2),
            "席位数": len(ky),
            "涉及个股": all_stocks[:8],
            "核心席位": ky.iloc[0]["交易营业部名称"][:20] if len(ky) > 0 else "",
        })

    # 拉萨天团
    ls_mask = summary["交易营业部名称"].str.contains("拉萨")
    ls = summary[ls_mask]
    if not ls.empty:
        total = ls["总净买入亿"].sum()
        all_stocks = list(sorted(set(s for lst in ls["涉及个股"] for s in lst)))
        direction = "净买入" if total > 0 else "净卖出"
        groups.append({
            "派系": "拉萨天团",
            "方向": direction,
            "总净额亿": round(total, 2),
            "席位数": len(ls),
            "涉及个股": all_stocks[:8],
            "核心席位": ls.iloc[0]["交易营业部名称"][:20] if len(ls) > 0 else "",
        })

    # 中信系
    zx_mask = summary["交易营业部名称"].str.contains("中信证券|中信建投|中信浙江")
    zx = summary[zx_mask]
    if not zx.empty:
        total = zx["总净买入亿"].sum()
        all_stocks = list(sorted(set(s for lst in zx["涉及个股"] for s in lst)))
        direction = "净买入" if total > 0 else "净卖出"
        groups.append({
            "派系": "中信系",
            "方向": direction,
            "总净额亿": round(total, 2),
            "席位数": len(zx),
            "涉及个股": all_stocks[:8],
            "核心席位": zx.iloc[0]["交易营业部名称"][:20] if len(zx) > 0 else "",
        })

    return groups


def build_top_net_buy(detail_df, n=10):
    """构建龙虎榜净买入TOP"""
    if detail_df.empty:
        return []

    # 排除可转债
    df = detail_df[~detail_df["代码"].str.startswith(("11", "12"))].copy()
    df = df.sort_values("龙虎榜净买额", ascending=False)

    # 去重（同一股票可能因多种原因多次上榜，取净买额最大的一条）
    seen = set()
    results = []
    for _, row in df.iterrows():
        code = row["代码"]
        if code in seen:
            continue
        seen.add(code)
        if len(results) >= n:
            break

        net_buy = safe_float(row["龙虎榜净买额"])
        chg = safe_float(row["涨跌幅"])
        results.append({
            "代码": code,
            "名称": row["名称"],
            "涨跌幅": round(chg, 2),
            "净买额亿": round(net_buy / 1e8, 2),
            "买入额亿": round(safe_float(row["龙虎榜买入额"]) / 1e8, 2),
            "卖出额亿": round(safe_float(row["龙虎榜卖出额"]) / 1e8, 2),
            "上榜原因": row.get("上榜原因", ""),
            "解读": row.get("解读", ""),
        })
    return results


def build_top_net_sell(detail_df, n=5):
    """构建龙虎榜净卖出TOP"""
    if detail_df.empty:
        return []

    df = detail_df[~detail_df["代码"].str.startswith(("11", "12"))].copy()
    df = df.sort_values("龙虎榜净买额", ascending=True)

    seen = set()
    results = []
    for _, row in df.iterrows():
        code = row["代码"]
        if code in seen:
            continue
        seen.add(code)
        if len(results) >= n:
            break

        net_buy = safe_float(row["龙虎榜净买额"])
        chg = safe_float(row["涨跌幅"])
        results.append({
            "代码": code,
            "名称": row["名称"],
            "涨跌幅": round(chg, 2),
            "净卖额亿": round(abs(net_buy) / 1e8, 2),
            "上榜原因": row.get("上榜原因", ""),
            "解读": row.get("解读", ""),
        })
    return results


def build_top_institution_buy(inst_df, n=10):
    """构建机构净买入TOP"""
    if inst_df.empty:
        return []

    df = inst_df.sort_values("机构买入净额", ascending=False)
    results = []
    for i, (_, row) in enumerate(df.iterrows()):
        if i >= n:
            break
        net_buy = safe_float(row["机构买入净额"])
        chg = safe_float(row["涨跌幅"])
        results.append({
            "代码": row["代码"],
            "名称": row["名称"],
            "涨跌幅": round(chg, 2),
            "买方机构数": int(row.get("买方机构数", 0)),
            "卖方机构数": int(row.get("卖方机构数", 0)),
            "机构净买入亿": round(net_buy / 1e8, 2),
            "上榜原因": row.get("上榜原因", ""),
        })
    return results


def build_top_hot_money(seats_df, n=10):
    """构建游资席位TOP"""
    if seats_df.empty:
        return [], []

    df = seats_df[~seats_df["交易营业部名称"].str.contains("机构专用|股通专用")].copy()
    df["净买入亿"] = df["净额"].apply(safe_float) / 1e8

    summary = df.groupby("交易营业部名称").agg(
        操作个股数=("股票代码", "nunique"),
        总净买入亿=("净买入亿", "sum"),
        涉及个股=("股票名称", lambda x: list(sorted(set(x)))),
    ).reset_index()

    # 净买入TOP
    buy_top = summary.sort_values("总净买入亿", ascending=False).head(n)
    top_buy = []
    for _, row in buy_top.iterrows():
        seat = row["交易营业部名称"]
        top_buy.append({
            "席位": seat,
            "昵称": nickname_seat(seat),
            "净买入亿": round(row["总净买入亿"], 2),
            "操作个股数": int(row["操作个股数"]),
            "涉及个股": row["涉及个股"][:5],
        })

    # 净卖出TOP
    sell_top = summary.sort_values("总净买入亿", ascending=True).head(n)
    top_sell = []
    for _, row in sell_top.iterrows():
        seat = row["交易营业部名称"]
        top_sell.append({
            "席位": seat,
            "昵称": nickname_seat(seat),
            "净卖出亿": round(abs(row["总净买入亿"]), 2),
            "操作个股数": int(row["操作个股数"]),
            "涉及个股": row["涉及个股"][:5],
        })

    return top_buy, top_sell


def build_key_stocks_detail(detail_df, inst_df, seats_df, n=5):
    """构建重点个股博弈拆解"""
    if detail_df.empty or seats_df.empty:
        return []

    # 选取净买入额最大的个股
    df = detail_df[~detail_df["代码"].str.startswith(("11", "12"))].copy()
    df = df.sort_values("龙虎榜净买额", ascending=False)

    seen = set()
    key_stocks = []
    for _, row in df.iterrows():
        code = row["代码"]
        if code in seen:
            continue
        seen.add(code)
        if len(key_stocks) >= n:
            break

        name = row["名称"]
        chg = safe_float(row["涨跌幅"])

        # 获取该股的席位明细
        stock_seats = seats_df[seats_df["股票代码"] == code].copy()
        stock_seats = stock_seats[~stock_seats["交易营业部名称"].str.contains("机构专用|股通专用")]
        stock_seats["净买入亿"] = stock_seats["净额"].apply(safe_float) / 1e8

        buy_seats = stock_seats.sort_values("净买入亿", ascending=False).head(3)
        sell_seats = stock_seats.sort_values("净买入亿", ascending=True).head(3)

        # 机构数据
        inst_row = inst_df[inst_df["代码"] == code] if not inst_df.empty else pd.DataFrame()
        buy_inst = int(inst_row["买方机构数"].iloc[0]) if not inst_row.empty else 0
        sell_inst = int(inst_row["卖方机构数"].iloc[0]) if not inst_row.empty else 0

        key_stocks.append({
            "代码": code,
            "名称": name,
            "涨跌幅": round(chg, 2),
            "买方机构数": buy_inst,
            "卖方机构数": sell_inst,
            "买入席位": [
                {
                    "席位": nickname_seat(r["交易营业部名称"]),
                    "净买入亿": round(safe_float(r["净买入亿"]), 2),
                }
                for _, r in buy_seats.iterrows()
            ],
            "卖出席位": [
                {
                    "席位": nickname_seat(r["交易营业部名称"]),
                    "净卖出亿": round(abs(safe_float(r["净买入亿"])), 2),
                }
                for _, r in sell_seats.iterrows()
            ],
        })

    return key_stocks


def infer_main_themes(top_net_buy, top_institution_buy):
    """推断主线板块"""
    themes = []

    # 从净买入TOP10中提取关键词
    ai_keywords = ["AI", "人工智能", "软件", "数字", "互联网", "传媒", "营销",
                   "万维", "光标", "在线", "天下", "网络", "用友", "福昕",
                   "致远", "普联", "泛微", "奥比", "卓易"]
    gold_keywords = ["黄金", "金", "贵金属"]
    energy_keywords = ["能科", "电力", "能源", "光伏", "储能", "华光"]
    medical_keywords = ["医疗", "医药", "药", "九安"]

    all_names = [s["名称"] for s in top_net_buy] + [s["名称"] for s in top_institution_buy]
    # 去重
    all_names = list(dict.fromkeys(all_names))
    all_text = " ".join(all_names)

    ai_count = sum(1 for name in all_names if any(kw in name for kw in ai_keywords))
    gold_count = sum(1 for name in all_names if any(kw in name for kw in gold_keywords))
    energy_count = sum(1 for name in all_names if any(kw in name for kw in energy_keywords))
    medical_count = sum(1 for name in all_names if any(kw in name for kw in medical_keywords))

    if ai_count >= 2:
        themes.append({"板块": "AI/软件/数字经济", "强度": "🔥🔥🔥" if ai_count >= 5 else "🔥🔥",
                        "个股": [n for n in all_names if any(kw in n for kw in ai_keywords)][:5]})
    if gold_count >= 1:
        themes.append({"板块": "黄金/资源", "强度": "🔥🔥" if gold_count >= 2 else "🔥",
                        "个股": [n for n in all_names if any(kw in n for kw in gold_keywords)][:3]})
    if energy_count >= 1:
        themes.append({"板块": "能源/电力", "强度": "🔥🔥" if energy_count >= 2 else "🔥",
                        "个股": [n for n in all_names if any(kw in n for kw in energy_keywords)][:3]})
    if medical_count >= 1:
        themes.append({"板块": "医疗", "强度": "🔥",
                        "个股": [n for n in all_names if any(kw in n for kw in medical_keywords)][:3]})

    return themes


def build_key_signals(top_net_buy, top_net_sell, top_institution_buy, hot_money_groups, key_stocks):
    """构建关键信号"""
    signals = []

    # 信号1：机构一致买入
    inst_only_buy = [s for s in top_institution_buy if s["卖方机构数"] == 0 and s["买方机构数"] >= 2]
    if inst_only_buy:
        names = "、".join([s["名称"] for s in inst_only_buy[:3]])
        signals.append(f"机构一致做多：{names}（机构只买不卖）")

    # 信号2：机构集中卖出
    inst_only_sell = [s for s in top_institution_buy if s["买方机构数"] == 0 and s["卖方机构数"] >= 2]
    if inst_only_sell:
        names = "、".join([s["名称"] for s in inst_only_sell[:3]])
        signals.append(f"⚠️ 机构集中出逃：{names}")

    # 信号3：游资派系方向
    for g in hot_money_groups[:3]:
        if abs(g["总净额亿"]) >= 0.5:
            direction = "做多" if g["总净额亿"] > 0 else "出货"
            stocks_str = "、".join(g["涉及个股"][:3])
            signals.append(f"{g['派系']}{direction}{abs(g['总净额亿']):.1f}亿，主攻{stocks_str}")

    # 信号4：重点个股分歧（机构买入但游资净卖出）
    for s in key_stocks[:3]:
        if s["买方机构数"] >= 2 and s["卖方机构数"] == 0:
            # 机构只买不卖，检查游资是否净卖出
            buy_total = sum(seat.get("净买入亿", 0) for seat in s.get("买入席位", []))
            sell_total = sum(seat.get("净卖出亿", 0) for seat in s.get("卖出席位", []))
            if sell_total > buy_total:
                signals.append(f"⚠️ {s['名称']}机构只买不卖但游资净卖出{sell_total:.1f}亿，分歧明显")

    return signals


def collect_akshare(date_str):
    """降级路径：AkShare（东方财富龙虎榜）。"""
    if ak is None or pd is None:
        raise RuntimeError("未安装 akshare/pandas，无法使用东方财富降级路径")
    trade_date = get_recent_trade_date(date_str)
    # akshare日期格式：YYYYMMDD
    ak_date = trade_date.replace("-", "")

    print(f"龙虎榜降级采集(AkShare/东方财富): {date_str} (交易日: {trade_date})", file=sys.stderr)

    # 1. 获取龙虎榜总览
    detail_df = fetch_lhb_detail(ak_date)

    # 2. 获取机构统计
    inst_df = fetch_institution_stats(ak_date)

    # 3. 获取游资席位
    seats_df = fetch_hot_money_seats(ak_date, detail_df)

    # 4. 构建各维度数据
    print("[4/4] 构建龙虎榜分析数据...", file=sys.stderr)

    top_net_buy = build_top_net_buy(detail_df, n=10)
    top_net_sell = build_top_net_sell(detail_df, n=5)
    top_institution_buy = build_top_institution_buy(inst_df, n=10)
    top_hot_money_buy, top_hot_money_sell = build_top_hot_money(seats_df, n=10)
    hot_money_groups = identify_hot_money_groups(seats_df)
    key_stocks = build_key_stocks_detail(detail_df, inst_df, seats_df, n=5)
    main_themes = infer_main_themes(top_net_buy, top_institution_buy)
    key_signals = build_key_signals(top_net_buy, top_net_sell, top_institution_buy, hot_money_groups, key_stocks)

    # 统计上榜个股数（排除可转债重复）
    stock_count = 0
    if not detail_df.empty:
        stock_codes = detail_df[~detail_df["代码"].str.startswith(("11", "12"))]["代码"].unique()
        stock_count = len(stock_codes)

    result = {
        "date": trade_date,
        "requested_date": date_str,
        "data_date": trade_date,
        "fetch_time": datetime.now().strftime("%H:%M:%S"),
        "total_stocks": stock_count,
        "top_net_buy": top_net_buy,
        "top_net_sell": top_net_sell,
        "top_institution_buy": top_institution_buy,
        "top_hot_money_buy": top_hot_money_buy,
        "top_hot_money_sell": top_hot_money_sell,
        "hot_money_groups": hot_money_groups,
        "key_stocks_detail": key_stocks,
        "main_themes": main_themes,
        "key_signals": key_signals,
        "source": "AkShare/东方财富龙虎榜接口",
        "components": {
            "龙虎榜总览": "ok" if not detail_df.empty else "empty",
            "机构统计": "ok" if not inst_df.empty else "empty",
            "游资席位": "ok" if not seats_df.empty else "empty",
        },
    }
    result["status"] = "ok" if stock_count > 0 else "empty"
    if stock_count == 0:
        result["note"] = f"{trade_date}暂无可核验龙虎榜数据；未使用旧缓存"
    else:
        missing = [name for name, status in result["components"].items() if status != "ok"]
        result["note"] = f"龙虎榜明细截至{trade_date}" + (f"；缺少：{'、'.join(missing)}" if missing else "")

    return result


def _yi(value):
    """元 -> 亿元，保留两位。"""
    try:
        return round(float(value or 0) / 1e8, 2)
    except (TypeError, ValueError):
        return 0.0


def _concepts(row, limit=2):
    names = [
        str(item.get("name"))
        for item in (row.get("concept_list") or [])
        if isinstance(item, dict) and item.get("name")
    ]
    return "、".join(names[:limit])


def _pct(change):
    try:
        return round(float(change or 0) * 100, 2)
    except (TypeError, ValueError):
        return 0.0


def collect_hithink(date_str):
    """主路径：同花顺官方龙虎榜（个股榜 + 机构榜 + 游资派系榜）。"""
    days = _hithink.trade_dates()
    usable = [d for d in days if d <= date_str]
    if not usable:
        raise _hithink.HithinkError(f"{date_str} 之前没有可用的交易日")
    trade_date = usable[-1]
    print(f"龙虎榜采集(同花顺官方): 请求 {date_str} → 交易日 {trade_date}", file=sys.stderr)

    all_board = _hithink.call("special", "dragon-tiger", "--board-type", "all", "--date", trade_date)
    org_board = _hithink.call("special", "dragon-tiger", "--board-type", "org", "--date", trade_date)
    hm_board = _hithink.call("special", "dragon-tiger", "--board-type", "hot_money", "--date", trade_date)

    stocks = [s for s in (all_board.get("stock_items") or []) if isinstance(s, dict)]
    org_items = [s for s in (org_board.get("stock_items") or []) if isinstance(s, dict)]
    hm_items = [g for g in (hm_board.get("hot_money_items") or []) if isinstance(g, dict)]
    if not stocks:
        raise _hithink.HithinkError(f"{trade_date} 没有返回龙虎榜个股明细")

    stock_count = int(all_board.get("stock_count") or len(stocks))
    net = lambda s: float(s.get("net_value") or 0)  # noqa: E731
    org_net = lambda s: float(s.get("org_net_value") or 0)  # noqa: E731

    # ── 净买入 TOP ──
    top_net_buy = []
    for s in sorted(stocks, key=net, reverse=True)[:10]:
        bits = []
        if s.get("org_net_value") is not None:
            bits.append(f"机构{_yi(s.get('org_net_value')):+.2f}亿")
        if s.get("hot_money_net_value") is not None:
            bits.append(f"游资{_yi(s.get('hot_money_net_value')):+.2f}亿")
        top_net_buy.append({
            "代码": s.get("ticker", ""),
            "名称": s.get("name", ""),
            "涨跌幅": _pct(s.get("change")),
            "净买额亿": _yi(s.get("net_value")),
            "买入额亿": _yi(s.get("buy_value")),
            "卖出额亿": _yi(s.get("sell_value")),
            "上榜原因": _concepts(s),
            "解读": " · ".join(bits),
        })

    # ── 净卖出 TOP ──
    top_net_sell = []
    for s in sorted(stocks, key=net)[:5]:
        if net(s) >= 0:
            continue
        top_net_sell.append({
            "代码": s.get("ticker", ""),
            "名称": s.get("name", ""),
            "涨跌幅": _pct(s.get("change")),
            "净卖额亿": abs(_yi(s.get("net_value"))),
            "上榜原因": _concepts(s),
        })

    # ── 机构净买入 TOP（含买卖机构家数）──
    top_institution_buy = []
    for s in sorted(org_items, key=org_net, reverse=True)[:8]:
        if org_net(s) <= 0:
            continue
        top_institution_buy.append({
            "代码": s.get("ticker", ""),
            "名称": s.get("name", ""),
            "机构净买入亿": _yi(s.get("org_net_value")),
            "买方机构数": int(s.get("org_buy_num") or 0),
            "卖方机构数": int(s.get("org_sell_num") or 0),
            "涨跌幅": _pct(s.get("change")),
        })

    # ── 游资派系 ──
    groups = []
    for g in hm_items:
        name = str(g.get("name") or "").strip()
        if not name:
            continue
        rows = [r for r in (g.get("rows") or []) if isinstance(r, dict)]
        groups.append({
            "派系": name,
            "净额亿": _yi(g.get("buying")),
            "操作个股数": len(rows),
            "涉及个股": [str(r.get("name") or "") for r in rows][:5],
        })

    ranked_groups = sorted(groups, key=lambda g: g["净额亿"], reverse=True)
    top_hot_money_buy = [
        {"席位": g["派系"], "昵称": g["派系"], "净买入亿": g["净额亿"],
         "操作个股数": g["操作个股数"], "涉及个股": g["涉及个股"]}
        for g in ranked_groups if g["净额亿"] > 0
    ][:8]
    top_hot_money_sell = [
        {"席位": g["派系"], "昵称": g["派系"], "净卖出亿": abs(g["净额亿"]),
         "操作个股数": g["操作个股数"], "涉及个股": g["涉及个股"]}
        for g in sorted(groups, key=lambda g: g["净额亿"]) if g["净额亿"] < 0
    ][:5]
    hot_money_groups = [
        {"派系": g["派系"],
         "方向": "净买入" if g["净额亿"] >= 0 else "净卖出",
         "总净额亿": abs(g["净额亿"]),
         "涉及个股": g["涉及个股"]}
        for g in sorted(groups, key=lambda g: abs(g["净额亿"]), reverse=True)[:3]
    ]

    # ── 概念分布（上榜个股的概念标签聚合，不等于当日涨停主线）──
    counter = {}
    for s in stocks:
        for item in (s.get("concept_list") or []):
            name = str((item or {}).get("name") or "").strip()
            if not name:
                continue
            bucket = counter.setdefault(name, {"count": 0, "stocks": []})
            bucket["count"] += 1
            if len(bucket["stocks"]) < 3:
                bucket["stocks"].append(str(s.get("name") or ""))
    main_themes = [
        {"板块": name,
         "强度": "🔥🔥" if value["count"] >= 5 else ("🔥" if value["count"] >= 3 else ""),
         "上榜家数": value["count"],
         "个股": value["stocks"]}
        for name, value in sorted(counter.items(), key=lambda kv: kv[1]["count"], reverse=True)[:6]
    ]

    # ── 关键信号 ──
    key_signals = []
    best = max(stocks, key=net)
    key_signals.append(f"最大单票净买 {best.get('name')} {_yi(best.get('net_value')):.2f}亿")
    inst_total = sum(org_net(s) for s in org_items)
    key_signals.append(f"机构合计净买 {inst_total / 1e8:.2f}亿（{len(org_items)}只上榜）")
    hm_in = sum(g["净额亿"] for g in groups if g["净额亿"] > 0)
    hm_out = sum(-g["净额亿"] for g in groups if g["净额亿"] < 0)
    key_signals.append(f"游资派系净买 {hm_in:.2f}亿 / 净卖 {hm_out:.2f}亿")
    multi = [s for s in stocks if int(s.get("range_days") or 1) >= 3]
    if multi:
        key_signals.append(f"{len(multi)}只连续3日以上上榜")

    key_stocks = []
    for s in sorted(stocks, key=lambda s: abs(net(s)), reverse=True)[:5]:
        key_stocks.append({
            "代码": s.get("ticker", ""),
            "名称": s.get("name", ""),
            "涨跌幅": _pct(s.get("change")),
            "净买额亿": _yi(s.get("net_value")),
            "机构净买亿": _yi(s.get("org_net_value")),
            "游资净买亿": _yi(s.get("hot_money_net_value")),
            "上榜天数": int(s.get("range_days") or 1),
        })

    components = {
        "龙虎榜总览": "ok" if stocks else "empty",
        "机构统计": "ok" if org_items else "empty",
        "游资派系": "ok" if groups else "empty",
    }
    missing = [name for name, status in components.items() if status != "ok"]
    result = {
        "date": trade_date,
        "requested_date": date_str,
        "data_date": trade_date,
        "fetch_time": datetime.now().strftime("%H:%M:%S"),
        "total_stocks": stock_count,
        "top_net_buy": top_net_buy,
        "top_net_sell": top_net_sell,
        "top_institution_buy": top_institution_buy,
        "top_hot_money_buy": top_hot_money_buy,
        "top_hot_money_sell": top_hot_money_sell,
        "hot_money_groups": hot_money_groups,
        "key_stocks_detail": key_stocks,
        "main_themes": main_themes,
        "key_signals": key_signals,
        "source": "同花顺官方龙虎榜（hithink-finance）",
        "components": components,
        "status": "ok" if stock_count > 0 else "empty",
    }
    result["note"] = f"龙虎榜明细截至{trade_date}" + (f"；缺少：{'、'.join(missing)}" if missing else "")
    return result


def main():
    if hasattr(sys.stdout, "reconfigure"):
        # 手动运行时控制台可能是 GBK；stdout 只承载 JSON，编排器也按 UTF-8 读取
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    date_str = get_date()
    result = None
    if _hithink.available():
        try:
            result = collect_hithink(date_str)
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARN] 同花顺龙虎榜不可用，回退 AkShare：{type(exc).__name__} {exc}", file=sys.stderr)
    else:
        print("  [WARN] 未检测到 hithink-finance CLI，直接使用 AkShare 降级路径", file=sys.stderr)

    if result is None:
        try:
            result = collect_akshare(date_str)
        except Exception as exc:  # noqa: BLE001
            trade_date = get_recent_trade_date(date_str)
            result = {
                "date": trade_date,
                "requested_date": date_str,
                "data_date": trade_date,
                "fetch_time": datetime.now().strftime("%H:%M:%S"),
                "total_stocks": 0,
                "top_net_buy": [], "top_net_sell": [], "top_institution_buy": [],
                "top_hot_money_buy": [], "top_hot_money_sell": [], "hot_money_groups": [],
                "key_stocks_detail": [], "main_themes": [], "key_signals": [],
                "source": "同花顺官方龙虎榜（hithink-finance）+ AkShare 降级",
                "components": {"龙虎榜总览": "error", "机构统计": "error", "游资派系": "error"},
                "status": "error",
                "note": f"两个数据源都失败：{type(exc).__name__} {exc}",
            }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
