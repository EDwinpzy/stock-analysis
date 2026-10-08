"""模型自检：冻结参数一致性、真实数据回归、无未来函数、环境权重边界。"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from emotion import EmotionEngine, compute_model, load_config  # noqa: E402
from emotion import core  # noqa: E402
from emotion.display import temperature_grade  # noqa: E402

PANEL = PROJECT_ROOT / "data" / "panel_history.csv"

# 真实面板上 2026-09 的回归基准
GOLDEN = {
    "2026-09-07": (90.081, 54.5274, "修复"),
    "2026-09-08": (79.6281, -31.0072, "修复"),
    "2026-09-09": (65.1402, 0.2513, "退潮"),
    "2026-09-10": (43.8595, -23.4464, "冰点"),
    "2026-09-11": (43.4047, 14.545, "冰点"),
    "2026-09-14": (67.9225, 6.5572, "修复"),
}


@pytest.fixture(scope="module")
def engine() -> EmotionEngine:
    return EmotionEngine().load_csv(PANEL)


def test_panel_shape(engine: EmotionEngine) -> None:
    history = engine.history
    assert len(history) == 400
    assert str(history["date"].iloc[0].date()) == "2025-01-21"
    assert str(history["date"].iloc[-1].date()) == "2026-09-14"


def test_frozen_parameters_match_config() -> None:
    """core.py 内联的常量必须与冻结参数表一致，防止公式口径漂移。"""
    config = load_config()
    weights = config["factor_weights"]

    assert weights == {"F": 0.34, "L": 0.24, "R": 0.18, "A": 0.15, "B": 0.06, "V": 0.03}
    assert sum(weights.values()) == pytest.approx(1.0)

    assert config["F"]["lianban_feedback"] == pytest.approx(0.60)
    assert config["F"]["limitup_feedback"] == pytest.approx(0.40)
    assert config["F"]["tanh_scale_pct"] == pytest.approx(3.0)
    assert core.G(0.0) == pytest.approx(50.0)
    assert core.G(3.0) == pytest.approx(50.0 + 50.0 * math.tanh(1.0))

    assert config["J"]["temperature_max_adjust"] == pytest.approx(1.5)
    assert config["J"]["tanh_scale"] == pytest.approx(35.0)
    assert config["temperature"]["intercept"] == pytest.approx(18.0)
    assert config["temperature"]["q_slope"] == pytest.approx(0.87)
    assert config["corrections"]["hot_bonus"] == pytest.approx(1.5)
    assert config["corrections"]["inertia_penalty"] == pytest.approx(2.0)
    assert config["normalization"]["min_same_regime_samples"] == 60
    assert config["normalization"]["same_regime_window"] == 250


def test_golden_temperatures(engine: EmotionEngine) -> None:
    output = engine.compute().set_index("date")
    for day, (score, seam, phase) in GOLDEN.items():
        row = output.loc[pd.Timestamp(day)]
        assert float(row["S"]) == pytest.approx(score, abs=1e-3), day
        assert float(row["J"]) == pytest.approx(seam, abs=1e-3), day
        assert str(row["phase"]) == phase, day


def test_no_lookahead(engine: EmotionEngine) -> None:
    """t 日结果只能依赖 t-1 及更早的数据：截断面板不得改变历史结果。"""
    full = engine.compute()
    history = engine.history
    for cutoff in (120, 250, 320, 380):
        partial = compute_model(history.iloc[:cutoff])
        merged = full.iloc[:cutoff].reset_index(drop=True)
        for col in ["S", "Q", "J", "F", "L", "R", "A", "B", "V", "M"]:
            pd.testing.assert_series_equal(
                merged[col].astype(float),
                partial[col].astype(float),
                check_names=False,
                rtol=1e-9,
                atol=1e-9,
            )
        pd.testing.assert_series_equal(
            merged["phase"].astype(str),
            partial["phase"].astype(str),
            check_names=False,
        )


def test_engine_api_surface(engine: EmotionEngine) -> None:
    day = "2026-09-11"
    assert engine.calculate_temperature(day) == pytest.approx(43.40, abs=0.01)

    seam = engine.calculate_J(day)
    assert seam["value"] == pytest.approx(14.55, abs=0.01)
    assert seam["label"] == "弱分歧→一致"

    cycle = engine.detect_cycle(day)
    assert cycle["phase"] == "冰点"
    assert cycle["grade"] == "深度冰点"

    state = engine.get_market_state(day)
    for key in ("S", "phase", "J", "F", "L", "R", "A", "B", "V", "Q", "delta1", "delta2"):
        assert key in state
    assert engine.render(day).startswith("市场温度 S: ")


def test_unknown_date_raises(engine: EmotionEngine) -> None:
    with pytest.raises(KeyError):
        engine.calculate_temperature("2001-01-01")


def test_environment_weights_direction(engine: EmotionEngine) -> None:
    """冰点/退潮阶段压低高位接力、抬高防守，且乘数受限幅保护。"""
    day = "2026-09-10"
    aggressive = engine.adjust_stock_score(100.0, {"high_relay": 1.0}, day=day)
    defensive = engine.adjust_stock_score(100.0, {"defensive": 1.0}, day=day)

    assert aggressive["multiplier"] < 1.0
    assert defensive["multiplier"] > 1.0
    assert aggressive["adjusted_score"] < defensive["adjusted_score"]

    for style in ("leader", "high_relay", "low_first", "theme", "oversold", "defensive", "ice_repair"):
        result = engine.adjust_stock_score(80.0, {style: 1.0}, day=day)
        assert 0.7 - 1e-9 <= result["multiplier"] <= 1.3 + 1e-9
        assert 0.0 <= result["adjusted_score"] <= 100.0


def test_environment_weights_high_tide(engine: EmotionEngine) -> None:
    """高潮阶段抬高龙头、压低超跌修复。"""
    day = "2026-09-01"  # 面板中真实的高潮日（S=91.8）
    assert engine.detect_cycle(day)["phase"] == "高潮"
    leader = engine.adjust_stock_score(60.0, {"leader": 1.0}, day=day)
    oversold = engine.adjust_stock_score(60.0, {"oversold": 1.0}, day=day)
    assert leader["adjusted_score"] > 60.0
    assert oversold["adjusted_score"] < 60.0


def test_grade_helpers() -> None:
    assert temperature_grade(30.0, "冰点") == "极限冰点"
    assert temperature_grade(40.0, "冰点") == "深度冰点"
    assert temperature_grade(52.0, "冰点") == "冰点"
    assert temperature_grade(98.0, "高潮") == "极限高潮"
    assert temperature_grade(66.0, "升温") == "主升一级"
    assert temperature_grade(55.0, "退潮") == "二级退潮"
