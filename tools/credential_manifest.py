#!/usr/bin/env python3
"""Audit and synchronize the external-service credential manifest.

The manifest contains names and metadata only. Secret values remain in the
user's ``~/.codex/daily-briefing.env`` file or in Cookie JSON files and are
never printed by this command.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "config" / "credentials.manifest.json"
SECRET_NAME_RE = re.compile(
    r"(?:API[_-]?KEY|APIKEY|CLIENT[_-]?ID|TOKEN|SECRET|PASSWORD|_KEY)$",
    re.IGNORECASE,
)


class CredentialError(RuntimeError):
    """Raised when the manifest or local configuration cannot be used."""


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CredentialError(f"无法读取清单 {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise CredentialError("清单必须是包含 items 数组的 JSON 对象")
    return payload


def parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
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


def load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        return parse_env_text(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CredentialError(f"无法读取本机配置 {path}: {exc}") from exc


def _nonempty(value: Any) -> str:
    return str(value or "").strip()


def resolve_env(
    names: Sequence[str],
    env_file: Mapping[str, str],
    environ: Mapping[str, str],
    *,
    prefer_process: bool = True,
) -> tuple[str, str]:
    """Return the effective value and a non-secret source label."""

    sources = (
        (environ, "process"),
        (env_file, "env-file"),
    )
    if not prefer_process:
        sources = tuple(reversed(sources))
    for source, label in sources:
        for name in names:
            value = _nonempty(source.get(name))
            if value:
                return value, f"{label}:{name}"
    return "", ""


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _secret_label(value: Any) -> str:
    if isinstance(value, list):
        return " / ".join(str(name) for name in value) or "-"
    return str(value or "-")


def is_secret_name(name: str) -> bool:
    return bool(SECRET_NAME_RE.search(name))


def parse_expiry(value: Any) -> datetime | None:
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 10_000_000_000:
            seconds /= 1000.0
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return parse_expiry(float(text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_cookie_entries(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CredentialError(f"Cookie 文件无法读取或不是合法 JSON：{path}") from exc
    if isinstance(payload, dict):
        entries = payload.get("cookies")
        if entries is None:
            raise CredentialError(f"Cookie JSON 缺少 cookies 数组：{path}")
    else:
        entries = payload
    if not isinstance(entries, list):
        raise CredentialError(f"Cookie JSON 必须是数组或包含 cookies 数组：{path}")
    return [entry for entry in entries if isinstance(entry, dict)]


def cookie_path(
    item: Mapping[str, Any],
    env_file: Mapping[str, str],
    environ: Mapping[str, str],
    *,
    prefer_process: bool,
) -> Path:
    value, _ = resolve_env(
        (str(item.get("env") or ""),),
        env_file,
        environ,
        prefer_process=prefer_process,
    )
    path = value or _nonempty(item.get("default"))
    if not path:
        raise CredentialError(f"{item.get('id')} 没有 Cookie 路径")
    return Path(path).expanduser()


def _display_expiry(moment: datetime | None, now: datetime) -> str:
    if moment is None:
        return "会话 Cookie"
    delta = moment - now
    hours = delta.total_seconds() / 3600
    if hours < 0:
        return f"{moment.astimezone().strftime('%Y-%m-%d %H:%M')}（已过期）"
    if hours < 48:
        return f"{moment.astimezone().strftime('%Y-%m-%d %H:%M')}（剩余 {hours:.1f} 小时）"
    return f"{moment.astimezone().strftime('%Y-%m-%d %H:%M')}（剩余 {hours / 24:.1f} 天）"


def evaluate_cookie(
    item: Mapping[str, Any],
    env_file: Mapping[str, str],
    environ: Mapping[str, str],
    now: datetime,
    *,
    prefer_process: bool = True,
) -> dict[str, Any]:
    path = cookie_path(
        item,
        env_file,
        environ,
        prefer_process=prefer_process,
    )
    result: dict[str, Any] = {
        "id": item.get("id"),
        "label": item.get("label"),
        "category": item.get("category"),
        "state": "fail",
        "detail": "",
        "source": str(path),
        "github_secret": item.get("github_secret"),
        "required": bool(item.get("required")),
    }
    if not path.is_file():
        result["detail"] = f"文件不存在：{path}"
        return result
    try:
        entries = load_cookie_entries(path)
    except CredentialError as exc:
        result["detail"] = str(exc)
        return result
    usable = {
        str(entry.get("name")): entry
        for entry in entries
        if _nonempty(entry.get("name")) and _nonempty(entry.get("value"))
    }
    markers = [str(name) for name in item.get("login_markers", [])]
    missing = [name for name in markers if name not in usable]
    expiries = [
        parse_expiry(usable[name].get("expires"))
        for name in markers
        if name in usable
    ]
    known_expiries = [moment for moment in expiries if moment is not None]
    soonest = min(known_expiries) if known_expiries else None
    login_required = bool(item.get("login_required"))
    expiry_warn_hours = int(item.get("expiry_warn_hours") or 72)
    expiry_text = _display_expiry(soonest, now)
    login_text = "登录标记齐全" if not missing else f"缺少 {','.join(missing)}"

    if missing and login_required:
        result["detail"] = f"{len(entries)} 条 Cookie；{login_text}"
        return result
    if soonest is not None and soonest <= now:
        result["state"] = "fail" if login_required else "warn"
        result["detail"] = f"{len(entries)} 条 Cookie；{login_text}；最近过期 {expiry_text}"
        return result
    if missing:
        result["state"] = "warn"
        result["detail"] = f"{len(entries)} 条 Cookie；{login_text}，将按公开页模式运行"
        return result
    if soonest is not None and soonest <= now + timedelta(hours=expiry_warn_hours):
        result["state"] = "warn"
        result["detail"] = f"{len(entries)} 条 Cookie；{login_text}；最近过期 {expiry_text}"
        return result

    result["state"] = "ok"
    result["detail"] = f"{len(entries)} 条 Cookie；{login_text}；最近过期 {expiry_text}"
    return result


def evaluate_env_item(
    item: Mapping[str, Any],
    env_file: Mapping[str, str],
    environ: Mapping[str, str],
    *,
    prefer_process: bool = True,
) -> dict[str, Any]:
    names = [str(item.get("env"))]
    names.extend(str(alias) for alias in item.get("aliases", []))
    value, source = resolve_env(
        names,
        env_file,
        environ,
        prefer_process=prefer_process,
    )
    secret = bool(item.get("secret")) or is_secret_name(names[0])
    allowed = item.get("allowed")
    result: dict[str, Any] = {
        "id": item.get("id"),
        "label": item.get("label"),
        "category": item.get("category"),
        "state": "optional",
        "detail": "",
        "source": source,
        "github_secret": item.get("github_secret"),
        "required": bool(item.get("required")),
    }
    if not value:
        default = _nonempty(item.get("default"))
        result["detail"] = f"未设置；默认 {default}" if default else "未设置"
        result["state"] = "fail" if item.get("required") else "optional"
        return result
    if item.get("deprecated"):
        result["state"] = "warn"
        result["detail"] = "已配置，但代码不读取；建议从本机配置删除"
        return result
    if isinstance(allowed, list) and value not in allowed:
        result["state"] = "fail"
        result["detail"] = f"值 {value!r} 不在允许范围 {allowed}"
        return result
    result["state"] = "ok"
    if secret:
        result["detail"] = f"已配置；sha256:{fingerprint(value)}"
    else:
        result["detail"] = value
    file_value, _ = resolve_env(
        names,
        env_file,
        {},
        prefer_process=False,
    )
    if (
        source.startswith("process:")
        and not file_value
        and item.get("persist_warning", True)
    ):
        result["state"] = "warn"
        result["detail"] = (
            f"{result['detail']}；仅进程环境存在，建议写入本机配置文件以保证重启后仍有效"
        )
    return result


def evaluate_any_env_item(
    item: Mapping[str, Any],
    env_file: Mapping[str, str],
    environ: Mapping[str, str],
    *,
    prefer_process: bool = True,
) -> dict[str, Any]:
    """Evaluate a group where at least one environment variable must be set."""

    names = [str(name) for name in item.get("env", []) if str(name).strip()]
    value, source = resolve_env(
        names,
        env_file,
        environ,
        prefer_process=prefer_process,
    )
    result: dict[str, Any] = {
        "id": item.get("id"),
        "label": item.get("label"),
        "category": item.get("category"),
        "state": "optional",
        "detail": "",
        "source": source,
        "github_secret": item.get("github_secret"),
        "required": bool(item.get("required")),
    }
    if value:
        source_name = source.split(":", 1)[-1]
        result["state"] = "ok"
        result["detail"] = f"已配置 {source_name}；sha256:{fingerprint(value)}"
    else:
        result["state"] = "fail" if item.get("required") else "optional"
        result["detail"] = "未配置任何一项：" + " / ".join(names)
    return result


def evaluate_complete_env_groups(
    item: Mapping[str, Any],
    env_file: Mapping[str, str],
    environ: Mapping[str, str],
    *,
    prefer_process: bool = True,
) -> dict[str, Any]:
    """Evaluate alternatives where every variable in one group must be present."""

    groups = [
        [str(name) for name in group if str(name).strip()]
        for group in item.get("groups", [])
    ]
    result: dict[str, Any] = {
        "id": item.get("id"),
        "label": item.get("label"),
        "category": item.get("category"),
        "state": "optional",
        "detail": "",
        "source": "",
        "github_secret": item.get("github_secret"),
        "required": bool(item.get("required")),
    }
    partial: list[str] = []
    for group in groups:
        values = [
            resolve_env(
                (name,),
                env_file,
                environ,
                prefer_process=prefer_process,
            )
            for name in group
        ]
        if group and all(value for value, _ in values):
            result["state"] = "ok"
            result["source"] = values[0][1]
            result["detail"] = "已配置完整组合：" + " + ".join(group)
            return result
        configured = [name for name, (value, _) in zip(group, values) if value]
        if configured:
            missing = [name for name in group if name not in configured]
            partial.append(
                " + ".join(configured) + " 缺少 " + " / ".join(missing)
            )
    result["state"] = "fail" if item.get("required") else "optional"
    detail = "未配置任何完整组合：" + "；".join(
        " + ".join(group) for group in groups
    )
    if partial:
        detail += "。不完整组合：" + "；".join(partial)
    if item.get("anonymous_available"):
        result["state"] = "warn"
        result["detail"] = (
            "未配置带 Key 的组合；可使用内置匿名云 API："
            + str(item.get("anonymous_label") or "anonymous")
            + f"。{detail}"
        )
        return result
    result["detail"] = detail
    return result


def evaluate_item(
    item: Mapping[str, Any],
    env_file: Mapping[str, str],
    environ: Mapping[str, str],
    now: datetime,
    *,
    prefer_process: bool = True,
) -> dict[str, Any]:
    kind = item.get("kind")
    if kind == "cookie_file":
        return evaluate_cookie(
            item,
            env_file,
            environ,
            now,
            prefer_process=prefer_process,
        )
    if kind == "env":
        return evaluate_env_item(
            item,
            env_file,
            environ,
            prefer_process=prefer_process,
        )
    if kind == "env_any":
        return evaluate_any_env_item(
            item,
            env_file,
            environ,
            prefer_process=prefer_process,
        )
    if kind == "env_any_complete":
        return evaluate_complete_env_groups(
            item,
            env_file,
            environ,
            prefer_process=prefer_process,
        )
    raise CredentialError(f"未知条目类型：{kind!r}")


def advanced_item(entry: Mapping[str, Any]) -> dict[str, Any]:
    name = str(entry.get("env") or "")
    return {
        "id": name,
        "label": name,
        "category": "高级/可选",
        "kind": "env",
        "env": name,
        "secret": is_secret_name(name),
        "required": False,
        "github_secret": None,
        "default": entry.get("default"),
        "note": entry.get("note"),
        "persist_warning": False,
    }


def github_secret_names(repo: str) -> set[str]:
    completed = subprocess.run(
        ["gh", "secret", "list", "--repo", repo, "--json", "name"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if completed.returncode != 0:
        error = (completed.stderr or completed.stdout or "").strip()
        raise CredentialError(f"无法读取 GitHub Secrets：{error or 'gh 返回非零状态'}")
    try:
        payload = json.loads(completed.stdout or "[]")
    except ValueError as exc:
        raise CredentialError("GitHub Secrets 返回值不是 JSON") from exc
    return {
        str(item.get("name"))
        for item in payload
        if isinstance(item, dict) and item.get("name")
    }


def apply_github_state(
    result: dict[str, Any],
    github_names: set[str],
    item: Mapping[str, Any] | None = None,
) -> None:
    secret = result.get("github_secret")
    if not secret:
        return
    if item and item.get("kind") == "env_any_complete":
        groups = [
            [str(name) for name in group if str(name).strip()]
            for group in item.get("groups", [])
        ]
        if any(group and all(name in github_names for name in group) for group in groups):
            result["detail"] = f"{result['detail']}；GitHub Secret 至少一组完整"
        elif item.get("anonymous_available"):
            result["state"] = "warn"
            result["detail"] = (
                f"{result['detail']}；GitHub Secret 无 Key 组合，"
                "云端将使用内置匿名 ASR 接口（STT.ai + NoteTakers，"
                "合计约 13 次/日/IP）"
            )
        else:
            required = bool(result.get("required"))
            result["state"] = "fail" if required else (
                "warn" if result.get("state") == "ok" else "optional"
            )
            result["detail"] = f"{result['detail']}；GitHub Secret 没有完整组合"
        return
    secret_names = [secret] if isinstance(secret, str) else [
        str(name) for name in secret if str(name).strip()
    ]
    if not secret_names:
        return
    missing = [name for name in secret_names if name not in github_names]
    if not missing:
        result["detail"] = f"{result['detail']}；GitHub Secret 已存在"
        return
    if len(secret_names) > 1 and len(missing) < len(secret_names):
        result["detail"] = f"{result['detail']}；GitHub Secret 至少一个已存在"
        return
    if missing:
        required = bool(result.get("required"))
        result["state"] = "fail" if required else (
            "warn" if result.get("state") == "ok" else "optional"
        )
        suffix = "缺失" if required else "缺失（可选）"
        result["detail"] = (
            f"{result['detail']}；GitHub Secret "
            + " / ".join(missing)
            + f" {suffix}"
        )


def build_check_rows(
    manifest: Mapping[str, Any],
    env_file: Mapping[str, str],
    environ: Mapping[str, str],
    *,
    include_advanced: bool,
    include_optional: bool,
    prefer_process: bool,
    now: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in manifest.get("items", []):
        if not include_optional and not item.get("required"):
            continue
        rows.append(
            evaluate_item(
                item,
                env_file,
                environ,
                now,
                prefer_process=prefer_process,
            )
        )
    if include_advanced:
        for entry in manifest.get("advanced", []):
            rows.append(
                evaluate_item(
                    advanced_item(entry),
                    env_file,
                    environ,
                    now,
                    prefer_process=prefer_process,
                )
            )
    return rows


def summarize(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"ok": 0, "warn": 0, "fail": 0, "optional": 0}
    for row in rows:
        state = str(row.get("state") or "optional")
        counts[state] = counts.get(state, 0) + 1
    return counts


def render_table(rows: Sequence[Mapping[str, Any]], *, github_checked: bool) -> str:
    headers = ["状态", "项目", "本机配置", "GitHub Secret", "说明"]
    body: list[list[str]] = []
    marks = {
        "ok": "OK",
        "warn": "WARN",
        "fail": "FAIL",
        "optional": "--",
    }
    for row in rows:
        body.append(
            [
                marks.get(str(row.get("state")), "?"),
                str(row.get("label") or row.get("id") or ""),
                str(row.get("source") or "未设置"),
                _secret_label(row.get("github_secret")),
                str(row.get("detail") or ""),
            ]
        )
    if not github_checked:
        headers = headers[:-2] + ["说明"]
        body = [row[:3] + row[4:] for row in body]
    widths = [len(header) for header in headers]
    for row in body:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    lines = [
        "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)),
        "  ".join("-" * width for width in widths),
    ]
    for row in body:
        lines.append(
            "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row))
        )
    return "\n".join(lines)


def render_markdown(rows: Sequence[Mapping[str, Any]], *, github_checked: bool) -> str:
    marks = {"ok": "✅", "warn": "⚠️", "fail": "❌", "optional": "—"}
    if github_checked:
        lines = [
            "| 状态 | 项目 | 本机配置 | GitHub Secret | 说明 |",
            "| --- | --- | --- | --- | --- |",
        ]
    else:
        lines = [
            "| 状态 | 项目 | 本机配置 | 说明 |",
            "| --- | --- | --- | --- |",
        ]
    for row in rows:
        cells = [
            marks.get(str(row.get("state")), "?"),
            str(row.get("label") or row.get("id") or ""),
            str(row.get("source") or "未设置"),
            str(row.get("detail") or ""),
        ]
        if github_checked:
            cells.insert(3, _secret_label(row.get("github_secret")))
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    return "\n".join(lines)


def render_json(
    manifest: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> str:
    payload = {
        "project": manifest.get("project"),
        "summary": summarize(rows),
        "items": list(rows),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def cookie_github_payload(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CredentialError(f"无法读取 Cookie 文件：{path}") from exc
    compressed = gzip.compress(data, mtime=0)
    return base64.b64encode(compressed).decode("ascii")


def build_github_payload(
    item: Mapping[str, Any],
    env_file: Mapping[str, str],
    environ: Mapping[str, str],
) -> str | None:
    if item.get("kind") in {"env_any", "env_any_complete"}:
        return None
    secret_name = item.get("github_secret")
    if not secret_name:
        return None
    if item.get("kind") == "cookie_file":
        path = cookie_path(
            item,
            env_file,
            environ,
            prefer_process=False,
        )
        if not path.is_file():
            raise CredentialError(f"{item.get('label')} Cookie 文件不存在：{path}")
        return cookie_github_payload(path)
    names = [str(item.get("env"))]
    names.extend(str(alias) for alias in item.get("aliases", []))
    value, _ = resolve_env(
        names,
        env_file,
        environ,
        prefer_process=False,
    )
    if not value:
        raise CredentialError(f"{item.get('label')} 本机值为空")
    return value


def sync_github(
    manifest: Mapping[str, Any],
    env_file: Mapping[str, str],
    environ: Mapping[str, str],
    *,
    apply: bool,
    only: set[str] | None,
) -> int:
    repo = _nonempty(manifest.get("project", {}).get("repository"))
    if not repo:
        raise CredentialError("清单缺少 project.repository")
    updates: list[tuple[str, str]] = []
    for item in manifest.get("items", []):
        if item.get("kind") in {"env_any", "env_any_complete"}:
            continue
        secret_name = _nonempty(item.get("github_secret"))
        if not secret_name or (only and secret_name not in only):
            continue
        try:
            payload = build_github_payload(item, env_file, environ)
        except CredentialError as exc:
            if item.get("required"):
                raise
            print(f"[SKIP] {item.get('label') or secret_name}: {exc}")
            continue
        if payload is not None:
            updates.append((secret_name, payload))
    if not updates:
        raise CredentialError("没有匹配到要同步的 GitHub Secret")
    print(f"准备同步 {len(updates)} 个 GitHub Secret 到 {repo}")
    for name, _ in updates:
        print(f"  {name}")
    if not apply:
        print("当前为预览模式；加 --apply 才会写入 GitHub。")
        return 0
    for name, payload in updates:
        completed = subprocess.run(
            ["gh", "secret", "set", name, "--repo", repo],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if completed.returncode != 0:
            error = (completed.stderr or completed.stdout or "").strip()
            print(f"[FAIL] {name}: {error}", file=sys.stderr)
            return 1
        print(f"[OK] {name}")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="审计并同步股票分析项目的凭证清单（不会打印 Secret 值）"
    )
    parser.add_argument(
        "command",
        choices=("check", "sync-github"),
        nargs="?",
        default="check",
        help="默认 check",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument(
        "--github",
        action="store_true",
        help="同时核对 GitHub Actions Secrets 名称",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="包含可选、高级和遗留配置",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON（不含 Secret 值）",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="输出 Markdown 表格",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="有必需项失败时返回非零",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="sync-github 时真正写入，默认只预览",
    )
    parser.add_argument(
        "--only",
        default="",
        help="sync-github 只同步指定 Secret，逗号分隔",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        project = manifest.get("project", {})
        env_path = args.env_file or Path(
            _nonempty(project.get("local_env_file")) or "~/.codex/daily-briefing.env"
        ).expanduser()
        env_file = load_env_file(env_path)
        if args.command == "sync-github":
            only = {item.strip() for item in args.only.split(",") if item.strip()}
            return sync_github(
                manifest,
                env_file,
                os.environ,
                apply=args.apply,
                only=only or None,
            )

        now = datetime.now(timezone.utc)
        rows = build_check_rows(
            manifest,
            env_file,
            os.environ,
            include_advanced=args.all,
            include_optional=args.all,
            prefer_process=True,
            now=now,
        )
        github_names: set[str] | None = None
        if args.github:
            github_names = github_secret_names(
                _nonempty(project.get("repository"))
            )
            items_by_id = {
                str(item.get("id")): item
                for item in manifest.get("items", [])
                if item.get("id")
            }
            for row in rows:
                apply_github_state(
                    row,
                    github_names,
                    items_by_id.get(str(row.get("id"))),
                )
        counts = summarize(rows)
        if args.json:
            print(render_json(manifest, rows))
        else:
            print(f"项目：{project.get('name', '')}")
            print(f"仓库：{project.get('repository', '')}")
            print(f"本机配置：{env_path}")
            print(
                f"运行目录：{Path(_nonempty(project.get('runtime_root')) or '~/.codex/daily-briefing-pro').expanduser()}"
            )
            if args.markdown:
                print()
                print(render_markdown(rows, github_checked=args.github))
            else:
                print()
                print(render_table(rows, github_checked=args.github))
            print()
            print(
                "汇总："
                f"OK={counts.get('ok', 0)} "
                f"WARN={counts.get('warn', 0)} "
                f"FAIL={counts.get('fail', 0)} "
                f"OPTIONAL={counts.get('optional', 0)}"
            )
        if counts.get("fail", 0):
            return 1 if args.strict else 0
        return 0
    except (CredentialError, OSError, subprocess.SubprocessError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
