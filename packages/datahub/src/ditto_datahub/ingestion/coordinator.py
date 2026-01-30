"""
IngestionCoordinator - 数据摄入路由协调器.

根据数据类型和源，将请求路由到对应的域 Ingestion 服务。

架构说明:
- 这是 Ingestion 层的第一层（路由层）
- 负责根据 Domain 枚举路由到对应的 Ingestion 服务
- 支持异步操作
- 处理未知 domain 和未实现服务的情况

Examples:
    >>> coordinator = IngestionCoordinator(
    ...     metadata=metadata_ingestion,
    ...     market=market_ingestion,
    ...     capital=capital_ingestion,
    ... )
    >>> result = await coordinator.ingest(
    ...     domain=Domain.METADATA,
    ...     data_type="instruments",
    ...     source=Source.TUSHARE,
    ...     trade_date=date(2024, 1, 2),
    ... )

"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ditto_datahub.models import Domain, Source


@dataclass(frozen=True)
class IngestionResult:
    """
    Data ingestion result.

    Attributes:
        success: Whether ingestion was successful.
        records_written: Number of records written to store.
        data_type: Data type name.
        domain: Domain name.
        error: Error message if ingestion failed.

    """

    success: bool
    records_written: int
    data_type: str
    domain: str
    error: str | None = None


class IngestionCoordinator:
    """
    数据摄入路由协调器.

    根据数据类型和源，将请求路由到对应的 Ingestion 服务。

    Attributes:
        _metadata: Metadata domain ingestion service.
        _market: Market domain ingestion service (optional).
        _capital: Capital domain ingestion service (optional).
            fundamental: Fundamental domain ingestion service (optional).

    Examples:
        >>> coordinator = IngestionCoordinator(
        ...     metadata=metadata_ingestion,
        ...     market=market_ingestion,
        ...     capital=capital_ingestion,
        ... )
        >>> result = await coordinator.ingest(
        ...     domain=Domain.METADATA,
        ...     data_type="instruments",
        ...     source=Source.TUSHARE,
        ...     trade_date=date(2024, 1, 2),
        ... )
        >>> assert result.success

    """

    def __init__(
        self,
        metadata: object,  # MetadataIngestion (TODO: 定义后再类型注解)
        market: object | None = None,  # MarketIngestion | None
        capital: object | None = None,  # CapitalIngestion | None
        fundamental: object | None = None,  # FundamentalIngestion | None
    ) -> None:
        """
        初始化 IngestionCoordinator.

        Args:
            metadata: Metadata domain ingestion service.
            market: Market domain ingestion service (optional).
            capital: Capital domain ingestion service (optional).
            fundamental: Fundamental domain ingestion service (optional).

        """
        self._metadata = metadata
        self._market = market
        self._capital = capital
        self._fundamental = fundamental

    async def ingest(
        self,
        domain: Domain,
        data_type: str,
        source: Source,
        trade_date: date,
    ) -> IngestionResult:
        """
        路由到对应的 Ingestion 服务.

        根据 domain 参数路由到对应的域 Ingestion 服务。

        Args:
            domain: 数据域（METADATA, MARKET, CAPITAL, FUNDAMENTAL）。
            data_type: 数据类型（如 "instruments", "daily_bars" 等）。
            source: 数据源（TUSHARE, AKSHARE 等）。
            trade_date: 交易日期。

        Returns:
            IngestionResult: 摄入结果。

        Raises:
            ValueError: 当 domain 不支持时。

        Examples:
            >>> result = await coordinator.ingest(
            ...     domain=Domain.METADATA,
            ...     data_type="instruments",
            ...     source=Source.TUSHARE,
            ...     trade_date=date(2024, 1, 2),
            ... )
            >>> assert result.success

        """
        # 路由到对应的域 Ingestion 服务
        if domain == Domain.METADATA:
            return await self._ingest_metadata(data_type, source, trade_date)
        elif domain == Domain.MARKET:
            return await self._ingest_market(data_type, source, trade_date)
        elif domain == Domain.CAPITAL:
            return await self._ingest_capital(data_type, source, trade_date)
        elif domain == Domain.FUNDAMENTAL:
            return await self._ingest_fundamental(data_type, source, trade_date)
        else:
            raise ValueError(f"不支持的 domain: {domain}")

    async def _ingest_metadata(
        self,
        data_type: str,
        source: Source,
        trade_date: date,
    ) -> IngestionResult:
        """
        Metadata 域摄入.

        Args:
            data_type: 数据类型。
            source: 数据源。
            trade_date: 交易日期。

        Returns:
            IngestionResult: 摄入结果。

        """
        # TODO: 实现 MetadataIngestion 后调用
        return IngestionResult(
            success=False,
            records_written=0,
            data_type=data_type,
            domain="metadata",
            error="MetadataIngestion 尚未实现",
        )

    async def _ingest_market(
        self,
        data_type: str,
        source: Source,
        trade_date: date,
    ) -> IngestionResult:
        """
        Market 域摄入.

        Args:
            data_type: 数据类型。
            source: 数据源。
            trade_date: 交易日期。

        Returns:
            IngestionResult: 摄入结果。

        Raises:
            ValueError: 当 MarketIngestion 未实现时。

        """
        if self._market is None:
            return IngestionResult(
                success=False,
                records_written=0,
                data_type=data_type,
                domain="market",
                error="MarketIngestion 未配置",
            )

        # TODO: 实现 MarketIngestion 后调用
        return IngestionResult(
            success=False,
            records_written=0,
            data_type=data_type,
            domain="market",
            error="MarketIngestion 尚未实现",
        )

    async def _ingest_fundamental(
        self,
        data_type: str,
        source: Source,
        trade_date: date,
    ) -> IngestionResult:
        """
        Fundamental 域摄入.

        Args:
            data_type: 数据类型.
            source: 数据源.
            trade_date: 交易日期.

        Returns:
            IngestionResult: 摄入结果.

        Raises:
            ValueError: 当 fundamental 未配置时.

        """
        if self._fundamental is None:
            raise ValueError("Fundamental ingestion service not configured")

        # Delegate to FundamentalIngestion (待实现)
        # return await self._fundamental.ingest(data_type, source, trade_date)
        raise NotImplementedError(
            f"Fundamental ingestion not yet implemented: {data_type}"
        )

    async def _ingest_capital(
        self,
        data_type: str,
        source: Source,
        trade_date: date,
    ) -> IngestionResult:
        """
        Capital 域摄入.

        Args:
            data_type: 数据类型。
            source: 数据源。
            trade_date: 交易日期。

        Returns:
            IngestionResult: 摄入结果。

        Raises:
            ValueError: 当 CapitalIngestion 未实现时。

        """
        if self._capital is None:
            return IngestionResult(
                success=False,
                records_written=0,
                data_type=data_type,
                domain="capital",
                error="CapitalIngestion 未配置",
            )

        # TODO: 实现 CapitalIngestion 接口后调用
        return IngestionResult(
            success=False,
            records_written=0,
            data_type=data_type,
            domain="capital",
            error="CapitalIngestion 接口尚未统一",
        )
