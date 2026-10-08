# -*- coding: utf-8 -*-
"""设计样板入口：调用 Skill 内的报刊风模板渲染器生成样板。

模板与样式已经固化在 Skill 里：
  daily-briefing-pro/scripts/build_broadsheet.py   渲染器
  daily-briefing-pro/templates/broadsheet.css      样式资产
这里只做路径绑定，避免工作区与 Skill 各维护一份实现。

用法:
    python build_broadsheet.py                  # 用默认源简报刷新样板
    python build_broadsheet.py --src X --out Y  # 参数原样透传给渲染器
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent
SKILL = Path(r"C:\Users\63054\.agents\skills\daily-briefing-pro")
RENDERER = SKILL / "scripts" / "build_broadsheet.py"

DEFAULT_SRC = WORKSPACE / "报告" / "每日简报" / "2026-09-21简报.html"
DEFAULT_OUT = HERE / "报刊风样板-v2.html"


def main():
    if not RENDERER.exists():
        raise SystemExit(f"找不到 Skill 内的渲染器：{RENDERER}")
    extra = sys.argv[1:]
    cmd = [sys.executable, str(RENDERER)]
    if not any(a.startswith("--src") for a in extra):
        cmd += ["--src", str(DEFAULT_SRC)]
    if not any(a.startswith("--out") for a in extra):
        cmd += ["--out", str(DEFAULT_OUT)]
    cmd += extra
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
