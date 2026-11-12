from __future__ import annotations

import fetch_industry_data as industry


class Frame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient="records"):
        assert orient == "records"
        return self.rows

    def __len__(self):
        return len(self.rows)


class Response:
    def __init__(self, rows):
        self.df = Frame(rows)
        self.error = None


def test_normalize_keyword_and_stock_name():
    assert industry.normalize_keyword("白酒Ⅲ") == "白酒"
    assert industry.normalize_keyword("白酒行业") == "白酒"
    assert industry.normalize_stock_name("五 粮 液") == "五粮液"
    assert industry.normalize_stock_name("万  科Ａ") == "万科A"


def test_numeric_handles_units_and_placeholders():
    assert industry.numeric("1,234.5%") == 1234.5
    assert industry.numeric("暂无") is None
    assert industry.numeric(None) is None


def test_resolve_sector_prefers_industry_and_strips_suffix():
    class FakeThs:
        def ths_industry(self):
            return Response([{"代码": "URFI881273", "名称": "白酒Ⅲ"}])

        def ths_concept(self):
            return Response([{"代码": "URFI885525", "名称": "白酒概念"}])

    sector = industry.resolve_sector(FakeThs(), "白酒")
    assert sector["block_code"] == "URFI881273"
    assert sector["kind"] == "industry"


def test_resolve_sector_retries_empty_directory():
    class FlakyThs:
        def __init__(self):
            self.calls = 0

        def ths_industry(self):
            self.calls += 1
            if self.calls == 1:
                return Response([])
            return Response([{"代码": "URFI881273", "名称": "白酒Ⅲ"}])

        def ths_concept(self):
            return Response([])

    fake = FlakyThs()
    sector = industry.resolve_sector(fake, "白酒", retry_delay=0)

    assert fake.calls == 2
    assert sector["block_code"] == "URFI881273"
    assert sector["name"] == "白酒Ⅲ"


def test_resolve_sector_reports_directory_failure():
    class EmptyThs:
        def ths_industry(self):
            return Response([])

        def ths_concept(self):
            return Response([])

    try:
        industry.resolve_sector(EmptyThs(), "白酒", attempts=1)
    except industry.IndustryError as exc:
        assert "目录为空" in str(exc)
    else:
        raise AssertionError("expected IndustryError")


def test_collect_financials_maps_wencai_metrics():
    year = industry.PREV_YEAR

    class FakeThs:
        def wencai_nlp(self, query):
            assert "贵州茅台" in query
            return Response(
                [
                    {
                        "股票代码": "600519",
                        "股票简称": "贵州茅台",
                        "最新价": 1402.3,
                        "最新涨跌幅": -2.55,
                        "市盈率": 20.1,
                        "市净率": 7.2,
                        "总市值": 1760000000000,
                        "股息率": 2.1,
                        f"营业收入[{year}]": 180000000000,
                        f"归属于母公司所有者的净利润[{year}]": 90000000000,
                        f"销售毛利率[{year}]": 91.2,
                        f"销售净利率[{year}]": 50.1,
                        f"净资产收益率ROE[{year}]": 30.2,
                        f"营业收入同比增长率[{year}]": 10.1,
                        f"净利润同比增长率[{year}]": 11.2,
                        "年初至今涨跌幅": 5.5,
                        "所属同花顺行业": "食品饮料-白酒",
                        "主营业务": "茅台酒",
                    }
                ]
            )

    members = [{"thscode": "USHA600519", "ticker": "600519", "name": "贵州茅台"}]
    sector = {"name": "白酒"}
    stocks, warnings = industry.collect_financials(FakeThs(), sector, members)
    assert warnings == []
    assert len(stocks) == 1
    assert stocks[0]["pe"] == 20.1
    assert stocks[0]["market_cap_yi"] == 17600.0
    assert stocks[0]["revenue_yi"] == 1800.0
    assert stocks[0]["net_profit_yi"] == 900.0
    assert stocks[0]["roe"] == 30.2


def test_resolve_members_normalizes_vendor_stock_names():
    class FakeThs:
        def block_constituents(self, block_code):
            assert block_code == "URFI885517"
            return Response(
                [
                    {"代码": "USZA000002", "名称": "万  科Ａ"},
                    {"代码": "USHA600519", "名称": "贵州茅台"},
                ]
            )

    members = industry.resolve_members(
        FakeThs(),
        {"block_code": "URFI885517"},
        limit=10,
    )

    assert [(item["ticker"], item["name"]) for item in members] == [
        ("000002", "万科A"),
        ("600519", "贵州茅台"),
    ]
