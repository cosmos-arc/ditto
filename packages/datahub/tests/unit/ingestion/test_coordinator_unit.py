"""
Unit tests for IngestionCoordinator.

测试路由层的核心功能：
- 路由到正确的域
- 处理未知 domain
- 处理未配置的 Ingestion 服务
"""

from datetime import date

import pytest
from ditto_datahub.ingestion.coordinator import IngestionCoordinator, IngestionResult
from ditto_datahub.models import Domain, Source


class TestIngestionCoordinator:
    """测试 IngestionCoordinator 路由功能."""

    def test_init_with_all_domains(self) -> None:
        """测试初始化时提供所有域的 Ingestion 服务."""
        metadata = object()
        market = object()
        capital = object()

        coordinator = IngestionCoordinator(
            metadata=metadata,
            market=market,
            capital=capital,
        )

        assert coordinator._metadata is metadata
        assert coordinator._market is market
        assert coordinator._capital is capital

    def test_init_with_optional_domains(self) -> None:
        """测试初始化时只提供必需的 Metadata 域."""
        metadata = object()

        coordinator = IngestionCoordinator(metadata=metadata)

        assert coordinator._metadata is metadata
        assert coordinator._market is None
        assert coordinator._capital is None

    @pytest.mark.asyncio
    async def test_ingest_metadata_domain(self) -> None:
        """测试路由到 Metadata 域."""
        metadata = object()
        coordinator = IngestionCoordinator(metadata=metadata)

        result = await coordinator.ingest(
            domain=Domain.METADATA,
            data_type="instruments",
            source=Source.TUSHARE,
            trade_date=date(2024, 1, 2),
        )

        # TODO: 实现 MetadataIngestion 后断言成功
        assert result.domain == "metadata"
        assert result.data_type == "instruments"
        assert result.success is False  # 尚未实现
        assert result.error == "MetadataIngestion 尚未实现"

    @pytest.mark.asyncio
    async def test_ingest_market_domain(self) -> None:
        """测试路由到 Market 域."""
        market = object()
        coordinator = IngestionCoordinator(metadata=object(), market=market)

        result = await coordinator.ingest(
            domain=Domain.MARKET,
            data_type="daily_bars",
            source=Source.TUSHARE,
            trade_date=date(2024, 1, 2),
        )

        # TODO: 实现 MarketIngestion 后断言成功
        assert result.domain == "market"
        assert result.data_type == "daily_bars"
        assert result.success is False  # 尚未实现
        assert result.error == "MarketIngestion 尚未实现"

    @pytest.mark.asyncio
    async def test_ingest_capital_domain(self) -> None:
        """测试路由到 Capital 域."""
        capital = object()
        coordinator = IngestionCoordinator(metadata=object(), capital=capital)

        result = await coordinator.ingest(
            domain=Domain.CAPITAL,
            data_type="balance_sheet",
            source=Source.TUSHARE,
            trade_date=date(2024, 1, 2),
        )

        # TODO: 实现 CapitalIngestion 接口后断言成功
        assert result.domain == "capital"
        assert result.data_type == "balance_sheet"
        assert result.success is False  # 接口尚未统一
        assert result.error == "CapitalIngestion 接口尚未统一"

    @pytest.mark.asyncio
    async def test_ingest_market_domain_not_configured(self) -> None:
        """测试 Market 域未配置的情况."""
        coordinator = IngestionCoordinator(metadata=object())

        result = await coordinator.ingest(
            domain=Domain.MARKET,
            data_type="daily_bars",
            source=Source.TUSHARE,
            trade_date=date(2024, 1, 2),
        )

        assert result.success is False
        assert result.error == "MarketIngestion 未配置"

    @pytest.mark.asyncio
    async def test_ingest_capital_domain_not_configured(self) -> None:
        """测试 Capital 域未配置的情况."""
        coordinator = IngestionCoordinator(metadata=object())

        result = await coordinator.ingest(
            domain=Domain.CAPITAL,
            data_type="balance_sheet",
            source=Source.TUSHARE,
            trade_date=date(2024, 1, 2),
        )

        assert result.success is False
        assert result.error == "CapitalIngestion 未配置"

    @pytest.mark.asyncio
    async def test_ingest_unsupported_domain(self) -> None:
        """测试不支持的 domain."""
        coordinator = IngestionCoordinator(metadata=object())

        # 注意：由于 Domain 是枚举，无法传入无效值
        # 这个测试验证所有支持的 domain 都能正常路由
        # 实际的不支持情况会在枚举定义时就限制
        for domain in [Domain.METADATA, Domain.MARKET, Domain.CAPITAL]:
            result = await coordinator.ingest(
                domain=domain,
                data_type="test",
                source=Source.TUSHARE,
                trade_date=date(2024, 1, 2),
            )
            # 所有支持的 domain 都应该返回结果（成功或失败）
            assert result.domain == domain.value


class TestIngestionResult:
    """测试 IngestionResult 数据类."""

    def test_success_result(self) -> None:
        """测试成功的摄入结果."""
        result = IngestionResult(
            success=True,
            records_written=100,
            data_type="instruments",
            domain="metadata",
        )

        assert result.success is True
        assert result.records_written == 100
        assert result.data_type == "instruments"
        assert result.domain == "metadata"
        assert result.error is None

    def test_failure_result(self) -> None:
        """测试失败的摄入结果."""
        result = IngestionResult(
            success=False,
            records_written=0,
            data_type="daily_bars",
            domain="market",
            error="Network error",
        )

        assert result.success is False
        assert result.records_written == 0
        assert result.error == "Network error"

    def test_result_is_frozen(self) -> None:
        """测试 IngestionResult 是不可变的."""
        from dataclasses import FrozenInstanceError

        result = IngestionResult(
            success=True,
            records_written=100,
            data_type="instruments",
            domain="metadata",
        )

        with pytest.raises(FrozenInstanceError):  # frozen dataclass 是不可变的
            result.success = False  # type: ignore[misc]
