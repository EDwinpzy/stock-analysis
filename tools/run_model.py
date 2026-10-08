#!/usr/bin/env python3
"""运行 A股超短情绪温度模型 3.2。

示例：
    python tools/run_model.py                          # 用自带面板跑最新一天
    python tools/run_model.py --date 2026-09-11        # 指定交易日
    python tools/run_model.py --tail 10                # 附带最近10天的温度表
    python tools/run_model.py --export out.csv         # 导出完整温度序列
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from emotion import EmotionEngine  # noqa: E402
from emotion.config import DEFAULT_DATA_DIR  # noqa: E402
from emotion.display import phase_display, render_state, temperature_grade  # noqa: E402


def _cell(value, digits: int = 1, dash: str = "—") -> str:
    if value is None or value != value:
        return dash
    return f"{value:.{digits}f}"


def _print_tail(engine: EmotionEngine, count: int) -> None:
    frame = engine.history_frame().tail(count)
    header = f"{'日期':<12}{'温度S':>8}{'Δ1':>9}{'Δ2':>9}  {'阶段':<10}{'接缝J':>8}  动能"
    print(header)
    print("-" * 74)
    for _, row in frame.iterrows():
        print(
            f"{row['date']:<12}{row['S']:>8.1f}{_cell(row['delta1']):>9}{_cell(row['delta2']):>9}  "
            f"{phase_display(str(row['phase'])):<10}{row['J']:>8.1f}  {row['momentum'] or '—'}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="A股超短情绪温度模型 3.2")
    parser.add_argument("--panel", default=str(DEFAULT_DATA_DIR / "panel_history.csv"))
    parser.add_argument("--date", default=None)
    parser.add_argument("--tail", type=int, default=0)
    parser.add_argument("--export", default=None)
    parser.add_argument("--json", action="store_true", help="以 JSON 输出当日状态")
    args = parser.parse_args()

    engine = EmotionEngine().load_csv(args.panel)
    state = engine.get_market_state(args.date)
    state = {**state, "grade": temperature_grade(state["S"], state["phase"])}

    if args.json:
        import json
        print(json.dumps(state, ensure_ascii=False, indent=2))
    else:
        print(f"=== 情绪温度模型 {state['model']} · {state['date']} ===")
        print(render_state(state))
        print()
        print(
            f"接缝分量: 龙头承压 {state['J_leader']:+.1f}x0.35  "
            f"跟风稳定 {state['J_follower']:+.1f}x0.25  "
            f"晋级方向 {state['J_promotion']:+.1f}x0.40  -> J={state['J']:+.1f}"
        )

    if args.tail:
        print()
        _print_tail(engine, args.tail)

    if args.export:
        out = Path(args.export)
        engine.history_frame().to_csv(out, index=False, encoding="utf-8-sig")
        print(f"\n已导出 {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
