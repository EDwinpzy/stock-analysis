from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

import fetch_stock_data


class ResolveTHS:
    def search_symbols(self, query: str):
        assert query == "600519"
        return SimpleNamespace(
            df=pd.DataFrame(
                [
                    {
                        "Code": "600519",
                        "Name": "贵州茅台",
                        "THSCODE": "USHA600519",
                    }
                ]
            )
        )


def test_numeric_code_resolution_returns_security_name():
    thscode, pure_code, name = fetch_stock_data.resolve_code(ResolveTHS(), "600519")

    assert (thscode, pure_code, name) == ("USHA600519", "600519", "贵州茅台")


def test_stock_name_normalization_removes_spaces_and_fullwidth_letters():
    assert fetch_stock_data.normalize_stock_name("万  科Ａ") == "万科A"


def test_numeric_code_resolution_normalizes_vendor_name():
    class SpacedTHS:
        def search_symbols(self, query: str):
            assert query == "000002"
            return SimpleNamespace(
                df=pd.DataFrame(
                    [
                        {
                            "Code": "000002",
                            "Name": "万  科Ａ",
                            "THSCODE": "USZA000002",
                        }
                    ]
                )
            )

    thscode, pure_code, name = fetch_stock_data.resolve_code(SpacedTHS(), "000002")

    assert (thscode, pure_code, name) == ("USZA000002", "000002", "万科A")


def test_dated_metric_uses_latest_non_empty_period():
    metric = fetch_stock_data._dated_metric(
        {
            "客户销售额合计占比(前五大)[20241231]": "11.52",
            "客户销售额合计占比(前五大)[20251231]": "10.1",
            "客户名称(前五大)[20251231]": None,
        },
        "客户销售额合计占比",
    )

    assert metric == {
        "value": "10.1",
        "period": "20251231",
        "source_column": "客户销售额合计占比(前五大)[20251231]",
    }


def test_dated_metric_returns_empty_when_all_values_are_missing():
    metric = fetch_stock_data._dated_metric(
        {"客户销售额合计占比(前五大)[20251231]": None},
        "客户销售额合计占比",
    )

    assert metric == {}


def test_industry_peer_terms_fall_back_from_leaf_to_parent():
    assert fetch_stock_data._industry_peer_terms(
        "银行-银行-股份制银行"
    ) == ["股份制银行", "银行"]
    assert fetch_stock_data._industry_peer_terms(
        "食品饮料-白酒-白酒Ⅲ"
    ) == ["白酒", "食品饮料"]
    assert fetch_stock_data._industry_peer_terms("暂无") == []


def test_vendor_quote_sentinel_is_reported_as_missing():
    assert fetch_stock_data._vendor_quote_value(2_147_483_648.0) == "暂无"
    assert fetch_stock_data._vendor_quote_value("2147483648") == "暂无"
    assert fetch_stock_data._vendor_quote_value(1402.3) == 1402.3


def test_big_order_row_maps_vendor_direction_column():
    row = pd.Series(
        {
            "时间": "2026-11-12 09:30",
            "成交方向": "-2",
            "成交量": 81500,
            "总金额": 952735,
        }
    )

    result = fetch_stock_data._format_big_order_row(row, row.index)

    assert result["成交方向"] == "中单卖出"
    assert result["成交方向_code"] == "-2"
    assert result["成交量"] == "81500"


def test_daily_aggregate_flow_replaces_vendor_quote_metric():
    data = {
        "quote": {
            "main_net_inflow": -12902090.0,
            "main_net_pct": -0.4625,
            "circulating_cap": 1761865000000.0,
        }
    }

    applied = fetch_stock_data._apply_daily_aggregate_flow(
        data,
        "daily_aggregate",
        -26068704.79,
    )

    assert applied
    assert data["quote"]["main_net_inflow"] == -26068704.79
    assert data["quote"]["main_net_pct"] == -0.0015


def test_tick_big_orders_keep_vendor_quote_metric():
    data = {
        "quote": {
            "main_net_inflow": -26068780.0,
            "main_net_pct": -0.0015,
        }
    }

    applied = fetch_stock_data._apply_daily_aggregate_flow(
        data,
        "",
        -26068704.79,
    )

    assert not applied
    assert data["quote"]["main_net_inflow"] == -26068780.0
