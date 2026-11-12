# -*- coding: utf-8 -*-
"""设计样板验收入口：调用 Skill 内的报刊风验收脚本。

用法:
    python verify_broadsheet.py            # 验收 报刊风样板-v2.html
    python verify_broadsheet.py --out X    # 参数原样透传
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent
SKILL = WORKSPACE / "plugins" / "daily-briefing-pro" / "skills" / "daily-briefing-pro"
CHECKER = SKILL / "scripts" / "verify_broadsheet.py"

DEFAULT_OUT = HERE / "报刊风样板-v2.html"
DEFAULT_SRC = WORKSPACE / "报告" / "每日简报" / "2026-09-21简报.html"
SHOTS = HERE / "_验收"


def main():
    if not CHECKER.exists():
        raise SystemExit(f"找不到 Skill 内的验收脚本：{CHECKER}")
    extra = sys.argv[1:]
    cmd = [sys.executable, str(CHECKER)]
    cmd += extra or ["--out", str(DEFAULT_OUT), "--src", str(DEFAULT_SRC), "--shots", str(SHOTS)]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
