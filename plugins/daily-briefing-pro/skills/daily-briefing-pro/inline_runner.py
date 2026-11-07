"""
每日简报Pro — 内联执行器
直接在当前Python进程中导入并执行所有数据采集脚本的核心逻辑
绕过Bash工具不可用的问题，通过Codex Agent的Python环境直接运行
"""
import json
import os
import sys
import time
import importlib.util
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

BASE_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = BASE_DIR / "scripts"

# AI 凭证从 ~/.codex/daily-briefing.env 读取，不写死在源码中
# （Skill 目录会同步到云端，源码里的密钥会随之外泄）
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from runtime_paths import get_data_dir  # noqa: E402
from trading_date import get_recent_trade_date  # noqa: E402

DATA_DIR = get_data_dir(BASE_DIR)
import env_config  # noqa: E402,F401


def run_script_as_module(name: str, args: list, timeout: int = 120) -> dict:
    """通过subprocess运行脚本（使用当前Python解释器）"""
    import subprocess
    script_path = SCRIPT_DIR / name
    cmd = [sys.executable, str(script_path)] + args
    t0 = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            cwd=str(BASE_DIR), timeout=timeout,
            env=os.environ.copy(),
        )
        elapsed = time.time() - t0
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            return {"_script": name, "_elapsed": elapsed, "_rc": result.returncode,
                    "_error": stderr[:500], "_stdout": stdout[:500]}

        # 尝试解析JSON
        data = None
        if stdout:
            try:
                data = json.loads(stdout)
            except json.JSONDecodeError:
                for line in reversed(stdout.split("\n")):
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            data = json.loads(line)
                            break
                        except json.JSONDecodeError:
                            continue

        if data is not None:
            return data
        else:
            return {"_script": name, "_elapsed": elapsed, "_rc": 0, "_raw_stdout": stdout[:500]}

    except subprocess.TimeoutExpired:
        elapsed = time.time() - t0
        return {"_script": name, "_elapsed": elapsed, "_error": "timeout"}
    except Exception as e:
        elapsed = time.time() - t0
        return {"_script": name, "_elapsed": elapsed, "_error": str(e)}


def save_result(name: str, data: dict):
    """保存脚本结果到 data/ 目录"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    name_map = {
        "panic_greed_index_enhanced.py": "panic_today.json",
        "fetch_news.py": "news_today.json",
        "fetch_future_events.py": "events_today.json",
        "pick_quote.py": "quote_today.json",
        "tgb_crawl.py": "tgb_today.json",
        "fetch_douyin.py": "douyin_today.json",
        "fetch_sentiment_survey.py": "sentiment_survey_today.json",
        "fetch_longhubang.py": "lhb_today.json",
        "fetch_lianban.py": "lianban_today.json",
        "fetch_rotation.py": "rotation_today.json",
    }
    filename = name_map.get(name, f"{name}_today.json")
    path = DATA_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    t0 = time.time()

    date_str = datetime.now().strftime("%Y-%m-%d")
    trade_date = get_recent_trade_date(date_str)
    print(f"日期: {date_str} → 交易日: {trade_date}")

    # ===== Group A: 快速脚本并行 =====
    print("\n═══ Group A: 快速数据采集（并行）═══")
    from concurrent.futures import ProcessPoolExecutor, as_completed

    date_args = ["--date", trade_date]
    group_a_scripts = [
        # 情绪模型 3.2：增量几秒，首次构建 400 日面板需要数分钟
        ("panic_greed_index_enhanced.py", date_args, 1200),
        ("fetch_news.py", ["--source", "eastmoney", "--limit", "15"] + date_args, 60),
        ("fetch_longhubang.py", date_args, 90),
        ("fetch_future_events.py", date_args, 60),
        ("fetch_lianban.py", date_args, 240),
        ("fetch_rotation.py", date_args, 900),
        ("pick_quote.py", ["--html"] + date_args, 30),
    ]

    group_a_results = {}
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = {}
        for name, args, timeout in group_a_scripts:
            future = executor.submit(run_script_as_module, name, args, timeout)
            futures[future] = name

        for future in as_completed(futures):
            name = futures[future]
            try:
                data = future.result()
                group_a_results[name] = data
                save_result(name, data)
                error = data.get("_error")
                if error:
                    print(f"  [WARN] {name}: {error[:100]}")
                else:
                    print(f"  [OK] {name}")
            except Exception as e:
                print(f"  [ERROR] {name}: {e}")
                group_a_results[name] = {"_error": str(e)}

    # ===== Group B: 必选板块并行 =====
    print("\n═══ Group B: 必选板块采集（并行）═══")
    group_b_scripts = [
        ("tgb_crawl.py", date_args, 120),
        ("fetch_douyin.py", date_args, 600),
        ("fetch_sentiment_survey.py", date_args, 300),
    ]

    group_b_results = {}
    with ProcessPoolExecutor(max_workers=3) as executor:
        futures = {}
        for name, args, timeout in group_b_scripts:
            future = executor.submit(run_script_as_module, name, args, timeout)
            futures[future] = name

        for future in as_completed(futures):
            name = futures[future]
            try:
                data = future.result()
                group_b_results[name] = data
                save_result(name, data)
                error = data.get("_error")
                if error:
                    print(f"  [WARN] {name}: {error[:100]}")
                else:
                    print(f"  [OK] {name}")
            except Exception as e:
                print(f"  [ERROR] {name}: {e}")
                group_b_results[name] = {"_error": str(e)}

    # 必选校验
    tgb_data = group_b_results.get("tgb_crawl.py", {})
    tgb_total = sum(b.get("replies_today", 0) + b.get("posts_today", 0)
                    for b in tgb_data.get("bloggers", {}).values())
    douyin_data = group_b_results.get("fetch_douyin.py", {})
    douyin_total = sum(len(b.get("videos", [])) for b in douyin_data.get("bloggers", []))

    if tgb_total < 1 and douyin_total < 1:
        print("  [⛔] 淘股吧和抖音均无数据！")
    elif tgb_total < 1:
        print(f"  [⚠️] 淘股吧0条，抖音{douyin_total}条视频")
    elif douyin_total < 1:
        print(f"  [⚠️] 抖音0条，淘股吧{tgb_total}条动态")

    # ===== 编译HTML =====
    print("\n═══ 编译HTML ═══")
    compile_result = run_script_as_module("build_briefing.py", ["--date", trade_date], timeout=120)

    elapsed = time.time() - t0
    print(f"\n═══ 完成 ({elapsed:.1f}s) ═══")

    # 输出结果摘要
    summary = {
        "date": trade_date,
        "elapsed_seconds": round(elapsed, 1),
        "group_a": {name: not bool(data.get("_error")) for name, data in group_a_results.items()},
        "group_b": {name: not bool(data.get("_error")) for name, data in group_b_results.items()},
        "tgb_total": tgb_total,
        "douyin_total": douyin_total,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # 输出交付按钮
    button = compile_result.get("BUTTON") or compile_result.get("_raw_stdout", "")
    if "打开今日简报" in str(button):
        for line in str(button).split("\n"):
            if "打开今日简报" in line:
                print(line.strip())
                break
    else:
        # 检查输出文件是否存在
        output_dir = Path(r"./outputs\每日简报")
        if not output_dir.exists():
            # 尝试其他路径
            output_dir = Path.cwd() / "reports" / "每日简报"
        output_path = output_dir / f"{trade_date}简报.html"
        if output_path.exists():
            abs_path = str(output_path).replace("\\", "/")
            encoded = quote(abs_path, safe="/:")
            print(f'<a href="file:///{encoded}" style="display:inline-block;padding:12px 28px;font-family:\'Microsoft YaHei\',sans-serif;font-size:15px;font-weight:700;color:#0b0f19;background:linear-gradient(135deg,#fbbf24,#f59e0b);border-radius:8px;text-decoration:none;box-shadow:0 4px 14px rgba(245,158,11,.35);border:1px solid rgba(255,255,255,.15);">📄 打开今日简报</a>')
        else:
            print(f"HTML文件未找到: {output_path}")
            # 搜索可能的输出位置
            for p in [BASE_DIR / "reports" / "每日简报",
                      Path.home() / "reports" / "每日简报",
                      Path(r"./project\reports\每日简报")]:
                candidate = p / f"{trade_date}简报.html"
                if candidate.exists():
                    abs_path = str(candidate).replace("\\", "/")
                    encoded = quote(abs_path, safe="/:")
                    print(f'<a href="file:///{encoded}" style="display:inline-block;padding:12px 28px;font-family:\'Microsoft YaHei\',sans-serif;font-size:15px;font-weight:700;color:#0b0f19;background:linear-gradient(135deg,#fbbf24,#f59e0b);border-radius:8px;text-decoration:none;box-shadow:0 4px 14px rgba(245,158,11,.35);border:1px solid rgba(255,255,255,.15);">📄 打开今日简报</a>')
                    break


if __name__ == "__main__":
    main()
