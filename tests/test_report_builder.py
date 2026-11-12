from __future__ import annotations

import json

import report_builder
from reporting import build_industry_report, build_stock_report
from reporting.stock import _peer_metric
from verify_skill_report import verify_report


def stock_fixture() -> dict:
    return {
        "fetch_time": "2026-11-11 15:00",
        "stock_name": "贵州茅台",
        "stock_code": "600519",
        "thscode": "USHA600519",
        "quote": {
            "name": "贵州茅台",
            "price": 1402.3,
            "change_pct": -2.55,
            "market_cap": 1752989400000.0,
            "pe_ttm": 21.34,
            "main_net_inflow": -227229380.0,
            "turnover_rate": 0.32,
            "5d_change": -3.05,
        },
        "finance_raw": {
            "股票简称": "贵州茅台",
            "股票代码": "600519",
            "所属同花顺行业": "食品饮料-白酒",
            "公司中文名称": "贵州茅台酒股份有限公司",
            "最新价": 1402.3,
            "最新涨跌幅": -2.55,
            "营业收入[20231231]": 147600000000,
            "营业收入[20241231]": 170900000000,
            "营业收入[20251231]": 180000000000,
            "归属于母公司所有者的净利润[20231231]": 74730000000,
            "归属于母公司所有者的净利润[20241231]": 86230000000,
            "归属于母公司所有者的净利润[20251231]": 90000000000,
            "销售毛利率[20251231]": 91.2,
            "净资产收益率[20251231]": 30.2,
            "资产负债率[20251231]": 20.1,
        },
        "peers_raw": [
            {
                "股票简称": "五粮液",
                "股票代码": "000858",
                "市盈率": 20.1,
                "市净率": 4.2,
                "总市值": 500000000000,
                "销售毛利率": 75.0,
                "净资产收益率": 20.0,
            }
        ],
        "holders_raw": {"前十大流通股东名称": "股东甲||股东乙"},
        "big_orders": [{"总金额": 1000000, "成交方向": "1"}],
        "news": [{"Time": 1790006400, "Title": "公司公告"}],
        "product_raw": {"主营产品名称": "茅台酒||系列酒"},
        "chip_structure": {"concentration": {"前十大股东持股比例合计": 58.0}},
        "blogger_opinions": {"tgb": [{"text": "样本观点"}]},
        "barrier_data": {
            "rd_raw": {"研发投入占比": 5.0},
            "customer_concentration": {"value": "10.1", "period": "20251231"},
            "supplier_concentration": {"value": "35.43", "period": "20241231"},
        },
        "research_reports": {
            "reports": [
                {
                    "date": "2026-11-01",
                    "org": "示例机构",
                    "title": "盈利与估值跟踪",
                    "rating": "买入",
                    "target_price": 1600,
                    "forecast_pe": 18.6,
                }
            ]
        },
        "warnings": [],
    }


def industry_fixture() -> dict:
    return {
        "fetch_time": "2026-11-11 15:00",
        "keyword": "白酒",
        "sector": {"name": "白酒", "block_code": "URFI881273", "kind": "industry"},
        "members": [{"name": "贵州茅台", "ticker": "600519"}],
        "stocks": [
            {
                "name": "贵州茅台",
                "ticker": "600519",
                "price": 1402.3,
                "change_pct": -2.55,
                "pe": 21.34,
                "pb": 8.1,
                "market_cap_yi": 17529.89,
                "revenue_yi": 1800.0,
                "net_profit_yi": 900.0,
                "gross_margin": 91.2,
                "net_margin": 50.0,
                "roe": 30.2,
                "revenue_yoy": 10.1,
                "profit_yoy": 11.2,
                "ytd_change": 5.5,
                "industry": "食品饮料-白酒",
            }
        ],
        "sector_snapshot": {
            "涨幅": -1.2,
            "5日涨幅": -2.1,
            "10日涨幅": 1.3,
            "20日涨幅": 3.4,
            "主力净流入": 120000000,
            "量比": 1.1,
        },
        "news": [
            {
                "stock": "贵州茅台",
                "ticker": "600519",
                "title": "公司公告",
                "category": "公告",
                "time": 1790006400,
            }
        ],
        "warnings": [],
    }


def test_generated_stock_report_passes_source_fact_gate(tmp_path):
    data = stock_fixture()
    path = tmp_path / "stock.html"
    path.write_text(build_stock_report(data), encoding="utf-8")

    result = verify_report(path, "stock", data=data)

    assert result["ok"] is True, result["problems"]
    assert "核心结论" in result["sections"]
    assert result["tables"] >= 6
    assert "股东甲" in path.read_text(encoding="utf-8")
    assert "股东乙" in path.read_text(encoding="utf-8")
    html = path.read_text(encoding="utf-8")
    assert "前五大客户销售额占比" in html
    assert "10.10%" in html
    assert "35.43%" in html
    assert "预测PE" in html


def test_stock_report_does_not_emit_empty_research_table(tmp_path):
    data = stock_fixture()
    data["research_reports"] = {"reports": []}
    path = tmp_path / "stock.html"
    path.write_text(build_stock_report(data), encoding="utf-8")

    result = verify_report(path, "stock", data=data)

    assert result["ok"] is True, result["problems"]
    assert result["empty_tables"] == 0
    html = path.read_text(encoding="utf-8")
    assert "当前数据快照没有可列示记录" not in html
    assert "本次采集未返回可核验的机构研报样本" in html


def test_stock_report_accepts_alternate_company_field_names():
    data = stock_fixture()
    data["finance_raw"]["控股股东"] = "示例控股股东"
    data["finance_raw"]["上市日期"] = "2001-08-27"

    report = build_stock_report(data)

    assert "示例控股股东" in report
    assert "2001-08-27" in report


def test_peer_metric_prefers_dynamic_pe_and_weighted_roe():
    peer = {
        "最新市盈率ttm": 6.992637,
        "最新动态市盈率": 6.882214,
        "净资产收益率[20260930]": 8.7745,
        "加权净资产收益率[20260930]": 10.1175,
    }

    assert _peer_metric(peer, "市盈率") == 6.882214
    assert _peer_metric(peer, "净资产收益率") == 10.1175


def test_cloud_stock_report_labels_sources_and_big_order_scope():
    data = stock_fixture()
    data["runtime"] = {"source": "cloud"}
    data["big_orders_scope"] = "daily_aggregate"
    data["big_orders"] = [
        {"总金额": 1000000, "成交方向": "1"},
        {"总金额": 500000, "成交方向": "-1"},
    ]
    data["chip_structure"]["margin"] = {
        "{(}融资余额[20261111]{/}a股市值(不含限售股)[20261112]{)}": 0.0178,
        "融资余额[20261111]": 4049080894,
    }
    data["chip_structure"]["holder_count_trend"] = {
        "总户数[20231231]": 573282,
        "总户数[20261231]": 441142,
    }

    report = build_stock_report(data)

    assert "扶摇 REST" in report
    assert "官方问财 OpenAPI" in report
    assert "证券检索、新闻与公告" in report
    assert "实时行情、财务、估值、同业、股东、产品、筹码、壁垒与大单日汇总" in report
    assert "行情、股东、资金、公告与新闻" not in report
    assert "同花顺 thsdk" not in report
    assert "大单日汇总 2 行（非逐笔）" in report
    assert "4,049,080,894.00" in report
    assert "-23.05%" in report


def test_cloud_industry_report_uses_structured_source_rows():
    data = industry_fixture()
    data["sources"] = [
        "扶摇 REST：板块目录/成分/板块快照/新闻/个股行情补充",
        "官方问财 OpenAPI：实时行情主数据、行业财务、估值与增速（env:IWENCAI_API_KEY）",
    ]

    report = build_industry_report(data)

    assert "扶摇 REST" in report
    assert "官方问财 OpenAPI" in report
    assert "板块目录/成分/板块快照/新闻/个股行情补充" in report
    assert "env:IWENCAI_API_KEY" not in report
    assert "同花顺 thsdk" not in report


def test_industry_snapshot_formats_floating_point_noise():
    data = industry_fixture()
    data["sector_snapshot"]["10日涨幅"] = 7.6955999999999995
    data["sector_snapshot"]["20日涨幅"] = 6.1624859999999995
    data["sector_snapshot"]["主力净流入"] = -130133560.0

    report = build_industry_report(data)

    assert "+7.70%" in report
    assert "+6.16%" in report
    assert "-1.30 亿" in report
    assert "7.6955999999999995" not in report


def test_generated_industry_report_passes_source_fact_gate(tmp_path):
    data = industry_fixture()
    path = tmp_path / "industry.html"
    path.write_text(build_industry_report(data), encoding="utf-8")

    result = verify_report(path, "industry", data=data)

    assert result["ok"] is True, result["problems"]
    assert "行业概览" in result["sections"]
    assert result["tables"] >= 5
    html = path.read_text(encoding="utf-8")
    assert "风险提示：" in html
    assert "风险观察" in html
    assert html.count("观察方式") == 1


def test_report_builder_cli_writes_verified_stock_report(tmp_path, capsys):
    data_path = tmp_path / "stock.json"
    data_path.write_text(json.dumps(stock_fixture(), ensure_ascii=False), encoding="utf-8")
    output_path = tmp_path / "report.html"

    exit_code = report_builder.main(
        ["--type", "stock", "--data-json", str(data_path), "--output", str(output_path)]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0, payload
    assert payload["ok"] is True
    assert output_path.is_file()


def test_report_builder_rejects_incomplete_source_data(tmp_path, capsys):
    data_path = tmp_path / "stock.json"
    data_path.write_text(
        json.dumps({"stock_code": "600519", "warnings": []}, ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = report_builder.main(["--type", "stock", "--data-json", str(data_path)])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["data_check"]["missing_or_empty"]
