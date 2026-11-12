#!/usr/bin/env python3
"""One portable entry point for the Daily Briefing Pro plugin.

Run from any directory:

    python cloud_cli.py doctor
    python cloud_cli.py market realtime 600519
    python cloud_cli.py stock 600519 --output-dir /runtime/data/stock-analysis
    python cloud_cli.py industry 白酒 --output-dir /runtime/data/industry-analysis
    python cloud_cli.py briefing --date 2026-11-11
    python cloud_cli.py verify report.html --type stock
    python cloud_cli.py parity --data-local local.json --data-cloud cloud.json

The CLI never contains credentials.  API keys and THS account credentials are
read from the process environment or the platform secret mount.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


PLUGIN_ROOT = Path(__file__).resolve().parent
SKILLS = PLUGIN_ROOT / "skills"
DAILY_SCRIPTS = SKILLS / "daily-briefing-pro" / "scripts"
if str(DAILY_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DAILY_SCRIPTS))
try:
    import env_config  # noqa: F401  Load the local credential file when present.
except ImportError:
    pass
MARKET = SKILLS / "market-query" / "scripts" / "market_query.py"
STOCK = SKILLS / "stock-analysis" / "scripts" / "fetch_stock_data.py"
INDUSTRY = SKILLS / "industry-analysis" / "scripts" / "fetch_industry_data.py"
BRIEFING = SKILLS / "daily-briefing-pro" / "scripts" / "run_all.py"
VERIFY = SKILLS / "daily-briefing-pro" / "scripts" / "verify_skill_report.py"
PARITY = SKILLS / "daily-briefing-pro" / "scripts" / "compare_cloud_parity.py"
BUSINESS_PARITY = (
    SKILLS / "daily-briefing-pro" / "scripts" / "compare_business_parity.py"
)
REPORT_BUILDER = PLUGIN_ROOT / "report_builder.py"

API_KEY_ENVS = ("FUYAO_API_KEY", "HITHINK_API_KEY", "HITHINK_FINANCE_API_KEY")
WENCAI_API_KEY_ENVS = ("IWENCAI_API_KEY", "WENCAI_API_KEY")


def timeout_seconds(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def runtime_root() -> Path:
    if os.getenv("DAILY_BRIEFING_HOME"):
        return Path(os.environ["DAILY_BRIEFING_HOME"]).expanduser().resolve()
    if Path("/runtime").is_dir():
        return Path("/runtime")
    return Path.home() / ".codex" / "daily-briefing-pro"


def data_dir() -> Path:
    if os.getenv("DAILY_BRIEFING_DATA_DIR"):
        return Path(os.environ["DAILY_BRIEFING_DATA_DIR"]).expanduser().resolve()
    return runtime_root() / "data"


def report_dir() -> Path:
    if os.getenv("BRIEFING_OUTPUT_DIR"):
        return Path(os.environ["BRIEFING_OUTPUT_DIR"]).expanduser().resolve()
    return runtime_root() / "reports"


def child_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONHASHSEED", "2")
    env.setdefault("DAILY_BRIEFING_DATA_DIR", str(data_dir()))
    env.setdefault("BRIEFING_OUTPUT_DIR", str(report_dir()))
    env.setdefault("DAILY_BRIEFING_CLOUD", "1")
    return env


def _process_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _start_process(command: list[str], capture: bool) -> subprocess.Popen:
    kwargs: dict[str, Any] = {"env": child_env()}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    if capture:
        kwargs.update(
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    return subprocess.Popen(command, **kwargs)


def _terminate_process_tree(process: subprocess.Popen) -> None:
    """Stop the command and all descendants, not only the direct child."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(process.pid, sig)
            except (OSError, ProcessLookupError):
                break
            try:
                process.wait(timeout=3)
                break
            except subprocess.TimeoutExpired:
                continue
    try:
        process.kill()
    except OSError:
        pass


def run_command(command: list[str], dry_run: bool = False, timeout: int | None = None) -> int:
    if dry_run:
        print(json.dumps({"dry_run": True, "command": command}, ensure_ascii=False, indent=2))
        return 0
    try:
        process = _start_process(command, capture=False)
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate_process_tree(process)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
            raise
    except subprocess.TimeoutExpired:
        print(
            json.dumps(
                {"ok": False, "error": f"命令超时：{command[0]}", "timeout_seconds": timeout},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 124
    except FileNotFoundError:
        print(
            json.dumps(
                {"ok": False, "error": f"找不到可执行文件：{command[0]}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 127


def run_capture(
    command: list[str],
    dry_run: bool = False,
    timeout: int | None = None,
) -> tuple[int, str, str]:
    if dry_run:
        print(json.dumps({"dry_run": True, "command": command}, ensure_ascii=False, indent=2))
        return 0, "", ""
    try:
        process = _start_process(command, capture=True)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _terminate_process_tree(process)
            try:
                tail_stdout, tail_stderr = process.communicate(timeout=10)
            except (subprocess.TimeoutExpired, ValueError):
                tail_stdout, tail_stderr = exc.stdout, exc.stderr
            stdout = _process_text(tail_stdout or exc.stdout)
            stderr = _process_text(tail_stderr or exc.stderr)
            return 124, stdout, (stderr + f"\n命令超时：{timeout} 秒").strip()
    except subprocess.TimeoutExpired as exc:
        stdout = _process_text(exc.stdout)
        stderr = _process_text(exc.stderr)
        return 124, stdout, (stderr + f"\n命令超时：{timeout} 秒").strip()
    except FileNotFoundError:
        return 127, "", f"找不到可执行文件：{command[0]}"
    return process.returncode, _process_text(stdout), _process_text(stderr)


def report_command(kind: str, subject: str, output_dir: str, preflight: bool, dry_run: bool) -> int:
    output = Path(output_dir).expanduser() if output_dir else data_dir() / f"{kind}-analysis"
    if kind == "stock":
        collect = [
            sys.executable,
            str(STOCK),
            subject,
            "--output-dir",
            str(output),
            "--source",
            "cloud",
        ]
    else:
        collect = [
            sys.executable,
            str(INDUSTRY),
            subject,
            "--output-dir",
            str(output),
            "--source",
            "cloud",
        ]
    if preflight:
        collect.append("--preflight")

    if dry_run:
        print(json.dumps({"dry_run": True, "collect": collect, "build": [sys.executable, str(REPORT_BUILDER), "--type", kind, "--data-json", "<collector-output>"]}, ensure_ascii=False, indent=2))
        return 0

    collect_timeout = timeout_seconds(
        "DAILY_BRIEFING_PREFLIGHT_TIMEOUT" if preflight else "DAILY_BRIEFING_COLLECT_TIMEOUT",
        120 if preflight else 300,
    )
    code, stdout, stderr = run_capture(collect, timeout=collect_timeout)
    if stderr:
        sys.stderr.write(stderr)
    if code != 0:
        print(json.dumps({"ok": False, "stage": "collect", "exit_code": code, "stdout": stdout.strip().splitlines()[-1:]}, ensure_ascii=False, indent=2))
        return code
    data_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not data_lines:
        print(json.dumps({"ok": False, "stage": "collect", "error": "采集器未返回 JSON 路径"}, ensure_ascii=False, indent=2))
        return 1
    data_path = Path(data_lines[-1]).expanduser().resolve()
    if preflight:
        print(json.dumps({"ok": True, "stage": "preflight", "data": str(data_path)}, ensure_ascii=False, indent=2))
        return 0
    if not data_path.is_file():
        print(json.dumps({"ok": False, "stage": "collect", "error": f"采集结果不存在：{data_path}"}, ensure_ascii=False, indent=2))
        return 1

    build = [sys.executable, str(REPORT_BUILDER), "--type", kind, "--data-json", str(data_path)]
    code, stdout, stderr = run_capture(
        build,
        timeout=timeout_seconds("DAILY_BRIEFING_BUILD_TIMEOUT", 120),
    )
    if stderr:
        sys.stderr.write(stderr)
    if stdout:
        print(stdout, end="" if stdout.endswith("\n") else "\n")
    return code


def writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".cloud-cli-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def doctor(probe: bool = False, dry_run: bool = False) -> int:
    thsdk_info: dict[str, Any] = {"available": False}
    try:
        import thsdk  # type: ignore

        thsdk_info["available"] = True
        thsdk_info["lib_dir"] = str(Path(thsdk.__file__).parent / "libs")
        thsdk_info["credentials"] = "account" if (os.getenv("THS_USERNAME") and os.getenv("THS_PASSWORD")) else "guest"
    except ImportError:
        thsdk_info["error"] = "未安装 thsdk"

    commands = {
        "python": sys.executable,
        "thsdk": thsdk_info,
        "market_query": {"path": str(MARKET), "exists": MARKET.is_file()},
        "stock_collector": {"path": str(STOCK), "exists": STOCK.is_file()},
        "industry_collector": {"path": str(INDUSTRY), "exists": INDUSTRY.is_file()},
        "briefing_runner": {"path": str(BRIEFING), "exists": BRIEFING.is_file()},
        "verifier": {"path": str(VERIFY), "exists": VERIFY.is_file()},
        "parity_verifier": {"path": str(PARITY), "exists": PARITY.is_file()},
        "business_parity_verifier": {
            "path": str(BUSINESS_PARITY),
            "exists": BUSINESS_PARITY.is_file(),
        },
        "report_builder": {"path": str(REPORT_BUILDER), "exists": REPORT_BUILDER.is_file()},
        "hithink_cli": {"path": shutil.which("hithink-finance") or ""},
        "adobe_note": "Node/Chromium/FFmpeg are only required by the full briefing pipeline.",
    }
    key_sources = {
        name: bool(str(os.getenv(name) or "").strip())
        for name in API_KEY_ENVS + WENCAI_API_KEY_ENVS
    }
    payload = {
        "ok": all(item.get("exists", True) for item in commands.values() if isinstance(item, dict)),
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "root": str(PLUGIN_ROOT),
        "runtime_root": str(runtime_root()),
        "data_dir": {"path": str(data_dir()), "writable": writable(data_dir())},
        "report_dir": {"path": str(report_dir()), "writable": writable(report_dir())},
        "api_keys": key_sources,
        "commands": commands,
    }
    if probe:
        payload["probe"] = []
        for label, command in (
            (
                "stock",
                [
                    sys.executable,
                    str(STOCK),
                    "600519",
                    "--preflight",
                    "--source",
                    "cloud",
                    "--output-dir",
                    str(data_dir() / "stock-analysis"),
                ],
            ),
            (
                "industry",
                [
                    sys.executable,
                    str(INDUSTRY),
                    "白酒",
                    "--preflight",
                    "--source",
                    "cloud",
                    "--output-dir",
                    str(data_dir() / "industry-analysis"),
                ],
            ),
            ("market", [sys.executable, str(MARKET), "status", "--probe", "--compact"]),
        ):
            if dry_run:
                payload["probe"].append({"name": label, "dry_run": command})
                continue
            code, stdout, stderr = run_capture(
                command,
                timeout=timeout_seconds("DAILY_BRIEFING_PROBE_TIMEOUT", 300),
            )
            payload["probe"].append(
                {
                    "name": label,
                    "exit_code": code,
                    "stdout_tail": stdout.strip().splitlines()[-1:],
                    "stderr_tail": stderr.strip().splitlines()[-2:],
                }
            )
        payload["ok"] = payload["ok"] and all(
            item.get("exit_code") == 0 for item in payload["probe"] if "exit_code" in item
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A股行情插件跨平台入口")
    parser.add_argument("--dry-run", action="store_true", help="只打印将执行的命令")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="检查运行环境")
    p.add_argument("--probe", action="store_true", help="实际运行三个取数预检")

    p = sub.add_parser("market", help="行情查询，参数透传给 market_query.py")
    p.add_argument("args", nargs=argparse.REMAINDER)

    p = sub.add_parser("stock", help="个股数据采集")
    p.add_argument("stock")
    p.add_argument("--output-dir", default="", help="默认 $DAILY_BRIEFING_DATA_DIR/stock-analysis")
    p.add_argument("--preflight", action="store_true")

    p = sub.add_parser("industry", help="行业/产业链数据采集")
    p.add_argument("industry")
    p.add_argument("--limit", type=int, default=15)
    p.add_argument("--output-dir", default="", help="默认 $DAILY_BRIEFING_DATA_DIR/industry-analysis")
    p.add_argument("--preflight", action="store_true")

    p = sub.add_parser("stock-report", help="个股采集、HTML 生成与完整性门禁")
    p.add_argument("stock")
    p.add_argument("--output-dir", default="", help="采集 JSON 目录")
    p.add_argument("--preflight", action="store_true")

    p = sub.add_parser("industry-report", help="行业采集、HTML 生成与完整性门禁")
    p.add_argument("industry")
    p.add_argument("--output-dir", default="", help="采集 JSON 目录")
    p.add_argument("--preflight", action="store_true")

    p = sub.add_parser("briefing", help="每日简报完整流水线")
    p.add_argument("args", nargs=argparse.REMAINDER)

    p = sub.add_parser("verify", help="校验个股/行业报告")
    p.add_argument("target")
    p.add_argument("--type", choices=("stock", "industry"), required=True)
    p.add_argument("--data-json", default="")

    p = sub.add_parser("parity", help="对照本机与云端采集数据/报告")
    p.add_argument("--data-local", required=True)
    p.add_argument("--data-cloud", required=True)
    p.add_argument("--html-local", default="")
    p.add_argument("--html-cloud", default="")
    p.add_argument("--ignore-path", action="append", default=[])
    p.add_argument("--type", choices=("stock", "industry"))
    p.add_argument("--business-only", action="store_true")

    raw_args = list(sys.argv[1:] if argv is None else argv)
    passthrough: list[str] | None = None
    command_index = 1 if raw_args and raw_args[0] == "--dry-run" else 0
    command = raw_args[command_index] if len(raw_args) > command_index else ""
    if command in ("market", "briefing"):
        passthrough = raw_args[command_index + 1 :]
        args = parser.parse_args(raw_args[: command_index + 1])
        if "--dry-run" in passthrough:
            args.dry_run = True
            passthrough = [item for item in passthrough if item != "--dry-run"]
        args.args = passthrough
    else:
        args = parser.parse_args(raw_args)

    if args.command == "doctor":
        return doctor(probe=args.probe, dry_run=args.dry_run)

    if args.command == "market":
        command = [sys.executable, str(MARKET), *args.args]
        return run_command(
            command,
            args.dry_run,
            timeout=timeout_seconds("DAILY_BRIEFING_COLLECT_TIMEOUT", 300),
        )

    if args.command == "stock":
        output = Path(args.output_dir).expanduser() if args.output_dir else data_dir() / "stock-analysis"
        command = [
            sys.executable,
            str(STOCK),
            args.stock,
            "--output-dir",
            str(output),
            "--source",
            "cloud",
        ]
        if args.preflight:
            command.append("--preflight")
        return run_command(
            command,
            args.dry_run,
            timeout=timeout_seconds("DAILY_BRIEFING_COLLECT_TIMEOUT", 300),
        )

    if args.command == "industry":
        output = Path(args.output_dir).expanduser() if args.output_dir else data_dir() / "industry-analysis"
        command = [
            sys.executable,
            str(INDUSTRY),
            args.industry,
            "--limit",
            str(args.limit),
            "--output-dir",
            str(output),
            "--source",
            "cloud",
        ]
        if args.preflight:
            command.append("--preflight")
        return run_command(
            command,
            args.dry_run,
            timeout=timeout_seconds("DAILY_BRIEFING_COLLECT_TIMEOUT", 300),
        )

    if args.command == "stock-report":
        return report_command("stock", args.stock, args.output_dir, args.preflight, args.dry_run)

    if args.command == "industry-report":
        return report_command("industry", args.industry, args.output_dir, args.preflight, args.dry_run)

    if args.command == "briefing":
        command = [sys.executable, str(BRIEFING), *args.args]
        return run_command(
            command,
            args.dry_run,
            timeout=timeout_seconds("DAILY_BRIEFING_RUN_TIMEOUT", 3600),
        )

    if args.command == "verify":
        command = [sys.executable, str(VERIFY), args.target, "--type", args.type]
        if args.data_json:
            command.extend(["--data-json", args.data_json])
        return run_command(command, args.dry_run)

    if args.command == "parity":
        if args.business_only:
            if not args.type:
                print(
                    json.dumps(
                        {"ok": False, "error": "--business-only 需要 --type"},
                        ensure_ascii=False,
                    )
                )
                return 2
            command = [
                sys.executable,
                str(BUSINESS_PARITY),
                "--type",
                args.type,
                "--local",
                args.data_local,
                "--cloud",
                args.data_cloud,
            ]
            return run_command(command, args.dry_run)
        command = [
            sys.executable,
            str(PARITY),
            "--data-local",
            args.data_local,
            "--data-cloud",
            args.data_cloud,
        ]
        if args.html_local:
            command.extend(["--html-local", args.html_local])
        if args.html_cloud:
            command.extend(["--html-cloud", args.html_cloud])
        for path in args.ignore_path:
            command.extend(["--ignore-path", path])
        return run_command(command, args.dry_run)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
