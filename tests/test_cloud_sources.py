from __future__ import annotations

import pytest

import cloud_sources
import fetch_industry_data
import fetch_stock_data
from cloud_sources import CloudSourceError, CloudStockAdapter
from reporting.stock import _holder_count_change


def payload(*rows):
    return {"datas": list(rows)}


def thsdk_unavailable(*args, **kwargs):
    raise RuntimeError("thsdk unavailable")


class FakeWencai:
    def __init__(self, responder):
        self.responder = responder
        self.calls = []

    def query(self, skill_id, query, page=1, limit=10):
        self.calls.append((skill_id, query, page, limit))
        result = self.responder(skill_id, query, limit)
        if isinstance(result, Exception):
            raise result
        return result


class FakeMarket:
    def __init__(self):
        self.news_calls = []

    def search(self, keyword, limit=20):
        return {
            "items": [
                {
                    "ticker": "000001",
                    "name": "平安银行",
                    "thscode": "USZA000001",
                    "exchange": "SZ",
                    "asset_type": "a-share",
                }
            ]
        }

    def sector(self, keyword):
        return {
            "sector": {"name": "白酒Ⅲ", "thscode": "URFI881273"},
            "members": [
                {"thscode": "USHA600519", "ticker": "600519", "name": "贵州茅台"},
                {"thscode": "USZA000568", "ticker": "000568", "name": "泸州老窖"},
            ],
            "snapshot": {
                "涨幅": 1.2,
                "最新价": 1000.0,
                "raw": {"thscode": "881273.TI", "nested": {"x": 1}},
            },
        }

    def realtime(self, codes):
        data = {}
        for code in codes:
            if code == "600519":
                data["USHA600519"] = {
                    "ticker": "600519",
                    "last_price": 1402.3,
                    "price_change_ratio_pct": -2.55,
                }
            elif code == "000568":
                data["USZA000568"] = {
                    "ticker": "000568",
                    "last_price": 76.99,
                    "price_change_ratio_pct": -3.75,
                }
        return {"data": data}

    def news(self, code, count=20):
        self.news_calls.append((code, count))
        return {
            "items": [
                {
                    "title": f"{code}公告",
                    "publish_time_ms": 1790006400000,
                    "source": "测试源",
                    "summary": "摘要",
                }
            ]
        }


def make_adapter(wencai, market=None, name="平安银行"):
    adapter = object.__new__(CloudStockAdapter)
    adapter.wencai = wencai
    adapter.wencai_source = "test"
    adapter.wencai_error = ""
    adapter.market = market
    adapter.market_error = ""
    adapter._names = {}
    adapter._cache = {}
    adapter._news_cache = None
    adapter.stock_name = name
    adapter._stock_code = ""
    adapter.holders_source = ""
    adapter.holders_error = ""
    adapter.peers_source = ""
    adapter.peers_error = ""
    adapter.peers_expected_count = 0
    adapter.peers_scope = ""
    adapter.finance_source = ""
    adapter.finance_error = ""
    adapter.quote_source = ""
    adapter.quote_fallback_error = ""
    adapter.quote_fill_sources = []
    adapter.chip_sources = []
    adapter.barrier_sources = []
    adapter.product_source = ""
    adapter.product_error = ""
    adapter._ths_client = None
    adapter._ths_connect_error = "unit-test-disable-thsdk"
    adapter._ths_connect_retry_at = float("inf")
    adapter._last_ths_query_at = 0.0
    adapter._f10_payload_cache = None
    adapter._f10_payload_error = ""
    return adapter


def test_quote_maps_dated_columns_and_previous_close():
    def responder(skill, query, limit):
        if "开盘价" in query:
            return payload(
                {
                    "股票简称": "平安银行",
                    "开盘价[20261112]": 11.69,
                    "最高价[20261112]": 11.78,
                    "最低价[20261112]": 11.66,
                    "收盘价[20261111]": 11.71,
                    "涨停价[20261112]": 12.88,
                    "跌停价[20261112]": 10.54,
                    "主力资金流向": 12133258,
                    "涨跌幅[20261106-20261112]": 0.859107,
                }
            )
        return payload(
            {
                "股票简称": "平安银行",
                "最新价": 11.74,
                "最新涨跌幅": 0.256191,
                "成交量[20261112]": 41846748,
                "成交额[20261112]": 490031198.42,
                "总市值[20261112]": 227825479644.52,
                "流通市值[20261112]": 227822740000.0,
                "最新市盈率ttm": 5.235313,
                "换手率[20261112]": 0.216,
                "振幅[20261112]": 1.024765,
            }
        )

    adapter = make_adapter(FakeWencai(responder), FakeMarket())
    row = adapter.market_data_cn("USZA000001", "汇总").df.iloc[0]

    assert row["价格"] == 11.74
    assert row["昨收价"] == 11.71
    assert row["涨跌"] == pytest.approx(0.03)
    assert row["开盘涨幅"] == pytest.approx((11.69 / 11.71 - 1) * 100)
    assert row["5日涨幅"] == 0.859107
    assert row["成交量"] == 41846748
    assert row["市盈率TTM"] == 5.235313
    assert row["名称"] == "平安银行"


def test_quote_falls_back_to_eastmoney_when_wencai_is_empty(monkeypatch):
    monkeypatch.setattr(
        CloudStockAdapter,
        "_thsdk_quote_fallback",
        lambda self, code: {},
    )
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_stock_quote",
        lambda code: {
            "f2": 1410.27,
            "f3": 0.57,
            "f9": 20.51,
            "f12": code,
            "f14": "贵州茅台",
            "f20": 1762952579442.0,
            "f21": 1762952579442.0,
            "f23": 6.5,
            "f25": 4.53,
        },
    )
    monkeypatch.setattr(
        cloud_sources,
        "_tencent_quote_snapshot",
        lambda codes: {
            "600519": {
                "name": "贵州茅台",
                "pe": 21.46,
                "5d_change": -2.87,
            }
        },
    )
    adapter = make_adapter(
        FakeWencai(lambda skill, query, limit: payload()),
        FakeMarket(),
        name="贵州茅台",
    )

    row = adapter.market_data_cn("USHA600519", "汇总").df.iloc[0]

    assert row["价格"] == 1410.27
    assert row["涨幅"] == 0.57
    assert row["市盈率TTM"] == 21.46
    assert row["总市值"] == 1762952579442.0
    assert row["名称"] == "贵州茅台"
    assert adapter.quote_source == "eastmoney"
    assert adapter.quote_fill_sources == ["eastmoney", "tencent"]


def test_thsdk_quote_fallback_returns_complete_vendor_fields(monkeypatch):
    class FakeThsClient:
        def realtime(self, codes):
            return {
                "data": {
                    "USHA600519": {
                        "name": "贵州茅台",
                        "raw": {
                            "价格": 1410.27,
                            "昨收价": 1402.3,
                            "成交量": 3237294,
                            "总金额": 4536814500,
                            "换手率": 0.259,
                            "振幅": 1.6323,
                            "市盈率TTM": 21.4574,
                            "5日涨幅": -2.874,
                            "总市值": 1762952600000,
                            "流通市值": 1762952600000,
                            "主力净流入": -29302050,
                            "主力净量": -0.0017,
                            "最高价": 1411,
                            "最低价": 1388.11,
                            "涨停价": 1542.53,
                            "跌停价": 1262.07,
                            "开盘涨幅": -0.5113,
                            "名称": "贵州茅台",
                        },
                    }
                }
            }

    adapter = make_adapter(
        FakeWencai(lambda skill, query, limit: payload()),
        FakeMarket(),
        name="贵州茅台",
    )
    monkeypatch.setattr(adapter, "_ths_connection", lambda: FakeThsClient())

    quote = adapter._thsdk_quote_fallback("USHA600519")

    assert quote["价格"] == pytest.approx(1410.27)
    assert quote["成交量"] == pytest.approx(3237294)
    assert quote["市盈率TTM"] == pytest.approx(21.4574)
    assert quote["主力净流入"] == pytest.approx(-29302050)
    assert quote["5日涨幅"] == pytest.approx(-2.874)
    assert quote["开盘价"] == pytest.approx(
        1402.3 * (1 - 0.5113 / 100)
    )


def test_holder_trend_falls_back_to_eastmoney_f10(monkeypatch):
    adapter = make_adapter(
        FakeWencai(lambda skill, query, limit: payload()),
        FakeMarket(),
        name="贵州茅台",
    )
    monkeypatch.setattr(
        CloudStockAdapter,
        "_eastmoney_holder_trend_frame",
        lambda self: cloud_sources.SimpleNamespace(
            df=cloud_sources.pd.DataFrame(
                [
                    {
                        "股东户数(报告期)[20250630]": 220658,
                        "股东户数(报告期)[20251231]": 255892,
                    }
                ]
            ),
            error="",
        ),
    )

    row = adapter.wencai_nlp(
        "贵州茅台 股东户数[20250630] 股东户数[20251231]"
    ).df.iloc[0]

    assert row["股东户数(报告期)[20251231]"] == 255892
    assert adapter.chip_sources == ["eastmoney"]


def test_share_structure_falls_back_to_tencent(monkeypatch):
    adapter = make_adapter(
        FakeWencai(lambda skill, query, limit: payload()),
        FakeMarket(),
        name="贵州茅台",
    )
    monkeypatch.setattr(
        CloudStockAdapter,
        "_eastmoney_share_structure_frame",
        lambda self: cloud_sources.SimpleNamespace(
            df=cloud_sources.pd.DataFrame(
                [
                    {
                        "总股本[20261112]": 1250081601,
                        "流通a股[20261112]": 1250081601,
                        "限售a股[20261112]": 0,
                    }
                ]
            ),
            error="",
            source="tencent",
        ),
    )

    row = adapter.wencai_nlp(
        "贵州茅台 总股本 流通a股 限售a股"
    ).df.iloc[0]

    assert row["总股本[20261112]"] == 1250081601
    assert adapter.chip_sources == ["tencent"]


def test_share_structure_falls_back_to_f10_ltgf_fields(monkeypatch):
    adapter = make_adapter(
        FakeWencai(lambda skill, query, limit: payload()),
        FakeMarket(),
        name="中芯国际",
    )
    adapter._stock_code = "688981"
    monkeypatch.setattr(
        cloud_sources,
        "_tencent_quote_snapshot",
        lambda codes: {},
    )
    monkeypatch.setattr(
        CloudStockAdapter,
        "_f10_payload",
        lambda self: (
            {
                "ltgf": [
                    {
                        "END_DATE": "2026-09-30 00:00:00",
                        "HOLD_NUM_COUNT": 6382467539,
                        "LIMITED_SHARES": 547182073,
                        "OTHER_UNLIMITED_SHARES": 1632695979,
                    }
                ]
            },
            "",
        ),
    )

    result = adapter._eastmoney_share_structure_frame()

    row = result.df.iloc[0]
    assert row["总股本[20260930]"] == 8562345591
    assert row["流通a股[20260930]"] == 8015163518
    assert row["限售a股[20260930]"] == 547182073
    assert result.source == "eastmoney"


def test_ths_connection_retries_after_transient_failure(monkeypatch):
    adapter = make_adapter(
        FakeWencai(lambda skill, query, limit: payload()),
        FakeMarket(),
    )
    adapter._ths_connect_error = ""
    adapter._ths_connect_retry_at = 0.0
    attempts = []

    class FakeThsClient:
        def __enter__(self):
            attempts.append("enter")
            if len(attempts) == 1:
                raise RuntimeError("temporary failure")
            return self

        def __exit__(self, *args):
            return None

    monkeypatch.setattr(cloud_sources.mq, "ThsClient", FakeThsClient)

    assert adapter._ths_connection() is None
    assert "temporary failure" in adapter._ths_connect_error
    assert adapter._ths_connection() is None
    assert len(attempts) == 1

    adapter._ths_connect_retry_at = 0.0
    assert adapter._ths_connection() is not None
    assert len(attempts) == 2
    assert adapter._ths_connect_error == ""


def test_margin_and_patents_fall_back_to_thsdk(monkeypatch):
    adapter = make_adapter(
        FakeWencai(lambda skill, query, limit: payload()),
        FakeMarket(),
        name="贵州茅台",
    )

    def fake_ths(self, query, limit=20):
        if "融资余额" in query:
            return cloud_sources.SimpleNamespace(
                df=cloud_sources.pd.DataFrame(
                    [{"融资余额[20261111]": 15093509194}]
                ),
                error="",
            )
        return cloud_sources.SimpleNamespace(
            df=cloud_sources.pd.DataFrame(
                [
                    {
                        "专利数量[20261111]": 272,
                        "发明专利[20261111]": 70,
                        "研发投入占营业收入的比重[20251231]": 0.48,
                    }
                ]
            ),
            error="",
        )

    monkeypatch.setattr(CloudStockAdapter, "_ths_wencai_frame", fake_ths)
    monkeypatch.setattr(CloudStockAdapter, "_eastmoney_rd_fallback", lambda self: {})

    margin = adapter.wencai_nlp("贵州茅台 融资余额 融资余额占流通市值比")
    patents = adapter.wencai_nlp(
        "贵州茅台 研发费用 专利数量 发明专利数量"
    )

    assert margin.df.iloc[0]["融资余额[20261111]"] == 15093509194
    assert patents.df.iloc[0]["专利数量合计[20261111]"] == 272
    assert patents.df.iloc[0]["研发投入占营业收入的比重[20251231]"] == 0.48
    assert adapter.chip_sources == ["thsdk"]
    assert adapter.barrier_sources == ["thsdk"]


def test_margin_falls_back_to_eastmoney_data_center(monkeypatch):
    adapter = make_adapter(
        FakeWencai(lambda skill, query, limit: payload()),
        FakeMarket(),
        name="贵州茅台",
    )
    adapter._stock_code = "600519"

    def fake_json(url, *, referer="https://emweb.securities.eastmoney.com/"):
        assert "RPTA_WEB_RZRQ_GGMX" in url
        assert "600519" in url
        return {
            "result": {
                "data": [
                    {
                        "DATE": "2026-11-11 00:00:00",
                        "RZYE": 15093509194,
                        "RZMRE": 303809512,
                        "RZCHE": 373412813,
                        "RZJME": -69603301,
                        "RQYE": 23149980,
                        "RZRQYE": 15116659174,
                        "RZYEZB": 0.82,
                    }
                ]
            }
        }

    monkeypatch.setattr(cloud_sources, "_fetch_eastmoney_json", fake_json)

    row = adapter.wencai_nlp(
        "贵州茅台 融资余额 融资余额占流通市值比"
    ).df.iloc[0]

    assert row["融资余额[20261111]"] == 15093509194
    assert row["融资净买入[20261111]"] == -69603301
    assert adapter.chip_sources == ["eastmoney"]


def test_product_mix_falls_back_to_eastmoney_f10(monkeypatch):
    adapter = make_adapter(
        FakeWencai(lambda skill, query, limit: payload()),
        FakeMarket(),
        name="贵州茅台",
    )
    adapter._stock_code = "600519"

    def fake_json(url, *, referer="https://emweb.securities.eastmoney.com/"):
        assert "BusinessAnalysis" in url
        return {
            "zygcfx": [
                {
                    "REPORT_DATE": "2025-12-31 00:00:00",
                    "MAINOP_TYPE": "2",
                    "ITEM_NAME": "茅台酒",
                    "MAIN_BUSINESS_INCOME": 145000000000,
                    "MBI_RATIO": 0.88,
                },
                {
                    "REPORT_DATE": "2025-12-31 00:00:00",
                    "MAINOP_TYPE": "2",
                    "ITEM_NAME": "其他系列酒",
                    "MAIN_BUSINESS_INCOME": 19800000000,
                    "MBI_RATIO": 0.12,
                },
                {
                    "REPORT_DATE": "2025-12-31 00:00:00",
                    "MAINOP_TYPE": "3",
                    "ITEM_NAME": "境外",
                    "MAIN_BUSINESS_INCOME": 5100000000,
                    "MBI_RATIO": 0.031,
                },
            ],
            "zyfw": [{"BUSINESS_SCOPE": "茅台酒及系列酒生产与销售"}],
        }

    monkeypatch.setattr(cloud_sources, "_fetch_eastmoney_json", fake_json)

    row = adapter.wencai_nlp(
        "贵州茅台 主营业务构成 产品类型"
    ).df.iloc[0]

    assert row["主营产品名称"] == "茅台酒||其他系列酒"
    assert "茅台酒" in row["主营业务构成"]
    assert "境外" in row["经营区域构成"]
    assert row["主营构成报告期"] == "20251231"
    assert adapter.product_source == "eastmoney"


def test_patent_query_skips_thsdk_when_wencai_is_complete(monkeypatch):
    adapter = make_adapter(
        FakeWencai(
            lambda skill, query, limit: payload(
                {
                    "专利数量[20261111]": 272,
                    "发明专利[20261111]": 70,
                    "研发投入占营业收入的比重[20251231]": 0.48,
                }
            )
        ),
        FakeMarket(),
        name="贵州茅台",
    )

    def fail_ths(self, query, limit=20):
        raise AssertionError("thsdk should not be called")

    def fail_rd(self):
        raise AssertionError("eastmoney R&D should not be called")

    monkeypatch.setattr(CloudStockAdapter, "_ths_wencai_frame", fail_ths)
    monkeypatch.setattr(CloudStockAdapter, "_eastmoney_rd_fallback", fail_rd)

    row = adapter.wencai_nlp(
        "贵州茅台 研发费用 专利数量 发明专利数量"
    ).df.iloc[0]

    assert row["专利数量合计[20261111]"] == 272
    assert adapter.barrier_sources == ["wencai"]


def test_finance_frame_aliases_roe_products_and_basic_info():
    def responder(skill, query, limit):
        if "加权净资产收益率" in query:
            return payload(
                {
                    "加权净资产收益率[20231231]": 11.38,
                    "加权净资产收益率[20241231]": 10.08,
                    "加权净资产收益率[20251231]": 9.15,
                    "资产负债率[20251231]": 90.6985,
                }
            )
        if "归属于母公司所有者的净利润" in query:
            return payload(
                {
                    "营业收入[20231231]": 164699000000.0,
                    "营业收入[20241231]": 146695000000.0,
                    "营业收入[20251231]": 131442000000.0,
                    "归母净利润[20251231]": 42633000000.0,
                }
            )
        if "销售毛利率" in query:
            return payload()
        if "注册地址" in query:
            return payload(
                {
                    "中文名称": "平安银行股份有限公司",
                    "注册地址": "广东省深圳市罗湖区深南东路5047号",
                    "实际控制人": "无实际控制人",
                    "股东名称": "中国平安保险(集团)股份有限公司",
                    "所属同花顺行业": ["银行", "银行", "股份制银行"],
                    "上市日期": "19910403",
                    "主营产品": ["存款业务", "贷款业务"],
                    "经营范围": "办理人民币存、贷、结算、汇兑业务",
                }
            )
        raise AssertionError(query)

    adapter = make_adapter(FakeWencai(responder), FakeMarket())
    result = adapter.wencai_nlp("平安银行，公司全称，主营业务")
    row = result.df.iloc[0]

    assert row["净资产收益率ROE[20251231]"] == 9.15
    assert row["归属于母公司所有者的净利润[20251231]"] == 42633000000.0
    assert row["所属同花顺行业"] == "银行-银行-股份制银行"
    assert row["主营产品名称"] == "存款业务||贷款业务"
    assert row["公司中文名称"] == "平安银行股份有限公司"
    assert row["控股股东名称"] == "中国平安保险(集团)股份有限公司"
    assert row["新股上市日期"] == "19910403"
    assert row["主营业务"] == "办理人民币存、贷、结算、汇兑业务"


def test_holder_query_routes_to_ranked_top_ten_names():
    def responder(skill, query, limit):
        assert "前十大流通股东名称" in query
        return payload(
            {
                "排名": 2.0,
                "名称": "股东乙",
                "机构持股占流通股比例[20260930]": 70.03,
                "总户数[20261112]": 406492,
            },
            {
                "排名": 1.0,
                "名称": "股东甲",
                "机构持股占流通股比例[20260930]": 70.03,
                "总户数[20261112]": 406492,
            },
        )

    adapter = make_adapter(FakeWencai(responder), FakeMarket())
    result = adapter.wencai_nlp(
        "平安银行，十大流通股东，北向资金持股比例，股东户数变化，机构持股比例"
    )
    row = result.df.iloc[0]

    assert row["前十大流通股东名称"] == "股东甲||股东乙"
    assert row["机构持股占流通股比例[20260930]"] == 70.03


def test_holder_query_falls_back_to_eastmoney_disclosure(monkeypatch):
    def responder(skill, query, limit):
        assert "前十大流通股东名称" in query
        return payload()

    adapter = make_adapter(FakeWencai(responder), FakeMarket())
    adapter._stock_code = "600519"

    monkeypatch.setattr(
        cloud_sources,
        "_fetch_eastmoney_holder_payload",
        lambda code: {
            "sdltgd": [
                {
                    "HOLDER_RANK": index,
                    "HOLDER_NAME": f"股东{index}",
                    "END_DATE": "2026-09-30 00:00:00",
                }
                for index in range(10, 0, -1)
            ],
            "jgcc": [
                {
                    "REPORT_DATE": "2026-09-30 00:00:00",
                    "ORG_TYPE": "00",
                    "TOTAL_SHARES_RATIO": 70.87,
                }
            ],
            "gdrs": [
                {
                    "END_DATE": "2026-09-30 00:00:00",
                    "HOLDER_TOTAL_NUM": 278364,
                    "TOTAL_NUM_RATIO": -6.09,
                }
            ],
        },
    )

    result = adapter.wencai_nlp(
        "贵州茅台，十大流通股东，北向资金持股比例，股东户数变化，机构持股比例"
    )
    row = result.df.iloc[0]

    assert row["前十大流通股东名称"] == "||".join(
        f"股东{index}" for index in range(1, 11)
    )
    assert row["机构持股占流通股比例[20260930]"] == pytest.approx(70.87)
    assert adapter.holders_source == "eastmoney"
    assert adapter.holders_error == ""


def test_peer_query_falls_back_to_eastmoney_f10_and_quotes(monkeypatch):
    def responder(skill, query, limit):
        assert "市盈率" in query and "市净率" in query
        return payload()

    adapter = make_adapter(FakeWencai(responder), None)
    adapter._stock_code = "600519"
    monkeypatch.setattr(cloud_sources, "_tencent_quote_snapshot", lambda codes: {})

    def fake_json(url, *, referer="https://emweb.securities.eastmoney.com/"):
        if "IndustryAnalysis" in url:
            return {
                "gzbj": [
                    {
                        "CORRE_SECURITY_CODE": "600519",
                        "CORRE_SECURITY_NAME": "贵州茅台",
                        "PE_TTM": 21.34,
                        "PB_MRQ": 7.17,
                    },
                    {
                        "CORRE_SECURITY_CODE": "000858",
                        "CORRE_SECURITY_NAME": "五粮液",
                        "PE_TTM": 21.7,
                        "PB_MRQ": 2.37,
                    },
                    {"CORRE_SECURITY_CODE": "行业平均"},
                ],
                "dbfxbj": [
                    {"CORRE_SECURITY_CODE": "600519", "ROE_AVG": 32.53},
                    {"CORRE_SECURITY_CODE": "000858", "ROE_AVG": 8.09},
                ],
                "gsgm": [
                    {
                        "CORRE_SECURITY_CODE": "600519",
                        "CORRE_SECURITY_NAME": "贵州茅台",
                        "TOTAL_CAP": 1752989429082.3,
                        "TOTAL_OPERATEINCOME": 133283652508.95,
                        "NETPROFIT": 66717143218.04,
                    }
                ],
                "gsgm_zsz": [
                    {
                        "CORRE_SECURITY_CODE": "000858",
                        "CORRE_SECURITY_NAME": "五粮液",
                        "TOTAL_CAP": 280989603481.95,
                        "TOTAL_OPERATEINCOME": 32858473964.34,
                        "NETPROFIT": 9969286777.24,
                    }
                ],
            }
        if "ulist.np" in url:
            raise RuntimeError("simulated ulist disconnect")
        if "stock/get" in url:
            if "secid=1.600519" in url:
                return {
                    "data": {
                        "f43": 140230,
                        "f57": "600519",
                        "f58": "贵州茅台",
                        "f116": 1752989400000.0,
                        "f117": 1752989400000.0,
                        "f162": 2134,
                        "f167": 717,
                        "f170": -255,
                    }
                }
            if "secid=0.000858" in url:
                return {
                    "data": {
                        "f43": 7239,
                        "f57": "000858",
                        "f58": "五 粮 液",
                        "f116": 280989603481.95,
                        "f117": 280989603481.95,
                        "f162": 2170,
                        "f167": 237,
                        "f170": -251,
                    }
                }
            raise AssertionError(url)
        if "NewFinanceAnalysis" in url:
            annual = {
                "600519": {
                    "REPORT_DATE": "2025-12-31 00:00:00",
                    "REPORT_YEAR": "2025",
                    "REPORT_TYPE": "年报",
                    "TOTALOPERATEREVE": 172054171890.91,
                    "PARENTNETPROFIT": 82320067101.68,
                    "XSMLL": 91.1795516835,
                    "XSJLL": 50.5278865155,
                    "ROEJQ": 32.53,
                    "TOTALOPERATEREVETZ": -1.200097176919,
                    "PARENTNETPROFITTZ": -4.532254817158,
                },
                "000858": {
                    "REPORT_DATE": "2025-12-31 00:00:00",
                    "REPORT_YEAR": "2025",
                    "REPORT_TYPE": "年报",
                    "TOTALOPERATEREVE": 40528509770.23,
                    "PARENTNETPROFIT": 8954257202.51,
                    "XSMLL": 77.5418415205,
                    "XSJLL": 22.9890347252,
                    "ROEJQ": 6.89,
                    "TOTALOPERATEREVETZ": -54.551804064166,
                    "PARENTNETPROFITTZ": -71.888962986,
                },
            }
            code = "600519" if "SH600519" in url else "000858"
            return {"data": [annual[code]]}
        raise AssertionError(url)

    monkeypatch.setattr(cloud_sources, "_fetch_eastmoney_json", fake_json)

    result = adapter.wencai_nlp(
        "白酒行业，市盈率，总市值，市净率，净资产收益率ROE，"
        "2025年营业收入，2025年销售毛利率，2025年销售净利率，股息率"
    )
    rows = result.df.to_dict("records")

    assert [row["股票代码"] for row in rows] == ["600519.SH", "000858.SZ"]
    assert rows[0]["股票简称"] == "贵州茅台"
    assert rows[1]["股票简称"] == "五粮液"
    assert rows[1]["市盈率(pe)"] == pytest.approx(21.7)
    assert rows[1]["销售毛利率"] == pytest.approx(77.5418415205)
    assert rows[1]["销售净利率"] == pytest.approx(22.9890347252)
    assert rows[1]["净资产收益率"] == pytest.approx(6.89)
    assert rows[1]["营业收入同比"] == pytest.approx(-54.551804064166)
    assert adapter.peers_source == "eastmoney"
    assert adapter.peers_error == ""


def test_peer_fallback_uses_full_eastmoney_industry_board(monkeypatch):
    adapter = make_adapter(
        FakeWencai(lambda skill, query, limit: payload()),
        FakeMarket(),
        name="贵州茅台",
    )
    adapter._stock_code = "600519"
    members = [
        {"f12": "600519", "f14": "贵州茅台", "f100": "白酒Ⅲ"},
        {"f12": "000858", "f14": "五粮液", "f100": "白酒Ⅲ"},
        {"f12": "000568", "f14": "泸州老窖", "f100": "白酒Ⅲ"},
    ]
    quotes = {
        "600519": {
            "f2": 1410.27,
            "f3": 0.57,
            "f9": 20.51,
            "f20": 1762952579442,
            "f21": 1762952579442,
            "f23": 6.5,
        },
        "000858": {
            "f2": 72.63,
            "f3": 0.33,
            "f9": 21.77,
            "f20": 281921189403,
            "f21": 281914317588,
            "f23": 2.38,
        },
        "000568": {
            "f2": 76.74,
            "f3": -0.32,
            "f9": 14.94,
            "f20": 112953718271,
            "f21": 112896897979,
            "f23": 2.4,
        },
    }
    annual = {
        "600519": {
            "TOTALOPERATEREVE": 168838102514.79,
            "PARENTNETPROFIT": 82320067101.68,
            "XSMLL": 91.18,
            "XSJLL": 48.76,
            "ROEJQ": 32.53,
            "TOTALOPERATEREVETZ": -1.21,
            "PARENTNETPROFITTZ": -4.53,
        },
        "000858": {
            "TOTALOPERATEREVE": 40528509770.23,
            "PARENTNETPROFIT": 8954257202.51,
            "XSMLL": 77.54,
            "XSJLL": 22.09,
            "ROEJQ": 6.89,
            "TOTALOPERATEREVETZ": -54.55,
            "PARENTNETPROFITTZ": -71.89,
        },
        "000568": {
            "TOTALOPERATEREVE": 16883810251.0,
            "PARENTNETPROFIT": 4000000000.0,
            "XSMLL": 86.62,
            "XSJLL": 23.69,
            "ROEJQ": 22.66,
            "TOTALOPERATEREVETZ": -17.52,
            "PARENTNETPROFITTZ": -19.61,
        },
    }
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_industry_name",
        lambda code: "白酒",
    )
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_industry_members",
        lambda name: members,
    )
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_quote_snapshot",
        lambda codes: quotes,
    )
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_annual_financials",
        lambda code, year: annual[code],
    )
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_dividend_yield",
        lambda code, price: 2.5,
    )
    monkeypatch.setattr(cloud_sources, "_tencent_quote_snapshot", lambda codes: {})
    monkeypatch.setattr(
        cloud_sources,
        "_fetch_eastmoney_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("IndustryAnalysis should not be needed")
        ),
    )

    result = adapter._peers_frame("白酒行业 市盈率 市净率")
    rows = result.df.to_dict("records")

    assert len(rows) == 3
    assert adapter.peers_source == "eastmoney"
    assert adapter.peers_expected_count == 3
    assert adapter.peers_scope == "白酒"
    assert {row["股票简称"] for row in rows} == {"贵州茅台", "五粮液", "泸州老窖"}
    assert rows[0]["所属行业"] == "白酒"
    assert rows[0]["股息率"] == pytest.approx(2.5)
    assert rows[0]["营业收入"] == pytest.approx(168838102514.79)
    assert rows[0]["营业收入同比"] == pytest.approx(-1.21)


def test_peer_fallback_uses_fuyao_board_when_eastmoney_push2_is_down(monkeypatch):
    market = FakeMarket()

    def sector(keyword):
        assert keyword == "白酒"
        return {
            "sector": {"name": "白酒Ⅲ", "thscode": "881273.TI"},
            "members": [
                {"thscode": "SH600519", "ticker": "600519", "name": "贵州茅台"},
                {"thscode": "SZ000858", "ticker": "000858", "name": "五粮液"},
            ],
        }

    monkeypatch.setattr(market, "sector", sector)
    adapter = make_adapter(
        FakeWencai(lambda skill, query, limit: payload()),
        market,
        name="贵州茅台",
    )
    adapter._stock_code = "600519"
    annual = {
        "600519": {
            "TOTALOPERATEREVE": 168838102514.79,
            "PARENTNETPROFIT": 82320067101.68,
            "XSMLL": 91.18,
            "XSJLL": 48.76,
            "ROEJQ": 32.53,
            "TOTALOPERATEREVETZ": -1.21,
            "PARENTNETPROFITTZ": -4.53,
        },
        "000858": {
            "TOTALOPERATEREVE": 40528509770.23,
            "PARENTNETPROFIT": 8954257202.51,
            "XSMLL": 77.54,
            "XSJLL": 22.09,
            "ROEJQ": 6.89,
            "TOTALOPERATEREVETZ": -54.55,
            "PARENTNETPROFITTZ": -71.89,
        },
    }
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_industry_name",
        lambda code: "白酒",
    )
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_industry_members",
        lambda name: [],
    )
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_quote_snapshot",
        lambda codes: (_ for _ in ()).throw(RuntimeError("push2 unavailable")),
    )
    monkeypatch.setattr(
        cloud_sources,
        "_tencent_quote_snapshot",
        lambda codes: {
            "600519": {
                "price": 1410.27,
                "pe": 20.51,
                "pb": 6.5,
                "market_cap": 1762952579442,
                "circulating_cap": 1762952579442,
                "change_pct": 0.57,
            },
            "000858": {
                "price": 72.63,
                "pe": 21.77,
                "pb": 2.38,
                "market_cap": 281921189403,
                "circulating_cap": 281914317588,
                "change_pct": 0.33,
            },
        },
    )
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_annual_financials",
        lambda code, year: annual[code],
    )
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_dividend_yield",
        lambda code, price: 2.5,
    )
    monkeypatch.setattr(
        cloud_sources,
        "_fetch_eastmoney_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("push2 unavailable")
        ),
    )

    result = adapter._peers_frame(
        "白酒行业，市盈率，总市值，市净率，净资产收益率ROE，股息率"
    )
    rows = result.df.to_dict("records")

    assert len(rows) == 2
    assert adapter.peers_source == "fuyao"
    assert adapter.peers_error == ""
    assert adapter.peers_expected_count == 2
    assert adapter.peers_scope == "白酒"
    assert {row["股票简称"] for row in rows} == {"贵州茅台", "五粮液"}
    assert all(row["所属行业"] == "白酒" for row in rows)


def test_annual_financials_prefers_operating_income_over_total_income(monkeypatch):
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_annual_reports",
        lambda code: {
            2025: {
                "REPORT_DATE": "2025-12-31 00:00:00",
                "TOTALOPERATEREVE": 172054171890.91,
                "TOTALOPERATEREVETZ": -1.200097,
                "PARENTNETPROFIT": 82320067101.68,
                "PARENTNETPROFITTZ": -4.532255,
                "ROEJQ": 32.53,
            }
        },
    )
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_income_reports",
        lambda code: {
            2025: {
                "OPERATE_INCOME": 168838102514.79,
                "OPERATE_INCOME_YOY": -1.206004,
                "PARENT_NETPROFIT": 82320067101.68,
                "PARENT_NETPROFIT_YOY": -4.532255,
            }
        },
    )

    annual = cloud_sources._eastmoney_annual_financials("600519", 2025)

    assert annual["TOTALOPERATEREVE"] == pytest.approx(168838102514.79)
    assert annual["TOTALOPERATEREVETZ"] == pytest.approx(-1.206004)
    assert annual["_SELECTED_REPORT_YEAR"] == 2025


def test_eastmoney_finance_fallback_uses_operating_income(monkeypatch):
    adapter = make_adapter(
        FakeWencai(lambda skill, query, limit: payload()),
        None,
        name="贵州茅台",
    )
    adapter._stock_code = "600519"
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_annual_reports",
        lambda code: {
            2025: {
                "REPORT_DATE": "2025-12-31 00:00:00",
                "TOTALOPERATEREVE": 172054171890.91,
                "TOTALOPERATEREVETZ": -1.200097,
                "PARENTNETPROFIT": 82320067101.68,
                "PARENTNETPROFITTZ": -4.532255,
                "ROEJQ": 32.53,
            }
        },
    )
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_income_reports",
        lambda code: {
            2025: {
                "OPERATE_INCOME": 168838102514.79,
                "OPERATE_INCOME_YOY": -1.206004,
            }
        },
    )

    fields = adapter._eastmoney_finance_fallback([2025])

    assert fields["营业收入[20251231]"] == pytest.approx(168838102514.79)
    assert fields["营业收入同比增长率[20251231]"] == pytest.approx(-1.206004)
    assert fields["归属于母公司所有者的净利润[20251231]"] == pytest.approx(
        82320067101.68
    )


def test_peer_query_fills_missing_valuation_from_tencent(monkeypatch):
    adapter = make_adapter(FakeWencai(lambda skill, query, limit: payload()), None)
    adapter._stock_code = "600519"

    def fake_json(url, *, referer="https://emweb.securities.eastmoney.com/"):
        assert "IndustryAnalysis" in url
        return {
            "gzbj": [
                {
                    "CORRE_SECURITY_CODE": "600519",
                    "CORRE_SECURITY_NAME": "贵州茅台",
                    "PE_TTM": 21.34,
                    "PB_MRQ": 7.17,
                },
                {"CORRE_SECURITY_CODE": "000858", "CORRE_SECURITY_NAME": "五粮液"},
            ],
            "gsgm": [
                {
                    "CORRE_SECURITY_CODE": "600519",
                    "CORRE_SECURITY_NAME": "贵州茅台",
                    "TOTAL_CAP": 1752989429082.3,
                    "FREECAP": 17529.89,
                }
            ],
            "gsgm_zsz": [
                {
                    "CORRE_SECURITY_CODE": "000858",
                    "CORRE_SECURITY_NAME": "五粮液",
                    "TOTAL_CAP": 280989603481.95,
                    "FREECAP": 2819.14,
                }
            ],
        }

    monkeypatch.setattr(cloud_sources, "_fetch_eastmoney_json", fake_json)
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_quote_snapshot",
        lambda codes: {
            "600519": {"f14": "贵州茅台", "f20": 1752989429082.3},
            "000858": {"f14": "五粮液"},
        },
    )
    monkeypatch.setattr(
        cloud_sources,
        "_tencent_quote_snapshot",
        lambda codes: {
            "600519": {"pe": 21.46, "pb": 6.5},
            "000858": {"pe": 23.13, "pb": 2.38},
        },
    )

    result = adapter.wencai_nlp(
        "白酒行业，市盈率，总市值，市净率，净资产收益率ROE，"
        "2025年营业收入，2025年销售毛利率，2025年销售净利率，股息率"
    )
    rows = {row["股票代码"]: row for row in result.df.to_dict("records")}

    peer = rows["000858.SZ"]
    assert peer["市盈率(pe)"] == pytest.approx(23.13)
    assert peer["市净率(pb)"] == pytest.approx(2.38)
    assert peer["总市值"] == pytest.approx(280989603481.95)
    assert peer["流通市值"] == pytest.approx(281914000000.0)
    assert "腾讯行情" in peer["数据来源"]


def test_finance_query_falls_back_to_eastmoney_annual_reports(monkeypatch):
    adapter = make_adapter(FakeWencai(lambda skill, query, limit: payload()))
    adapter._stock_code = "600519"
    adapter.stock_name = "贵州茅台"

    annual_items = [
        {
            "REPORT_DATE": f"{year}-12-31 00:00:00",
            "REPORT_YEAR": str(year),
            "REPORT_TYPE": "年报",
            "TOTALOPERATEREVE": revenue,
            "PARENTNETPROFIT": profit,
            "XSMLL": 91.0,
            "XSJLL": 50.0,
            "ROEJQ": 32.53,
            "ZCFZL": 16.4,
            "TOTALOPERATEREVETZ": -1.2,
            "PARENTNETPROFITTZ": -4.5,
        }
        for year, revenue, profit in (
            (2023, 150560330316.45, 74734071550.75),
            (2024, 174144069958.25, 86228146421.62),
            (2025, 172054171890.91, 82320067101.68),
        )
    ]

    def fake_json(url, *, referer="https://emweb.securities.eastmoney.com/"):
        if "CompanySurvey" in url:
            return {
                "jbzl": [
                    {
                        "ORG_NAME": "贵州茅台酒股份有限公司",
                        "EM2016": "白酒Ⅲ",
                        "REG_ADDRESS": "贵州省仁怀市茅台镇",
                        "BUSINESS_SCOPE": "茅台酒及系列酒生产与销售",
                        "LISTING_DATE": "2001-08-27 00:00:00",
                    }
                ]
            }
        if "ShareholderResearch" in url:
            return {
                "sjkzr": [{"HOLDER_NAME": "贵州省人民政府国有资产监督管理委员会"}],
                "sdgd": [{"HOLDER_RANK": 1, "HOLDER_NAME": "中国贵州茅台酒厂（集团）有限责任公司"}],
            }
        assert "NewFinanceAnalysis" in url
        return {"data": annual_items}

    monkeypatch.setattr(cloud_sources, "_fetch_eastmoney_json", fake_json)

    row = adapter.wencai_nlp("贵州茅台 公司全称 主营业务").df.iloc[0]

    assert row["营业收入[20251231]"] == pytest.approx(172054171890.91)
    assert row["归属于母公司所有者的净利润[20251231]"] == pytest.approx(
        82320067101.68
    )
    assert row["销售毛利率[20251231]"] == pytest.approx(91.0)
    assert row["加权净资产收益率[20251231]"] == pytest.approx(32.53)
    assert row["资产负债率[20251231]"] == pytest.approx(16.4)
    assert row["公司中文名称"] == "贵州茅台酒股份有限公司"
    assert row["所属同花顺行业"] == "白酒Ⅲ"
    assert row["注册地址"] == "贵州省仁怀市茅台镇"
    assert row["实际控制人"] == "贵州省人民政府国有资产监督管理委员会"
    assert row["控股股东名称"] == "中国贵州茅台酒厂（集团）有限责任公司"
    assert adapter.finance_source == "eastmoney"
    assert adapter.finance_error == ""


def test_concentration_frame_aliases_top_ten_and_first_holder():
    def responder(skill, query, limit):
        assert "前十大股东持股比例合计" in query
        return payload(
            {
                "持股比例[20260930]": 0.6667,
                "持股比例": 49.56,
                "名称": "中国平安保险(集团)股份有限公司-集团本级-自有资金",
                "户均持股数量[20261112]": 47739.40198331086,
                "户均持股市值[20261112]": 560460.5792840695,
            }
        )

    adapter = make_adapter(FakeWencai(responder), FakeMarket())
    row = adapter.wencai_nlp(
        "平安银行 前十大股东持股比例合计 第一大股东持股比例 第一大股东名称 "
        "户均持股数量 户均持股市值"
    ).df.iloc[0]

    assert row["前十大股东持股比例合计"] == pytest.approx(66.67)
    assert row["第一大股东持股比例"] == 49.56
    assert row["第一大股东名称"].startswith("中国平安")
    assert row["户均持股数量"] == 47739.40198331086


def test_patent_query_aliases_total_count():
    def responder(skill, query, limit):
        assert "专利数量" in query
        return payload(
            {
                "专利数量[20261112]": 569.0,
                "发明专利[20261112]": 504.0,
                "实用新型[20261112]": 1.0,
            }
        )

    adapter = make_adapter(FakeWencai(responder), FakeMarket())
    row = adapter.wencai_nlp(
        "平安银行，研发费用，研发费用占营业收入比，专利数量，发明专利数量，"
        "实用新型专利数量，2025年研发费用，2025年研发费用占营业收入比"
    ).df.iloc[0]

    assert row["专利数量合计[20261112]"] == 569.0
    assert row["发明专利[20261112]"] == 504.0


def test_holder_trend_ignores_future_period_and_change_rate_columns():
    def responder(skill, query, limit):
        assert "股东户数" in query
        return payload(
            {
                "总户数[20230630]": 536701.0,
                "总户数[20251231]": 441142.0,
                "总户数[20261231]": 406492.0,
                "总户数较上期增长率[20251231]": -2.73,
            }
        )

    adapter = make_adapter(FakeWencai(responder), FakeMarket())
    row = adapter.wencai_nlp(
        "平安银行 股东户数[20230630] 股东户数[20251231] 股东户数[20261231]"
    ).df.iloc[0].to_dict()

    assert "总户数[20261231]" not in row
    assert "总户数[20251231]" in row
    assert _holder_count_change(row) == pytest.approx((441142 / 536701 - 1) * 100)


def test_big_order_flow_is_marked_as_daily_aggregate():
    def responder(skill, query, limit):
        assert "大单买入量" in query
        return payload(
            {
                "大单买入量[20261112]": 19013501,
                "大单卖出量[20261112]": 17568166,
                "大单买入额[20261112]": 222720230.75,
                "大单卖出额[20261112]": 205670722.12,
            }
        )

    adapter = make_adapter(FakeWencai(responder), FakeMarket())
    result = adapter.big_order_flow("USZA000001")

    assert result.scope == "daily_aggregate"
    assert len(result.df) == 2
    assert list(result.df["成交方向"]) == ["1", "-1"]
    assert result.df.iloc[0]["总金额"] == 222720230.75
    assert result.main_net_inflow == pytest.approx(17049508.63)


def test_big_order_flow_falls_back_to_thsdk(monkeypatch):
    def responder(skill, query, limit):
        return payload()

    def fake_thsdk(self, thscode):
        rows = [
            {
                "时间": 1794449213,
                "成交方向": "1",
                "成交量": 300,
                "总金额": 417900,
                "委托买入价": "",
                "委托卖出价": "",
                "成交方向码": "1",
            }
        ]
        return cloud_sources.SimpleNamespace(
            df=cloud_sources.pd.DataFrame(rows),
            error="",
            scope="tick",
            source="thsdk",
        )

    monkeypatch.setattr(CloudStockAdapter, "_ths_big_order_flow", fake_thsdk)
    adapter = make_adapter(FakeWencai(responder), FakeMarket())
    result = adapter.big_order_flow("USZA000001")

    assert result.source == "thsdk"
    assert result.scope == "tick"
    assert len(result.df) == 1
    assert result.df.iloc[0]["成交方向"] == "1"


def test_big_order_flow_falls_back_to_eastmoney_daily_net_flow(monkeypatch):
    def responder(skill, query, limit):
        return payload()

    def fake_thsdk(self, thscode):
        return cloud_sources.SimpleNamespace(
            df=cloud_sources.pd.DataFrame(),
            error="thsdk unavailable",
        )

    def fake_json(url, *, referer="https://emweb.securities.eastmoney.com/"):
        assert "fflow/daykline" in url
        assert "secid=0.000001" in url
        return {
            "data": {
                "klines": [
                    "2026-11-11,-100000.0,20000.0,-30000.0,-40000.0,-50000.0",
                    "2026-11-12,-322878512.0,100000000.0,-50000000.0,"
                    "-200000000.0,-172878512.0",
                ]
            }
        }

    monkeypatch.setattr(CloudStockAdapter, "_ths_big_order_flow", fake_thsdk)
    monkeypatch.setattr(cloud_sources, "_fetch_eastmoney_json", fake_json)
    adapter = make_adapter(FakeWencai(responder), FakeMarket())

    result = adapter.big_order_flow("USZA000001")

    assert result.source == "eastmoney"
    assert result.scope == "daily_net_flow"
    assert result.main_net_inflow == pytest.approx(-322878512.0)
    assert result.df.iloc[-1]["大单净流入"] == pytest.approx(-200000000.0)
    assert result.df.iloc[-1]["超大单净流入"] == pytest.approx(-172878512.0)


def test_tencent_quote_snapshot_parses_valuation_fields(monkeypatch):
    fields = [""] * 80
    fields[1] = "古井贡酒"
    fields[2] = "000596"
    fields[3] = "105.80"
    fields[4] = "106.14"
    fields[5] = "106.00"
    fields[33] = "107.20"
    fields[34] = "104.80"
    fields[36] = "12000"
    fields[37] = "12800"
    fields[38] = "0.42"
    fields[43] = "2.25"
    fields[44] = "432.30"
    fields[45] = "420.10"
    fields[32] = "-0.32"
    fields[39] = "30.25"
    fields[46] = "2.24"
    fields[47] = "116.75"
    fields[48] = "95.53"
    fields[62] = "-17.47"
    fields[63] = "3.21"
    fields[72] = "390000000"
    fields[73] = "400000000"
    body = ('v_sz000596="' + "~".join(fields) + '";').encode("gbk")

    class FakeResponse:
        content = body

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        cloud_sources.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )

    quotes = cloud_sources._tencent_quote_snapshot(["000596"])

    assert quotes["000596"]["price"] == pytest.approx(105.8)
    assert quotes["000596"]["change_pct"] == pytest.approx(-0.32)
    assert quotes["000596"]["pe"] == pytest.approx(30.25)
    assert quotes["000596"]["pb"] == pytest.approx(2.24)
    assert quotes["000596"]["market_cap"] == pytest.approx(432.3e8)
    assert quotes["000596"]["circulating_cap"] == pytest.approx(420.1e8)
    assert quotes["000596"]["volume"] == pytest.approx(1200000)
    assert quotes["000596"]["amount"] == pytest.approx(128000000)
    assert quotes["000596"]["turnover_rate"] == pytest.approx(0.42)
    assert quotes["000596"]["amplitude"] == pytest.approx(2.25)
    assert quotes["000596"]["prev_close"] == pytest.approx(106.14)
    assert quotes["000596"]["limit_up"] == pytest.approx(116.75)
    assert quotes["000596"]["limit_down"] == pytest.approx(95.53)
    assert quotes["000596"]["5d_change"] == pytest.approx(3.21)
    assert quotes["000596"]["total_shares"] == pytest.approx(400000000)
    assert quotes["000596"]["float_shares"] == pytest.approx(390000000)
    assert quotes["000596"]["ytd_change"] == pytest.approx(-17.47)


def test_tencent_quote_fallback_only_fills_missing_fields():
    stocks = [
        {
            "ticker": "000596",
            "price": 105.8,
            "change_pct": None,
            "pe": 99.0,
            "pb": None,
            "market_cap": None,
            "ytd_change": None,
            "data_sources": ["eastmoney"],
        }
    ]
    quotes = {
        "000596": {
            "price": 100.0,
            "change_pct": -0.32,
            "pe": 30.25,
            "pb": 2.24,
            "market_cap": 432.3e8,
            "ytd_change": -17.47,
        }
    }

    filled = cloud_sources._apply_tencent_quote_fallback(stocks, quotes)

    assert filled == ["000596"]
    assert stocks[0]["price"] == pytest.approx(105.8)
    assert stocks[0]["pe"] == pytest.approx(99.0)
    assert stocks[0]["change_pct"] == pytest.approx(-0.32)
    assert stocks[0]["pb"] == pytest.approx(2.24)
    assert stocks[0]["market_cap_yi"] == pytest.approx(432.3)
    assert stocks[0]["ytd_change"] == pytest.approx(-17.47)
    assert stocks[0]["data_sources"] == ["eastmoney", "tencent"]


def test_dividend_yield_is_recomputed_after_tencent_price_fill(monkeypatch):
    stocks = [
        {"ticker": "000568", "price": 76.74, "dividend_yield": None},
        {"ticker": "600519", "price": 1410.27, "dividend_yield": 2.5},
    ]
    calls = []

    def dividend_yield(code, price):
        calls.append((code, price))
        return 4.2

    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_dividend_yield",
        dividend_yield,
    )

    cloud_sources._fill_missing_dividend_yields(stocks)

    assert stocks[0]["dividend_yield"] == pytest.approx(4.2)
    assert stocks[1]["dividend_yield"] == pytest.approx(2.5)
    assert calls == [("000568", 76.74)]


def test_industry_cloud_uses_weighted_roe_and_builds_all_domains(monkeypatch):
    market = FakeMarket()

    def responder(skill, query, limit):
        if "成分股" in query and "归母净利润同比增长率" in query:
            return payload(
                {
                    "股票代码": "600519.SH",
                    "股票简称": "贵州茅台",
                    "归母净利润同比增长率[20251231]": 11.2,
                    "年涨跌幅[20261112]": 5.5,
                    "所属同花顺行业": ["食品饮料", "白酒"],
                    "主营产品": ["茅台酒"],
                },
                {
                    "股票代码": "000568.SZ",
                    "股票简称": "泸州老窖",
                    "归母净利润同比增长率[20251231]": -19.6,
                    "年涨跌幅[20261112]": -30.3,
                    "所属同花顺行业": ["食品饮料", "白酒"],
                    "主营产品": ["国窖1573"],
                },
            )
        if "成分股" in query:
            return payload(
                {
                    "股票代码": "600519.SH",
                    "股票简称": "贵州茅台",
                    "最新价": 1402.3,
                    "最新涨跌幅": -2.55,
                    "最新市盈率ttm": 20.1,
                    "最新动态市盈率": 21.0,
                    "总市值[20261112]": 1760000000000,
                    "最新市净率": 7.2,
                    "净资产收益率[20260930]": 25.0,
                    "加权净资产收益率[20260930]": 30.2,
                    "加权净资产收益率[20251231]": 30.2,
                    "年度股息率[20251231]": 2.5,
                    "营业收入[20251231]": 180000000000,
                    "销售毛利率[20251231]": 91.2,
                    "销售净利率[20251231]": 50.1,
                },
                {
                    "股票代码": "000568.SZ",
                    "股票简称": "泸州老窖",
                    "最新价": 76.99,
                    "最新涨跌幅": -3.75,
                    "最新市盈率ttm": 15.0,
                    "最新动态市盈率": 15.0,
                    "总市值[20261112]": 113000000000,
                    "最新市净率": 2.4,
                    "净资产收益率[20260930]": 18.0,
                    "加权净资产收益率[20260930]": 22.66,
                    "加权净资产收益率[20251231]": 22.66,
                    "营业收入[20251231]": 25731010647,
                    "销售毛利率[20251231]": 86.62,
                    "销售净利率[20251231]": 42.2,
                },
            )
        if "5日涨幅" in query:
            return payload(
                {
                    "涨跌幅[20261106-20261112]": 1.1,
                    "涨跌幅[20261030-20261112]": 2.2,
                    "涨跌幅[20261016-20261112]": 3.3,
                    "主力净买入额[20261112]": 123456789,
                    "量比[20261112]": 1.5,
                }
            )
        raise AssertionError(query)

    monkeypatch.setattr(cloud_sources, "_safe_market_client", lambda: (market, ""))
    monkeypatch.setattr(cloud_sources, "_wencai_client", lambda: (FakeWencai(responder), "test"))
    monkeypatch.setattr(
        cloud_sources, "_eastmoney_quote_snapshot", lambda codes: {}
    )
    monkeypatch.setattr(
        cloud_sources, "_eastmoney_annual_financials", lambda code, year: {}
    )
    monkeypatch.setattr(
        cloud_sources, "_tencent_quote_snapshot", lambda codes: {}
    )

    result = cloud_sources.collect_industry_cloud("白酒", limit=2)

    assert result["sector"]["name"] == "白酒Ⅲ"
    assert len(result["stocks"]) == 2
    by_code = {item["ticker"]: item for item in result["stocks"]}
    assert by_code["600519"]["roe"] == 30.2
    assert by_code["600519"]["pe"] == 21.0
    assert by_code["600519"]["dividend_yield"] == 2.5
    assert by_code["600519"]["ytd_change"] == 5.5
    assert by_code["600519"]["main_business"] == "茅台酒"
    assert by_code["600519"]["revenue_yi"] == 1800.0
    assert by_code["000568"]["roe"] == 22.66
    assert result["sector_snapshot"]["5日涨幅"] == 1.1
    assert result["sector_snapshot"]["10日涨幅"] == 2.2
    assert result["sector_snapshot"]["20日涨幅"] == 3.3
    assert result["sector_snapshot"]["量比"] == 1.5
    assert "raw" not in result["sector_snapshot"]
    assert len(result["news"]) == 2
    assert any("扶摇 REST" in item for item in result["sources"])
    assert any("官方问财 OpenAPI" in item and "实时行情主数据" in item for item in result["sources"])


def test_industry_cloud_preflight_checks_channels_without_full_collection(monkeypatch):
    market = FakeMarket()

    def responder(skill, query, limit):
        assert skill == "hithink-industry-query"
        assert "白酒Ⅲ行业成分股" in query
        assert limit == 5
        return payload({"股票代码": "600519.SH", "最新价": 1402.3})

    wencai = FakeWencai(responder)
    monkeypatch.setattr(cloud_sources, "_safe_market_client", lambda: (market, ""))
    monkeypatch.setattr(cloud_sources, "_wencai_client", lambda: (wencai, "test"))

    result = cloud_sources.preflight_industry_cloud("白酒")

    assert result["ok"] is True
    assert result["mode"] == "preflight"
    assert result["sector"]["name"] == "白酒Ⅲ"
    assert result["members_count"] == 2
    assert result["channels"]["fuyao"] == "ok"
    assert result["channels"]["wencai"] == "ok"
    assert len(wencai.calls) == 1


def test_industry_cloud_preflight_falls_back_when_wencai_quota_is_exhausted(
    monkeypatch,
):
    market = FakeMarket()

    def responder(skill, query, limit):
        raise cloud_sources.mq.QueryError(
            "今天的次数已用完",
            "wencai_quota_exhausted",
        )

    def fake_json(url, *, referer="https://emweb.securities.eastmoney.com/"):
        if "searchapi.eastmoney.com" in url:
            return {
                "QuotationCodeTable": {
                    "Data": [
                        {
                            "Code": "BK1575",
                            "Name": "白酒Ⅲ",
                            "MktNum": "90",
                            "QuoteID": "90.BK1575",
                        }
                    ]
                }
            }
        if "kline/get" in url:
            return {
                "data": {
                    "klines": [
                        f"2026-11-{index + 1:02d},"
                        f"{100 + index},{100 + index},"
                        f"{100 + index},{100 + index},"
                        f"{1000000 + index * 10000},"
                        f"{100000000 + index * 1000000},"
                        "1.0,0.0,0.0,1.0"
                        for index in range(30)
                    ]
                }
            }
        if "fflow" in url:
            return {
                "data": {
                    "klines": [
                        "2026-11-12,-160098192.0,-364834816.0,"
                        "524732672.0,-355624736.0,195526544.0"
                    ]
                }
            }
        if "stock/get" in url:
            return {"data": {"f50": 1.23, "f170": 0.35}}
        raise AssertionError(url)

    monkeypatch.setattr(cloud_sources, "_safe_market_client", lambda: (market, ""))
    monkeypatch.setattr(
        cloud_sources,
        "_wencai_client",
        lambda: (FakeWencai(responder), "test"),
    )
    monkeypatch.setattr(cloud_sources, "_thsdk_sector_metrics", thsdk_unavailable)
    monkeypatch.setattr(cloud_sources, "_fetch_eastmoney_json", fake_json)

    result = cloud_sources.preflight_industry_cloud("白酒")

    assert result["ok"] is True
    assert result["channels"]["fuyao"] == "ok"
    assert result["channels"]["wencai"] == "unavailable"
    assert result["channels"]["eastmoney"] == "ok"
    assert result["eastmoney_board"]["code"] == "BK1575"
    assert result["warnings"]


def test_industry_cloud_preflight_uses_thsdk_block_snapshot(monkeypatch):
    market = FakeMarket()

    def responder(skill, query, limit):
        raise cloud_sources.mq.QueryError(
            "今天的次数已用完",
            "wencai_quota_exhausted",
        )

    def thsdk_success(sector_code, snapshot):
        assert sector_code == "URFI881273"
        return {
            "board": {
                "code": "URFI881273",
                "secid": "URFI881273",
                "name": "白酒Ⅲ",
            },
            "as_of": "",
            "metrics": {
                "涨幅": 0.7944,
                "5日涨幅": -4.1862,
                "10日涨幅": 8.205,
                "20日涨幅": 6.6646,
                "主力净流入": 95341780.0,
                "量比": 1.1614,
            },
        }

    monkeypatch.setattr(cloud_sources, "_safe_market_client", lambda: (market, ""))
    monkeypatch.setattr(
        cloud_sources,
        "_wencai_client",
        lambda: (FakeWencai(responder), "test"),
    )
    monkeypatch.setattr(cloud_sources, "_thsdk_sector_metrics", thsdk_success)
    monkeypatch.setattr(
        cloud_sources,
        "_eastmoney_sector_metrics",
        lambda *_: (_ for _ in ()).throw(AssertionError("eastmoney should be skipped")),
    )
    monkeypatch.setattr(
        cloud_sources,
        "_hithink_sector_metrics",
        lambda *_: (_ for _ in ()).throw(AssertionError("hithink should be skipped")),
    )

    result = cloud_sources.preflight_industry_cloud("白酒")

    assert result["channels"]["thsdk"] == "ok"
    assert result["channels"]["eastmoney"] == "not_needed"
    assert result["channels"]["hithink"] == "not_needed"
    assert result["sector_metrics"]["主力净流入"] == 95341780.0
    assert result["sector_metrics"]["量比"] == 1.1614


def test_industry_cloud_preflight_falls_back_to_hithink_index(monkeypatch):
    market = FakeMarket()

    def responder(skill, query, limit):
        raise cloud_sources.mq.QueryError(
            "今天的次数已用完",
            "wencai_quota_exhausted",
        )

    def eastmoney_partial(keyword):
        return {
            "board": {"code": "BK0896", "secid": "90.BK0896", "name": "白酒"},
            "as_of": "",
            "metrics": {"主力净流入": -133299008.0},
        }

    seen = {}

    def hithink_success(sector_code, snapshot):
        seen["sector_code"] = sector_code
        seen["snapshot"] = snapshot
        return {
            "board": {"code": "881273.TI", "secid": "881273.TI", "name": "白酒Ⅲ"},
            "as_of": "2026-11-12",
            "metrics": {
                "涨幅": 0.4,
                "5日涨幅": -4.18,
                "10日涨幅": 8.2,
                "20日涨幅": 6.66,
                "量比": 1.16,
            },
        }

    monkeypatch.setattr(cloud_sources, "_safe_market_client", lambda: (market, ""))
    monkeypatch.setattr(
        cloud_sources,
        "_wencai_client",
        lambda: (FakeWencai(responder), "test"),
    )
    monkeypatch.setattr(cloud_sources, "_thsdk_sector_metrics", thsdk_unavailable)
    monkeypatch.setattr(cloud_sources, "_eastmoney_sector_metrics", eastmoney_partial)
    monkeypatch.setattr(cloud_sources, "_hithink_sector_metrics", hithink_success)

    result = cloud_sources.preflight_industry_cloud("白酒")

    assert result["ok"] is True
    assert result["channels"]["eastmoney"] == "ok"
    assert result["channels"]["hithink"] == "ok"
    assert result["eastmoney_board"]["code"] == "BK0896"
    assert result["hithink_board"]["code"] == "881273.TI"
    assert result["sector_metrics"]["主力净流入"] == -133299008.0
    assert result["sector_metrics"]["5日涨幅"] == -4.18
    assert seen["sector_code"] == "URFI881273"
    assert seen["snapshot"]["涨幅"] == 1.2


def test_industry_cloud_falls_back_to_eastmoney_annual_financials(monkeypatch):
    market = FakeMarket()

    def responder(skill, query, limit):
        if "5日涨幅" in query:
            return payload()
        if "成分股" in query:
            raise cloud_sources.mq.QueryError(
                "今天的次数已用完",
                "wencai_quota_exhausted",
            )
        raise AssertionError(query)

    def fake_json(url, *, referer="https://emweb.securities.eastmoney.com/"):
        if "BusinessAnalysis" in url:
            name = "茅台酒" if "600519" in url else "国窖1573"
            return {
                "zygcfx": [
                    {
                        "REPORT_DATE": "2025-12-31 00:00:00",
                        "MAINOP_TYPE": "2",
                        "ITEM_NAME": name,
                        "MBI_RATIO": 0.9,
                    }
                ]
            }
        if "BonusFinancing" in url:
            return {
                "fhyx": [
                    {
                        "ASSIGN_PROGRESS": "实施方案",
                        "EX_DIVIDEND_DATE": "2026-06-22 00:00:00",
                        "IMPL_PLAN_PROFILE": "10派280.2423元",
                    }
                ]
            }
        if "ZYZBAjaxNew" in url:
            if "600519" in url:
                return {
                    "data": [
                        {
                            "REPORT_TYPE": "年报",
                            "REPORT_DATE": "2025-12-31 00:00:00",
                            "REPORT_YEAR": "2025",
                            "TOTALOPERATEREVE": 172054171890.91,
                            "PARENTNETPROFIT": 82320067101.68,
                            "TOTALOPERATEREVETZ": -1.2001,
                            "PARENTNETPROFITTZ": -4.5323,
                            "ROEJQ": 32.53,
                            "XSMLL": 91.1796,
                            "XSJLL": 50.5279,
                        }
                    ]
                }
            if "000568" in url:
                return {
                    "data": [
                        {
                            "REPORT_TYPE": "年报",
                            "REPORT_DATE": "2025-12-31 00:00:00",
                            "REPORT_YEAR": "2025",
                            "TOTALOPERATEREVE": 25731010647.0,
                            "PARENTNETPROFIT": 10800000000.0,
                            "TOTALOPERATEREVETZ": -19.6,
                            "PARENTNETPROFITTZ": -20.1,
                            "ROEJQ": 22.66,
                            "XSMLL": 86.62,
                            "XSJLL": 42.2,
                        }
                    ]
                }
        if "ulist.np" in url:
            return {
                "data": {
                    "diff": [
                        {
                            "f12": "600519",
                            "f2": 1402.3,
                            "f3": -2.55,
                            "f9": 21.0,
                            "f20": 1760000000000,
                            "f23": 7.2,
                            "f25": 5.5,
                        },
                        {
                            "f12": "000568",
                            "f2": 76.99,
                            "f3": -3.75,
                            "f9": 15.0,
                            "f20": 113000000000,
                            "f23": 2.4,
                            "f25": -30.3,
                        },
                    ]
                }
            }
        if "searchapi.eastmoney.com" in url:
            return {
                "QuotationCodeTable": {
                    "Data": [
                        {
                            "Code": "BK1575",
                            "Name": "白酒Ⅲ",
                            "MktNum": "90",
                            "QuoteID": "90.BK1575",
                        }
                    ]
                }
            }
        if "kline/get" in url and "fflow" not in url:
            return {
                "data": {
                    "klines": [
                        f"2026-11-{index + 1:02d},"
                        f"{100 + index},{100 + index},"
                        f"{100 + index},{100 + index},"
                        f"{1000000 + index * 10000},"
                        f"{100000000 + index * 1000000},"
                        "1.0,0.0,0.0,1.0"
                        for index in range(30)
                    ]
                }
            }
        if "fflow" in url:
            return {
                "data": {
                    "klines": [
                        "2026-11-12,-160098192.0,-364834816.0,"
                        "524732672.0,-355624736.0,195526544.0"
                    ]
                }
            }
        if "stock/get" in url:
            return {"data": {"f50": 1.23, "f170": 0.35}}
        raise AssertionError(url)

    monkeypatch.setattr(cloud_sources, "_safe_market_client", lambda: (market, ""))
    monkeypatch.setattr(
        cloud_sources,
        "_wencai_client",
        lambda: (FakeWencai(responder), "test"),
    )
    monkeypatch.setattr(cloud_sources, "_thsdk_sector_metrics", thsdk_unavailable)
    monkeypatch.setattr(cloud_sources, "_fetch_eastmoney_json", fake_json)

    result = cloud_sources.collect_industry_cloud("白酒", limit=2)
    by_code = {item["ticker"]: item for item in result["stocks"]}

    assert by_code["600519"]["revenue"] == pytest.approx(172054171890.91)
    assert by_code["600519"]["net_profit"] == pytest.approx(82320067101.68)
    assert by_code["600519"]["roe"] == pytest.approx(32.53)
    assert by_code["600519"]["gross_margin"] == pytest.approx(91.1796)
    assert by_code["600519"]["pe"] == pytest.approx(21.0)
    assert by_code["600519"]["market_cap_yi"] == pytest.approx(17600.0)
    assert by_code["000568"]["revenue_yoy"] == pytest.approx(-19.6)
    assert by_code["000568"]["profit_yoy"] == pytest.approx(-20.1)
    assert by_code["000568"]["ytd_change"] == pytest.approx(-30.3)
    assert by_code["600519"]["industry"] == "白酒Ⅲ"
    assert by_code["600519"]["dividend_yield"] == pytest.approx(
        280.2423 / 10 / 1402.3 * 100,
        abs=0.0001,
    )
    assert by_code["600519"]["main_business"] == "茅台酒"
    assert by_code["000568"]["main_business"] == "国窖1573"
    assert result["sector_snapshot"]["5日涨幅"] == pytest.approx((129 / 124 - 1) * 100)
    assert result["sector_snapshot"]["10日涨幅"] == pytest.approx((129 / 119 - 1) * 100)
    assert result["sector_snapshot"]["20日涨幅"] == pytest.approx((129 / 109 - 1) * 100)
    assert result["sector_snapshot"]["主力净流入"] == pytest.approx(-160098192.0)
    assert result["sector_snapshot"]["量比"] == pytest.approx(1.23)
    assert result["sector"]["eastmoney_block_code"] == "BK1575"
    assert any("东方财富 F10/行情" in item for item in result["sources"])
    assert any("东方财富板块行情" in item for item in result["sources"])
    assert any("问财行业财务数据不完整" in item for item in result["warnings"])


def test_stock_adapter_constructs_without_wencai_key(monkeypatch):
    monkeypatch.setattr(cloud_sources.mq, "wencai_api_key", lambda: (None, None))
    monkeypatch.setattr(
        cloud_sources,
        "_safe_market_client",
        lambda: (FakeMarket(), ""),
    )

    adapter = CloudStockAdapter()

    assert adapter.wencai is None
    assert "IWENCAI_API_KEY" in adapter.wencai_error
    assert adapter._query("贵州茅台 营业收入").df.empty
    assert "IWENCAI_API_KEY" in adapter._query("贵州茅台 营业收入").error


def test_stock_adapter_fails_closed_without_market_key(monkeypatch):
    monkeypatch.setattr(cloud_sources, "_wencai_client", lambda: (FakeWencai(lambda *_: payload()), "test"))
    monkeypatch.setattr(cloud_sources, "_safe_market_client", lambda: (None, "missing key"))

    with pytest.raises(CloudSourceError) as excinfo:
        CloudStockAdapter()

    assert "FUYAO_API_KEY" in str(excinfo.value)
    assert "missing key" in str(excinfo.value)


def test_industry_cloud_fails_closed_without_market_key(monkeypatch):
    monkeypatch.setattr(cloud_sources, "_safe_market_client", lambda: (None, "missing key"))

    with pytest.raises(CloudSourceError) as excinfo:
        cloud_sources.collect_industry_cloud("白酒")

    assert "missing key" in str(excinfo.value)


def test_auto_source_selects_cloud_only_in_cloud_environment(monkeypatch):
    monkeypatch.delenv("DAILY_BRIEFING_CLOUD", raising=False)
    assert fetch_stock_data.resolve_source("auto") == "ths"
    assert fetch_industry_data.resolve_source("auto") == "ths"

    monkeypatch.setenv("DAILY_BRIEFING_CLOUD", "1")
    assert fetch_stock_data.resolve_source("auto") == "cloud"
    assert fetch_industry_data.resolve_source("auto") == "cloud"
    assert fetch_stock_data.resolve_source("ths") == "ths"
    assert fetch_industry_data.resolve_source("cloud") == "cloud"
