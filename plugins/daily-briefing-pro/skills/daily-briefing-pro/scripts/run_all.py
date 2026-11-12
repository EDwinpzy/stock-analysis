#!/usr/bin/env python3
"""
每日简报Pro — 一体化编排脚本
并行执行所有数据采集脚本，编译HTML简报

架构: Group A(快速数据并行采集) → Group B(内容并行采集) → 编译HTML

用法: python run_all.py [--date YYYY-MM-DD]
"""
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import quote

import env_config  # noqa: F401  注入本机凭证（~/.codex/daily-briefing.env）
from runtime_paths import get_data_dir
from summary_cache import cached_tgb_summaries_complete, load_summary_cache
from trading_date import get_recent_trade_date
from data_quality import data_error_reason
from codex_summary_cli import semantic_summary_available
from _hithink import trade_dates
from runtime_preflight import build_preflight, write_report

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
DATA_DIR = get_data_dir(BASE_DIR)

DEFAULT_REPORT_SUBDIR = ("报告", "每日简报")


def default_output_dir() -> Path:
    """简报输出目录：环境变量优先，否则落在调用方目录的 报告/每日简报。"""
    env_dir = os.environ.get("BRIEFING_OUTPUT_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.cwd().joinpath(*DEFAULT_REPORT_SUBDIR)


# AI 总结 API 只从环境变量读取，不在 Skill 源码中内置凭证。
# 淘股吧有可核验内容时，正式编译门禁会要求提供 AI 凭证；抖音无 AI 时
# 可以保留真实转录摘录并明确标注来源。


def get_date():
    """获取日期（支持 --date 参数）"""
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return datetime.now(ZoneInfo('Asia/Shanghai')).strftime("%Y-%m-%d")


def compiler_preflight_error(script_dir: Path = SCRIPT_DIR) -> str:
    """Return an actionable error before collection if the compiler cannot run."""
    compiler = Path(script_dir) / "build_briefing.py"
    if not compiler.is_file():
        return f"缺少HTML编译器：{compiler}"
    python_executable = Path(sys.executable)
    if not python_executable.is_file():
        return f"当前Python解释器不可用：{sys.executable or '(empty)'}"
    return ""


def compiler_failure_reason(result: dict) -> str:
    """Validate both the compiler exit result and its reported HTML artifact."""
    if not isinstance(result, dict):
        return "HTML编译器没有返回有效结果"
    error = result.get("_error")
    return_code = result.get("_rc")
    if error or (return_code is not None and return_code != 0):
        details = str(error or f"退出码 {return_code}")
        return f"HTML编译失败：{details}"

    output = result.get("output")
    if not output:
        return "HTML编译器未报告生成文件"
    output_path = Path(str(output))
    if not output_path.is_absolute():
        output_path = BASE_DIR / output_path
    try:
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            return f"HTML编译器未生成有效文件：{output_path}"
    except OSError as exc:
        return f"无法检查HTML编译结果：{exc}"
    return ""


def run_script(name: str, args: list, timeout: int = 120) -> dict:
    """运行单个脚本，返回结果dict"""
    script_path = SCRIPT_DIR / name
    cmd = [sys.executable, str(script_path)] + args
    t0 = time.time()
    try:
        child_env = os.environ.copy()
        # 统一子进程的 I/O 编码，避免情绪周期标签中的 emoji/中文在 Windows
        # 默认代码页下被误解码，进而让成功的 JSON 结果被编排器判定为失败。
        child_env["PYTHONIOENCODING"] = "utf-8"
        # 让编译产物落在调用方目录，而不是随子进程 cwd 漂移
        child_env["BRIEFING_OUTPUT_DIR"] = str(default_output_dir())
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(BASE_DIR), timeout=timeout, env=child_env
        )
        elapsed = time.time() - t0
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            print(f"  [WARN] {name} 返回码 {result.returncode} ({elapsed:.1f}s)", file=sys.stderr)
            if stderr:
                print(f"    stderr: {stderr[:200]}", file=sys.stderr)
            return {"_script": name, "_args": args, "_elapsed": elapsed, "_rc": result.returncode, "_error": stderr[:200]}

        # 解析JSON输出
        data = None
        if stdout:
            # 尝试整体解析
            try:
                data = json.loads(stdout)
            except json.JSONDecodeError:
                # 逐行查找JSON
                for line in reversed(stdout.split("\n")):
                    line = line.strip()
                    if line.startswith("{"):
                        try:
                            data = json.loads(line)
                            break
                        except json.JSONDecodeError:
                            continue

        if data is not None:
            print(f"  [OK] {name} ({elapsed:.1f}s)", file=sys.stderr)
            return data
        if name == "build_briefing.py":
            result_data = {"_script": name, "_args": args, "_elapsed": elapsed, "_rc": 0, "_stdout": stdout}
            for line in stdout.splitlines():
                if line.startswith("BUTTON:"):
                    result_data["BUTTON"] = line[len("BUTTON:"):]
                elif line.startswith("OK:"):
                    result_data["output"] = line[3:].strip()
            if not result_data.get("output"):
                result_data["_rc"] = 3
                result_data["_error"] = "编译器未报告生成的HTML文件"
                print(f"  [ERROR] {name} 未生成可验证的HTML文件", file=sys.stderr)
                return result_data
            print(f"  [OK] {name} ({elapsed:.1f}s)", file=sys.stderr)
            return result_data
        else:
            print(f"  [WARN] {name} 无JSON输出 ({elapsed:.1f}s)", file=sys.stderr)
            raw_stdout = stdout if name == "pick_quote.py" else stdout[:200]
            return {"_script": name, "_args": args, "_elapsed": elapsed, "_rc": 0, "_raw_stdout": raw_stdout}

    except subprocess.TimeoutExpired as exc:
        elapsed = time.time() - t0
        print(f"  [ERROR] {name} 超时 ({timeout}s)", file=sys.stderr)
        detail = exc.stderr or ''
        if isinstance(detail, bytes):
            detail = detail.decode('utf-8', errors='replace')
        last_stage = '\n'.join(str(detail).splitlines()[-3:])[-600:]
        return {"_script": name, "_args": args, "_elapsed": elapsed,
                "_error": f"timeout ({timeout}s)", "note": f"采集超过{timeout}秒时限；末条阶段：{last_stage or '无阶段日志'}"}
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [ERROR] {name} 异常: {e}", file=sys.stderr)
        return {"_script": name, "_args": args, "_elapsed": elapsed, "_error": str(e)}


def save_script_output(name: str, args: list, stdout: str, data_dir: Path = DATA_DIR):
    """Persist a non-JSON script output without turning HTML into JSON."""
    data_dir.mkdir(parents=True, exist_ok=True)
    if name == "pick_quote.py" and "--html" in args:
        (data_dir / "quote_today.html").write_text(stdout or "", encoding="utf-8")
        stale_json = data_dir / "quote_today.json"
        if stale_json.exists():
            stale_json.unlink()
        return
    raise ValueError(f"不支持保存非JSON输出：{name}")


def save_result(name: str, data: dict, suffix: str = ".json"):
    """保存脚本结果到 data/ 目录"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # 映射脚本名到数据文件名
    name_map = {
        "panic_greed_index_enhanced.py": "panic_today.json",
        "fetch_news.py": "news_today.json",
        "fetch_future_events.py": "events_today.json",
        "fetch_yanbao.py": "yanbao_latest.json",
        "tgb_crawl.py": "tgb_today.json",
        "fetch_douyin.py": "douyin_today.json",
        "fetch_sentiment_survey.py": "sentiment_survey_today.json",
        "fetch_longhubang.py": "lhb_today.json",
        "fetch_lianban.py": "lianban_today.json",
        "fetch_rotation.py": "rotation_today.json",
        "build_node_cycle.py": "node_cycle_today.json",
        "fetch_indices.py": "indices_today.json",
    }
    filename = name_map.get(name, f"{name}_today{suffix}")
    path = DATA_DIR / filename

    # 特殊处理: pick_quote 输出HTML而非JSON
    if name == "pick_quote.py" and "--html" in data.get("_args", []):
        save_script_output(name, data.get("_args", []), data.get("_raw_stdout", ""), DATA_DIR)
        return

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_group_a(raw_date: str, trade_date: str) -> dict:
    """Group A: market snapshots use the trade date; content uses raw date."""
    print("\n═══ Group A: 快速数据采集（并行）═══", file=sys.stderr)
    trade_args = ["--date", trade_date]
    raw_args = ["--date", raw_date]
    scripts = [
        # 市场温度走情绪模型 3.2：增量运行只需几秒，但首次构建 400 日面板
        # （约 1.6 年 开盘啦 历史）需要数分钟，因此给足超时。
        ("panic_greed_index_enhanced.py", trade_args, 1200),
        ("fetch_news.py", ["--source", "eastmoney", "--limit", "15"] + raw_args, 60),
        ("fetch_longhubang.py", trade_args, 90),
        ("fetch_yanbao.py", raw_args, 900),
        ("fetch_future_events.py", raw_args, 60),
        # 盘面补充：同花顺官方给盘面事实（可回填历史），连板网补新高新低/融资/次日观察
        ("fetch_lianban.py", raw_args, 240),
        # 云端首次运行最多要补齐 90 个行业和沪深300，再调用内部 900s 预测；
        # 外层时限必须覆盖行情刷新与预测之和，避免刷新完成前被提前杀掉。
        ("fetch_rotation.py", raw_args, 1800),
        ("fetch_indices.py", raw_args, 90),
        ("pick_quote.py", ["--html"] + raw_args, 30),
    ]

    results = {}
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = {}
        for name, args, timeout in scripts:
            future = executor.submit(run_script, name, args, timeout)
            futures[future] = name

        for future in as_completed(futures):
            name = futures[future]
            try:
                data = future.result()
                results[name] = data
                if name == "pick_quote.py" and data.get("_raw_stdout") is not None:
                    save_script_output(name, data.get("_args", []), data.get("_raw_stdout", ""), DATA_DIR)
                else:
                    save_result(name, data)
            except Exception as e:
                print(f"  [ERROR] {name} future异常: {e}", file=sys.stderr)
                results[name] = {"_error": str(e)}

    return results


def run_group_b(date: str) -> dict:
    """Group B: 淘股吧+抖音+博主观点统计并行执行（必选板块）"""
    print("\n═══ Group B: 必选板块采集（并行）═══", file=sys.stderr)
    date_args = ["--date", date]
    scripts = [
        ("tgb_crawl.py", date_args, 120),
        # Each video has its own bounded analyzer; allow several two-video
        # batches without killing a healthy collection at the old 600s boundary.
        ("fetch_douyin.py", date_args, 1800),
        # Includes both platform collection (up to 420s) and the bounded
        # parallel semantic review (840s). Keep the outer budget above their
        # sum so completed/checkpointed batches are not killed prematurely.
        ("fetch_sentiment_survey.py", ["--date", get_recent_trade_date(date)], 1300),
    ]

    results = {}
    with ProcessPoolExecutor(max_workers=3) as executor:
        futures = {}
        for name, args, timeout in scripts:
            future = executor.submit(run_script, name, args, timeout)
            futures[future] = name

        for future in as_completed(futures):
            name = futures[future]
            try:
                data = future.result()
                results[name] = data
                save_result(name, data)
            except Exception as e:
                print(f"  [ERROR] {name} future异常: {e}", file=sys.stderr)
                results[name] = {"_error": str(e)}

    # 仅记录结果；真正的编译门禁由 required_modules_ready 统一执行。
    tgb_data = results.get("tgb_crawl.py", {})
    tgb_total = sum(b.get("replies_today", 0) + b.get("posts_today", 0) for b in tgb_data.get("bloggers", {}).values())
    if tgb_total < 1:
        print(f"  [⛔] 淘股吧4位博主总动态数={tgb_total}（含回退），Cookie可能过期！", file=sys.stderr)

    douyin_data = results.get("fetch_douyin.py", {})
    douyin_total = sum(len(b.get("videos", [])) for b in douyin_data.get("bloggers", []))
    if douyin_total < 1:
        print(f"  [⚠️] 抖音博主视频数={douyin_total}（含回退），可能无更新或转录失败", file=sys.stderr)

    return results


def _tgb_activity(data: dict) -> int:
    if not isinstance(data, dict):
        return 0
    return sum(
        int(b.get("replies_today", 0) or 0) + int(b.get("posts_today", 0) or 0)
        + len(b.get("top_replies", []) or []) + len(b.get("posts", []) or [])
        for b in (data.get("bloggers", {}) or {}).values()
        if isinstance(b, dict)
    )


def _douyin_activity(data: dict) -> int:
    if not isinstance(data, dict):
        return 0
    return sum(len(b.get("videos", []) or []) for b in (data.get("bloggers", []) or []) if isinstance(b, dict))


def required_modules_ready(results: dict, target_date: str | None = None) -> bool:
    """Raise with an actionable reason unless both core blogger sources have data."""
    failures = []
    tgb = results.get("tgb_crawl.py", {}) if isinstance(results, dict) else {}
    douyin = results.get("fetch_douyin.py", {}) if isinstance(results, dict) else {}
    if data_error_reason(tgb):
        failures.append(
            f"淘股吧：{tgb.get('note') or tgb.get('error')}"
            "（修复：登录 tgb.cn 后导出 Cookie 到 ~/.codex/tgb_cookies.json）"
        )
    elif _tgb_activity(tgb) < 1:
        failures.append(
            "淘股吧：目标日及回退工作日没有可核验主帖/跟帖"
            "（修复：确认 Cookie 未过期，或核对 settings 中的博主ID）"
        )
    ai_configured = semantic_summary_available()
    cache = load_summary_cache(DATA_DIR / "tgb_ai_summaries.json")
    cache_ready = cached_tgb_summaries_complete(cache, target_date or get_date(), tgb)
    if _tgb_activity(tgb) >= 1 and not ai_configured and not cache_ready:
        failures.append(
            "淘股吧：有可核验内容但缺少AI语义总结凭证"
            "（修复：登录 Codex CLI，或在 ~/.codex/daily-briefing.env 配置有效的 AI API Key）"
        )
    if data_error_reason(douyin):
        failures.append(
            f"抖音：{douyin.get('note') or data_error_reason(douyin)}"
            "（修复：根据具体采集/下载/转录错误检查对应步骤）"
        )
    elif _douyin_activity(douyin) < 1:
        failures.append(
            "抖音：目标日及回退工作日没有可核验视频"
            "（修复：检查 Cookie、ffmpeg 与 Whisper 转录环境）"
        )
    elif any(not v.get('transcript') or v.get('warning') for b in douyin.get('bloggers', []) for v in b.get('videos', [])):
        failures.append('抖音：目标视频转录未全部完成')
    if failures:
        raise RuntimeError("；".join(dict.fromkeys(failures)) + "。未编译HTML简报。")
    return True


def compile_html(date: str) -> dict:
    """编译HTML简报"""
    print("\n═══ 编译HTML ═══", file=sys.stderr)
    compiler = SCRIPT_DIR / "build_briefing.py"
    if not compiler.is_file():
        return {"_script": "build_briefing.py", "_rc": 127, "_error": f"缺少HTML编译器：{compiler}"}
    result = run_script("build_briefing.py", ["--date", date], timeout=600)
    return result


def compile_broadsheet(date: str) -> str:
    """生成并验收每日简报的最终报刊版交付。"""
    print("\n═══ 报刊风版式 ═══", file=sys.stderr)
    out_dir = default_output_dir()
    src_path = out_dir / f"{date}简报.html"
    out_path = out_dir / f"{date}简报-报刊版.html"
    if not src_path.exists():
        raise RuntimeError(f"找不到当日简报源文件：{src_path}")

    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["BRIEFING_OUTPUT_DIR"] = str(out_dir)
    temp_path = out_path.with_name(f".{out_path.stem}.{os.getpid()}.tmp.html")
    shots_path = out_dir / "_验收" / f"{date}-{os.getpid()}"
    steps = (
        ("build_broadsheet.py", ["--src", str(src_path), "--out", str(temp_path), "--date", date], 180),
        ("verify_broadsheet.py", ["--out", str(temp_path), "--src", str(src_path), "--shots", str(shots_path)], 300),
    )
    try:
        for name, args, timeout in steps:
            if not (SCRIPT_DIR / name).exists():
                raise RuntimeError(f"缺少报刊版必需脚本：{name}")
            try:
                proc = subprocess.run(
                    [sys.executable, str(SCRIPT_DIR / name)] + args,
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    cwd=str(BASE_DIR), timeout=timeout, env=child_env
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"{name} 超时（{timeout}s）") from exc
            for line in (proc.stdout or "").strip().splitlines()[-6:]:
                print(f"  {line}", file=sys.stderr)
            for line in (proc.stderr or "").strip().splitlines()[-6:]:
                print(f"  {line}", file=sys.stderr)
            if proc.returncode != 0:
                raise RuntimeError(f"{name} 验收失败，退出码 {proc.returncode}")
            if name == "build_broadsheet.py" and not temp_path.is_file():
                raise RuntimeError("报刊版编译器未生成输出文件")
        os.replace(temp_path, out_path)
    finally:
        temp_path.unlink(missing_ok=True)

    print(f"  [OK] 报刊版验收通过：{out_path}", file=sys.stderr)
    return str(out_path)


def delivery_button(report_path: Path) -> str:
    """Create the final user-facing link for the verified report artifact."""
    abs_path = str(report_path.resolve()).replace("\\", "/")
    encoded = quote(abs_path, safe="/:")
    return (
        '<a href="file:///' + encoded + '" style="display:inline-block;padding:12px 28px;'
        'font-family:\'Microsoft YaHei\',sans-serif;font-size:15px;font-weight:700;color:#0b0f19;'
        'background:linear-gradient(135deg,#fbbf24,#f59e0b);border-radius:8px;text-decoration:none;'
        'box-shadow:0 4px 14px rgba(245,158,11,.35);border:1px solid rgba(255,255,255,.15);">'
        '📄 打开今日简报</a>'
    )


def main():
    t0 = time.time()
    if '--help' in sys.argv or '-h' in sys.argv:
        print(
            '用法: python run_all.py [--date YYYY-MM-DD] [--resume] '
            '[--scheduled] [--preflight-only]'
        )
        return
    if '--skip-transcription' in sys.argv:
        print(json.dumps({'status': 'error', 'reason': '已取消跳过转录；完整简报必须完成抖音转录'}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)

    # 确定日期
    raw_date = get_date()
    resume = '--resume' in sys.argv
    if '--scheduled' in sys.argv:
        try:
            sessions = trade_dates()
            # The CLI calendar covers the past year through the request date;
            # its last row is the last *open* session, including on holidays.
            reference_date = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')
            if not sessions or raw_date < min(sessions) or raw_date > reference_date:
                raise RuntimeError('交易日历尚未覆盖目标日，不能推断休市')
            if raw_date not in sessions:
                print(json.dumps({'date': raw_date, 'status': 'skipped', 'reason': '交易所日历确认非交易日'}, ensure_ascii=False))
                return
        except Exception as exc:
            print(json.dumps({'date': raw_date, 'status': 'error', 'reason': f'交易日历核验失败：{exc}'}, ensure_ascii=False), file=sys.stderr)
            raise SystemExit(2)
    trade_date = get_recent_trade_date(raw_date)
    print(f"日期: {raw_date} → 交易日: {trade_date}", file=sys.stderr)

    preflight_error = compiler_preflight_error()
    if preflight_error:
        summary = {"date": raw_date, "trade_date": trade_date, "status": "error", "reason": preflight_error}
        print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(2)

    try:
        runtime_report = build_preflight(
            raw_date,
            trade_date,
            data_dir=DATA_DIR,
            package_dir=BASE_DIR,
            output_dir=default_output_dir(),
            collecting=not resume,
        )
        write_report(runtime_report, DATA_DIR / "preflight.json")
    except Exception as exc:
        summary = {
            "date": raw_date,
            "trade_date": trade_date,
            "status": "blocked",
            "phase": "preflight",
            "reason": f"运行预检失败：{type(exc).__name__}: {exc}",
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(2)

    for warning in runtime_report.warnings:
        print(f"  [PREFLIGHT][WARN] {warning.label}: {warning.detail}", file=sys.stderr)
    if '--preflight-only' in sys.argv:
        print(json.dumps(runtime_report.as_dict(), ensure_ascii=False, indent=2))
        raise SystemExit(0 if runtime_report.ok else 2)
    if not runtime_report.ok:
        elapsed = time.time() - t0
        failures = [
            f"{item.label}：{item.detail}" + (f"（修复：{item.fix}）" if item.fix else "")
            for item in runtime_report.blockers
        ]
        print("\n═══ 运行前检查已阻断 ═══", file=sys.stderr)
        for failure in failures:
            print(f"  [BLOCK] {failure}", file=sys.stderr)
        summary = {
            "date": raw_date,
            "trade_date": trade_date,
            "status": "blocked",
            "phase": "preflight",
            "reason": "；".join(failures),
            "elapsed_seconds": round(elapsed, 1),
            "preflight": runtime_report.as_dict(),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(2)

    # Step 1: Group A 并行
    def persisted(filename):
        try:
            return json.loads((DATA_DIR / filename).read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            return {'_error': f'缺少可解析的{filename}'}
    group_a = {filename.removesuffix('_today.json'): persisted(filename) for filename in ('panic_today.json', 'news_today.json', 'events_today.json', 'yanbao_latest.json', 'lhb_today.json', 'lianban_today.json', 'rotation_today.json', 'indices_today.json')} if resume else run_group_a(raw_date, trade_date)

    # 节点票模型必须在连板池写入后再更新，保留近三个月滚动历史供次日重复计算。
    # 节点模型除连板历史回补外，还要为每个节点抓一次日线核验"是否走A"，
    # 行情源偶发限流时会有退避重试，因此超时给宽一些。
    node_result = persisted('node_cycle_today.json') if resume else run_script("build_node_cycle.py", ["--date", trade_date], timeout=420)
    if not node_result.get("_error"):
        save_result("build_node_cycle.py", node_result)
    else:
        print("  [WARN] 节点票模型更新失败，简报将如实显示节点数据不可用", file=sys.stderr)
    group_a["build_node_cycle.py"] = node_result

    # Step 2: Group B 并行
    group_b = {name: persisted(filename) for name, filename in {'tgb_crawl.py':'tgb_today.json', 'fetch_douyin.py':'douyin_today.json', 'fetch_sentiment_survey.py':'sentiment_survey_today.json'}.items()} if resume else run_group_b(raw_date)

    try:
        required_modules_ready(group_b, raw_date)
    except RuntimeError as exc:
        elapsed = time.time() - t0
        print(f"\n═══ 已阻断编译 ({elapsed:.1f}s) ═══", file=sys.stderr)
        print(f"  [⛔] {exc}", file=sys.stderr)
        summary = {
            "date": raw_date,
            "trade_date": trade_date,
            "status": "blocked",
            "reason": str(exc),
            "elapsed_seconds": round(elapsed, 1),
            "group_a": {name: not bool(data_error_reason(data)) for name, data in group_a.items()},
            "group_b": {name: not bool(data_error_reason(data)) for name, data in group_b.items()},
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(2)

    # Step 3: 编译HTML
    compile_result = compile_html(raw_date)
    compile_error = compiler_failure_reason(compile_result)
    if compile_error:
        elapsed = time.time() - t0
        print(f"\n═══ 编译失败 ({elapsed:.1f}s) ═══", file=sys.stderr)
        summary = {
            "date": raw_date,
            "trade_date": trade_date,
            "status": "error",
            "reason": compile_error,
            "elapsed_seconds": round(elapsed, 1),
            "group_a": {name: not bool(data_error_reason(data)) for name, data in group_a.items()},
            "group_b": {name: not bool(data_error_reason(data)) for name, data in group_b.items()},
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(3)

    # Step 4: 报刊版是最终交付，编译或视觉验收失败时不交付未验收的原版。
    try:
        broadsheet_path = compile_broadsheet(raw_date)
    except RuntimeError as exc:
        elapsed = time.time() - t0
        print(f"\n═══ 报刊版失败 ({elapsed:.1f}s) ═══", file=sys.stderr)
        summary = {
            "date": raw_date,
            "trade_date": trade_date,
            "status": "error",
            "reason": str(exc),
            "elapsed_seconds": round(elapsed, 1),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
        raise SystemExit(4)

    elapsed = time.time() - t0
    print(f"\n═══ 完成 ({elapsed:.1f}s) ═══", file=sys.stderr)

    # 输出结果摘要
    summary = {
        "date": raw_date,
        "trade_date": trade_date,
        "status": "ok",
        "elapsed_seconds": round(elapsed, 1),
        "group_a": {name: not bool(data_error_reason(data)) for name, data in group_a.items()},
        "group_b": {name: not bool(data_error_reason(data)) for name, data in group_b.items()},
    }
    if broadsheet_path:
        summary["broadsheet"] = broadsheet_path
    print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)

    # 只交付通过模板和视觉验收的报刊版。
    print(delivery_button(Path(broadsheet_path)))


if __name__ == "__main__":
    main()
