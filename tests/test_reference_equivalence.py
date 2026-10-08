"""锁定口径：本地实现与冻结的完整包 reference_impl.py 必须逐日完全一致。

reference/ 目录保存的是用户提供的「A股超短情绪温度模型3.2_完整包」原件。
只要这个测试还是绿的，emotion/core.py 就没有偏离 3.2 冻结口径。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from emotion.config import load_config  # noqa: E402
from emotion.core import compute_model as ours  # noqa: E402

REFERENCE_DIR = PROJECT_ROOT / "reference"
REFERENCE_IMPL = REFERENCE_DIR / "reference_impl.py"
PANEL = PROJECT_ROOT / "data" / "panel_history.csv"

NUMERIC_COLUMNS = [
    "F", "L", "R", "A", "B", "V", "Q",
    "J", "J_leader", "J_follower", "J_promotion", "M",
    "S", "delta1", "delta2",
    "C_hot", "C_J", "P_breadth", "P_down", "P_bomb", "P_cool", "P_inertia",
]
LABEL_COLUMNS = ["phase", "momentum", "J_label"]


def _reference_compute_model():
    namespace: dict = {"__name__": "reference_impl"}
    source = REFERENCE_IMPL.read_text(encoding="utf-8")
    exec(compile(source, str(REFERENCE_IMPL), "exec"), namespace)
    return namespace["compute_model"]


pytestmark = pytest.mark.skipif(
    not REFERENCE_IMPL.exists(),
    reason="reference/ 目录缺失，跳过与冻结实现的口径比对",
)


def test_reference_matches_bit_for_bit() -> None:
    panel = pd.read_csv(PANEL, dtype={"date": str})
    mine = ours(panel)
    theirs = _reference_compute_model()(panel)

    assert len(mine) == len(theirs)

    for column in NUMERIC_COLUMNS:
        delta = (mine[column].astype(float) - theirs[column].astype(float)).abs().max()
        assert delta < 1e-12, f"{column} 偏离冻结实现：最大差 {delta}"

    for column in LABEL_COLUMNS:
        same = (mine[column].astype(str) == theirs[column].astype(str)).all()
        assert same, f"{column} 与冻结实现不一致"

    same_repair = (
        mine["repair_confirmed"].astype(bool) == theirs["repair_confirmed"].astype(bool)
    ).all()
    assert same_repair


def test_reference_package_parameters_are_intact() -> None:
    """完整包里的冻结参数表应原样保留，未被改写。"""
    vendored = REFERENCE_DIR / "model_config.json"
    assert vendored.exists()
    assert load_config(vendored) == load_config()
