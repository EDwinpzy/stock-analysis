#!/usr/bin/env python3
"""
解析同花顺远航版 stockblock.ini，提取全部自选股（去重）
使用手动解析，避免 configparser 编码和转义问题
"""
import json
import os
import re
import sys

THS_DIR = os.environ.get("THS_SELFSTOCK_PATH", r"C:\应用\同花顺\mo_4aknfs5zs")
if THS_DIR.endswith(".json"):
    THS_DIR = os.path.dirname(THS_DIR)
STOCKBLOCK_FILE = os.path.join(THS_DIR, "stockblock.ini")

MARKET_MAP = {"17": "SH", "33": "SZ", "48": "BJ"}


def parse_stockblock(filepath=None):
    if filepath is None:
        filepath = STOCKBLOCK_FILE

    if not os.path.exists(filepath):
        print(json.dumps({"error": f"文件不存在: {filepath}"}, ensure_ascii=False))
        sys.exit(1)

    with open(filepath, "rb") as f:
        raw_bytes = f.read()

    # 尝试编码
    for enc in ["gbk", "utf-8", "gb2312", "gb18030"]:
        try:
            content = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        content = raw_bytes.decode("latin-1")

    # 解析节
    sections = {}
    current_section = None
    for line in content.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1]
            sections[current_section] = {}
            continue
        if current_section and "=" in line:
            idx = line.index("=")
            key = line[:idx].strip()
            value = line[idx + 1:].strip()
            sections[current_section][key] = value

    # 板块名称映射
    name_map = sections.get("BLOCK_NAME_MAP_TABLE", {})

    # 解析所有板块的股票
    all_stocks = {}
    group_stats = {}

    stock_context = sections.get("BLOCK_STOCK_CONTEXT", {})
    for group_id, raw in stock_context.items():
        entries = re.findall(r"(\d+):(\d+)", raw)
        stocks_in_group = []

        for market, code in entries:
            prefix = MARKET_MAP.get(market, "UNKNOWN")
            full_code = f"{code}.{prefix}" if prefix != "UNKNOWN" else code

            if code not in all_stocks:
                all_stocks[code] = {
                    "code": code,
                    "market": market,
                    "prefix": prefix,
                    "full_code": full_code,
                    "groups": [],
                }
            all_stocks[code]["groups"].append(group_id)
            stocks_in_group.append(code)

        group_stats[group_id] = {
            "name": name_map.get(group_id, group_id),
            "count": len(stocks_in_group),
            "stocks": stocks_in_group,
        }

    stock_list = list(all_stocks.values())
    stock_list.sort(key=lambda x: x["code"])

    # 分组统计
    sorted_groups = sorted(group_stats.items())

    return {
        "total_unique_stocks": len(stock_list),
        "total_groups": len(group_stats),
        "groups": {gid: {"name": gs["name"], "count": gs["count"]} for gid, gs in sorted_groups},
        "stocks": stock_list,
    }


if __name__ == "__main__":
    data = parse_stockblock()

    # 摘要输出
    print(json.dumps(
        {
            "total_unique_stocks": data["total_unique_stocks"],
            "total_groups": data["total_groups"],
            "groups": data["groups"],
        },
        ensure_ascii=False,
        indent=2,
    ))

    # 完整代码列表输出到 stderr
    codes = data["stocks"]
    sh_stocks = [s for s in codes if s["prefix"] == "SH"]
    sz_stocks = [s for s in codes if s["prefix"] == "SZ"]
    bj_stocks = [s for s in codes if s["prefix"] == "BJ"]

    print(
        f"\n// SH: {len(sh_stocks)} | SZ: {len(sz_stocks)} | BJ: {len(bj_stocks)} | Total: {len(codes)}",
        file=sys.stderr,
    )

    # 按市场分组输出代码（SH开头 + SZ开头）
    sh_list = ",".join(s["full_code"] for s in sh_stocks)
    sz_list = ",".join(s["full_code"] for s in sz_stocks)
    print(f"---SH---\n{sh_list}\n---SZ---\n{sz_list}", file=sys.stderr)
