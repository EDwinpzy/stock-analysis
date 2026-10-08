#!/usr/bin/env python3
"""按情绪周期整理「节点票」。

定义（按超短周期的节点口径）：

1. 高标连板段：某只票连续交易日的涨停连板数逐日 +1（首板、二板、三板……），
   直到它不再出现在涨停池里，这一段就是它的连板生命周期。
2. 断板日：高标连板段结束的次一个交易日。老高标在这天没能继续封板
   （无论是冲高炸板还是直接走弱），是情绪周期换节点的位置。
3. 节点票：断板日当天，连板高度落在「首板 / 二板」这一层里最高的那批票。
   二板优先于首板；同一高度先按首封时间早、再按封单额大排序。
   这批票就是下一个节点的候选龙头。

数据来自 tools/fetch_limit_up_pools.py 缓存的涨停池。

示例：
    python tools/node_stocks.py --min-height 4
    python tools/node_stocks.py --min-height 5 --start 2026-01-01
    python tools/node_stocks.py --min-height 4 --csv data/node_stocks.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POOL_DIR = PROJECT_ROOT / "data" / "pools"
NODE_TIER = 2  # 节点票只看首板/二板这一层

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


@dataclass
class Bar:
    """某只票在某个交易日的涨停记录。"""

    day: date
    cnt: int
    time: str
    seal_money: float
    reason: str


@dataclass
class Run:
    """一只票的一段连板生命周期。"""

    code: str
    name: str
    bars: list[Bar] = field(default_factory=list)

    @property
    def start(self) -> date:
        return self.bars[0].day

    @property
    def end(self) -> date:
        return self.bars[-1].day

    @property
    def peak(self) -> int:
        return max(bar.cnt for bar in self.bars)

    @property
    def reason(self) -> str:
        return self.bars[-1].reason


def load_pools(pool_dir: Path) -> dict[date, list[dict]]:
    pools: dict[date, list[dict]] = {}
    for path in sorted(pool_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        day = datetime.fromisoformat(payload["date"]).date()
        pools[day] = payload.get("items") or []
    return pools


def build_runs(days: list[date], pools: dict[date, list[dict]]) -> list[Run]:
    """把逐日涨停池拆成「一只票的一段连板生命周期」。"""
    order = {day: index for index, day in enumerate(days)}
    seen: dict[str, list[Bar]] = {}
    names: dict[str, str] = {}
    for day in days:
        for item in pools.get(day, []):
            code = str(item.get("thscode") or item.get("ticker"))
            names[code] = str(item.get("name") or code)
            seen.setdefault(code, []).append(
                Bar(
                    day=day,
                    cnt=int(item.get("continue_day_cnt") or 1),
                    time=str(item.get("limit_up_time") or ""),
                    seal_money=float(item.get("seal_money") or 0.0),
                    reason=str(item.get("limit_up_reason") or ""),
                )
            )

    runs: list[Run] = []
    for code, bars in seen.items():
        bars.sort(key=lambda bar: bar.day)
        current: list[Bar] = []
        for bar in bars:
            if not current:
                current = [bar]
                continue
            prev = current[-1]
            # 连续交易日且连板数恰好 +1，才算同一段连板。
            if bar.cnt == prev.cnt + 1 and order[bar.day] - order[prev.day] == 1:
                current.append(bar)
            else:
                runs.append(Run(code=code, name=names[code], bars=current))
                current = [bar]
        if current:
            runs.append(Run(code=code, name=names[code], bars=current))
    return runs


def rank_candidates(items: list[dict]) -> list[dict]:
    """节点票候选排序：连板高度 > 首封时间早 > 封单额大。"""

    def sort_key(item: dict):
        return (
            -int(item.get("continue_day_cnt") or 1),
            str(item.get("limit_up_time") or "99:99"),
            -float(item.get("seal_money") or 0.0),
        )

    return sorted(items, key=sort_key)


PICK_RULES = ("time", "seal", "combo")


def pick_by_rule(candidates: list[dict], rule: str) -> dict | None:
    """在最高板层（二板优先）里按指定规则挑一只。"""
    if not candidates:
        return None
    top = max(int(item.get("continue_day_cnt") or 1) for item in candidates)
    tier = [item for item in candidates if int(item.get("continue_day_cnt") or 1) == top]

    def seal(item: dict) -> float:
        return float(item.get("seal_money") or 0.0)

    def clock(item: dict) -> str:
        return str(item.get("limit_up_time") or "99:99")

    if rule == "time":
        return min(tier, key=lambda item: (clock(item), -seal(item)))
    if rule == "seal":
        return sorted(tier, key=lambda item: (-seal(item), clock(item)))[0]

    # combo：首封时间与封单额各排一次名，名次相加取最优。
    by_time = {id(item): rank for rank, item in enumerate(sorted(tier, key=clock))}
    by_seal = {
        id(item): rank for rank, item in enumerate(sorted(tier, key=seal, reverse=True))
    }
    return min(tier, key=lambda item: (by_time[id(item)] + by_seal[id(item)], clock(item)))


def follow_up(runs_by_code: dict[str, list[Run]], code: str, day: date) -> Run | None:
    """找出覆盖某日的连板段，用来回溯节点票后续走到了哪一步。"""
    for run in runs_by_code.get(code, []):
        if run.start <= day <= run.end:
            return run
    return None


def space_of(pool: list[dict]) -> int:
    return max((int(item.get("continue_day_cnt") or 1) for item in pool), default=0)


def tops_of(pool: list[dict], space: int) -> list[str]:
    """某天处于最高连板高度的票。"""
    return [
        str(item.get("thscode"))
        for item in pool
        if int(item.get("continue_day_cnt") or 1) == space
    ]


def find_nodes(
    days: list[date],
    pools: dict[date, list[dict]],
    min_height: int,
    leader_days: int = 1,
) -> list[dict]:
    """找出「市场空间板断板」的节点日。

    判定：前一个交易日的最高连板高度 ≥ min_height，且当天最高的那批票
    全部没有出现在涨停池里（即市场空间板断板）。

    leader_days > 1 时，还要求这只高标连续 leader_days 个交易日都站在
    市场最高连板高度上，用来滤掉退潮期里只当了一天最高标的伪节点。
    """
    nodes: list[dict] = []
    for index in range(1, len(days)):
        prev_day, day = days[index - 1], days[index]
        prev_pool = pools.get(prev_day, [])
        prev_space = space_of(prev_pool)
        if prev_space < min_height:
            continue
        leaders = tops_of(prev_pool, prev_space)
        today_codes = {str(item.get("thscode")) for item in pools.get(day, [])}
        if any(code in today_codes for code in leaders):
            continue
        if leader_days > 1:
            held = set(leaders)
            for back in range(2, leader_days + 1):
                earlier = days[index - back]
                held &= set(tops_of(pools.get(earlier, []), space_of(pools.get(earlier, []))))
            if not held:
                continue
            leaders = [code for code in leaders if code in held]
        names = {
            str(item.get("thscode")): item
            for item in prev_pool
        }
        nodes.append(
            {
                "break_day": day,
                "prev_day": prev_day,
                "leader_peak": prev_space,
                "leaders": [
                    {
                        "code": code,
                        "name": str(names[code].get("name")),
                        "reason": str(names[code].get("limit_up_reason") or ""),
                    }
                    for code in leaders
                    if code in names
                ],
            }
        )
    return nodes


def main() -> int:
    parser = argparse.ArgumentParser(description="按周期整理节点票")
    parser.add_argument("--pools", default=str(POOL_DIR))
    parser.add_argument("--start", default=None, help="只输出该日期之后的节点")
    parser.add_argument("--end", default=None, help="只输出该日期之前的节点")
    parser.add_argument(
        "--min-height",
        type=int,
        default=5,
        help="只统计市场空间板高度不低于该值的断板节点（默认 5）",
    )
    parser.add_argument("--csv", default=None, help="把结果写成 CSV")
    parser.add_argument("--candidates-csv", default=None, help="断板日首板/二板候选明细 CSV")
    parser.add_argument("--detail", action="store_true", help="打印每个节点的候选明细")
    parser.add_argument(
        "--pick",
        choices=PICK_RULES,
        default="time",
        help="同高度二板里的选票规则：time 首封最早 / seal 封单最大 / combo 综合",
    )
    parser.add_argument("--stats", action="store_true", help="比较各选票规则的历史命中率")
    parser.add_argument(
        "--leader-days",
        type=int,
        default=2,
        help="高标需连续多少个交易日占据空间板才算周期龙头（默认 2，设 1 关闭过滤）",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()

    pools = load_pools(Path(args.pools))
    if not pools:
        print("没有找到涨停池缓存，先跑 tools/fetch_limit_up_pools.py")
        return 1

    days = sorted(pools)
    runs = build_runs(days, pools)
    runs_by_code: dict[str, list[Run]] = {}
    for run in runs:
        runs_by_code.setdefault(run.code, []).append(run)

    start = datetime.fromisoformat(args.start).date() if args.start else None
    end = datetime.fromisoformat(args.end).date() if args.end else None

    records: list[dict] = []
    candidate_rows: list[dict] = []
    stat_rows: list[dict] = []
    for node_event in find_nodes(days, pools, args.min_height, args.leader_days):
        break_day: date = node_event["break_day"]
        if start and break_day < start:
            continue
        if end and break_day > end:
            continue
        leaders = node_event["leaders"]
        pool = pools.get(break_day, [])
        tiered = [
            item
            for item in pool
            if int(item.get("continue_day_cnt") or 1) <= NODE_TIER
        ]
        ranked = rank_candidates(tiered)
        top_cnt = int(ranked[0].get("continue_day_cnt") or 1) if ranked else 0
        picks = [item for item in ranked if int(item.get("continue_day_cnt") or 1) == top_cnt]

        node = pick_by_rule(tiered, args.pick) if tiered else None
        if node is not None:
            picks = [node] + [item for item in picks if item is not node]
        node_follow = None
        if node is not None:
            node_follow = follow_up(runs_by_code, str(node.get("thscode")), break_day)
        stat_rows.append(
            {
                "break_day": break_day,
                "candidates": tiered,
                "runs_by_code": runs_by_code,
            }
        )

        candidates: list[dict] = []
        for item in ranked:
            follow = follow_up(runs_by_code, str(item.get("thscode")), break_day)
            candidates.append(
                {
                    "break_day": break_day.isoformat(),
                    "leader": "/".join(leader["name"] for leader in leaders),
                    "leader_peak": node_event["leader_peak"],
                    "code": str(item.get("thscode")),
                    "name": str(item.get("name")),
                    "cnt": int(item.get("continue_day_cnt") or 1),
                    "time": str(item.get("limit_up_time") or ""),
                    "seal_money": float(item.get("seal_money") or 0.0),
                    "reason": str(item.get("limit_up_reason") or ""),
                    "later_peak": follow.peak if follow else None,
                    "later_end": follow.end.isoformat() if follow else None,
                }
            )
        candidate_rows.extend(candidates)

        records.append(
            {
                "break_day": break_day.isoformat(),
                "prev_day": node_event["prev_day"].isoformat(),
                "leader": "/".join(leader["name"] for leader in leaders),
                "leader_peak": node_event["leader_peak"],
                "leader_reason": "/".join(
                    dict.fromkeys(leader["reason"] for leader in leaders if leader["reason"])
                ),
                "candidate_height": top_cnt,
                "candidate_count": len(picks),
                "node_code": str(node.get("thscode")) if node else "",
                "node_name": str(node.get("name")) if node else "",
                "node_time": str(node.get("limit_up_time")) if node else "",
                "node_seal_money": float(node.get("seal_money") or 0.0) if node else 0.0,
                "node_reason": str(node.get("limit_up_reason")) if node else "",
                "other_candidates": "、".join(
                    f"{item['name']}({item['limit_up_time']})" for item in picks[1:]
                ),
                "node_peak": node_follow.peak if node_follow else None,
                "node_end": node_follow.end.isoformat() if node_follow else None,
            }
        )

    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=1))
    else:
        header = (
            f"{'断板日':<12}{'老龙头(峰值)':<22}{'节点票':<14}"
            f"{'板':>3}{'首封':>7}{'封单(亿)':>9}  {'后续最高':<8}题材"
        )
        print(header)
        print("-" * 122)
        for row in records:
            leader = f"{row['leader']}({row['leader_peak']}板)"
            node = row["node_name"] or "—"
            peak = f"{row['node_peak']}板" if row["node_peak"] else "—"
            print(
                f"{row['break_day']:<12}{leader:<22}{node:<14}"
                f"{row['candidate_height']:>3}{row['node_time']:>7}"
                f"{row['node_seal_money'] / 1e8:>9.2f}  {peak:<8}{row['node_reason'][:24]}"
            )
        print(f"\n共 {len(records)} 个节点（空间板高度 ≥ {args.min_height} 后断板）")

    if args.stats and not args.json:
        print(f"\n选票规则对比（{len(stat_rows)} 个节点，命中=该票后续走到 ≥3板 / ≥4板）")
        print(f"{'规则':<10}{'≥3板命中':>12}{'≥4板命中':>12}{'平均后续最高':>14}")
        print("-" * 50)
        for rule in PICK_RULES:
            peaks: list[int] = []
            for stat in stat_rows:
                chosen = pick_by_rule(stat["candidates"], rule)
                if chosen is None:
                    continue
                follow = follow_up(
                    stat["runs_by_code"], str(chosen.get("thscode")), stat["break_day"]
                )
                peaks.append(follow.peak if follow else 1)
            if not peaks:
                continue
            hit3 = sum(1 for peak in peaks if peak >= 3)
            hit4 = sum(1 for peak in peaks if peak >= 4)
            label = {"time": "首封最早", "seal": "封单最大", "combo": "综合"}[rule]
            print(
                f"{label:<10}{hit3:>7}/{len(peaks):<4}{hit4:>8}/{len(peaks):<4}"
                f"{sum(peaks) / len(peaks):>14.2f}"
            )

    if args.detail and not args.json:
        print()
        for row in records:
            group = [c for c in candidate_rows if c["break_day"] == row["break_day"]]
            print(
                f"◆ {row['break_day']}  {row['leader']} 断板（{row['leader_peak']}板）"
                f"  → 候选 {len(group)} 只"
            )
            for candidate in group:
                peak = f"{candidate['later_peak']}板" if candidate["later_peak"] else "—"
                marker = "★" if candidate["code"] == row["node_code"] else " "
                print(
                    f"  {marker} {candidate['cnt']}板 {candidate['name']:<8}"
                    f"{candidate['time']:>6}  封{candidate['seal_money'] / 1e8:>5.2f}亿"
                    f"  后续{peak:<5}{candidate['reason'][:30]}"
                )

    if args.csv:
        target = Path(args.csv)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
            writer.writeheader()
            writer.writerows(records)
        print(f"已写出 {target}")

    if args.candidates_csv and candidate_rows:
        target = Path(args.candidates_csv)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(candidate_rows[0].keys()))
            writer.writeheader()
            writer.writerows(candidate_rows)
        print(f"已写出 {target}（{len(candidate_rows)} 行候选）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
