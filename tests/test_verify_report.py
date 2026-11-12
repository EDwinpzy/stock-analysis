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


def test_report_gate_rejects_public_data_placeholder(tmp_path):
    path = tmp_path / "bad.html"
    path.write_text(
        make_html(STOCK_SECTIONS, 6) + "<p>公开数据未覆盖</p>",
        encoding="utf-8",
    )
    result = verify.verify_report(path, "stock")

    assert result["ok"] is False
    assert "公开数据未覆盖" in " ".join(result["placeholders"])


def test_data_gate_checks_required_fields(tmp_path):
    data = {
        "quote": {
            "price": 10,
            "change_pct": 1,
            "change_amt": 0.1,
            "volume": 100,
            "amount": 1000,
            "market_cap": 100000,
            "circulating_cap": 90000,
            "pe_ttm": 20,
            "turnover_rate": 0.5,
            "amplitude": 2.0,
            "main_net_inflow": 100,
            "main_net_pct": 0.1,
            "high": 10.2,
            "low": 9.8,
            "open_change": 0.2,
            "prev_close": 9.9,
            "limit_up": 10.89,
            "limit_down": 8.91,
            "5d_change": -1.2,
        },
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
        "chip_structure": {
            "holder_count_trend": {
                "股东户数[20250630]": 1000,
                "股东户数[20251231]": 900,
            },
            "share_structure": {
                "总股本[20251231]": 100000000,
                "流通a股[20251231]": 90000000,
                "限售a股[20251231]": 10000000,
            },
            "unlock_data": {"未来解禁安排": "无公开待解禁记录"},
            "concentration": {"前十大股东持股比例合计": 66.0},
            "margin": {"融资余额[20251231]": 1000000},
        },
        "blogger_opinions": [{"text": "view"}],
        "barrier_data": {
            "rd_raw": {
                "研发投入占营业收入的比重[20251231]": 5.0,
                "专利数量合计[20251231]": 100,
            },
            "customer_concentration": {"value": 10.0, "period": "20251231"},
            "supplier_concentration": {"value": 20.0, "period": "20251231"},
        },
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


def test_data_gate_rejects_empty_chip_and_barrier_blocks(tmp_path):
    data = {
        "quote": {
            "price": 10,
            "change_pct": 1,
            "change_amt": 0.1,
            "volume": 100,
            "amount": 1000,
            "market_cap": 100000,
            "circulating_cap": 90000,
            "pe_ttm": 20,
            "turnover_rate": 0.5,
            "amplitude": 2.0,
            "main_net_inflow": 100,
            "main_net_pct": 0.1,
            "high": 10.2,
            "low": 9.8,
            "open_change": 0.2,
            "prev_close": 9.9,
            "limit_up": 10.89,
            "limit_down": 8.91,
            "5d_change": -1.2,
        },
        "finance_raw": {"营业收入[20251231]": 10000000000},
        "peers_raw": [{"name": "peer"}],
        "holders_raw": [{"name": "holder"}],
        "big_orders": [{"amount": 1}],
        "news": [{"title": "news"}],
        "product_raw": {"product": "main"},
        "chip_structure": {
            "holder_count_trend": {},
            "share_structure": {},
            "unlock_data": {},
            "concentration": {},
            "margin": {},
        },
        "blogger_opinions": [{"text": "view"}],
        "barrier_data": {
            "rd_raw": {},
            "customer_concentration": {},
            "supplier_concentration": {},
        },
        "research_reports": [{"title": "report"}],
        "warnings": [],
    }
    path = tmp_path / "stock.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    result = verify.verify_data(path, "stock")

    assert result["ok"] is False
    problems = " ".join(result["problems"])
    assert "筹码子项为空" in problems
    assert "壁垒子项为空" in problems


def test_data_gate_treats_quote_error_object_as_missing(tmp_path):
    path = tmp_path / "stock.json"
    path.write_text(
        '{"quote": {"error": "无行情数据"}, "warnings": []}',
        encoding="utf-8",
    )

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


def test_source_fact_gate_rejects_missing_industry_snapshot_metrics(tmp_path):
    path = tmp_path / "industry.html"
    path.write_text(
        make_html(INDUSTRY_SECTIONS, 5) + "<p>白酒 贵州茅台 600519</p>",
        encoding="utf-8",
    )
    data = {
        "sector": {"name": "白酒"},
        "stocks": [{"name": "贵州茅台", "ticker": "600519"}],
        "sector_snapshot": {"涨幅": 1.2},
    }
    result = verify.verify_report(path, "industry", data=data)

    assert result["ok"] is False
    assert any("板块指标" in problem for problem in result["problems"])


def test_source_fact_gate_rejects_industry_metric_mismatch(tmp_path):
    path = tmp_path / "industry.html"
    path.write_text(
        make_html(INDUSTRY_SECTIONS, 5)
        + "<p>白酒 贵州茅台 600519 5日涨幅 +1.00% 公开数据未覆盖</p>",
        encoding="utf-8",
    )
    data = {
        "sector": {"name": "白酒"},
        "stocks": [
            {
                "name": "贵州茅台",
                "ticker": "600519",
                "price": 1402.3,
                "change_pct": -2.55,
                "pe": 21.0,
                "pb": 7.2,
                "market_cap_yi": 17600.0,
                "revenue_yi": 1720.54,
                "net_profit_yi": 823.2,
                "gross_margin": 91.18,
                "net_margin": 50.53,
                "roe": 32.53,
                "revenue_yoy": -1.2,
                "profit_yoy": -4.53,
                "ytd_change": 5.5,
                "industry": "白酒Ⅲ",
            }
        ],
        "sector_snapshot": {
            "涨幅": 1.2,
            "5日涨幅": -2.1,
            "10日涨幅": 1.3,
            "20日涨幅": 3.4,
            "主力净流入": 120000000,
            "量比": 1.1,
        },
    }
    result = verify.verify_report(path, "industry", data=data)

    assert result["ok"] is False
    assert any("5日涨幅" in problem for problem in result["problems"])
    assert any("公开数据未覆盖" in problem for problem in result["problems"])


def test_data_gate_rejects_incomplete_industry_metrics(tmp_path):
    path = tmp_path / "industry.json"
    path.write_text(
        json.dumps(
            {
                "sector": {"name": "白酒"},
                "members": [{"name": "贵州茅台", "ticker": "600519"}],
                "stocks": [{"name": "贵州茅台", "ticker": "600519"}],
                "sector_snapshot": {"涨幅": 1.2, "5日涨幅": -2.1},
                "news": [{"title": "公告"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = verify.verify_data(path, "industry")

    assert result["ok"] is False
    assert any("板块指标缺失" in problem for problem in result["problems"])
    assert any("核心标的字段缺失" in problem for problem in result["problems"])


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
