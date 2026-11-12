from __future__ import annotations

import json
import subprocess

import cloud_cli


def test_doctor_reports_writable_roots(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DAILY_BRIEFING_HOME", str(tmp_path))
    monkeypatch.delenv("DAILY_BRIEFING_DATA_DIR", raising=False)
    monkeypatch.delenv("BRIEFING_OUTPUT_DIR", raising=False)
    exit_code = cloud_cli.main(["doctor"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["data_dir"]["writable"] is True
    assert payload["report_dir"]["writable"] is True
    assert payload["api_keys"]["HITHINK_API_KEY"] is False
    assert list(payload["api_keys"]) == [
        "FUYAO_API_KEY",
        "HITHINK_API_KEY",
        "HITHINK_FINANCE_API_KEY",
        "IWENCAI_API_KEY",
        "WENCAI_API_KEY",
    ]


def test_doctor_probe_failure_is_not_success(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DAILY_BRIEFING_HOME", str(tmp_path))

    monkeypatch.setattr(
        cloud_cli,
        "run_capture",
        lambda *args, **kwargs: (1, "", "probe failed"),
    )
    exit_code = cloud_cli.doctor(probe=True)
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["ok"] is False
    assert all(item["exit_code"] == 1 for item in payload["probe"])


def test_dry_run_market_command(capsys):
    assert cloud_cli.main(["--dry-run", "market", "realtime", "600519"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["command"][-2:] == ["realtime", "600519"]


def test_dry_run_stock_uses_output_dir(tmp_path, capsys):
    output = tmp_path / "stock"
    assert (
        cloud_cli.main(
            ["--dry-run", "stock", "600519", "--output-dir", str(output), "--preflight"]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert "--output-dir" in payload["command"]
    assert str(output) in payload["command"]
    assert payload["command"][-1] == "--preflight"


def test_dry_run_stock_report_wraps_collector_and_builder(tmp_path, capsys):
    output = tmp_path / "stock"
    assert (
        cloud_cli.main(
            ["--dry-run", "stock-report", "600519", "--output-dir", str(output)]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert ["--output-dir", str(output)] == payload["collect"][
        payload["collect"].index("--output-dir") : payload["collect"].index("--output-dir") + 2
    ]
    assert payload["collect"][-2:] == ["--source", "cloud"]
    assert payload["build"][-2:] == ["--data-json", "<collector-output>"]
    assert payload["build"][-4:-2] == ["--type", "stock"]
    assert any(item.endswith("fetch_stock_data.py") for item in payload["collect"])
    assert any(item.endswith("report_builder.py") for item in payload["build"])


def test_dry_run_industry_report_wraps_collector_and_builder(tmp_path, capsys):
    output = tmp_path / "industry"
    assert (
        cloud_cli.main(
            ["--dry-run", "industry-report", "白酒", "--output-dir", str(output)]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert ["--output-dir", str(output)] == payload["collect"][
        payload["collect"].index("--output-dir") : payload["collect"].index("--output-dir") + 2
    ]
    assert payload["collect"][-2:] == ["--source", "cloud"]
    assert any(item.endswith("fetch_industry_data.py") for item in payload["collect"])
    assert any(item.endswith("report_builder.py") for item in payload["build"])


def test_stock_report_runs_collector_then_builder(tmp_path, monkeypatch, capsys):
    data_path = tmp_path / "collected.json"
    data_path.write_text('{"quote": {"name": "样本"}}', encoding="utf-8")
    commands = []

    def fake_run_capture(command, dry_run=False, timeout=None):
        commands.append(command)
        if any(item.endswith("fetch_stock_data.py") for item in command):
            return 0, f"progress line\n{data_path}\n", ""
        if any(item.endswith("report_builder.py") for item in command):
            assert command[-2:] == ["--data-json", str(data_path)]
            return 0, '{"ok": true}\n', ""
        raise AssertionError(command)

    monkeypatch.setattr(cloud_cli, "run_capture", fake_run_capture)
    output = tmp_path / "reports"

    assert cloud_cli.report_command("stock", "600519", str(output), False, False) == 0
    assert len(commands) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": True}


def test_industry_report_runs_collector_then_builder(tmp_path, monkeypatch, capsys):
    data_path = tmp_path / "collected.json"
    data_path.write_text('{"sector": {"name": "白酒"}}', encoding="utf-8")
    commands = []

    def fake_run_capture(command, dry_run=False, timeout=None):
        commands.append(command)
        if any(item.endswith("fetch_industry_data.py") for item in command):
            return 0, f"progress line\n{data_path}\n", ""
        if any(item.endswith("report_builder.py") for item in command):
            assert command[-2:] == ["--data-json", str(data_path)]
            return 0, '{"ok": true}\n', ""
        raise AssertionError(command)

    monkeypatch.setattr(cloud_cli, "run_capture", fake_run_capture)
    output = tmp_path / "reports"

    assert cloud_cli.report_command("industry", "白酒", str(output), False, False) == 0
    assert len(commands) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": True}


def test_dry_run_briefing_passes_date_arguments(capsys):
    assert (
        cloud_cli.main(
            ["--dry-run", "briefing", "--date", "2026-11-11", "--preflight-only"]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"][-3:] == [
        "--date",
        "2026-11-11",
        "--preflight-only",
    ]


def test_dry_run_parity_compares_data_and_html(tmp_path, capsys):
    assert (
        cloud_cli.main(
            [
                "--dry-run",
                "parity",
                "--data-local",
                str(tmp_path / "local.json"),
                "--data-cloud",
                str(tmp_path / "cloud.json"),
                "--html-local",
                str(tmp_path / "local.html"),
                "--html-cloud",
                str(tmp_path / "cloud.html"),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert any(item.endswith("compare_cloud_parity.py") for item in payload["command"])
    assert payload["command"][-2:] == [
        "--html-cloud",
        str(tmp_path / "cloud.html"),
    ]


def test_stock_named_market_is_not_treated_as_subcommand(capsys):
    assert cloud_cli.main(["--dry-run", "stock", "market"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "market" in payload["command"]
    assert any(item.endswith("fetch_stock_data.py") for item in payload["command"])


def test_child_env_sets_runtime_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("DAILY_BRIEFING_HOME", str(tmp_path))
    env = cloud_cli.child_env()
    assert env["DAILY_BRIEFING_DATA_DIR"].endswith("data")
    assert env["BRIEFING_OUTPUT_DIR"].endswith("reports")
    assert env["DAILY_BRIEFING_CLOUD"] == "1"


def test_run_capture_reports_timeout(monkeypatch):
    class Process:
        pid = 123
        returncode = 124

        def __init__(self):
            self.calls = 0

        def communicate(self, timeout=None):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(
                    ["probe"],
                    timeout,
                    output="partial output",
                    stderr="partial error",
                )
            return "partial output", "partial error"

    process = Process()
    terminated = []
    monkeypatch.setattr(cloud_cli, "_start_process", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        cloud_cli,
        "_terminate_process_tree",
        lambda target: terminated.append(target),
    )
    code, stdout, stderr = cloud_cli.run_capture(["probe"], timeout=7)

    assert code == 124
    assert stdout == "partial output"
    assert "命令超时：7 秒" in stderr
    assert terminated == [process]
