"""#521/#522 fina_indicator 披露增量 + fund_portfolio 双模式单测."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import httpx
import orjson
import polars as pl
import pytest
from ditto_data.config import DataSourceSettings
from ditto_data.sources.base import SourceFetchError
from ditto_data.sources.tushare._fundamental import (
    fetch_fina_indicator,
    fetch_fund_portfolio,
)
from ditto_data.sources.tushare.adapters.fundamental import FundamentalTushareAdapter
from ditto_data.sources.tushare.client import TushareClient


@pytest.mark.unit
def test_vip_indicator_does_not_treat_provider_cap_as_complete(respx_mock) -> None:
    """A short capped page and redundant rows must not lose later disclosures."""
    rows = [
        {
            "ts_code": f"{600000 + index}.SH",
            "ann_date": "20261030",
            "end_date": "20260930",
            "eps": 3.5,
            "update_flag": "1",
        }
        for index in range(600)
    ]
    rows.insert(1, dict(rows[0]))

    def respond(request: httpx.Request) -> httpx.Response:
        body = orjson.loads(request.content)
        assert body["api_name"] == "fina_indicator_vip"
        fields = body["fields"].split(",")
        params = body["params"]
        offset = params.get("offset", 0)
        page = rows[offset : offset + min(params.get("limit", 2000), 500)]
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "fields": fields,
                    "items": [[row.get(field) for field in fields] for row in page],
                },
            },
        )

    respx_mock.post("http://api.tushare.pro/").mock(side_effect=respond)
    with TushareClient(settings=DataSourceSettings(tushare_token="recorded")) as client:
        result = FundamentalTushareAdapter(_client=client).fetch_fina_indicator_vip(
            period="20260930"
        )
    assert result.height == 600
    assert result.filter(pl.col("source_ticker") == "600599.SH")["eps"].item() == 3.5


def _compact(value: str) -> str:
    return value.replace("-", "")


@pytest.mark.unit
class TestFinaIndicatorDisclosureDelta:
    """fina_indicator 复用三表披露增量语义：近期报告期超集 + kd 截止过滤."""

    def test_trade_date_pulls_recent_periods_and_filters_future_knowledge(self) -> None:
        fundamental = MagicMock(spec=FundamentalTushareAdapter)
        # 两期响应：Q2 披露日早于截止日保留；Q3 披露日晚于截止日剔除
        # adapter 输出契约：ts_code→source_ticker、ann_date→knowledge_date、
        # end_date→report_date（指标列透传）
        fundamental.fetch_fina_indicator_vip.side_effect = [
            pl.DataFrame(
                {
                    "source_ticker": ["600519.SH"],
                    "knowledge_date": [date(2026, 7, 21)],
                    "report_date": [date(2026, 6, 30)],
                    "eps": [33.19],
                    "roe": [19.2],
                }
            ),
            pl.DataFrame(
                {
                    "source_ticker": ["600519.SH"],
                    "knowledge_date": [date(2026, 10, 28)],
                    "report_date": [date(2026, 9, 30)],
                    "eps": [45.0],
                    "roe": [21.0],
                }
            ),
        ] + [
            pl.DataFrame(
                schema={
                    "source_ticker": pl.String,
                    "knowledge_date": pl.Date,
                    "report_date": pl.Date,
                }
            )
        ] * 6

        result = fetch_fina_indicator(fundamental, trade_date="2026-09-30")

        assert result.height == 1
        row = result.row(0, named=True)
        assert row["knowledge_date"] == date(2026, 7, 21)
        assert row["report_date"] == date(2026, 6, 30)
        # 指标列透传：未在 mapping 声明的列原样带出
        assert row["eps"] == pytest.approx(33.19)
        fundamental.fetch_fina_indicator.assert_not_called()
        assert fundamental.fetch_fina_indicator_vip.call_count == 8

    def test_instrument_mode_filters_disclosures_after_fetching_history(self) -> None:
        fundamental = MagicMock(spec=FundamentalTushareAdapter)
        fundamental.fetch_fina_indicator_vip.return_value = pl.DataFrame(
            {
                "source_ticker": ["600519.SH"] * 5,
                "knowledge_date": [
                    date(2026, 1, 1),
                    date(2026, 6, 30),
                    date(2025, 12, 31),
                    date(2026, 7, 1),
                    None,
                ],
                "report_date": [date(2024, 3, 31)] * 5,
                "eps": [19.16, 19.17, 19.18, 19.19, 19.20],
            }
        )
        result = fetch_fina_indicator(
            fundamental,
            source_ticker="600519.SH",
            start_date="2026-01-01",
            end_date="2026-06-30",
        )
        fundamental.fetch_fina_indicator_vip.assert_called_once_with(
            ts_code="600519.SH"
        )
        assert result["eps"].to_list() == [19.16, 19.17]
        fundamental.fetch_fina_indicator.assert_not_called()


@pytest.mark.unit
class TestFundPortfolioModes:
    """fund_portfolio 公告日驱动（日更）/报告期窗口（按基金回填）."""

    def test_market_request_uses_exact_announcement_day(self) -> None:
        fundamental = MagicMock(spec=FundamentalTushareAdapter)
        fundamental.fetch_fund_portfolio.return_value = pl.DataFrame(
            {"source_ticker": ["000001.OF", "510300.SH"]}
        )
        result = fetch_fund_portfolio(fundamental, _compact, trade_date="2026-07-21")
        assert result.height == 2
        fundamental.fetch_fund_portfolio.assert_called_once_with(
            ts_code=None, ann_date="20260721"
        )

    def test_trade_date_queries_one_fund(self) -> None:
        fundamental = MagicMock(spec=FundamentalTushareAdapter)
        fundamental.fetch_fund_portfolio.return_value = pl.DataFrame(
            {"source_ticker": ["000001.OF"]}
        )
        result = fetch_fund_portfolio(
            fundamental,
            _compact,
            trade_date="2026-07-21",
            source_ticker="000001.OF",
        )
        assert result["source_ticker"].to_list() == ["000001.OF"]
        fundamental.fetch_fund_portfolio.assert_called_once_with(
            ts_code="000001.OF", ann_date="20260721"
        )

    def test_instrument_mode_uses_report_range_and_filters_late_disclosure(
        self,
    ) -> None:
        fundamental = MagicMock(spec=FundamentalTushareAdapter)
        fundamental.fetch_fund_portfolio.return_value = pl.DataFrame(
            {
                "source_ticker": ["510300.SH", "510300.SH"],
                "report_date": [date(2026, 3, 31), date(2026, 6, 30)],
                "knowledge_date": [date(2026, 4, 22), date(2026, 7, 21)],
                "holding_symbol": ["600519.SH", "600519.SH"],
                "market_value": [1.0, 1.5],
            }
        )
        result = fetch_fund_portfolio(
            fundamental,
            _compact,
            source_ticker="510300.SH",
            start_date="2026-04-01",
            end_date="2026-05-31",
        )

        fundamental.fetch_fund_portfolio.assert_called_once_with(
            ts_code="510300.SH", start_date="20251231", end_date="20260531"
        )
        # 披露晚于 end_date 的 Q2 行被剔除，只剩 Q1
        assert result.height == 1
        assert result.row(0, named=True)["report_date"] == date(2026, 3, 31)

    @pytest.mark.pit
    def test_ann_date_filtered_source_keeps_tail_and_rejects_future(self) -> None:
        fundamental = MagicMock(spec=FundamentalTushareAdapter)
        observed = pl.DataFrame(
            {
                "source_ticker": ["561250.SH"] * 3,
                "report_date": [date(2026, 9, 30)] * 3,
                "knowledge_date": [
                    date(2026, 10, 26),
                    date(2026, 11, 5),
                    date(2026, 11, 6),
                ],
                "market_value": [1.0, 2.0, 999999.0],
            }
        )
        # Live #708 probe: this route returns nothing until the announcement
        # date, even though the report period is already September 30.
        fundamental.fetch_fund_portfolio.side_effect = lambda **params: (
            observed if params["end_date"] >= "20261026" else observed.head(0)
        )
        for cutoff, expected in [
            ("2026-11-05", [1.0, 2.0]),
            ("2026-11-06", [1.0, 2.0, 999999.0]),
        ]:
            result = fetch_fund_portfolio(
                fundamental,
                _compact,
                source_ticker="561250.SH",
                start_date="2014-01-01",
                end_date=cutoff,
            )
            assert result["market_value"].to_list() == expected

    def test_requires_mode_arguments(self) -> None:
        fundamental = MagicMock(spec=FundamentalTushareAdapter)
        with pytest.raises(ValueError, match="source_ticker"):
            fetch_fund_portfolio(fundamental, _compact)
        with pytest.raises(ValueError, match="start_date and end_date"):
            fetch_fund_portfolio(fundamental, _compact, source_ticker="510300.SH")


@pytest.mark.unit
class TestFinaIndicatorDedupDeterminism:
    """#521 验收「多版本去重有测试锁定」：确定性 keep-one + 数值归一."""

    def _duplicate_rows(self) -> pl.DataFrame:
        base = {
            "source_ticker": ["600519.SH", "600519.SH"],
            "report_date": [date(2026, 6, 30), date(2026, 6, 30)],
            "knowledge_date": [date(2026, 7, 21), date(2026, 7, 21)],
            "eps": [33.19, 33.20],
            "roe": [19.2, 19.3],
        }
        return pl.DataFrame(base)

    def test_same_rows_both_orders_yield_identical_output(self) -> None:
        from ditto_data.sources.tushare.adapters.fundamental import (
            _dedupe_fina_disclosure_key,
        )

        forward = _dedupe_fina_disclosure_key(self._duplicate_rows())
        reversed_ = _dedupe_fina_disclosure_key(self._duplicate_rows().reverse())
        assert forward.height == 1
        assert reversed_.height == 1
        assert forward.equals(reversed_)

    def test_numeric_passthrough_columns_normalized_to_float(self) -> None:
        from ditto_data.sources.tushare.adapters.fundamental import (
            _normalize_fina_numeric_columns,
        )

        frame = pl.DataFrame(
            {
                "source_ticker": ["600519.SH"],
                "report_date": [date(2026, 6, 30)],
                "knowledge_date": [date(2026, 7, 21)],
                "eps": [33],
                "roe": [19.2],
            }
        )
        normalized = _normalize_fina_numeric_columns(frame)
        assert normalized["eps"].dtype == pl.Float64
        assert normalized["roe"].dtype == pl.Float64
        assert normalized["source_ticker"].dtype == pl.String

    def test_vip_fetch_dedupes_same_disclosure_key(self) -> None:
        from unittest.mock import MagicMock

        from ditto_data.sources.tushare.adapters.fundamental import (
            FundamentalTushareAdapter,
        )

        client = MagicMock()
        # client 返回原始列形状（transform 前端）：ts_code/ann_date/end_date
        client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["600519.SH", "600519.SH"],
                "ann_date": ["20260721", "20260721"],
                "end_date": ["20260630", "20260630"],
                "eps": [33.19, 33.20],
                "roe": [19.2, 19.3],
            }
        )
        adapter = FundamentalTushareAdapter(_client=client)

        frame = adapter.fetch_fina_indicator_vip(period="20260630")

        assert frame.height == 1
        assert frame["eps"].dtype == pl.Float64

    def _flag_version_rows(self) -> pl.DataFrame:
        # #591 形态：同披露键 update_flag 0/1 共存，旧版 null 新版有值
        return pl.DataFrame(
            {
                "source_ticker": ["600519.SH", "600519.SH"],
                "report_date": [date(2026, 3, 31), date(2026, 3, 31)],
                "knowledge_date": [date(2026, 4, 28), date(2026, 4, 28)],
                "update_flag": ["0", "1"],
                "fcff": [None, 1234.5],
                "fcfe": [None, 987.6],
            }
        )

    def test_flag_one_row_wins_over_flag_zero(self) -> None:
        from ditto_data.sources.tushare.adapters.fundamental import (
            _dedupe_fina_disclosure_key,
        )

        for order in (self._flag_version_rows(), self._flag_version_rows().reverse()):
            out = _dedupe_fina_disclosure_key(order)
            assert out.height == 1
            assert out["fcff"][0] == 1234.5
            assert out["fcfe"][0] == 987.6
            # 选版判别列完成使命后不进输出帧（store schema 不变）
            assert "update_flag" not in out.columns

    def test_flag_null_falls_back_to_hash_dedup(self) -> None:
        from ditto_data.sources.tushare.adapters.fundamental import (
            _dedupe_fina_disclosure_key,
        )

        frame = self._flag_version_rows().with_columns(
            pl.lit(None, dtype=pl.String).alias("update_flag")
        )
        out = _dedupe_fina_disclosure_key(frame)
        assert out.height == 1
        # 回退旧行为：确定性哈希选行，两序一致
        assert out.equals(_dedupe_fina_disclosure_key(frame.reverse()))
        assert "update_flag" not in out.columns

    def test_update_flag_stays_string_through_normalize(self) -> None:
        from ditto_data.sources.tushare.adapters.fundamental import (
            _normalize_fina_numeric_columns,
        )

        normalized = _normalize_fina_numeric_columns(self._flag_version_rows())
        assert normalized["update_flag"].dtype == pl.String
        assert normalized["fcff"].dtype == pl.Float64

    def test_numeric_update_flag_normalized_to_string(self) -> None:
        # correctness F2：源端改送数值 0/1 时不得 ComputeError
        from ditto_data.sources.tushare.adapters.fundamental import (
            _dedupe_fina_disclosure_key,
            _normalize_fina_numeric_columns,
        )

        frame = pl.DataFrame(
            {
                "source_ticker": ["600519.SH", "600519.SH"],
                "report_date": [date(2026, 3, 31)] * 2,
                "knowledge_date": [date(2026, 4, 28)] * 2,
                "update_flag": [0, 1],
                "fcff": [None, 1234.5],
            }
        )
        out = _dedupe_fina_disclosure_key(_normalize_fina_numeric_columns(frame))
        assert out.height == 1
        assert out["fcff"][0] == 1234.5

    def test_nonvip_fetch_survives_update_flag_without_f_ann_date(self) -> None:
        # correctness F1：非 VIP 请求集含 update_flag 且无 f_ann_date 时，
        # 不得命中财务三表的通用去重块（ColumnNotFoundError）
        from unittest.mock import MagicMock

        from ditto_data.sources.tushare.adapters.fundamental import (
            FundamentalTushareAdapter,
        )

        client = MagicMock()
        client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["600519.SH", "600519.SH"],
                "ann_date": ["20260428", "20260428"],
                "end_date": ["20260331", "20260331"],
                "update_flag": ["0", "1"],
                "eps": [None, 33.19],
                "fcff": [None, 1234.5],
            }
        )
        adapter = FundamentalTushareAdapter(_client=client)

        frame = adapter.fetch_fina_indicator(ts_code="600519.SH", period="20260331")

        assert frame.height == 1
        assert frame["fcff"][0] == 1234.5
        assert "update_flag" not in frame.columns

    def test_nonvip_fetch_empty_response_ok(self) -> None:
        from unittest.mock import MagicMock

        from ditto_data.sources.tushare.adapters.fundamental import (
            FundamentalTushareAdapter,
        )

        client = MagicMock()
        client.query.return_value = pl.DataFrame()
        adapter = FundamentalTushareAdapter(_client=client)

        frame = adapter.fetch_fina_indicator(ts_code="600519.SH")
        assert frame.height == 0


class TestFinaIndicatorCorrectionFlag:
    """#613 G:选版胜者携带修正标记列,供写入层单调升级。"""

    def test_flag_one_winner_carries_correction_marker(self) -> None:
        from ditto_data.sources.tushare.adapters.fundamental import (
            _dedupe_fina_disclosure_key,
        )
        from ditto_platform.foundation.storage import CORRECTION_FLAG_COLUMN

        frame = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ", "000001.SZ"],
                "knowledge_date": ["2026-04-28", "2026-04-28"],
                "report_date": ["2025-12-31", "2025-12-31"],
                "fcff": [None, 5.5e8],
                "update_flag": ["0", "1"],
            }
        )
        result = _dedupe_fina_disclosure_key(frame)
        assert result.height == 1
        assert result[CORRECTION_FLAG_COLUMN].to_list() == [True]

    def test_flag_zero_only_rows_carry_false_marker(self) -> None:
        from ditto_data.sources.tushare.adapters.fundamental import (
            _dedupe_fina_disclosure_key,
        )
        from ditto_platform.foundation.storage import CORRECTION_FLAG_COLUMN

        frame = pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "knowledge_date": ["2026-04-28"],
                "report_date": ["2025-12-31"],
                "fcff": [3.9e8],
                "update_flag": ["0"],
            }
        )
        result = _dedupe_fina_disclosure_key(frame)
        assert result[CORRECTION_FLAG_COLUMN].to_list() == [False]


def test_daily_rejects_multiple_codes_before_provider_request() -> None:
    from ditto_data.sources.tushare.adapters.stock import StockTushareAdapter

    client = MagicMock()
    adapter = StockTushareAdapter(_client=client)
    with pytest.raises(ValueError, match="single source_ticker"):
        adapter.fetch_stock_daily(
            source_ticker="000001.SZ,000002.SZ",
            start_date="2026-11-01",
            end_date="2026-11-05",
        )
    client.query.assert_not_called()


@pytest.mark.unit
def test_vip_single_code_rejects_ignored_selector() -> None:
    client = MagicMock(spec=TushareClient)
    client.query.return_value = pl.DataFrame({"ts_code": ["000001.SZ"]})
    with pytest.raises(SourceFetchError, match="outside requested ts_code"):
        FundamentalTushareAdapter(_client=client).fetch_fina_indicator_vip(
            ts_code="600519.SH"
        )
    assert client.query.call_args.kwargs["ts_code"] == "600519.SH"
