"""Tests for SourceQueryFacade — 封装 SourceDataPort + MetadataService."""

from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.source import SourceDataPort, SourceQueryFacade
from ditto_data.catalog.promotion import DatasetMaturityPromotion


class _MaturityPromotionReader:
    def __init__(
        self,
        promotions_by_dataset: dict[str, DatasetMaturityPromotion] | None = None,
    ) -> None:
        self._promotions_by_dataset = promotions_by_dataset or {}

    def get_dataset_maturity_promotion(
        self,
        dataset_id: str,
    ) -> DatasetMaturityPromotion | None:
        return self._promotions_by_dataset.get(dataset_id)


def _make_facade(
    source_data: SourceDataPort | None = None,
    metadata_service: MagicMock | None = None,
    maturity_promotion_reader: _MaturityPromotionReader | None = None,
) -> SourceQueryFacade:
    """Helper to create a SourceQueryFacade with mock dependencies."""
    return SourceQueryFacade(
        source_data=source_data or MagicMock(spec=SourceDataPort),
        metadata_service=metadata_service or MagicMock(),
        maturity_promotion_reader=maturity_promotion_reader,
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
            allow_experimental_data=True,
        )

        assert result is expected
        mock_source.fetch_stock_daily.assert_called_once_with(
            source_ticker="000001.SZ",
            start_date="2026-01-01",
            end_date="2026-01-31",
        )

    def test_stock_daily_requires_explicit_research_opt_in(self) -> None:
        mock_source = MagicMock(spec=SourceDataPort)
        facade = _make_facade(source_data=mock_source)

        with pytest.raises(AppQueryError, match="allow_experimental_data=True"):
            facade.fetch_source_data(
                source="tushare",
                dataset="stock_daily",
                source_ticker="000001.SZ",
                start_date="2026-01-01",
                end_date="2026-01-31",
            )

        mock_source.fetch_stock_daily.assert_not_called()

    def test_promoted_stock_daily_does_not_need_research_opt_in(self) -> None:
        expected = pl.DataFrame({"trade_date": ["2026-01-05"], "close": [10.0]})
        mock_source = MagicMock(spec=SourceDataPort)
        mock_source.fetch_stock_daily.return_value = expected
        facade = _make_facade(
            source_data=mock_source,
            maturity_promotion_reader=_MaturityPromotionReader(
                {
                    "stock_daily": DatasetMaturityPromotion(
                        dataset_id="stock_daily",
                        previous_maturity="experimental",
                        promoted_maturity="initial-focus",
                        promoted_by="architecture-review",
                    )
                }
            ),
        )

        result = facade.fetch_source_data(
            source="tushare",
            dataset="stock_daily",
            source_ticker="000001.SZ",
            start_date="2026-01-01",
            end_date="2026-01-31",
        )

        assert result is expected
        mock_source.fetch_stock_daily.assert_called_once()

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
