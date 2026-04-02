"""ServiceBackedDataProvider 单元测试."""

from unittest.mock import MagicMock

import polars as pl
from ditto_data.provider import BarQuery, InstrumentQuery
from ditto_data.query.provider import ServiceBackedDataProvider


def _make_mock_service(name: str) -> MagicMock:
    """创建 mock service."""
    return MagicMock(name=name)


class TestServiceBackedDataProvider:
    """ServiceBackedDataProvider 测试."""

    def _make_provider(self) -> tuple[ServiceBackedDataProvider, dict[str, MagicMock]]:
        """创建 provider + mock services."""
        market = _make_mock_service("market")
        metadata = _make_mock_service("metadata")
        derived = _make_mock_service("derived")

        provider = ServiceBackedDataProvider(
            market_service=market,
            metadata_service=metadata,
            derived_service=derived,
        )
        return provider, {"market": market, "metadata": metadata, "derived": derived}

    # --- get_bars ---

    def test_get_bars_resolves_tickers(self) -> None:
        """get_bars 应先 resolve ticker -> instrument_id."""
        provider, mocks = self._make_provider()

        # ticker -> id 映射
        mocks["metadata"].resolve_instrument_ids_batch.return_value = {
            "000001.SZ": 1,
            "600000.SH": 2,
        }
        # bars 数据
        expected_df = pl.DataFrame({"instrument_id": [1, 2], "close": [10.0, 20.0]})
        mocks["market"].find_bars.return_value = expected_df

        query = BarQuery(
            instruments=["000001.SZ", "600000.SH"],
            start="2024-01-01",
            end="2024-12-31",
        )
        result = provider.get_bars(query)

        assert result.equals(expected_df)
        mocks["metadata"].resolve_instrument_ids_batch.assert_called_once_with(
            identifiers=["000001.SZ", "600000.SH"],
            source="tushare",
            asof=None,
        )

    def test_get_bars_empty_ticker_mapping(self) -> None:
        """get_bars 在无 ticker 映射时应返回空 DataFrame."""
        provider, mocks = self._make_provider()

        mocks["metadata"].resolve_instrument_ids_batch.return_value = {}

        query = BarQuery(
            instruments=["INVALID.XX"],
            start="2024-01-01",
            end="2024-12-31",
        )
        result = provider.get_bars(query)

        assert result.is_empty()
        mocks["market"].find_bars.assert_not_called()

    def test_get_bars_with_adj(self) -> None:
        """get_bars 应正确传递复权参数."""
        provider, mocks = self._make_provider()

        mocks["metadata"].resolve_instrument_ids_batch.return_value = {
            "000001.SZ": 1,
        }
        mocks["market"].find_bars.return_value = pl.DataFrame()

        query = BarQuery(
            instruments=["000001.SZ"],
            start="2024-01-01",
            end="2024-12-31",
            adj="hfq",
        )
        provider.get_bars(query)

        # 验证 find_bars 被调用时包含正确的 adj 参数
        call_args = mocks["market"].find_bars.call_args
        bars_query = call_args[0][0]
        assert bars_query.adj.value == "hfq"

    def test_get_bars_partial_ticker_resolution(self) -> None:
        """get_bars 只解析到部分 ticker 时应只查询已解析的."""
        provider, mocks = self._make_provider()

        mocks["metadata"].resolve_instrument_ids_batch.return_value = {
            "000001.SZ": 1,
            # 600000.SH 未解析到
        }
        mocks["market"].find_bars.return_value = pl.DataFrame(
            {"instrument_id": [1], "close": [10.0]}
        )

        query = BarQuery(
            instruments=["000001.SZ", "600000.SH"],
            start="2024-01-01",
            end="2024-12-31",
        )
        provider.get_bars(query)

        call_args = mocks["market"].find_bars.call_args
        bars_query = call_args[0][0]
        assert bars_query.instrument_ids == [1]

    # --- get_instruments ---

    def test_get_instruments_with_asset_class(self) -> None:
        """get_instruments 应按 asset_class 过滤."""
        provider, mocks = self._make_provider()

        expected_df = pl.DataFrame(
            {"instrument_id": [1, 2], "asset_class": ["etf", "etf"]}
        )
        mocks["metadata"].find_securities.return_value = expected_df

        query = InstrumentQuery(asset_class="etf")
        result = provider.get_instruments(query)

        assert result.equals(expected_df)
        mocks["metadata"].find_securities.assert_called_once_with(
            None, asset_class="etf", exchange=None
        )

    def test_get_instruments_no_filter(self) -> None:
        """get_instruments 无过滤应返回全部."""
        provider, mocks = self._make_provider()

        expected_df = pl.DataFrame({"instrument_id": [1, 2]})
        mocks["metadata"].find_securities.return_value = expected_df

        query = InstrumentQuery()
        result = provider.get_instruments(query)

        assert result.equals(expected_df)
        mocks["metadata"].find_securities.assert_called_once_with(
            None, asset_class=None, exchange=None
        )

    def test_get_instruments_with_exchange(self) -> None:
        """get_instruments 应按 exchange 过滤."""
        provider, mocks = self._make_provider()

        expected_df = pl.DataFrame({"instrument_id": [1], "exchange": ["XSHE"]})
        mocks["metadata"].find_securities.return_value = expected_df

        query = InstrumentQuery(exchange="XSHE")
        result = provider.get_instruments(query)

        assert result.equals(expected_df)
        mocks["metadata"].find_securities.assert_called_once_with(
            None, asset_class=None, exchange="XSHE"
        )

    # --- get_schedule ---

    def test_get_schedule(self) -> None:
        """get_schedule 应返回交易日历."""
        provider, mocks = self._make_provider()

        expected = pl.DataFrame({"trade_date": ["2024-01-02", "2024-01-03"]})
        mocks["metadata"].list_calendar_range.return_value = expected

        result = provider.get_schedule("2024-01-01", "2024-01-31")

        assert result.equals(expected)
        mocks["metadata"].list_calendar_range.assert_called_once_with(
            "2024-01-01", "2024-01-31", only_open=True
        )

    # --- get_factor ---

    def test_get_factor(self) -> None:
        """get_factor 应委托给 DerivedQueryService."""
        provider, mocks = self._make_provider()

        mocks["metadata"].resolve_instrument_ids_batch.return_value = {
            "000001.SZ": 1,
        }
        expected = pl.DataFrame(
            {
                "derived_id": ["momentum_20d"],
                "instrument_id": [1],
                "trade_date": ["2024-01-02"],
                "value": [0.5],
            }
        )
        mocks["derived"].query_for_evaluation.return_value = expected

        result = provider.get_factor(
            name="momentum_20d",
            instruments=("000001.SZ",),
            start="2024-01-01",
            end="2024-12-31",
        )
        assert result.equals(expected)
        mocks["derived"].query_for_evaluation.assert_called_once_with(
            derived_ids=("momentum_20d",),
            instrument_ids=(1,),
            start="2024-01-01",
            end="2024-12-31",
        )

    def test_get_factor_empty_instruments(self) -> None:
        """get_factor 在无 ticker 映射时应返回空 DataFrame."""
        provider, mocks = self._make_provider()

        mocks["metadata"].resolve_instrument_ids_batch.return_value = {}

        result = provider.get_factor(
            name="momentum_20d",
            instruments=("INVALID.XX",),
            start="2024-01-01",
            end="2024-12-31",
        )

        assert result.is_empty()
        mocks["derived"].query_for_evaluation.assert_not_called()

    # --- Protocol 一致性 ---

    def test_satisfies_data_provider_protocol(self) -> None:
        """ServiceBackedDataProvider 应满足 DataProvider Protocol."""
        provider, _ = self._make_provider()
        # Protocol 一致性：结构检查
        assert hasattr(provider, "get_bars")
        assert hasattr(provider, "get_instruments")
        assert hasattr(provider, "get_schedule")
        assert hasattr(provider, "get_factor")
