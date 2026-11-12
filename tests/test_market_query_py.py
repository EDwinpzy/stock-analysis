from __future__ import annotations

from datetime import datetime
import os
import sys
from types import SimpleNamespace

import market_query as mq
import pytest


class Frame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orient="records"):
        assert orient == "records"
        return self.rows


class Response:
    def __init__(self, rows=None, error=None):
        self.df = Frame(rows or [])
        self.error = error


def test_cloud_code_conversion():
    assert mq.normalize_thscode("600519.SH") == "USHA600519"
    assert mq.normalize_thscode("000001.SZ") == "USZA000001"
    assert mq.normalize_thscode("881273.TI") == "881273.TI"
    assert mq.cloud_thscode("600519") == "600519.SH"
    assert mq.cloud_thscode("USHA600519") == "600519.SH"
    assert mq.cloud_thscode("000001") == "000001.SZ"
    assert mq.cloud_thscode("600519.SH") == "600519.SH"
    assert mq.cloud_thscode("881273.TI") == "881273.TI"


def test_vendor_null_sentinel_is_normalized_to_none():
    assert mq.numeric(2_147_483_648) is None
    assert mq.numeric("2147483648") is None
    assert mq.numeric(1402.3) == 1402.3


def test_cloud_realtime_uses_vendor_codes(monkeypatch):
    client = mq.CloudClient(key="test-key")
    captured = {}

    def fake_get(path, params=None):
        captured["path"] = path
        captured["params"] = params
        return {
            "code": 0,
            "data": {
                "timestamp": 1,
                "item": [
                    {
                        "thscode": "600519.SH",
                        "ticker": "600519",
                        "name": "贵州茅台",
                        "last_price": 1402.3,
                        "prev_price": 1439,
                    }
                ],
            },
            "request_id": "r1",
        }

    monkeypatch.setattr(client, "get", fake_get)
    result = client.realtime(["600519"])
    assert captured["params"]["thscodes"] == "600519.SH"
    row = result["data"]["USHA600519"]
    assert row["vendor_thscode"] == "600519.SH"
    assert row["last_price"] == 1402.3
    for field in ("5", "6", "7", "8", "9", "10", "13", "19", "55", "199112", "264648"):
        assert field in row
    assert row["6"] == 1439
    assert row["55"] == "贵州茅台"


def test_cloud_candle_trims_to_requested_count_and_normalizes_date(monkeypatch):
    client = mq.CloudClient(key="test-key")
    captured = {}
    rows = [
        {
            "date_ms": 1790006400000 + index * 86400000,
            "open_price": 1,
            "high_price": 2,
            "low_price": 0.5,
            "close_price": 1.5,
            "volume": 100,
            "turnover": 150,
        }
        for index in range(6)
    ]

    def fake_get(path, params=None):
        captured["params"] = params
        return {"code": 0, "data": {"timestamp": 1, "item": rows}, "request_id": "r2"}

    monkeypatch.setattr(client, "get", fake_get)
    result = client.candle("600519", count=5)
    assert captured["params"]["thscode"] == "600519.SH"
    bars = result["data"]["USHA600519"]
    assert len(bars) == 5
    assert isinstance(bars[0]["1"], int)


def test_ths_news_balances_categories(monkeypatch):
    client = mq.ThsClient()

    def fake_news(text_id, ticker, market):
        assert ticker == "600519"
        assert market == "USHA"
        category = {0x3805: "公告", 0x3806: "研报", 0x3808: "社区"}[text_id]
        return Response(
            [
                {"Title": f"{category}-{index}", "Time": 1}
                for index in range(10)
            ]
        )

    client._ths = type("FakeThs", (), {"news": staticmethod(fake_news)})()
    monkeypatch.setattr(mq.time, "sleep", lambda _: None)
    result = client.news("600519", count=6)
    assert len(result["items"]) == 6
    counts = {}
    for item in result["items"]:
        counts[item["_category"]] = counts.get(item["_category"], 0) + 1
    assert counts == {"公告": 2, "研报": 2, "社区": 2}
    assert result["errors"] == []


def test_ths_candle_trims_and_formats_date(monkeypatch):
    client = mq.ThsClient()

    def fake_klines(thscode, **kwargs):
        assert thscode == "USHA600519"
        return Response(
            [
                {
                    "时间": datetime(2026, 11, 4 + index),
                    "开盘价": 1,
                    "最高价": 2,
                    "最低价": 0.5,
                    "收盘价": 1.5,
                    "成交量": 100,
                    "总金额": 150,
                }
                for index in range(6)
            ]
        )

    client._ths = type("FakeThs", (), {"klines": staticmethod(fake_klines)})()
    result = client.candle("600519", count=5)
    bars = result["data"]["USHA600519"]
    assert len(bars) == 5
    assert bars[0]["1"] == 20261105
    assert bars[-1]["1"] == 20261109


def test_ths_trend_maps_desktop_field_ids():
    client = mq.ThsClient()

    class FakeThs:
        @staticmethod
        def intraday_data(thscode):
            assert thscode == "USHA600519"
            return Response(
                [
                    {
                        "时间": datetime(2026, 11, 12, 9, 30),
                        "价格": 1402.3,
                        "成交量": 200,
                        "总金额": 280460,
                    }
                ]
            )

    client._ths = FakeThs()
    result = client.trend("600519")
    item = result["items"][0]
    assert isinstance(item["1"], int)
    assert item["10"] == 1402.3
    assert item["13"] == 200
    assert item["19"] == 280460


def test_ths_realtime_and_trend_drop_vendor_null_sentinel():
    client = mq.ThsClient()

    class FakeThs:
        @staticmethod
        def market_data_cn(codes, query):
            return Response(
                [
                    {
                        "THSCODE": "USHA600519",
                        "名称": "贵州茅台",
                        "价格": 2_147_483_648.0,
                        "昨收价": 1402.3,
                        "涨幅": 2_147_483_648.0,
                    }
                ]
            )

        @staticmethod
        def intraday_data(thscode):
            return Response(
                [
                    {
                        "时间": datetime(2026, 11, 12, 9, 30),
                        "价格": 2_147_483_648,
                        "成交量": 0,
                        "总金额": 2_147_483_648,
                    }
                ]
            )

    client._ths = FakeThs()
    realtime = client.realtime(["600519"])
    assert realtime["data"]["USHA600519"]["last_price"] is None
    assert realtime["data"]["USHA600519"]["prev_close"] == 1402.3
    assert realtime["data"]["USHA600519"]["price_change_ratio_pct"] is None

    trend = client.trend("600519")
    assert trend["items"][0]["10"] is None
    assert trend["items"][0]["13"] == 0
    assert trend["items"][0]["19"] is None


def test_ths_tick_trims_count_and_maps_desktop_field_ids():
    client = mq.ThsClient()

    class FakeThs:
        @staticmethod
        def tick_level1(thscode):
            assert thscode == "USHA600519"
            return Response(
                [
                    {
                        "时间": 1794359701 + index,
                        "价格": 1400 + index,
                        "成交方向": 1,
                        "交易笔数": 2,
                        "当前量": 300,
                    }
                    for index in range(4)
                ]
            )

    client._ths = FakeThs()
    result = client.tick("600519", count=2)
    assert result["count"] == 2
    assert result["items"][0]["1"] == 1794359703
    assert result["items"][-1]["10"] == 1403
    assert result["items"][-1]["12"] == 1
    assert result["items"][-1]["18"] == 2
    assert result["items"][-1]["49"] == 300


def test_ths_blocks_retries_empty_directory(monkeypatch):
    client = mq.ThsClient()
    calls = 0

    def fake_industry():
        nonlocal calls
        calls += 1
        if calls == 1:
            return Response([])
        return Response([{"代码": "URFI881273", "名称": "白酒"}])

    class FakeThs:
        @staticmethod
        def ths_industry():
            return fake_industry()

        @staticmethod
        def ths_concept():
            return Response([])

    client._ths = FakeThs()
    monkeypatch.setattr(mq.time, "sleep", lambda _: None)
    result = client.blocks("白酒")

    assert calls == 2
    assert result["items"] == [
        {"block_code": "URFI881273", "name": "白酒", "kind": "industry"}
    ]


def test_fields_catalog_filters_data_type_and_query():
    result = mq.load_catalog("fields", query="最新价", limit=5, data_type="tick")
    assert result["count"] == 1
    assert result["items"][0]["fieldId"] == "10"
    assert result["items"][0]["dataType"] == "tick"


def test_ths_client_keeps_machine_stdout_clean(monkeypatch, capsys):
    class FakeThs:
        def __init__(self):
            print("多数据返回: 2")

        def connect(self):
            print("connect diagnostic")

        def disconnect(self):
            print("disconnect diagnostic")

    monkeypatch.setitem(sys.modules, "thsdk", SimpleNamespace(THS=FakeThs))
    with mq.ThsClient():
        pass
    assert capsys.readouterr().out == ""


def test_status_probe_requires_a_live_channel(monkeypatch):
    class FailingThsClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def search(self, *args, **kwargs):
            raise RuntimeError("ths unavailable")

    class FailingCloudClient:
        def __init__(self, *args, **kwargs):
            pass

        def search(self, *args, **kwargs):
            raise RuntimeError("cloud unavailable")

    monkeypatch.setitem(sys.modules, "thsdk", SimpleNamespace(THS=object))
    monkeypatch.setenv("FUYAO_API_KEY", "test-key")
    monkeypatch.delenv("IWENCAI_API_KEY", raising=False)
    monkeypatch.delenv("WENCAI_API_KEY", raising=False)
    monkeypatch.setattr(mq, "ThsClient", FailingThsClient)
    monkeypatch.setattr(mq, "CloudClient", FailingCloudClient)

    payload = mq.status_payload(probe=True)

    assert payload["ok"] is False
    assert payload["thsdk"]["probe"]["ok"] is False
    assert payload["cloud_api"]["probe"]["ok"] is False


def test_status_probe_passes_when_cloud_channel_is_live(monkeypatch):
    class FailingThsClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def search(self, *args, **kwargs):
            raise RuntimeError("ths unavailable")

    class LiveCloudClient:
        def __init__(self, *args, **kwargs):
            pass

        def search(self, *args, **kwargs):
            return {"items": [{"thscode": "USHA600519"}]}

    monkeypatch.setitem(sys.modules, "thsdk", SimpleNamespace(THS=object))
    monkeypatch.setenv("FUYAO_API_KEY", "test-key")
    monkeypatch.delenv("IWENCAI_API_KEY", raising=False)
    monkeypatch.delenv("WENCAI_API_KEY", raising=False)
    monkeypatch.setattr(mq, "ThsClient", FailingThsClient)
    monkeypatch.setattr(mq, "CloudClient", LiveCloudClient)

    payload = mq.status_payload(probe=True)

    assert payload["ok"] is True
    assert payload["thsdk"]["probe"]["ok"] is False
    assert payload["cloud_api"]["probe"]["ok"] is True


def test_status_probe_passes_when_wencai_channel_is_live(monkeypatch):
    class FailingThsClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def search(self, *args, **kwargs):
            raise RuntimeError("ths unavailable")

    class LiveWencaiClient:
        def __init__(self, *args, **kwargs):
            pass

        def query(self, *args, **kwargs):
            return {"datas": [{"股票代码": "600519.SH"}], "columns": ["股票代码"]}

    monkeypatch.setitem(sys.modules, "thsdk", SimpleNamespace(THS=object))
    monkeypatch.delenv("FUYAO_API_KEY", raising=False)
    monkeypatch.delenv("HITHINK_API_KEY", raising=False)
    monkeypatch.delenv("HITHINK_FINANCE_API_KEY", raising=False)
    monkeypatch.setenv("IWENCAI_API_KEY", "test-key")
    monkeypatch.setattr(mq, "ThsClient", FailingThsClient)
    monkeypatch.setattr(mq, "WencaiClient", LiveWencaiClient)

    payload = mq.status_payload(probe=True)

    assert payload["ok"] is True
    assert payload["thsdk"]["probe"]["ok"] is False
    assert payload["cloud_api"]["probe"]["ok"] is False
    assert payload["wencai"]["probe"]["ok"] is True


def test_suppress_native_stdout_blocks_fd_writes(capfd):
    with mq.suppress_native_stdout():
        os.write(1, b"native diagnostic\n")
    print("json output")
    captured = capfd.readouterr()
    assert "native diagnostic" not in captured.out
    assert "json output" in captured.out


def test_cloud_news_uses_stock_timeline_endpoint(monkeypatch):
    client = mq.CloudClient(key="test-key")
    captured = {}

    def fake_get(path, params=None):
        captured["path"] = path
        captured["params"] = params
        return {
            "code": 0,
            "data": {
                "items": [{"id": "1", "title": "新闻"}],
                "has_more": False,
                "offset": "next",
            },
            "request_id": "r3",
        }

    monkeypatch.setattr(client, "get", fake_get)
    result = client.news("600519", count=5)
    assert captured["path"] == "/api/news/stock/timeline-list"
    assert captured["params"]["thscode"] == "600519.SH"
    assert result["items"][0]["_category"] == "新闻"


def test_cloud_sector_preserves_vendor_index_code(monkeypatch):
    client = mq.CloudClient(key="test-key")
    captured = {}
    monkeypatch.setattr(
        client,
        "search",
        lambda *args, **kwargs: {
            "items": [
                {
                    "name": "中证白酒",
                    "thscode": "USZA399997",
                    "vendor_thscode": "399997.SZ",
                    "ticker": "399997",
                    "exchange": "SZ",
                    "asset_type": "a-share-index",
                }
            ]
        },
    )

    def fake_get(path, params=None):
        if path == "/api/a-share-index/constituents/ths-stock-list":
            captured["members_params"] = params
            return {"code": 0, "data": {"item": [{"thscode": "600519.SH"}]}}
        if path == "/api/a-share-index/prices/snapshot":
            captured["snapshot_params"] = params
            return {
                "code": 0,
                "data": {
                    "item": [
                        {
                            "thscode": "399997.SZ",
                            "last_price": 1000,
                            "price_change_ratio_pct": 1.2,
                        }
                    ]
                },
            }
        raise AssertionError(path)

    monkeypatch.setattr(client, "get", fake_get)
    result = client.sector("中证白酒")
    assert result["sector"]["thscode"] == "399997.SZ"
    assert captured["members_params"]["thscode"] == "399997.SZ"
    assert captured["snapshot_params"]["thscodes"] == "399997.SZ"
    assert result["snapshot"]["最新价"] == 1000
    assert result["snapshot_error"] == ""


def test_cloud_ti_sector_resolves_display_name(monkeypatch):
    client = mq.CloudClient(key="test-key")
    captured = {}
    monkeypatch.setattr(
        client,
        "search",
        lambda *args, **kwargs: {
            "items": [
                {
                    "name": "白酒",
                    "thscode": "881273.TI",
                    "vendor_thscode": "881273.TI",
                    "ticker": "881273",
                    "exchange": None,
                    "asset_type": "a-share-index",
                }
            ]
        },
    )

    def fake_get(path, params=None):
        if path == "/api/a-share-index/constituents/ths-stock-list":
            captured["members_params"] = params
            return {"code": 0, "data": {"item": [{"thscode": "600519.SH", "name": "贵州茅台"}]}}
        if path == "/api/a-share-index/prices/snapshot":
            captured["snapshot_params"] = params
            return {
                "code": 0,
                "data": {
                    "item": [
                        {
                            "thscode": "881273.TI",
                            "last_price": 2090.073,
                            "price_change_ratio_pct": -3.08036,
                        }
                    ]
                },
            }
        raise AssertionError(path)

    monkeypatch.setattr(client, "get", fake_get)
    result = client.sector("881273.TI")
    assert result["sector"]["name"] == "白酒"
    assert result["sector"]["thscode"] == "881273.TI"
    assert captured["members_params"]["thscode"] == "881273.TI"
    assert captured["snapshot_params"]["thscodes"] == "881273.TI"
    assert result["snapshot"]["代码"] == "URFI881273"
    assert result["snapshot"]["涨幅"] == -3.08036


def test_redact_removes_environment_key(monkeypatch):
    monkeypatch.setenv("HITHINK_API_KEY", "secret-value")
    assert "secret-value" not in mq.redact("failed with secret-value")


def test_cloud_api_key_prefers_explicit_fuyao_key(monkeypatch):
    monkeypatch.setenv("HITHINK_FINANCE_API_KEY", "cli-key")
    monkeypatch.setenv("FUYAO_API_KEY", "fuyao-key")
    assert mq.cloud_api_key() == ("fuyao-key", "env:FUYAO_API_KEY")


def test_cloud_realtime_fills_missing_name(monkeypatch):
    client = mq.CloudClient(key="test-key")

    def fake_get(path, params=None):
        if path == "/api/a-share/prices/snapshot":
            return {
                "data": {
                    "item": [
                        {
                            "thscode": "600519.SH",
                            "ticker": "600519",
                            "last_price": 1402.3,
                            "price_change_ratio_pct": -2.55,
                        }
                    ]
                }
            }
        if path == "/api/meta/tickers/search":
            return {
                "data": {
                    "item": [
                        {
                            "thscode": "600519.SH",
                            "ticker": "600519",
                            "name": "贵州茅台",
                        }
                    ]
                }
            }
        raise AssertionError(path)

    monkeypatch.setattr(client, "get", fake_get)
    result = client.realtime(["600519"])
    assert result["data"]["USHA600519"]["name"] == "贵州茅台"
    assert result["data"]["USHA600519"]["55"] == "贵州茅台"


def test_cloud_sort_filters_market_scope_and_paginates(monkeypatch):
    client = mq.CloudClient(key="test-key")
    rows = [
        {"thscode": "600519.SH", "last_price": 1400, "prev_price": 1390, "price_change_ratio_pct": 0.72},
        {"thscode": "000001.SZ", "last_price": 11, "prev_price": 10, "price_change_ratio_pct": 10.0},
        {"thscode": "920001.BJ", "last_price": 20, "prev_price": 19, "price_change_ratio_pct": 5.0},
    ]
    monkeypatch.setattr(client, "_snapshot_rows", lambda: (rows, 1))
    monkeypatch.setattr(
        client,
        "ticker_names",
        lambda: {
            "600519.SH": "贵州茅台",
            "000001.SZ": "平安银行",
            "920001.BJ": "北交样本",
        },
    )

    result = client.sort(block="14", sort_field=199112, sort_order=1, count=10)

    assert result["total"] == 2
    assert [item["security"] for item in result["items"]] == [
        "USZA000001",
        "USHA600519",
    ]
    assert result["items"][0]["name"] == "平安银行"
    assert result["items"][0]["rank"] == 1


def test_cloud_sort_reports_premarket_missing_values_without_fabricating(monkeypatch):
    client = mq.CloudClient(key="test-key")
    rows = [
        {
            "thscode": "600519.SH",
            "last_price": None,
            "prev_price": 1390,
            "price_change_ratio_pct": None,
        },
        {
            "thscode": "000001.SZ",
            "last_price": None,
            "prev_price": 10,
            "price_change_ratio_pct": None,
        },
        {
            "thscode": "920001.BJ",
            "last_price": 20,
            "prev_price": 19,
            "price_change_ratio_pct": 5.0,
        },
    ]
    monkeypatch.setattr(client, "_snapshot_rows", lambda: (rows, 1794355200))
    monkeypatch.setattr(client, "ticker_names", lambda: {})

    result = client.sort(block="14", sort_field=199112, sort_order=1, count=10)

    assert result["total"] == 0
    assert result["items"] == []
    assert result["missing_count"] == 2
    assert result["timestamp"] == 1794355200


def test_ths_sort_supports_block_members_and_ordering(monkeypatch):
    client = mq.ThsClient()
    calls = []

    class FakeThs:
        @staticmethod
        def block(block_id):
            calls.append(("block", block_id))
            return Response(
                [
                    {"代码": "USHA600519"},
                    {"代码": "USZA000001"},
                ]
            )

        @staticmethod
        def market_data_cn(codes, query):
            calls.append(("quotes", codes, query))
            assert query == "基础数据"
            return Response(
                [
                    {
                        "代码": "USHA600519",
                        "名称": "贵州茅台",
                        "价格": 1402.3,
                        "昨收价": 1439,
                        "涨幅": -1.2,
                        "成交量": 100,
                        "总金额": 280460,
                    },
                    {
                        "代码": "USZA000001",
                        "名称": "平安银行",
                        "价格": 11.2,
                        "昨收价": 10,
                        "涨幅": 12.0,
                        "成交量": 200,
                        "总金额": 2240,
                    },
                ]
            )

    client._ths = FakeThs()
    result = client.sort(block=14, sort_field=199112, sort_order=1, count=1)

    assert calls[0] == ("block", 14)
    assert result["total"] == 2
    assert result["items"][0]["security"] == "USZA000001"
    assert result["items"][0]["name"] == "平安银行"
    assert result["items"][0]["rank"] == 1
    assert result["items"][0]["fields"]["199112"] == 12.0
    assert result["items"][0]["fields"]["264648"] == pytest.approx(1.2)


def test_watchlist_reads_ths_selfstock_cache(tmp_path):
    path = tmp_path / "SelfStockCache.json"
    path.write_text(
        '{"Data":{"Selfstock":"600519|000001|,17|33|","Count":2}}',
        encoding="utf-8",
    )

    result = mq.watchlist_payload(str(path))

    assert result["count"] == 2
    assert result["source"] == str(path)
    assert [item["security"] for item in result["securities"]] == [
        "USHA600519",
        "USZA000001",
    ]


def test_watchlist_reads_cloud_environment_codes(monkeypatch):
    monkeypatch.setenv("THS_SELFSTOCK_CODES", "600519, 000001.SZ；300750")
    monkeypatch.delenv("THS_SELFSTOCK_PATH", raising=False)
    monkeypatch.delenv("THS_SELFSTOCK_JSON", raising=False)

    result = mq.watchlist_payload()

    assert result["count"] == 3
    assert result["source"] == "env:THS_SELFSTOCK_CODES"
    assert [item["security"] for item in result["securities"]] == [
        "USHA600519",
        "USZA000001",
        "USZA300750",
    ]


def test_watchlist_reads_cloud_environment_json_object(monkeypatch):
    monkeypatch.delenv("THS_SELFSTOCK_CODES", raising=False)
    monkeypatch.delenv("THS_SELFSTOCK_PATH", raising=False)
    monkeypatch.setenv(
        "THS_SELFSTOCK_JSON",
        '{"stocks":[{"code":"600519","market":"17"},{"code":"000001","market":"33"}]}',
    )

    result = mq.watchlist_payload()

    assert result["count"] == 2
    assert result["source"] == "env:THS_SELFSTOCK_JSON"
    assert [item["security"] for item in result["securities"]] == [
        "USHA600519",
        "USZA000001",
    ]


def test_sectors_lists_default_watchlist_group(tmp_path):
    path = tmp_path / "SelfStockInfo.json"
    path.write_text(
        '[{"C":"600519","M":"17"},{"C":"920001","M":"20"}]',
        encoding="utf-8",
    )

    result = mq.sectors_payload(str(path))

    assert result["count"] == 1
    assert result["items"][0]["sectorId"] == "-1"
    assert result["items"][0]["count"] == 2


def test_subscribe_is_a_one_shot_snapshot_and_filters_fields(monkeypatch):
    client = mq.ThsClient()
    monkeypatch.setattr(
        client,
        "realtime",
        lambda target: {
            "securities": [{"thscode": "USHA600519"}],
            "data": {
                "USHA600519": {
                    "10": 1402.3,
                    "55": "贵州茅台",
                    "13": 100,
                }
            },
        },
    )
    args = SimpleNamespace(
        subscribe_api="SubscribeRealtime",
        target="600519",
        fields="10,55",
        period=1,
        count=60,
        adjust=1,
        timeout_ms=8000,
    )

    result = mq.subscribe_payload(client, args, "ths")

    assert result["api"] == "SubscribeRealtime"
    assert result["mode"] == "one_shot"
    assert result["timeout_ms"] == 8000
    assert result["push"]["data"]["USHA600519"] == {
        "10": 1402.3,
        "55": "贵州茅台",
    }


def test_subscribe_intraday_candle_defaults_to_period_five():
    args = mq.build_parser().parse_args(
        ["subscribe", "--api", "SubscribeIntradayCandle", "--target", "600519"]
    )

    assert args.period == 5


def test_call_sort_query_maps_desktop_arguments(monkeypatch):
    client = mq.CloudClient(key="test-key")
    captured = {}

    def fake_sort(block, sort_field, sort_order, offset, count, exclude_blocks):
        captured.update(
            {
                "block": block,
                "sort_field": sort_field,
                "sort_order": sort_order,
                "offset": offset,
                "count": count,
                "exclude_blocks": exclude_blocks,
            }
        )
        return {"items": []}

    monkeypatch.setattr(client, "sort", fake_sort)
    args = SimpleNamespace(
        tool="sort_query",
        call_args={
            "block": 14,
            "sortField": 199112,
            "sortOrder": 0,
            "offset": 5,
            "count": 20,
            "excludeBlocks": "21",
        },
    )

    result = mq.call_payload(client, args, "cloud")

    assert result["tool"] == "sort_query"
    assert captured == {
        "block": "14",
        "sort_field": 199112,
        "sort_order": 0,
        "offset": 5,
        "count": 20,
        "exclude_blocks": "21",
    }


def test_call_wencai_query_uses_thsdk_and_paginates():
    client = mq.ThsClient()

    class FakeThs:
        @staticmethod
        def wencai_nlp(condition):
            assert condition == "今日涨幅前5"
            return Response(
                [
                    {"代码": "600519", "名称": "贵州茅台", "涨幅": 1.2},
                    {"代码": "000001", "名称": "平安银行", "涨幅": 0.8},
                    {"代码": "300750", "名称": "宁德时代", "涨幅": 0.5},
                ]
            )

    client._ths = FakeThs()
    args = SimpleNamespace(
        tool="wencai_query",
        call_args={"query": "今日涨幅前5", "page": 2, "limit": 1},
    )

    result = mq.call_payload(client, args, "ths")

    assert result == {
        "tool": "wencai_query",
        "source": "ths",
        "result": {
            "datas": [{"代码": "000001", "名称": "平安银行", "涨幅": 0.8}],
            "columns": ["代码", "名称", "涨幅"],
            "row_count": 3,
            "status_code": 0,
        },
    }


def test_call_wencai_query_cloud_requires_wencai_key(monkeypatch):
    monkeypatch.delenv("IWENCAI_API_KEY", raising=False)
    monkeypatch.delenv("WENCAI_API_KEY", raising=False)
    client = mq.CloudClient(key="test-key")
    args = SimpleNamespace(
        tool="wencai_query",
        call_args={"query": "今日涨幅前5", "limit": 5},
    )

    with pytest.raises(mq.QueryError, match="IWENCAI_API_KEY"):
        mq.call_payload(client, args, "cloud")


def test_wencai_client_posts_official_contract(monkeypatch):
    if mq.requests is None:
        pytest.skip("requests is not installed")
    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {
                "status_code": 0,
                "data": {
                    "datas": [{"股票代码": "600519.SH", "最新价": 1395.22}],
                    "columns": ["股票代码", "最新价"],
                },
            }

    def fake_post(url, headers=None, json=None, timeout=None, allow_redirects=None):
        captured.update(
            {
                "url": url,
                "headers": headers,
                "body": json,
                "timeout": timeout,
                "allow_redirects": allow_redirects,
            }
        )
        return FakeResponse()

    monkeypatch.setattr(mq.requests, "post", fake_post)
    result = mq.WencaiClient("test-wencai-key", timeout=9).query(
        "hithink-market-query",
        "贵州茅台最新价",
        page=2,
        limit=3,
    )

    assert captured["url"] == "https://openapi.iwencai.com/v1/query2data"
    assert captured["headers"]["Authorization"] == "Bearer test-wencai-key"
    assert captured["headers"]["X-Claw-Skill-Id"] == "hithink-market-query"
    assert captured["headers"]["X-Claw-Skill-Version"] == "1.0.0"
    assert captured["headers"]["X-Claw-Plugin-Id"] == "none"
    assert len(captured["headers"]["X-Claw-Trace-Id"]) == 64
    assert captured["body"] == {
        "query": "贵州茅台最新价",
        "page": "2",
        "limit": "3",
        "is_cache": "1",
        "expand_index": "true",
    }
    assert captured["timeout"] == 9
    assert captured["allow_redirects"] is False
    assert result == {
        "datas": [{"股票代码": "600519.SH", "最新价": 1395.22}],
        "columns": ["股票代码", "最新价"],
    }


def test_wencai_client_rejects_unknown_skill_and_business_error(monkeypatch):
    with pytest.raises(mq.QueryError, match="未知问财 skillId"):
        mq.WencaiClient("key").query("unknown-skill", "贵州茅台")

    if mq.requests is None:
        pytest.skip("requests is not installed")

    class FakeResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"status_code": 2001, "status_msg": "invalid token"}

    monkeypatch.setattr(mq.requests, "post", lambda *args, **kwargs: FakeResponse())
    with pytest.raises(mq.QueryError, match="问财 OpenAPI 返回错误"):
        mq.WencaiClient("key").query("hithink-market-query", "贵州茅台")


def test_wencai_query_payload_prefers_official_key(monkeypatch):
    monkeypatch.setenv("IWENCAI_API_KEY", "test-key")

    def fake_query(self, skill_id, query, page=1, limit=10):
        assert skill_id == "hithink-finance-query"
        assert query == "贵州茅台营收"
        assert page == 2
        assert limit == 5
        return {"datas": [], "columns": [], "status_code": 0}

    monkeypatch.setattr(mq.WencaiClient, "query", fake_query)
    result = mq.wencai_query_payload(
        {
            "skillId": "hithink-finance-query",
            "query": "贵州茅台营收",
            "page": 2,
            "limit": 5,
        },
        "cloud",
    )
    assert result["source"] == "wencai"
    assert result["result"]["status_code"] == 0


def test_run_action_wencai_does_not_require_fuyao_key(monkeypatch):
    monkeypatch.setenv("IWENCAI_API_KEY", "test-key")
    for name in ("FUYAO_API_KEY", "HITHINK_API_KEY", "HITHINK_FINANCE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        mq.WencaiClient,
        "query",
        lambda self, skill_id, query, page=1, limit=10: {
            "datas": [{"股票代码": "600519.SH"}],
            "columns": ["股票代码"],
            "status_code": 0,
        },
    )
    args = SimpleNamespace(
        action="call",
        tool="wencai_query",
        call_args={"skillId": "hithink-market-query", "query": "贵州茅台"},
        mode="cloud",
        include_meta=False,
    )

    result = mq.run_action(args)

    assert result["source"] == "wencai"
    assert result["result"]["datas"] == [{"股票代码": "600519.SH"}]


def _indicator_bars(count=80):
    bars = []
    for index in range(count):
        close = float(index + 1)
        bars.append(
            {
                "time": 1_700_000_000 + index * 86_400,
                "1": 20240101,
                "8": close + 1,
                "9": close - 1,
                "11": close,
                "13": 100 + index,
            }
        )
    return bars


class IndicatorClient:
    def __init__(self):
        self.bars = _indicator_bars()
        self.calls = []

    def candle(self, code, period=5, count=60, adjust=1):
        self.calls.append(
            {"code": code, "period": period, "count": count, "adjust": adjust}
        )
        return {"data": {mq.normalize_thscode(code): self.bars}}


def test_indicator_payload_latest_and_series():
    client = IndicatorClient()
    indicators = ["MA5", "MACD", "RSI14", "KDJ", "BOLL", "ATR14", "OBV", "VOL_MA5", "量比", "振幅"]
    latest = mq.indicator_payload(
        client,
        {
            "securities": ["600519"],
            "period": "day",
            "indicators": indicators,
            "mode": "latest",
        },
    )

    assert latest["success"] is True
    assert latest["bars"] == 1
    assert latest["indicators"] == indicators
    assert latest["data"]["USHA600519"]["values"]["MA5"] == 78.0
    assert set(latest["data"]["USHA600519"]["values"]) == set(indicators)
    assert latest["history"]["USHA600519"]["actualBars"] == 80
    assert latest["history"]["USHA600519"]["status"] == "insufficient_history"
    assert client.calls == [
        {"code": "USHA600519", "period": 5, "count": 750, "adjust": 1}
    ]

    series = mq.indicator_payload(
        client,
        {
            "securities": ["600519"],
            "period": "day",
            "indicators": ["MA5"],
            "mode": "series",
            "bars": 5,
        },
    )
    assert len(series["data"]["USHA600519"]) == 5
    assert series["data"]["USHA600519"][-1]["values"]["MA5"] == 78.0
    assert isinstance(series["data"]["USHA600519"][0]["time"], int)


def test_indicator_payload_validates_period_indicator_and_cloud_scope():
    client = IndicatorClient()
    with pytest.raises(mq.QueryError, match="不支持的技术指标"):
        mq.indicator_payload(
            client,
            {"securities": ["600519"], "indicators": ["NOT_AN_INDICATOR"]},
        )
    with pytest.raises(mq.QueryError, match="不支持的周期"):
        mq.indicator_payload(
            client,
            {"securities": ["600519"], "indicators": ["MA5"], "period": "year"},
        )
    with pytest.raises(mq.QueryError, match="扶摇公开 REST 只提供日 K"):
        mq.indicator_payload(
            mq.CloudClient(key="test-key"),
            {"securities": ["600519"], "indicators": ["MA5"], "period": "week"},
        )


def test_call_indicator_query_is_allowlisted_and_dispatched():
    parser = mq.build_parser()
    args = parser.parse_args(
        [
            "call",
            "--tool",
            "indicator_query",
            "--arguments-json",
            '{"securities":["600519"],"indicators":["MA5"],"mode":"latest"}',
            "--mode",
            "cloud",
        ]
    )
    args.call_args = {
        "securities": ["600519"],
        "indicators": ["MA5"],
        "mode": "latest",
    }
    result = mq.call_payload(IndicatorClient(), args, "cloud", mode="cloud")
    assert result["tool"] == "indicator_query"
    assert result["result"]["data"]["USHA600519"]["values"]["MA5"] == 78.0
