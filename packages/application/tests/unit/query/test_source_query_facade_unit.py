"""Tests for SourceQueryFacade — 封装 SourceDataPort + MetadataService."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.source import SourceDataPort, SourceQueryFacade


def _make_facade(
    source_data: SourceDataPort | None = None,
    metadata_service: MagicMock | None = None,
) -> SourceQueryFacade:
    """Helper to create a SourceQueryFacade with mock dependencies."""
    return SourceQueryFacade(
        source_data=source_data or MagicMock(spec=SourceDataPort),
        metadata_service=metadata_service or MagicMock(),
    )


class TestSourceQueryFacadeGetDatasetAssetClass:
    """SourceQueryFacade.get_dataset_asset_class — 内部使用 Dataset 枚举。"""

    def test_valid_dataset_returns_asset_class(self) -> None:
        facade = _make_facade()

        result = facade.get_dataset_asset_class("stock_daily")

        assert result == "stock"

    def test_metadata_dataset_returns_none(self) -> None:
        facade = _make_facade()

        result = facade.get_dataset_asset_class("stock_basic")

        assert result is None

    def test_invalid_dataset_raises_value_error(self) -> None:
        facade = _make_facade()

        with pytest.raises(AppQueryError, match="不支持的数据集"):
            facade.get_dataset_asset_class("nonexistent_dataset")


class TestSourceQueryFacadeResolveSourceTicker:
    """SourceQueryFacade.resolve_source_ticker — 委托给 MetadataService。"""

    def test_delegates_to_metadata_service(self) -> None:
        metadata_service = MagicMock()
        metadata_service.resolve_source_ticker.return_value = "000001.SZ"
        facade = _make_facade(metadata_service=metadata_service)

        result = facade.resolve_source_ticker(
            ticker="000001",
            standard_ticker=None,
            instrument_id=None,
            asset_class="stock",
            source="tushare",
        )

        assert result == "000001.SZ"
        metadata_service.resolve_source_ticker.assert_called_once_with(
            ticker="000001",
            standard_ticker=None,
            instrument_id=None,
            asset_class="stock",
            source="tushare",
        )


class TestSourceQueryFacadeFetchSourceData:
    """SourceQueryFacade.fetch_source_data — route-facing source fetch facade."""

    def test_fetches_tushare_stock_daily(self) -> None:
        expected = pl.DataFrame({"trade_date": ["2026-01-05"], "close": [10.0]})
        mock_source = MagicMock(spec=SourceDataPort)
        mock_source.fetch_stock_daily.return_value = expected
        facade = _make_facade(source_data=mock_source)

        result = facade.fetch_source_data(
            source="tushare",
            dataset="stock_daily",
            source_ticker="000001.SZ",
            start_date="2026-01-01",
            end_date="2026-01-31",
        )

        assert result is expected
        mock_source.fetch_stock_daily.assert_called_once_with(
            source_ticker="000001.SZ",
            start_date="2026-01-01",
            end_date="2026-01-31",
        )

    def test_unsupported_source_raises_value_error(self) -> None:
        facade = _make_facade()

        with pytest.raises(AppQueryError, match="不支持的数据源"):
            facade.fetch_source_data(
                source="fred",
                dataset="stock_daily",
                source_ticker="000001.SZ",
                start_date="2026-01-01",
                end_date="2026-01-31",
            )

    def test_unsupported_dataset_raises_value_error(self) -> None:
        facade = _make_facade()

        with pytest.raises(AppQueryError, match="暂不支持 Source API 查询"):
            facade.fetch_source_data(
                source="tushare",
                dataset="index_daily",
                source_ticker="000001.SH",
                start_date="2026-01-01",
                end_date="2026-01-31",
            )
