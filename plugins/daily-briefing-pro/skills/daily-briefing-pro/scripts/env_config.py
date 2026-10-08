"""本机凭证加载器。

凭证不写死在 Skill 源码中：Skill 目录会被同步到云端，源码里的密钥会跟着外泄。
本模块在导入时读取 ``~/.codex/daily-briefing.env``，只填充尚未设置的环境变量，
因此命令行/系统环境变量始终优先。

文件格式为 ``KEY=VALUE``，支持 ``#`` 注释、空行和可选的引号包裹。
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(os.path.expanduser("~")) / ".codex" / "daily-briefing.env"


def parse_env_text(text: str) -> dict:
    """把配置文件文本解析为键值对（不含已存在的环境变量判断）。"""
    values = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def load_env_file(path: Path | None = None) -> dict:
    """读取凭证文件并注入环境变量，返回本次实际注入的键值对。"""
    target = Path(path) if path else ENV_FILE
    if not target.exists():
        return {}
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return {}

    applied = {}
    for key, value in parse_env_text(text).items():
        if os.environ.get(key):
            continue
        os.environ[key] = value
        applied[key] = value
    return applied


load_env_file()
