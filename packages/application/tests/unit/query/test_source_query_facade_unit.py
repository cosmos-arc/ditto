"""Tests for SourceQueryFacade — 封装 SourceService + MetadataService."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_application.queries.source import SourceQueryFacade


class TestSourceQueryFacadeGetDatasetAssetClass:
    """SourceQueryFacade.get_dataset_asset_class — 内部使用 Dataset 枚举。"""

    def test_valid_dataset_returns_asset_class(self) -> None:
        source_service = MagicMock()
        metadata_service = MagicMock()
        facade = SourceQueryFacade(
            source_service=source_service,
            metadata_service=metadata_service,
        )

        result = facade.get_dataset_asset_class("stock_daily")

        assert result == "stock"

    def test_metadata_dataset_returns_none(self) -> None:
        source_service = MagicMock()
        metadata_service = MagicMock()
        facade = SourceQueryFacade(
            source_service=source_service,
            metadata_service=metadata_service,
        )

        result = facade.get_dataset_asset_class("stock_basic")

        assert result is None

    def test_invalid_dataset_raises_value_error(self) -> None:
        source_service = MagicMock()
        metadata_service = MagicMock()
        facade = SourceQueryFacade(
            source_service=source_service,
            metadata_service=metadata_service,
        )

        with pytest.raises(ValueError, match="不支持的数据集"):
            facade.get_dataset_asset_class("nonexistent_dataset")


class TestSourceQueryFacadeResolveSourceTicker:
    """SourceQueryFacade.resolve_source_ticker — 委托给 MetadataService。"""

    def test_delegates_to_metadata_service(self) -> None:
        source_service = MagicMock()
        metadata_service = MagicMock()
        metadata_service.resolve_source_ticker.return_value = "000001.SZ"
        facade = SourceQueryFacade(
            source_service=source_service,
            metadata_service=metadata_service,
        )

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


class TestSourceQueryFacadeGetSource:
    """SourceQueryFacade.get_source — 委托给 SourceService。"""

    def test_get_source_by_name(self) -> None:
        mock_source = MagicMock()
        source_service = MagicMock()
        source_service.get_source.return_value = mock_source
        metadata_service = MagicMock()
        facade = SourceQueryFacade(
            source_service=source_service,
            metadata_service=metadata_service,
        )

        result = facade.get_source("tushare")

        assert result is mock_source
        source_service.get_source.assert_called_once_with("tushare")

    def test_tushare_property(self) -> None:
        mock_source = MagicMock()
        source_service = MagicMock()
        source_service.tushare = mock_source
        metadata_service = MagicMock()
        facade = SourceQueryFacade(
            source_service=source_service,
            metadata_service=metadata_service,
        )

        assert facade.tushare is mock_source
