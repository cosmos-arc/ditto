"""Tests for MetadataService.resolve_instrument_identifier unified entry."""

from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.services.metadata_service import MetadataService
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.sources.tushare.transformer import TushareExchangeTransformer
from ditto_kernel import NoIdentifierProvidedError


@pytest.fixture
def mock_dependencies() -> dict[str, MagicMock]:
    """创建 MetadataService 的 mock 依赖."""
    return {
        "instrument_reader": MagicMock(),
        "instrument_writer": MagicMock(),
        "name_history_reader": MagicMock(),
        "name_history_writer": MagicMock(),
        "calendar_reader": MagicMock(),
        "calendar_writer": MagicMock(),
        "industry_reader": MagicMock(),
        "industry_writer": MagicMock(),
        "industry_mapping_reader": MagicMock(),
        "industry_mapping_writer": MagicMock(),
        "universe_reader": MagicMock(),
        "universe_writer": MagicMock(),
        "rebalance_reader": MagicMock(),
        "rebalance_writer": MagicMock(),
        "instrument_id_allocator": MagicMock(),
        "index_composition_reader": MagicMock(),
    }


@pytest.fixture
def exchange_transformers() -> ExchangeTransformers:
    """创建 ExchangeTransformers 实例."""
    return ExchangeTransformers(
        tushare=TushareExchangeTransformer(),
        tdx=MagicMock(),
    )


def _make_service(
    mock_dependencies: dict[str, MagicMock],
    exchange_transformers: ExchangeTransformers,
) -> MetadataService:
    """构建 MetadataService 实例的辅助函数."""
    return MetadataService(
        **mock_dependencies,
        exchange_transformers=exchange_transformers,
    )


@pytest.mark.unit
class TestResolveInstrumentIdentifier:
    """测试 resolve_instrument_identifier 统一入口."""

    def test_instrument_id_queries_existence(
        self,
        mock_dependencies: dict[str, MagicMock],
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """传入 instrument_id 时应查询 metadata，存在则返回 InstrumentId."""
        mock_dependencies["instrument_reader"].get_by_instrument_id.return_value = {
            "instrument_id": 1000001
        }

        service = _make_service(mock_dependencies, exchange_transformers)

        result = service.resolve_instrument_identifier(
            instrument_id=1000001,
            source="tushare",
        )

        assert isinstance(result, int)
        assert result == 1000001
        # 必须调用 reader 查询存在性
        mock_dependencies[
            "instrument_reader"
        ].get_by_instrument_id.assert_called_once_with(1000001)

    def test_instrument_id_not_found_returns_none(
        self,
        mock_dependencies: dict[str, MagicMock],
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """传入不存在的 instrument_id 时应返回 None，不抛异常."""
        mock_dependencies["instrument_reader"].get_by_instrument_id.return_value = None

        service = _make_service(mock_dependencies, exchange_transformers)

        result = service.resolve_instrument_identifier(
            instrument_id=9999999,
            source="tushare",
        )

        assert result is None

    def test_standard_ticker_to_instrument_id(
        self,
        mock_dependencies: dict[str, MagicMock],
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """standard_ticker 应解析为 InstrumentId."""
        mock_dependencies[
            "instrument_reader"
        ].resolve_instrument_id.return_value = 1000001

        service = _make_service(mock_dependencies, exchange_transformers)

        result = service.resolve_instrument_identifier(
            standard_ticker="000001.XSHE",
            source="tushare",
        )

        assert isinstance(result, int)
        assert result == 1000001
        # standard_ticker "000001.XSHE" -> tushare source_ticker "000001.SZ"
        mock_dependencies[
            "instrument_reader"
        ].resolve_instrument_id.assert_called_once_with("000001.SZ", "tushare", None)

    def test_ticker_to_instrument_id(
        self,
        mock_dependencies: dict[str, MagicMock],
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """ticker 应解析为 InstrumentId."""
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
        mock_dependencies[
            "instrument_reader"
        ].resolve_instrument_id.return_value = 1000001

        service = _make_service(mock_dependencies, exchange_transformers)

        result = service.resolve_instrument_identifier(
            ticker="600519",
            source="tushare",
            asset_class="stock",
        )

        assert isinstance(result, int)
        assert result == 1000001
        mock_dependencies[
            "instrument_reader"
        ].resolve_instrument_id.assert_called_once_with("600519.SH", "tushare", None)

    def test_priority_instrument_id_over_ticker(
        self,
        mock_dependencies: dict[str, MagicMock],
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """同时传入 instrument_id 和 ticker 时，instrument_id 优先."""
        mock_dependencies["instrument_reader"].get_by_instrument_id.return_value = {
            "instrument_id": 1000001
        }

        service = _make_service(mock_dependencies, exchange_transformers)

        result = service.resolve_instrument_identifier(
            instrument_id=1000001,
            ticker="600519",
            source="tushare",
        )

        assert isinstance(result, int)
        assert result == 1000001
        # ticker 不应触发 find_securities 查询
        mock_dependencies["instrument_reader"].find_securities.assert_not_called()

    def test_no_identifier_raises_no_identifier_provided_error(
        self,
        mock_dependencies: dict[str, MagicMock],
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """未提供任何标识符时应抛出 NoIdentifierProvidedError."""
        service = _make_service(mock_dependencies, exchange_transformers)

        with pytest.raises(NoIdentifierProvidedError):
            service.resolve_instrument_identifier(
                source="tushare",
            )

    def test_ticker_not_found_returns_none(
        self,
        mock_dependencies: dict[str, MagicMock],
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """ticker 解析后找不到映射时应返回 None，不抛异常."""
        mock_dependencies[
            "instrument_reader"
        ].find_securities.return_value = pl.DataFrame()

        service = _make_service(mock_dependencies, exchange_transformers)

        result = service.resolve_instrument_identifier(
            ticker="999999",
            source="tushare",
            asset_class="stock",
        )

        assert result is None

    def test_standard_ticker_not_found_returns_none(
        self,
        mock_dependencies: dict[str, MagicMock],
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """standard_ticker 解析后找不到映射时应返回 None，不抛异常."""
        mock_dependencies["instrument_reader"].resolve_instrument_id.return_value = None

        service = _make_service(mock_dependencies, exchange_transformers)

        result = service.resolve_instrument_identifier(
            standard_ticker="000001.XSHE",
            source="tushare",
        )

        assert result is None

    def test_asof_passed_to_resolve_instrument_id(
        self,
        mock_dependencies: dict[str, MagicMock],
        exchange_transformers: ExchangeTransformers,
    ) -> None:
        """asof 参数应正确传递给 resolve_instrument_id."""
        mock_dependencies[
            "instrument_reader"
        ].resolve_instrument_id.return_value = 1000001

        service = _make_service(mock_dependencies, exchange_transformers)

        result = service.resolve_instrument_identifier(
            standard_ticker="000001.XSHE",
            source="tushare",
            asof="2024-01-01",
        )

        assert result == 1000001
        mock_dependencies[
            "instrument_reader"
        ].resolve_instrument_id.assert_called_once_with(
            "000001.SZ", "tushare", "2024-01-01"
        )
