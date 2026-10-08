#!/usr/bin/env python3
"""市场温度入口 — 转发到 A股超短情绪温度模型 3.2。

保留原文件名是为了兼容 run_all.py / inline_runner.py / generate_briefing.py
里既有的编排与数据文件映射（输出仍写 data/panic_today.json）。

实际计算在：
  market_temperature_v32.py   面板构建 + 增量补齐 + JSON 输出
  sentiment_model_v32.py      模型本体（F/L/R/A/B/V → Q → J → S → 六阶段）

旧版 11 因子线性公式已停用，保留在 market_temperature.py 仅作历史参考。
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

import market_temperature_v32  # noqa: E402


if __name__ == "__main__":
    market_temperature_v32.main()
