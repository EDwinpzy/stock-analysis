from __future__ import annotations

import json

from compare_cloud_parity import compare_html, compare_json, main


def test_compare_json_ignores_runtime_fields_and_column_order():
    local = {
        "stock_name": "贵州茅台",
        "fetch_time": "2026-11-12 07:19:29",
        "elapsed_seconds": 33.3,
        "runtime": {"platform": "win32", "data_dirs": ["D:/local"]},
        "product_columns": ["涨跌幅", "股票代码", "股票简称"],
        "quote": {"price": 1402.3},
    }
    cloud = {
        "stock_name": "贵州茅台",
        "fetch_time": "2026-11-12 07:20:06",
        "elapsed_seconds": 13.7,
        "runtime": {"platform": "linux", "data_dirs": ["/runtime/data"]},
        "product_columns": ["涨跌幅", "股票简称", "股票代码"],
        "quote": {"price": 1402.3},
    }

    assert compare_json(local, cloud) == []


def test_compare_json_reports_business_value_and_shape_differences():
    local = {
        "quote": {"price": 1402.3, "volume": 100},
        "members": [{"thscode": "USHA600519"}],
    }
    cloud = {
        "quote": {"price": 1402.4},
        "members": [{"thscode": "USHA600519"}, {"thscode": "USZA000858"}],
    }

    differences = compare_json(local, cloud)
    paths = {item["path"] for item in differences}

    assert "quote.price" in paths
    assert "quote.volume" in paths
    assert "members" in paths


def test_compare_html_ignores_matching_collection_timestamp(tmp_path):
    local = tmp_path / "local.html"
    cloud = tmp_path / "cloud.html"
    local.write_text(
        '<div>采集时间 2026-11-12 07:19:29</div>'
        '<div class="news">2026-11-11 15:00:00</div>'
        '<div class="price">1402.30</div>',
        encoding="utf-8",
    )
    cloud.write_text(
        '<div>采集时间 2026-11-12 07:20:06</div>'
        '<div class="news">2026-11-11 15:00:00</div>'
        '<div class="price">1402.30</div>',
        encoding="utf-8",
    )

    result = compare_html(
        local,
        cloud,
        local_timestamp="2026-11-12 07:19:29",
        cloud_timestamp="2026-11-12 07:20:06",
    )

    assert result["ok"] is True


def test_compare_html_reports_business_timestamp_difference(tmp_path):
    local = tmp_path / "local.html"
    cloud = tmp_path / "cloud.html"
    local.write_text(
        '<div>采集时间 2026-11-12 07:19:29</div>'
        '<div class="news">2026-11-11 15:00:00</div>',
        encoding="utf-8",
    )
    cloud.write_text(
        '<div>采集时间 2026-11-12 07:20:06</div>'
        '<div class="news">2026-11-10 15:00:00</div>',
        encoding="utf-8",
    )

    result = compare_html(
        local,
        cloud,
        local_timestamp="2026-11-12 07:19:29",
        cloud_timestamp="2026-11-12 07:20:06",
    )

    assert result["ok"] is False
    assert "2026-11-11 15:00:00" in "\n".join(result["differences"][0]["diff"])


def test_compare_html_without_timestamp_does_not_hide_difference(tmp_path):
    local = tmp_path / "local.html"
    cloud = tmp_path / "cloud.html"
    local.write_text("<div>2026-11-12 07:19:29</div>", encoding="utf-8")
    cloud.write_text("<div>2026-11-12 07:20:06</div>", encoding="utf-8")

    assert compare_html(local, cloud)["ok"] is False


def test_cli_returns_nonzero_for_business_difference(tmp_path, capsys):
    local = tmp_path / "local.json"
    cloud = tmp_path / "cloud.json"
    local.write_text(json.dumps({"quote": {"price": 1}}), encoding="utf-8")
    cloud.write_text(json.dumps({"quote": {"price": 2}}), encoding="utf-8")

    code = main(["--data-local", str(local), "--data-cloud", str(cloud)])
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["ok"] is False
    assert payload["data"]["differences"][0]["path"] == "quote.price"
