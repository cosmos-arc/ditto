"""Tests for MetadataService.resolve_source_ticker method."""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.sources import ExchangeTransformers
from ditto_datahub.sources.tushare.transformer import TushareExchangeTransformer


@pytest.fixture
def mock_dependencies() -> dict[str, MagicMock]:
    """创建 MetadataService 的 mock 依赖."""
    return {
        "instrument_reader": MagicMock(),
        "instrument_writer": MagicMock(),
        "calendar_reader": MagicMock(),
        "calendar_writer": MagicMock(),
        "industry_reader": MagicMock(),
        "industry_writer": MagicMock(),
        "industry_mapping_reader": MagicMock(),
        "industry_mapping_writer": MagicMock(),
        "universe_reader": MagicMock(),
        "universe_writer": MagicMock(),
        "instrument_id_allocator": MagicMock(),
    }


@pytest.fixture
def exchange_transformers() -> ExchangeTransformers:
    """创建 ExchangeTransformers 实例."""
    return ExchangeTransformers(
        tushare=TushareExchangeTransformer(),
        tdx=MagicMock(),  # TDX not needed for these tests
    )


@pytest.mark.unit
class TestResolveSourceTicker:
    """测试 resolve_source_ticker 方法."""

    def test_resolve_by_instrument_id(
        self,
        mock_dependencies: dict[str, MagicMock],
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """instrument_id 优先级最高."""
        mock_dependencies[
            "instrument_reader"
        ].get_source_ticker.return_value = "000001.SZ"

        service = MetadataService(
            **mock_dependencies,
            exchange_transformers=exchange_transformers,
        )

        result = service.resolve_source_ticker(
            ticker="000001",
            standard_ticker="000001.XSHE",
            instrument_id=1000001,
            asset_class="stock",
            source="tushare",
        )

        assert result == "000001.SZ"
        mock_dependencies[
            "instrument_reader"
        ].get_source_ticker.assert_called_once_with(1000001, "tushare", None)

    def test_resolve_by_standard_ticker(
        self,
        mock_dependencies: dict[str, MagicMock],
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """standard_ticker 应转换为 source_ticker."""
        mock_dependencies[
            "instrument_reader"
        ].resolve_instrument_id.return_value = 1000001
        mock_dependencies[
            "instrument_reader"
        ].get_source_ticker.return_value = "000001.SZ"

        service = MetadataService(
            **mock_dependencies,
            exchange_transformers=exchange_transformers,
        )

        result = service.resolve_source_ticker(
            standard_ticker="000001.XSHE",
            asset_class="stock",
            source="tushare",
        )

        assert result == "000001.SZ"

    def test_resolve_by_ticker_unique(
        self,
        mock_dependencies: dict[str, MagicMock],
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """唯一 ticker 应正常解析."""
        mock_dependencies[
            "instrument_reader"
        ].find_securities.return_value = pl.DataFrame(
            {
                "instrument_id": [1000001],
                "source_ticker": ["600519.SH"],
                "name": ["贵州茅台"],
                "ticker": ["600519"],
            }
        )

        service = MetadataService(
            **mock_dependencies,
            exchange_transformers=exchange_transformers,
        )

        result = service.resolve_source_ticker(
            ticker="600519",
            asset_class="stock",
            source="tushare",
        )

        assert result == "600519.SH"

    def test_resolve_by_ticker_ambiguous_raises_error(
        self,
        mock_dependencies: dict[str, MagicMock],
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """歧义 ticker 应抛出 AmbiguousTickerError."""
        mock_dependencies[
            "instrument_reader"
        ].find_securities.return_value = pl.DataFrame(
            {
                "instrument_id": [1000001, 1000002],
                "source_ticker": ["000001.SZ", "000001.SH"],
                "name": ["平安银行", "上证指数"],
                "ticker": ["000001", "000001"],
            }
        )

        service = MetadataService(
            **mock_dependencies,
            exchange_transformers=exchange_transformers,
        )

        with pytest.raises(Exception) as exc_info:
            service.resolve_source_ticker(
                ticker="000001",
                asset_class="stock",
                source="tushare",
            )

        assert "歧义" in str(exc_info.value) or "Ambiguous" in str(exc_info.value)

    def test_no_identifier_raises_error(
        self,
        mock_dependencies: dict[str, MagicMock],
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """未提供任何标识符应抛出 ValueError."""
        service = MetadataService(
            **mock_dependencies,
            exchange_transformers=exchange_transformers,
        )

        with pytest.raises(ValueError, match="必须指定"):
            service.resolve_source_ticker(
                asset_class="stock",
                source="tushare",
            )

    def test_not_found_ticker_raises_error(
        self,
        mock_dependencies: dict[str, MagicMock],
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """未找到 ticker 应抛出 NotFoundError."""
        mock_dependencies[
            "instrument_reader"
        ].find_securities.return_value = pl.DataFrame()

        service = MetadataService(
            **mock_dependencies,
            exchange_transformers=exchange_transformers,
        )

        with pytest.raises(Exception) as exc_info:
            service.resolve_source_ticker(
                ticker="999999",
                asset_class="stock",
                source="tushare",
            )

        err_msg = str(exc_info.value).lower()
        assert "未找到" in str(exc_info.value) or "not found" in err_msg

    def test_not_found_instrument_id_raises_error(
        self,
        mock_dependencies: dict[str, MagicMock],
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """未找到 instrument_id 应抛出 NotFoundError."""
        mock_dependencies["instrument_reader"].get_source_ticker.return_value = None

        service = MetadataService(
            **mock_dependencies,
            exchange_transformers=exchange_transformers,
        )

        with pytest.raises(Exception) as exc_info:
            service.resolve_source_ticker(
                instrument_id=9999999,
                asset_class="stock",
                source="tushare",
            )

        err_msg = str(exc_info.value).lower()
        assert "未找到" in str(exc_info.value) or "not found" in err_msg
