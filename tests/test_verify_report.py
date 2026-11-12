from __future__ import annotations

import json

import verify_skill_report as verify


STOCK_SECTIONS = [
    "核心结论",
    "概览与估值",
    "产品与客户",
    "基本面与壁垒",
    "消息资金筹码",
    "市场声音",
    "前瞻指引",
    "风险全景",
    "行动建议",
    "数据来源",
]

INDUSTRY_SECTIONS = [
    "行业概览",
    "竞争格局",
    "核心标的",
    "客户订单",
    "同行指标",
    "投资逻辑",
    "风险提示",
    "核心结论",
]


def make_html(sections, tables, rows=3):
    body = "".join(f"<h2>{section}</h2>" for section in sections)
    body += "".join(
        "<table>" + "".join("<tr><td>数据</td></tr>" for _ in range(rows)) + "</table>"
        for _ in range(tables)
    )
    return f"<html><body>{body}</body></html>"


def test_stock_report_gate_passes(tmp_path):
    path = tmp_path / "stock.html"
    path.write_text(make_html(STOCK_SECTIONS, 6), encoding="utf-8")
    result = verify.verify_report(path, "stock")
    assert result["ok"] is True
    assert result["tables"] == 6
    assert result["missing_sections"] == []


def test_industry_report_gate_passes(tmp_path):
    path = tmp_path / "industry.html"
    path.write_text(make_html(INDUSTRY_SECTIONS, 5), encoding="utf-8")
    result = verify.verify_report(path, "industry")
    assert result["ok"] is True
    assert result["tables"] == 5


def test_report_gate_rejects_missing_sections_and_placeholders(tmp_path):
    path = tmp_path / "bad.html"
    path.write_text(make_html(["核心结论"], 1) + "<p>NaN</p>", encoding="utf-8")
    result = verify.verify_report(path, "stock")
    assert result["ok"] is False
    assert "概览与估值" in result["missing_sections"]
    assert result["placeholders"]


def test_report_gate_rejects_short_temporary_data_marker(tmp_path):
    path = tmp_path / "bad.html"
    path.write_text(make_html(STOCK_SECTIONS, 6) + "<p>暂无</p>", encoding="utf-8")
    result = verify.verify_report(path, "stock")
    assert result["ok"] is False
    assert "暂无" in " ".join(result["placeholders"])


def test_data_gate_checks_required_fields(tmp_path):
    data = {
        "quote": {"last_price": 1},
        "finance_raw": {
            "pe": 20,
            "营业收入[20251231]": 10000000000,
            "归属于母公司所有者的净利润[20251231]": 1000000000,
        },
        "peers_raw": [{"name": "peer"}],
        "holders_raw": [{"name": "holder"}],
        "big_orders": [{"amount": 1}],
        "news": [{"title": "news"}],
        "product_raw": {"product": "main"},
        "chip_structure": {"cost": 10},
        "blogger_opinions": [{"text": "view"}],
        "barrier_data": {"moat": "brand"},
        "research_reports": [{"title": "report"}],
        "warnings": [],
    }
    path = tmp_path / "stock.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    result = verify.verify_data(path, "stock")
    assert result["ok"] is True
    assert result["missing_or_empty"] == []


def test_data_gate_reports_missing_field(tmp_path):
    path = tmp_path / "stock.json"
    path.write_text('{"quote": {}, "warnings": []}', encoding="utf-8")
    result = verify.verify_data(path, "stock")
    assert result["ok"] is False
    assert "行情" in result["missing_or_empty"]


def test_source_fact_gate_rejects_stock_price_mismatch(tmp_path):
    path = tmp_path / "stock.html"
    path.write_text(
        make_html(STOCK_SECTIONS, 6) + "<p>贵州茅台 600519 最新价 999.00</p>",
        encoding="utf-8",
    )
    data = {
        "stock_code": "600519",
        "quote": {"name": "贵州茅台", "price": 1402.3},
        "finance_raw": {"股票简称": "贵州茅台"},
    }
    result = verify.verify_report(path, "stock", data=data)
    assert result["ok"] is False
    assert any("最新价" in problem for problem in result["problems"])


def test_source_fact_gate_rejects_stock_financial_mismatch(tmp_path):
    path = tmp_path / "stock.html"
    path.write_text(
        make_html(STOCK_SECTIONS, 6)
        + "<p>贵州茅台 600519 最新价 1,402.30 营业收入 1,700.00 亿 归母净利润 900.00 亿</p>",
        encoding="utf-8",
    )
    data = {
        "stock_code": "600519",
        "quote": {"name": "贵州茅台", "price": 1402.3},
        "finance_raw": {
            "股票简称": "贵州茅台",
            "营业收入[20251231]": 180000000000,
            "归属于母公司所有者的净利润[20251231]": 90000000000,
        },
    }
    result = verify.verify_report(path, "stock", data=data)

    assert result["ok"] is False
    assert any("营业收入" in problem for problem in result["problems"])


def test_source_fact_gate_normalizes_vendor_name_spacing(tmp_path):
    path = tmp_path / "stock.html"
    path.write_text(
        make_html(STOCK_SECTIONS, 6)
        + "<p>万科A 000002 最新价 7.00 营业收入 100.00 亿 归母净利润 10.00 亿</p>",
        encoding="utf-8",
    )
    data = {
        "stock_code": "000002",
        "quote": {"name": "万  科Ａ", "price": 7.0},
        "finance_raw": {
            "股票简称": "万科A",
            "营业收入[20251231]": 10000000000,
            "归属于母公司所有者的净利润[20251231]": 1000000000,
        },
    }
    result = verify.verify_report(path, "stock", data=data)
    assert result["ok"] is True, result["problems"]


def test_source_fact_gate_rejects_missing_stock_financials(tmp_path):
    path = tmp_path / "stock.html"
    path.write_text(
        make_html(STOCK_SECTIONS, 6) + "<p>贵州茅台 600519 最新价 1,402.30</p>",
        encoding="utf-8",
    )
    data = {
        "stock_code": "600519",
        "quote": {"name": "贵州茅台", "price": 1402.3},
        "finance_raw": {"股票简称": "贵州茅台"},
    }
    result = verify.verify_report(path, "stock", data=data)

    assert result["ok"] is False
    assert any("缺少最新年度营业收入" in problem for problem in result["problems"])
    assert any("缺少最新年度归母净利润" in problem for problem in result["problems"])


def test_source_fact_gate_rejects_missing_industry_member(tmp_path):
    path = tmp_path / "industry.html"
    path.write_text(make_html(INDUSTRY_SECTIONS, 5), encoding="utf-8")
    data = {
        "sector": {"name": "白酒"},
        "stocks": [{"name": "贵州茅台", "ticker": "600519"}],
    }
    result = verify.verify_report(path, "industry", data=data)
    assert result["ok"] is False
    assert any("贵州茅台" in problem for problem in result["problems"])


def test_source_fact_gate_rejects_missing_industry_ticker(tmp_path):
    path = tmp_path / "industry.html"
    path.write_text(
        make_html(INDUSTRY_SECTIONS, 5) + "<p>白酒 贵州茅台</p>",
        encoding="utf-8",
    )
    data = {
        "sector": {"name": "白酒"},
        "stocks": [{"name": "贵州茅台", "ticker": "600519"}],
    }
    result = verify.verify_report(path, "industry", data=data)

    assert result["ok"] is False
    assert any("证券代码" in problem for problem in result["problems"])


def test_source_fact_gate_rejects_missing_shareholder_names(tmp_path):
    path = tmp_path / "stock.html"
    path.write_text(
        make_html(STOCK_SECTIONS, 6) + "<p>贵州茅台 600519 最新价 1,402.30</p>",
        encoding="utf-8",
    )
    data = {
        "stock_code": "600519",
        "quote": {"name": "贵州茅台", "price": 1402.3},
        "finance_raw": {"股票简称": "贵州茅台"},
        "holders_raw": {"前十大流通股东名称": "股东甲||股东乙"},
    }
    result = verify.verify_report(path, "stock", data=data)
    assert result["ok"] is False
    assert any("股东名称" in problem for problem in result["problems"])


def test_verify_cli_checks_source_facts_with_data_json(tmp_path, capsys):
    path = tmp_path / "stock.html"
    path.write_text(
        make_html(STOCK_SECTIONS, 6) + "<p>贵州茅台 600519 最新价 999.00</p>",
        encoding="utf-8",
    )
    data_path = tmp_path / "stock.json"
    data_path.write_text(
        json.dumps(
            {
                "stock_code": "600519",
                "quote": {"name": "贵州茅台", "price": 1402.3},
                "finance_raw": {"股票简称": "贵州茅台"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = verify.main(
        [str(path), "--type", "stock", "--data-json", str(data_path)]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert any("最新价" in problem for problem in payload["problems"])
