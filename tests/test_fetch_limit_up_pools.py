from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "fetch_limit_up_pools.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("fetch_limit_up_pools", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_run_cli_uses_cross_platform_executable(monkeypatch):
    module = _load_tool()
    captured: dict = {}

    monkeypatch.setattr(
        module.shutil,
        "which",
        lambda name: "/usr/local/bin/hithink-finance" if name == "hithink-finance" else None,
    )
    monkeypatch.setenv("FUYAO_API_KEY", "shared-test-key")

    class Completed:
        stdout = '{"ok": true, "data": {"item": []}}'
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module._run_cli(["market", "calendar"]) == {
        "ok": True,
        "data": {"item": []},
    }
    assert captured["command"] == [
        "/usr/local/bin/hithink-finance",
        "market",
        "calendar",
    ]
    assert captured["command"][0] != "cmd"
    assert captured["kwargs"]["env"]["HITHINK_FINANCE_API_KEY"] == "shared-test-key"
    assert captured["kwargs"]["text"] is True


def test_run_cli_reports_missing_cloud_cli(monkeypatch):
    module = _load_tool()
    monkeypatch.setattr(module.shutil, "which", lambda _name: None)

    with pytest.raises(RuntimeError, match="hithink-finance"):
        module._run_cli(["market", "calendar"])
