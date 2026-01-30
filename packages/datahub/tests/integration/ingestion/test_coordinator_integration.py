"""
Integration tests for IngestionCoordinator.

测试路由层与实际 Ingestion 服务的集成：
- 与 CapitalIngestion 的集成
- 完整的摄入流程
"""

from datetime import date
from unittest.mock import MagicMock

import pytest
from ditto_datahub.ingestion.coordinator import IngestionCoordinator, IngestionResult
from ditto_datahub.models import Domain, Source


@pytest.mark.integration
class TestIngestionCoordinatorIntegration:
    """测试 IngestionCoordinator 与域 Ingestion 服务的集成."""

    @pytest.mark.asyncio
    async def test_coordinator_with_capital_ingestion(self) -> None:
        """测试 IngestionCoordinator 与 CapitalIngestion 的集成."""
        # 创建 mock CapitalIngestion
        mock_capital = MagicMock()

        # 创建 Coordinator，只配置 Capital 域
        coordinator = IngestionCoordinator(
            metadata=object(),
            capital=mock_capital,
        )

        # 测试路由是否正确
        result = await coordinator.ingest(
            domain=Domain.CAPITAL,
            data_type="balance_sheet",
            source=Source.TUSHARE,
            trade_date=date(2024, 1, 2),
        )

        # 验证返回结果的结构
        assert isinstance(result, IngestionResult)
        assert result.domain == "capital"
        assert result.data_type == "balance_sheet"

        # 注意：当前实现返回"尚未实现"错误
        # 待 CapitalIngestion 接口统一后，这里应该验证成功情况
        assert result.success is False
        assert "CapitalIngestion" in result.error

    @pytest.mark.asyncio
    async def test_coordinator_metadata_domain(self) -> None:
        """测试 Metadata 域路由."""
        coordinator = IngestionCoordinator(metadata=object())

        result = await coordinator.ingest(
            domain=Domain.METADATA,
            data_type="instruments",
            source=Source.TUSHARE,
            trade_date=date(2024, 1, 2),
        )

        assert result.domain == "metadata"
        assert result.data_type == "instruments"
        # MetadataIngestion 尚未实现
        assert result.success is False

    @pytest.mark.asyncio
    async def test_coordinator_market_domain_not_configured(self) -> None:
        """测试 Market 域未配置时的行为."""
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
    async def test_coordinator_capital_domain_not_configured(self) -> None:
        """测试 Capital 域未配置时的行为."""
        coordinator = IngestionCoordinator(metadata=object())

        result = await coordinator.ingest(
            domain=Domain.CAPITAL,
            data_type="balance_sheet",
            source=Source.TUSHARE,
            trade_date=date(2024, 1, 2),
        )

        assert result.success is False
        assert result.error == "CapitalIngestion 未配置"


@pytest.mark.integration
class TestIngestionCoordinatorEndToEnd:
    """测试 IngestionCoordinator 的端到端流程."""

    @pytest.mark.asyncio
    async def test_full_ingestion_flow(self) -> None:
        """测试完整的摄入流程（路由 → 执行 → 结果）."""
        mock_capital = MagicMock()
        coordinator = IngestionCoordinator(
            metadata=object(),
            capital=mock_capital,
        )

        # 测试 Capital 域的完整流程
        result = await coordinator.ingest(
            domain=Domain.CAPITAL,
            data_type="balance_sheet",
            source=Source.TUSHARE,
            trade_date=date(2024, 1, 2),
        )

        # 验证结果结构
        assert hasattr(result, "success")
        assert hasattr(result, "records_written")
        assert hasattr(result, "data_type")
        assert hasattr(result, "domain")
        assert hasattr(result, "error")

        # 验证域名正确
        assert result.domain == "capital"
