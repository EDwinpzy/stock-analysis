#!/usr/bin/env python3
"""
解析同花顺（含远航版）自选股文件
支持三种格式：
  1. 旧版同花顺：SelfStockInfo.json (数组格式)
  2. 新版远航版：bin/users/*/SelfStockCache.json (管道分隔格式)
  3. 新版远航版：transaction/xiadan-plus/selfstock_*.json (管道分隔格式)

搜索优先级（自动发现）：
  1. THS_SELFSTOCK_PATH 环境变量（精确路径或目录）
  2. 远航版 bin/users/*/SelfStockCache.json
  3. 远航版 transaction/xiadan-plus/selfstock_*.json
  4. 旧版同花顺 mo_*/SelfStockInfo.json
"""
import json
import os
import sys
import glob as glob_mod


# 市场代码映射 (M字段→交易所前缀)
MARKET_MAP = {
    "17": "SH",  # 上海
    "33": "SZ",  # 深圳
    "48": "BJ",  # 北京（旧）
    "20": "BJ",  # 北京（新）
}


# ── 文件发现 ────────────────────────────────────────────

def _find_ths_base_dirs():
    """查找同花顺安装根目录"""
    candidates = []
    for base in [r"C:\应用\同花顺远航版", r"C:\应用\同花顺"]:
        if os.path.isdir(base):
            candidates.append(base)
    return candidates


def discover_selfstock_file():
    """
    自动发现自选股文件，返回 (filepath, format_type)
    format_type: 'cache_json' | 'xiadan_json' | 'old_json' | None
    """
    # 1. 环境变量优先
    env_path = os.environ.get("THS_SELFSTOCK_PATH", "")
    if env_path:
        if os.path.isfile(env_path):
            # 根据文件名判断格式
            fname = os.path.basename(env_path)
            if "SelfStockCache" in fname:
                return env_path, "cache_json"
            elif "selfstock_" in fname.lower():
                return env_path, "xiadan_json"
            elif "SelfStockInfo" in fname:
                return env_path, "old_json"
            else:
                return env_path, "cache_json"  # 猜
        elif os.path.isdir(env_path):
            # 目录：尝试在下面找
            for fmt, pattern in [
                ("cache_json", "SelfStockCache.json"),
                ("old_json", "SelfStockInfo.json"),
            ]:
                p = os.path.join(env_path, pattern)
                if os.path.isfile(p):
                    return p, fmt

    # 2. 远航版 bin/users/*/SelfStockCache.json（优先：有 Count 字段，最新）
    for base in _find_ths_base_dirs():
        pattern = os.path.join(base, "bin", "users", "*", "SelfStockCache.json")
        files = sorted(glob_mod.glob(pattern), key=os.path.getmtime, reverse=True)
        if files:
            return files[0], "cache_json"

    # 3. 远航版 transaction/xiadan-plus/selfstock_*.json
    for base in _find_ths_base_dirs():
        pattern = os.path.join(base, "transaction", "xiadan-plus", "selfstock_*.json")
        files = sorted(glob_mod.glob(pattern), key=os.path.getmtime, reverse=True)
        if files:
            return files[0], "xiadan_json"

    # 4. 旧版同花顺 mo_*/SelfStockInfo.json
    for base in _find_ths_base_dirs():
        pattern = os.path.join(base, "mo_*", "SelfStockInfo.json")
        files = sorted(glob_mod.glob(pattern), key=os.path.getmtime, reverse=True)
        if files:
            return files[0], "old_json"

    # 5. 远航版 transaction/mo_*/SelfStockInfo.json
    for base in _find_ths_base_dirs():
        pattern = os.path.join(base, "transaction", "mo_*", "SelfStockInfo.json")
        files = sorted(glob_mod.glob(pattern), key=os.path.getmtime, reverse=True)
        if files:
            return files[0], "old_json"

    return None, None


# ── 解析器 ──────────────────────────────────────────────

def _parse_cache_json(filepath):
    """
    解析 SelfStockCache.json（远航版新版格式）
    格式: {"Data": {"Selfstock": "code1|code2|...|,mkt1|mkt2|...", "Count": N, "ModifyTime": "..."}}
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    d = data.get("Data", data)
    n = d.get("Count", 0)
    raw = d.get("Selfstock", d.get("selfstock", ""))

    if not raw or n == 0:
        return []

    parts = [p for p in raw.split("|") if p]
    codes = parts[:n]
    markets_raw = parts[n:n * 2] if len(parts) >= n * 2 else []

    markets = []
    for m in markets_raw:
        m = m.lstrip(",")  # 第一个市场码前有逗号
        markets.append(m)

    stocks = []
    for i in range(n):
        code = codes[i]
        mkt = markets[i] if i < len(markets) else "?"
        prefix = MARKET_MAP.get(mkt, f"UNKNOWN({mkt})")
        stocks.append({
            "code": code,
            "market": mkt,
            "prefix": prefix,
            "full_code": f"{code}.{prefix}",
            "price": "",
            "add_date": "",
        })
    return stocks


def _parse_xiadan_json(filepath):
    """
    解析 xiadan-plus/selfstock_*.json
    格式与 cache_json 类似，但字段名略有不同
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    d = data.get("data", data.get("Data", {}))
    n = d.get("num", d.get("Count", 0))
    raw = d.get("selfstock", d.get("Selfstock", ""))

    if not raw or n == 0:
        return []

    parts = [p for p in raw.split("|") if p]
    codes = parts[:n]
    markets_raw = parts[n:n * 2] if len(parts) >= n * 2 else []

    markets = []
    for m in markets_raw:
        m = m.lstrip(",")
        markets.append(m)

    stocks = []
    for i in range(n):
        code = codes[i]
        mkt = markets[i] if i < len(markets) else "?"
        prefix = MARKET_MAP.get(mkt, f"UNKNOWN({mkt})")
        stocks.append({
            "code": code,
            "market": mkt,
            "prefix": prefix,
            "full_code": f"{code}.{prefix}",
            "price": "",
            "add_date": "",
        })
    return stocks


def _parse_old_json(filepath):
    """
    解析旧版 SelfStockInfo.json
    格式: [{"C": "600693", "M": "17", "P": "", "T": ""}, ...]
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    stocks = []
    for item in data:
        code = item.get("C", "")
        market = item.get("M", "")
        price = item.get("P", "")
        date = item.get("T", "")

        prefix = MARKET_MAP.get(market, "UNKNOWN")
        full_code = f"{code}.{prefix}" if prefix != "UNKNOWN" else code

        stocks.append({
            "code": code,
            "market": market,
            "prefix": prefix,
            "full_code": full_code,
            "price": price,
            "add_date": date,
        })
    return stocks


# ── 公共接口 ────────────────────────────────────────────

def parse_selfstock(filepath=None, fmt=None):
    """
    解析自选股文件，返回股票列表

    Args:
        filepath: 自选股文件路径，为 None 时自动发现
        fmt: 格式提示，'cache_json' | 'xiadan_json' | 'old_json'，为 None 时自动检测

    Returns:
        List[Dict]: 股票列表，每个元素包含 code, market, prefix, full_code, price, add_date
    """
    if filepath is None:
        filepath, fmt = discover_selfstock_file()
        if filepath is None:
            raise FileNotFoundError(
                "未找到自选股文件。请设置 THS_SELFSTOCK_PATH 环境变量，"
                "或确保同花顺（远航版）已安装在默认位置。"
            )

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"自选股文件不存在: {filepath}")

    if fmt is None:
        fname = os.path.basename(filepath)
        if "SelfStockCache" in fname:
            fmt = "cache_json"
        elif "selfstock_" in fname.lower():
            fmt = "xiadan_json"
        elif "SelfStockInfo" in fname:
            fmt = "old_json"
        else:
            # 尝试自动检测
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                fmt = "old_json"
            elif "Selfstock" in data.get("Data", {}):
                fmt = "cache_json"
            elif "selfstock" in data.get("data", {}):
                fmt = "xiadan_json"
            else:
                raise ValueError(f"无法识别的自选股文件格式: {filepath}")

    parsers = {
        "cache_json": _parse_cache_json,
        "xiadan_json": _parse_xiadan_json,
        "old_json": _parse_old_json,
    }
    parser = parsers.get(fmt)
    if parser is None:
        raise ValueError(f"不支持的格式: {fmt}")

    return parser(filepath)


def get_selfstock_codes(filepath=None, fmt=None):
    """获取自选股代码列表（仅代码字符串列表）"""
    stocks = parse_selfstock(filepath, fmt)
    return [s["code"] for s in stocks]


def get_selfstock_fullcodes(filepath=None, fmt=None):
    """获取自选股完整代码列表（含交易所前缀）"""
    stocks = parse_selfstock(filepath, fmt)
    return [s["full_code"] for s in stocks]


def _read_sync_time(filepath):
    """从自选股文件中读取同步时间（若有）"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        d = data.get("Data", data.get("data", {}))
        # SelfStockCache 用 ModifyTime，xiadan 用 rtime
        return d.get("ModifyTime", d.get("rtime", d.get("modify_time", "")))
    except Exception:
        return ""


def get_selfstock_source_info(filepath=None, fmt=None):
    """返回自选股来源信息（文件路径、格式、股票数量、同步时间）"""
    if filepath is None:
        filepath, fmt = discover_selfstock_file()
    if filepath is None:
        return {"found": False, "error": "未找到自选股文件"}
    stocks = parse_selfstock(filepath, fmt)
    sync_time = _read_sync_time(filepath)
    return {
        "found": True,
        "filepath": filepath,
        "format": fmt,
        "count": len(stocks),
        "sync_time": sync_time,
    }


# ── CLI ─────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        info = get_selfstock_source_info()
        if not info["found"]:
            print(json.dumps({
                "error": info.get("error", "未找到自选股文件"),
                "hint": "请设置 THS_SELFSTOCK_PATH 环境变量",
            }, ensure_ascii=False, indent=2))
            sys.exit(1)

        stocks = parse_selfstock(info["filepath"], info["format"])
        print(json.dumps({
            "count": len(stocks),
            "stocks": stocks,
            "source_file": info["filepath"],
            "source_format": info["format"],
            "sync_time": info.get("sync_time", ""),
        }, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False, indent=2))
        sys.exit(1)
