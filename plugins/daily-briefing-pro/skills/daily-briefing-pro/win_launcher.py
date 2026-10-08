"""
每日简报Pro — Windows启动器
通过Python subprocess直接调用run_all.py，绕过Git Bash不可用的问题
输出结果写入状态文件，供Codex读取
"""
import subprocess
import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
SCRIPT_DIR = BASE_DIR / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from runtime_paths import get_data_dir
from trading_date import get_recent_trade_date

DATA_DIR = get_data_dir(BASE_DIR)
STATUS_FILE = DATA_DIR / "launcher_status.json"

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Write initial status
    status = {"status": "running", "start_time": datetime.now().isoformat(), "step": "initializing"}
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    date_str = datetime.now().strftime("%Y-%m-%d")
    trade_date = get_recent_trade_date(date_str)

    # AI 凭证从 ~/.codex/daily-briefing.env 读取，不写死在源码中
    script_dir = BASE_DIR / "scripts"
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    import env_config  # noqa: F401
    env_config.load_env_file()

    # Run run_all.py
    run_all_path = BASE_DIR / "scripts" / "run_all.py"
    cmd = [sys.executable, str(run_all_path), "--date", trade_date]

    status["step"] = "running_run_all"
    status["command"] = " ".join(cmd)
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(BASE_DIR),
            timeout=600,  # 10 minutes max
        )

        status["status"] = "completed" if result.returncode == 0 else "failed"
        status["returncode"] = result.returncode
        status["stdout"] = result.stdout[-2000:] if result.stdout else ""
        status["stderr"] = result.stderr[-2000:] if result.stderr else ""
        status["end_time"] = datetime.now().isoformat()

    except subprocess.TimeoutExpired:
        status["status"] = "timeout"
        status["end_time"] = datetime.now().isoformat()
    except Exception as e:
        status["status"] = "error"
        status["error"] = str(e)
        status["end_time"] = datetime.now().isoformat()

    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    # Print key output for Codex to read
    print(status.get("stdout", ""))
    if status["status"] != "completed":
        print(f"ERROR: {status.get('error', status.get('stderr', 'Unknown error'))}", file=sys.stderr)

if __name__ == "__main__":
    main()
