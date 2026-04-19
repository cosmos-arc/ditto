"""auto-init 标识符解析链 — 从 ingestion_coordinator 提取的纯编排函数."""

from __future__ import annotations

from ditto_data.errors import IdentifierNotFoundError
from ditto_data.services.metadata_service import MetadataService
from ditto_data.sources.base import DataSource
from ditto_infra.foundation import logger
from ditto_kernel import AmbiguousTickerError
from ditto_kernel.instrument import InstrumentIngestParams

from ditto_app.process.ingestion.coordinator_constants import (
    A_SHARE_CODE_LENGTH,
    EXCHANGE_PREFIX_MAP,
)


def infer_exchange_suffix(ticker: str) -> str | None:
    """
    从股票代码推断交易所后缀.

    Args:
        ticker: 裸股票代码（如 "600519"，必须为 6 位数字）

    Returns:
        交易所后缀（"SH", "SZ", "BJ"）或 None

    """
    if len(ticker) != A_SHARE_CODE_LENGTH or not ticker.isdigit():
        return None

    for prefix, exchange in EXCHANGE_PREFIX_MAP.items():
        if ticker.startswith(prefix):
            return exchange

    return None


def resolve_identifier_with_auto_init(
    params: InstrumentIngestParams,
    asset_class: str,
    dataset: str,
    metadata_service: MetadataService,
    source: DataSource,
    source_name: str,
) -> str:
    """
    解析标识符，如果失败则尝试自动初始化证券信息.

    对于股票类型，如果标识符未找到，会尝试从数据源获取
    该股票的基本信息并注册，然后重试解析。

    Args:
        params: 摄取参数
        asset_class: 资产类别
        dataset: 数据集名称（用于日志）
        metadata_service: 元数据服务
        source: 数据源
        source_name: 数据源名称

    Returns:
        解析后的 source_ticker

    Raises:
        AmbiguousTickerError: 标识符模糊
        IdentifierNotFoundError: 标识符未找到且无法自动初始化

    """
    try:
        return metadata_service.resolve_source_ticker(
            ticker=params.ticker,
            standard_ticker=params.standard_ticker,
            instrument_id=params.instrument_id,
            asset_class=asset_class,
            source=source_name,
        )
    except AmbiguousTickerError:
        # 模糊标识符无法自动修复
        raise
    except IdentifierNotFoundError as e:
        # 仅对股票类型尝试自动初始化
        if asset_class != "stock":
            logger.error(
                "标识符解析失败",
                event="identifier_resolution_failed",
                dataset=dataset,
                error=str(e),
            )
            raise
        # 尝试自动初始化
        return _auto_init_stock_instrument(
            params, dataset, e, metadata_service, source, source_name
        )


def _auto_init_stock_instrument(
    params: InstrumentIngestParams,
    dataset: str,
    original_error: IdentifierNotFoundError,
    metadata_service: MetadataService,
    source: DataSource,
    source_name: str,
) -> str:
    """
    自动初始化股票证券信息.

    从 Tushare 获取股票基本信息并注册，然后返回 source_ticker。

    Args:
        params: 摄取参数
        dataset: 数据集名称
        original_error: 原始的标识符未找到错误
        metadata_service: 元数据服务
        source: 数据源
        source_name: 数据源名称

    Returns:
        source_ticker

    Raises:
        IdentifierNotFoundError: 如果无法获取股票信息

    """
    source_ticker = _resolve_stock_source_ticker(params, dataset, original_error)
    _fetch_and_register_stock(
        source_ticker, dataset, original_error, metadata_service, source, source_name
    )
    return source_ticker


def _resolve_stock_source_ticker(
    params: InstrumentIngestParams,
    dataset: str,
    original_error: IdentifierNotFoundError,
) -> str:
    """从参数中提取 ticker 并构建 source_ticker（含交易所后缀）."""
    ticker = params.ticker or (
        params.standard_ticker.split(".")[0] if params.standard_ticker else None
    )
    if not ticker:
        logger.error(
            "无法确定股票代码",
            event="auto_init_missing_ticker",
            dataset=dataset,
        )
        raise original_error

    exchange_suffix = infer_exchange_suffix(ticker)
    if not exchange_suffix:
        logger.error(
            "无法确定交易所",
            event="auto_init_unknown_exchange",
            ticker=ticker,
        )
        raise original_error

    return f"{ticker}.{exchange_suffix}"


def _fetch_and_register_stock(
    source_ticker: str,
    dataset: str,
    original_error: IdentifierNotFoundError,
    metadata_service: MetadataService,
    source: DataSource,
    source_name: str,
) -> None:
    """从数据源获取股票基本信息并注册到元数据服务."""
    logger.info(
        "尝试自动初始化股票信息",
        event="auto_init_stock_start",
        source_ticker=source_ticker,
        dataset=dataset,
    )

    try:
        basic_df = source.fetch_stock_basic(source_ticker)
    except Exception as fetch_error:
        logger.error(
            "获取股票基本信息失败",
            event="auto_init_fetch_failed",
            source_ticker=source_ticker,
            error=str(fetch_error),
        )
        raise original_error from fetch_error

    if basic_df.is_empty():
        logger.warning(
            "股票在数据源中不存在",
            event="auto_init_stock_not_found",
            source_ticker=source_ticker,
        )
        raise original_error

    try:
        metadata_service.register_instruments_batch(
            df=basic_df,
            source=source_name,
            asset_class="stock",
            source_ticker_col="source_ticker",
        )
    except Exception as register_error:
        logger.error(
            "注册证券失败",
            event="auto_init_register_failed",
            source_ticker=source_ticker,
            error=str(register_error),
        )
        raise original_error from register_error

    logger.info(
        "自动初始化股票信息成功",
        event="auto_init_stock_success",
        source_ticker=source_ticker,
    )


__all__ = [
    "infer_exchange_suffix",
    "resolve_identifier_with_auto_init",
]
