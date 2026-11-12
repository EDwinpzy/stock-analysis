from __future__ import annotations

import base64
import gzip
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools import credential_manifest as cm


ROOT = Path(__file__).resolve().parents[1]
CONFIG_ENV_PATTERN = re.compile(
    r"""(?:os\.getenv|os\.environ\.get)\(\s*["']([A-Z][A-Z0-9_]+)["']"""
)
INDIRECT_CONFIG_ENV_NAMES = {
    "DAILY_BRIEFING_AI_API_KEY",
    "DAILY_BRIEFING_AI_BASE_URL",
    "DAILY_BRIEFING_AI_FALLBACK_MODEL",
    "DAILY_BRIEFING_AI_MODEL",
    "DAILY_BRIEFING_MODEL_CACHE",
    "HITHINK_API_KEY",
    "HITHINK_FINANCE_API_KEY",
    "NODE_USE_ENV_PROXY",
    "THS_HOME",
    "THS_INSTALL_DIR",
    "THS_ROOT",
    "WENCAI_API_KEY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
}


def _manifest() -> dict:
    return json.loads(
        (ROOT / "config" / "credentials.manifest.json").read_text(encoding="utf-8")
    )


def _cookie_item() -> dict:
    return {
        "id": "tgb",
        "label": "TGB",
        "category": "Cookie",
        "kind": "cookie_file",
        "env": "TGB_COOKIE_PATH",
        "required": True,
        "login_markers": ["tgbpwd", "tgbuser"],
        "login_required": True,
        "expiry_warn_hours": 72,
    }


def _manifest_env_names() -> set[str]:
    manifest = _manifest()
    names: set[str] = set()
    for item in manifest["items"]:
        raw = item.get("env")
        if isinstance(raw, list):
            names.update(str(name) for name in raw)
        elif raw:
            names.add(str(raw))
    for item in manifest["items"]:
        names.update(item.get("aliases", []))
    names.update(
        entry["env"]
        for entry in manifest.get("advanced", [])
        if entry.get("env")
    )
    return names


def _write_cookies(path: Path, expires: str | int, include_session: bool = False) -> None:
    cookies = [
        {"name": "tgbpwd", "value": "secret-a", "expires": expires},
        {"name": "tgbuser", "value": "secret-b", "expires": expires},
    ]
    if include_session:
        cookies.append({"name": "sessionid", "value": "secret-c", "expires": expires})
    path.write_text(json.dumps(cookies), encoding="utf-8")


def test_manifest_github_secrets_match_workflow():
    manifest = _manifest()
    workflow = (ROOT / manifest["project"]["workflow"]).read_text(encoding="utf-8")
    workflow_secrets = set(re.findall(r"secrets\.([A-Z0-9_]+)", workflow))
    manifest_secrets: set[str] = set()
    for item in manifest["items"]:
        raw = item.get("github_secret")
        if isinstance(raw, list):
            manifest_secrets.update(str(name) for name in raw)
        elif raw:
            manifest_secrets.add(str(raw))
    assert manifest_secrets == workflow_secrets


def test_required_env_names_exist_in_template():
    manifest = _manifest()
    template = cm.parse_env_text(
        (ROOT / manifest["project"]["template"]).read_text(encoding="utf-8")
    )
    required_names = {
        item["env"]
        for item in manifest["items"]
        if item.get("required") and item.get("kind") == "env"
    }
    cookie_path_names = {
        item["env"]
        for item in manifest["items"]
        if item.get("required") and item.get("kind") == "cookie_file"
    }
    assert required_names | cookie_path_names <= set(template)


def test_manifest_and_template_do_not_contain_secret_literals():
    manifest_text = (ROOT / "config" / "credentials.manifest.json").read_text(
        encoding="utf-8"
    )
    template_text = (ROOT / "config" / "daily-briefing.env.example").read_text(
        encoding="utf-8"
    )
    combined = manifest_text + "\n" + template_text
    assert not re.search(r"sk-[A-Za-z0-9_-]{20,}", combined)
    assert "magpie-key-" not in combined


def test_manifest_covers_configurable_env_names_in_source():
    used_names = set(INDIRECT_CONFIG_ENV_NAMES)
    ignored_parts = {"__pycache__", "runtime", "tests", "work"}
    for source_root in (ROOT / "plugins" / "daily-briefing-pro", ROOT / "tools"):
        for path in source_root.rglob("*.py"):
            if ignored_parts.intersection(path.parts):
                continue
            used_names.update(
                CONFIG_ENV_PATTERN.findall(path.read_text(encoding="utf-8"))
            )

    missing = sorted(used_names - _manifest_env_names())
    assert not missing, f"清单缺少源码仍在读取的配置变量：{missing}"


def test_manifest_env_names_are_unique():
    manifest = _manifest()
    names = [
        item["env"]
        for item in manifest["items"]
        if item.get("env")
    ]
    for item in manifest["items"]:
        names.extend(item.get("aliases", []))
    names.extend(
        entry["env"]
        for entry in manifest.get("advanced", [])
        if entry.get("env")
    )
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert not duplicates


def test_cookie_expiry_warning_and_expired_failure(tmp_path, monkeypatch):
    now = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
    path = tmp_path / "tgb.json"
    monkeypatch.setenv("TGB_COOKIE_PATH", str(path))

    _write_cookies(path, (now + timedelta(hours=10)).isoformat().replace("+00:00", "Z"))
    warning = cm.evaluate_cookie(
        _cookie_item(),
        {},
        {"TGB_COOKIE_PATH": str(path)},
        now,
    )
    assert warning["state"] == "warn"
    assert "最近过期" in warning["detail"]

    _write_cookies(path, (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"))
    expired = cm.evaluate_cookie(
        _cookie_item(),
        {},
        {"TGB_COOKIE_PATH": str(path)},
        now,
    )
    assert expired["state"] == "fail"
    assert "已过期" in expired["detail"]


def test_cookie_missing_optional_login_is_warning(tmp_path, monkeypatch):
    now = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
    path = tmp_path / "douyin.json"
    path.write_text(
        json.dumps([{"name": "passport_csrf_token", "value": "x", "expires": 0}]),
        encoding="utf-8",
    )
    item = {
        "id": "douyin",
        "label": "Douyin",
        "category": "Cookie",
        "kind": "cookie_file",
        "env": "DOUYIN_COOKIE_PATH",
        "required": True,
        "login_markers": ["sessionid"],
        "login_required": False,
    }
    result = cm.evaluate_cookie(
        item,
        {},
        {"DOUYIN_COOKIE_PATH": str(path)},
        now,
    )
    assert result["state"] == "warn"
    assert "公开页模式" in result["detail"]


def test_secret_is_masked_in_audit_output_and_alias_is_supported():
    item = {
        "id": "fuyao",
        "label": "Fuyao",
        "category": "行情",
        "kind": "env",
        "env": "FUYAO_API_KEY",
        "aliases": ["HITHINK_FINANCE_API_KEY"],
        "secret": True,
        "required": True,
    }
    result = cm.evaluate_env_item(
        item,
        {},
        {"HITHINK_FINANCE_API_KEY": "super-secret-value"},
    )
    assert result["state"] == "warn"
    assert "process:HITHINK_FINANCE_API_KEY" == result["source"]
    assert "super-secret-value" not in json.dumps(result)
    assert cm.fingerprint("super-secret-value") in result["detail"]


def test_optional_missing_github_secret_is_not_a_failure():
    result = {
        "state": "ok",
        "detail": "云端 ASR 已配置",
        "github_secret": "DOUYIN_ASR_API_KEY",
        "required": False,
    }

    cm.apply_github_state(result, set())

    assert result["state"] == "warn"
    assert "缺失（可选）" in result["detail"]


def test_cookie_github_payload_round_trips(tmp_path):
    path = tmp_path / "cookie.json"
    _write_cookies(path, "2026-11-13T05:27:54.588Z")
    encoded = cm.cookie_github_payload(path)
    assert gzip.decompress(base64.b64decode(encoded)) == path.read_bytes()
