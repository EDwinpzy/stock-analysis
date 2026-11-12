#!/usr/bin/env python3
"""解析自选股配置，不扫描本机同花顺安装目录。

配置优先级：
  1. ``THS_SELFSTOCK_CODES``：逗号、分号或空白分隔的代码列表
  2. ``THS_SELFSTOCK_JSON``：代码数组，或含 ``stocks``/``codes`` 的对象
  3. ``THS_SELFSTOCK_PATH``：显式指定的只读 JSON 文件

文件格式兼容旧版 ``SelfStockInfo.json`` 以及远航版导出的管道分隔格式。
云端应通过环境变量或只读 Secret 提供数据，禁止依赖用户电脑上的安装目录。
"""
import json
import os
import re
import sys


# 市场代码映射 (M字段→交易所前缀)
MARKET_MAP = {
    "17": "SH",  # 上海
    "33": "SZ",  # 深圳
    "48": "BJ",  # 北京（旧）
    "20": "BJ",  # 北京（新）
}


# ── 配置源发现 ──────────────────────────────────────────

_EXCHANGE_BY_MARKET = {"17": "SH", "33": "SZ", "48": "BJ", "20": "BJ"}
_MARKET_BY_EXCHANGE = {"SH": "17", "SZ": "33", "BJ": "20"}


def _stock_from_code(value, market=""):
    raw = str(value or "").strip()
    if not raw:
        return None
    code, _, suffix = raw.partition(".")
    code = code.strip()
    suffix = suffix.strip().upper()
    exchange = suffix if suffix in _MARKET_BY_EXCHANGE else ""
    if not exchange and market:
        exchange = _EXCHANGE_BY_MARKET.get(str(market), str(market))
    if not exchange and re.fullmatch(r"\d{6}", code):
        if code[0] in "69":
            exchange = "SH"
        elif code[0] in "03":
            exchange = "SZ"
        elif code[0] in "48":
            exchange = "BJ"
    if exchange not in _MARKET_BY_EXCHANGE:
        exchange = "UNKNOWN"
    return {
        "code": code,
        "market": str(market) or _MARKET_BY_EXCHANGE.get(exchange, ""),
        "prefix": exchange,
        "full_code": f"{code}.{exchange}" if exchange in _MARKET_BY_EXCHANGE else code,
        "price": "",
        "add_date": "",
    }


def _dedupe_stocks(stocks):
    unique = {}
    for stock in stocks:
        if stock and stock.get("code"):
            unique.setdefault(stock["code"], stock)
    return list(unique.values())


def _parse_codes(value):
    return _dedupe_stocks(
        _stock_from_code(code)
        for code in re.split(r"[,;，；\s]+", str(value or ""))
        if code.strip()
    )


def _parse_env_json(value):
    payload = json.loads(value)
    if isinstance(payload, dict):
        payload = payload.get("stocks") or payload.get("codes") or payload.get("data") or []
    if not isinstance(payload, list):
        raise ValueError("THS_SELFSTOCK_JSON 必须是数组，或包含 stocks/codes 数组的对象")
    stocks = []
    for row in payload:
        if isinstance(row, dict):
            stocks.append(
                _stock_from_code(
                    row.get("code") or row.get("C") or "",
                    row.get("market") or row.get("M") or "",
                )
            )
        else:
            stocks.append(_stock_from_code(row))
    return _dedupe_stocks(stocks)


def _env_selfstock():
    codes = os.environ.get("THS_SELFSTOCK_CODES", "").strip()
    if codes:
        return _parse_codes(codes), "env_codes"
    payload = os.environ.get("THS_SELFSTOCK_JSON", "").strip()
    if payload:
        return _parse_env_json(payload), "env_json"
    return None, ""


def discover_selfstock_file():
    """
    返回显式配置的自选股文件，不递归扫描系统目录。

    Returns:
        (filepath, format_type)
    format_type: 'cache_json' | 'xiadan_json' | 'old_json' | None
    """
    env_path = os.environ.get("THS_SELFSTOCK_PATH", "").strip()
    if env_path:
        expanded = os.path.expanduser(env_path)
        if os.path.isfile(expanded):
            fname = os.path.basename(expanded)
            if "SelfStockCache" in fname:
                return expanded, "cache_json"
            if "selfstock_" in fname.lower():
                return expanded, "xiadan_json"
            if "SelfStockInfo" in fname:
                return expanded, "old_json"
            return expanded, "cache_json"
        if os.path.isdir(expanded):
            for fmt, pattern in [
                ("cache_json", "SelfStockCache.json"),
                ("old_json", "SelfStockInfo.json"),
            ]:
                candidate = os.path.join(expanded, pattern)
                if os.path.isfile(candidate):
                    return candidate, fmt

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
        filepath: 自选股文件路径；为 None 时读取显式环境变量配置
        fmt: 格式提示，'cache_json' | 'xiadan_json' | 'old_json'，为 None 时自动检测

    Returns:
        List[Dict]: 股票列表，每个元素包含 code, market, prefix, full_code, price, add_date
    """
    if filepath is None:
        env_stocks, _ = _env_selfstock()
        if env_stocks is not None:
            return env_stocks
        filepath, fmt = discover_selfstock_file()
        if filepath is None:
            raise FileNotFoundError(
                "未配置自选股。请设置 THS_SELFSTOCK_CODES、THS_SELFSTOCK_JSON，"
                "或用 THS_SELFSTOCK_PATH 指向只读 JSON。"
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
        env_stocks, env_format = _env_selfstock()
        if env_stocks is not None:
            return {
                "found": True,
                "filepath": "",
                "format": env_format,
                "count": len(env_stocks),
                "sync_time": "",
            }
        filepath, fmt = discover_selfstock_file()
    if filepath is None:
        return {
            "found": False,
            "error": "未配置 THS_SELFSTOCK_CODES、THS_SELFSTOCK_JSON 或 THS_SELFSTOCK_PATH",
        }
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
                "hint": "请设置 THS_SELFSTOCK_CODES 或 THS_SELFSTOCK_JSON；云端不要扫描本机安装目录",
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
