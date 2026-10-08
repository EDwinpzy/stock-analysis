"""模型参数加载。

config/model_config.json 是 3.2 版本的冻结参数表，权重与阈值不随代码改动。
emotion/core.py 内联的常量与这里必须一致，tests/test_model.py 会做一致性校验。
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "model_config.json"
ENV_WEIGHTS_PATH = PROJECT_ROOT / "config" / "environment_weights.json"

DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


def load_config(path: str | Path | None = None) -> dict:
    """读取模型参数；默认读取项目内的 config/model_config.json。"""
    target = Path(path) if path else CONFIG_PATH
    with target.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_env_weights(path: str | Path | None = None) -> dict:
    """读取个股评分的环境权重表（3.2 核心模型之外的扩展层）。"""
    target = Path(path) if path else ENV_WEIGHTS_PATH
    with target.open(encoding="utf-8") as handle:
        return json.load(handle)


def model_version(path: str | Path | None = None) -> str:
    return str(load_config(path).get("version", "unknown"))
