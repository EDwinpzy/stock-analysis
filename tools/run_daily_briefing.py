"""Run the project's maintained briefing plugin from any working directory."""
from pathlib import Path
import os
import subprocess
import sys


def main() -> int:
    project = Path(__file__).resolve().parents[1]
    entry = project / 'plugins/daily-briefing-pro/skills/daily-briefing-pro/scripts/run_all.py'
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    env.setdefault('BRIEFING_OUTPUT_DIR', str(project / '报告/每日简报'))
    return subprocess.call([sys.executable, str(entry), *sys.argv[1:]], cwd=project, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
