from __future__ import annotations

import copy
import json
from pathlib import Path

from compare_business_parity import compare_payload


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests" / "fixtures" / "business-baseline"


def _load(name: str) -> dict:
    return json.loads((BASELINE / name).read_text(encoding="utf-8"))


def test_stock_business_parity_accepts_same_business_data(tmp_path):
    local = tmp_path / "local-stock.json"
    cloud = tmp_path / "cloud-stock.json"
    data = _load("stock-600519-2026-11-12.json")
    local.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    cloud_data = copy.deepcopy(data)
    cloud_data["quote"]["price"] *= 1.005
    cloud_data["quote"]["market_cap"] *= 1.005
    cloud_data["quote"]["pe_ttm"] *= 1.005
    cloud_data["peers_scope"] = "白酒"
    cloud_data["peers_expected_count"] = len(cloud_data["peers_raw"])
    cloud.write_text(json.dumps(cloud_data, ensure_ascii=False), encoding="utf-8")

    result = compare_payload("stock", local, cloud)

    assert result["ok"] is True, result["problems"]


def test_stock_business_parity_rejects_short_peer_universe(tmp_path):
    local = tmp_path / "local-stock.json"
    cloud = tmp_path / "cloud-stock.json"
    data = _load("stock-600519-2026-11-12.json")
    local.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    cloud_data = copy.deepcopy(data)
    cloud_data["peers_raw"] = cloud_data["peers_raw"][:9]
    cloud_data["peers_scope"] = "eastmoney_f10_sample"
    cloud.write_text(json.dumps(cloud_data, ensure_ascii=False), encoding="utf-8")

    result = compare_payload("stock", local, cloud)

    assert result["ok"] is False
    assert any("同业" in problem for problem in result["problems"])


def test_stock_business_parity_accepts_semantically_covered_product_subset(tmp_path):
    local = tmp_path / "local-stock.json"
    cloud = tmp_path / "cloud-stock.json"
    data = _load("stock-600519-2026-11-12.json")
    local.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    cloud_data = copy.deepcopy(data)
    cloud_data["peers_scope"] = "白酒"
    cloud_data["peers_expected_count"] = len(cloud_data["peers_raw"])
    cloud_data["product_raw"] = {"主营产品名称": "茅台酒||系列酒"}
    cloud.write_text(json.dumps(cloud_data, ensure_ascii=False), encoding="utf-8")

    result = compare_payload("stock", local, cloud)

    assert result["ok"] is True, result["problems"]
    product_check = next(
        item for item in result["checks"] if item["label"] == "主营产品范围"
    )
    assert product_check["cloud_coverage"] == 1.0


def test_stock_business_parity_rejects_unrelated_product_scope(tmp_path):
    local = tmp_path / "local-stock.json"
    cloud = tmp_path / "cloud-stock.json"
    data = _load("stock-600519-2026-11-12.json")
    local.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    cloud_data = copy.deepcopy(data)
    cloud_data["peers_scope"] = "白酒"
    cloud_data["peers_expected_count"] = len(cloud_data["peers_raw"])
    cloud_data["product_raw"] = {"主营产品名称": "银行服务||贷款"}
    cloud.write_text(json.dumps(cloud_data, ensure_ascii=False), encoding="utf-8")

    result = compare_payload("stock", local, cloud)

    assert result["ok"] is False
    assert any("主营产品" in problem for problem in result["problems"])


def test_industry_business_parity_rejects_missing_dividend_and_business(tmp_path):
    local = tmp_path / "local-industry.json"
    cloud = tmp_path / "cloud-industry.json"
    data = _load("industry-baijiu-2026-11-12.json")
    local.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    cloud_data = copy.deepcopy(data)
    cloud_data["stocks"][0]["dividend_yield"] = None
    cloud_data["stocks"][0]["main_business"] = ""
    cloud.write_text(json.dumps(cloud_data, ensure_ascii=False), encoding="utf-8")

    result = compare_payload("industry", local, cloud)

    assert result["ok"] is False
    assert any("股息率" in problem for problem in result["problems"])
    assert any("主营业务" in problem for problem in result["problems"])


def test_industry_business_parity_accepts_intraday_quote_moves(tmp_path):
    local = tmp_path / "local-industry.json"
    cloud = tmp_path / "cloud-industry.json"
    data = _load("industry-baijiu-2026-11-12.json")
    local.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    cloud_data = copy.deepcopy(data)
    for stock in cloud_data["stocks"]:
        for key in ("price", "pe", "pb"):
            if stock.get(key):
                stock[key] *= 1.08
        if stock.get("market_cap_yi"):
            stock["market_cap_yi"] *= 1.08
    cloud.write_text(json.dumps(cloud_data, ensure_ascii=False), encoding="utf-8")

    result = compare_payload("industry", local, cloud)

    assert result["ok"] is True, result["problems"]
