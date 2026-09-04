"""Tests for Index adapter."""

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

import polars as pl
import pytest


@pytest.mark.unit
class TestIndexAdapter:
    """测试 IndexAdapter."""

    def test_index_adapter_has_fetch_basic(self) -> None:
        """验证 IndexAdapter 有 fetch_basic 方法."""
        from ditto_data.sources.tushare.adapters.index import IndexTushareAdapter

        # 创建 mock client
        mock_client = MagicMock()
        adapter = IndexTushareAdapter(_client=mock_client)
        assert hasattr(adapter, "fetch_basic")
        assert callable(adapter.fetch_basic)

    def test_index_adapter_has_fetch_daily(self) -> None:
        """验证 IndexAdapter 有 fetch_daily 方法."""
        from ditto_data.sources.tushare.adapters.index import IndexTushareAdapter

        # 创建 mock client
        mock_client = MagicMock()
        adapter = IndexTushareAdapter(_client=mock_client)
        assert hasattr(adapter, "fetch_daily")
        assert callable(adapter.fetch_daily)

    def test_fetch_basic_returns_dataframe(self) -> None:
        """验证 fetch_basic 返回 DataFrame."""
        from ditto_data.sources.tushare.adapters.index import IndexTushareAdapter

        mock_client = MagicMock()
        mock_response = pl.DataFrame(
            {
                "ts_code": ["000001.SH", "000016.SH"],
                "name": ["上证指数", "上证50"],
                "market": ["SSE", "SSE"],
                "list_date": ["19910715", "20040102"],
            }
        )
        mock_client.query.return_value = mock_response

        adapter = IndexTushareAdapter(_client=mock_client)
        result = adapter.fetch_basic()

        assert isinstance(result, pl.DataFrame)
        mock_client.query.assert_called_once()

    def test_fetch_global_daily_preserves_market_close_and_observation_time(
        self,
    ) -> None:
        """Global bars carry real session time and fail-closed retrieval time."""
        from ditto_data.sources.tushare.adapters.index import IndexTushareAdapter

        mock_client = MagicMock()
        mock_client.query.side_effect = [
            pl.DataFrame(
                {
                    "ts_code": ["SPX"],
                    "trade_date": ["20240328"],
                    "open": [5230.0],
                    "high": [5264.0],
                    "low": [5228.0],
                    "close": [5254.35],
                    "pre_close": [5248.49],
                    "change": [5.86],
                    "pct_chg": [0.1117],
                    "vol": [1.0],
                }
            ),
            pl.DataFrame(
                {
                    "ts_code": ["N225"],
                    "trade_date": ["20240328"],
                    "open": [40500.0],
                    "high": [40600.0],
                    "low": [40200.0],
                    "close": [40168.07],
                    "pre_close": [40762.73],
                    "change": [-594.66],
                    "pct_chg": [-1.4588],
                    "vol": [1.0],
                }
            ),
        ]
        observed_at = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
        adapter = IndexTushareAdapter(_client=mock_client)

        result = adapter.fetch_global_daily(
            codes=["SPX", "N225"],
            start_date="2024-03-28",
            end_date="2024-03-28",
            observed_at=observed_at,
        ).sort("source_ticker")

        assert result["source_ticker"].to_list() == ["N225", "SPX"]
        assert result["event_time"].to_list() == [
            datetime(2024, 3, 28, 6, 0, tzinfo=UTC),
            datetime(2024, 3, 28, 20, 0, tzinfo=UTC),
        ]
        assert result["available_at"].to_list() == [observed_at, observed_at]
        assert result["timezone"].to_list() == [
            "Asia/Tokyo",
            "America/New_York",
        ]
        assert result["currency"].to_list() == ["JPY", "USD"]
        assert all(
            call.kwargs["api_name"] == "index_global"
            for call in mock_client.query.call_args_list
        )

    def test_fetch_global_daily_rejects_unknown_provider_code(self) -> None:
        from ditto_data.sources.tushare.adapters.index import IndexTushareAdapter

        adapter = IndexTushareAdapter(_client=MagicMock())

        with pytest.raises(ValueError, match="Unsupported global index code"):
            adapter.fetch_global_daily(
                codes=["UNKNOWN"],
                start_date="2024-03-28",
                end_date="2024-03-28",
                observed_at=datetime(2026, 9, 1, tzinfo=UTC),
            )

    def test_fetch_sw_industry_daily_uses_provider_native_surface(self) -> None:
        """SW industry codes are not silently sent to the empty index_daily API."""
        from ditto_data.sources.tushare.adapters.index import IndexTushareAdapter

        mock_client = MagicMock()
        mock_client.query.return_value = pl.DataFrame(
            {
                "ts_code": ["801010.SI"],
                "trade_date": ["20240329"],
                "open": [4044.2],
                "high": [4088.1],
                "low": [4020.3],
                "close": [4070.5],
                "change": [25.5],
                "pct_change": [0.63],
                "vol": [1_000.0],
                "amount": [2_000.0],
            }
        )
        adapter = IndexTushareAdapter(_client=mock_client)

        result = adapter.fetch_daily(
            source_ticker="801010.SI",
            start_date="2024-03-29",
            end_date="2024-03-29",
        )

        assert result.to_dicts() == [
            {
                "source_ticker": "801010.SI",
                "trade_date": date(2024, 3, 29),
                "knowledge_date": date(2024, 3, 30),
                "open": 4044.2,
                "high": 4088.1,
                "low": 4020.3,
                "close": 4070.5,
                "pre_close": 4045.0,
                "volume": 1_000.0,
                "amount": 2_000.0,
                "pct_change": 0.63,
            }
        ]
        assert mock_client.query.call_args.kwargs["api_name"] == "sw_daily"

    def test_fetch_daily_batch_routes_sw_and_exchange_indexes_separately(self) -> None:
        """A mixed index basket preserves both provider API contracts."""
        from ditto_data.sources.tushare.adapters.index import IndexTushareAdapter

        mock_client = MagicMock()
        mock_client.query.side_effect = [
            pl.DataFrame(
                {
                    "ts_code": ["000300.SH"],
                    "trade_date": ["20240329"],
                    "open": [3500.0],
                    "high": [3510.0],
                    "low": [3490.0],
                    "close": [3505.0],
                    "pre_close": [3500.0],
                    "vol": [100.0],
                    "amount": [200.0],
                    "pct_chg": [0.14],
                }
            ),
            pl.DataFrame(
                {
                    "ts_code": ["801010.SI"],
                    "trade_date": ["20240329"],
                    "open": [4044.2],
                    "high": [4088.1],
                    "low": [4020.3],
                    "close": [4070.5],
                    "change": [25.5],
                    "pct_change": [0.63],
                    "vol": [1_000.0],
                    "amount": [2_000.0],
                }
            ),
        ]
        adapter = IndexTushareAdapter(_client=mock_client)

        result = adapter.fetch_daily(
            trade_date="2024-03-29",
            ts_codes=["000300.SH", "801010.SI"],
        )

        assert result.get_column("source_ticker").to_list() == [
            "000300.SH",
            "801010.SI",
        ]
        assert [
            call.kwargs["api_name"] for call in mock_client.query.call_args_list
        ] == ["index_daily", "sw_daily"]
