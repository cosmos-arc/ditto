"""
标识符解析 — 从 InstrumentService 提取的标识符解析逻辑.

提供 resolve_instrument_identifier 和 resolve_source_ticker 模块级函数，
供 InstrumentService 的同名方法委托调用。
"""

from __future__ import annotations

from typing import Any

import polars as pl
from ditto_kernel import AmbiguousTickerError, NoIdentifierProvidedError
from ditto_kernel.identity import InstrumentId

from ditto_data.errors import IdentifierNotFoundError
from ditto_data.sources.exchange_transformers import ExchangeTransformers
from ditto_data.storage.metadata.instrument import (
    InstrumentReader,
    SecurityQuery,
)


def resolve_instrument_identifier(  # noqa: PLR0913 — 提取自类方法，依赖通过参数注入
    instrument_reader: InstrumentReader,
    exchange_transformers: ExchangeTransformers,
    *,
    instrument_id: int | None = None,
    standard_ticker: str | None = None,
    ticker: str | None = None,
    asset_class: str | None = None,
    source: str = "tushare",
    asof: str | None = None,
) -> InstrumentId | None:
    """
    统一标识符解析入口.

    将 instrument_id / standard_ticker / ticker 中的一种解析为
    类型安全的 InstrumentId。查不到返回 None（正常流程）。

    优先级: instrument_id > standard_ticker > ticker

    Args:
        instrument_reader: 证券元数据读取器.
        exchange_transformers: 交易所转换器.
        instrument_id: 内部 ID（如 1000001）.
        standard_ticker: Ditto 标准格式（如 "000001.XSHE"）.
        ticker: 裸代码（如 "000001"）.
        asset_class: 资产类型（stock | etf | index），ticker 解析时必需.
        source: 数据源名称（如 "tushare"）.
        asof: 时间点日期 (YYYY-MM-DD).

    Returns:
        InstrumentId 类型安全的证券标识符，查不到返回 None.

    Raises:
        NoIdentifierProvidedError: 未提供任何标识符.
        AmbiguousTickerError: ticker 不唯一.

    """
    if instrument_id is not None:
        # 查询存在性，不存在返回 None
        record = instrument_reader.get_by_instrument_id(instrument_id)
        if record is None:
            return None
        return InstrumentId(instrument_id)

    # 至少需要一个非 instrument_id 标识符
    if standard_ticker is None and ticker is None:
        raise NoIdentifierProvidedError(
            "未提供任何标识符 (instrument_id / standard_ticker / ticker)"
        )

    # 复用 resolve_source_ticker 得到 source_ticker，再解析为 instrument_id
    try:
        source_ticker = resolve_source_ticker(
            instrument_reader,
            exchange_transformers,
            ticker=ticker,
            standard_ticker=standard_ticker,
            asset_class=asset_class or "stock",
            source=source,
            asof=asof,
        )
    except IdentifierNotFoundError:
        return None

    resolved_id = instrument_reader.resolve_instrument_id(source_ticker, source, asof)
    if resolved_id is None:
        return None
    return InstrumentId(resolved_id)


def resolve_source_ticker(  # noqa: PLR0913 — 提取自类方法，依赖通过参数注入
    instrument_reader: InstrumentReader,
    exchange_transformers: ExchangeTransformers,
    *,
    ticker: str | None = None,
    standard_ticker: str | None = None,
    instrument_id: int | None = None,
    asset_class: str = "stock",
    source: str = "tushare",
    asof: str | None = None,
) -> str:
    """
    将任意标识符解析为 source_ticker.

    优先级: instrument_id > standard_ticker > ticker

    Args:
        instrument_reader: 证券元数据读取器.
        exchange_transformers: 交易所转换器.
        ticker: 裸代码（如 "000001"）
        standard_ticker: Ditto 标准格式（如 "000001.XSHE"）
        instrument_id: 内部 ID（如 1000001）
        asset_class: 资产类型（stock | etf | index）
        source: 数据源名称（如 "tushare"）
        asof: Point-in-Time 日期，None 表示当前

    Returns:
        source_ticker 字符串

    Raises:
        ValueError: 未提供任何标识符
        AmbiguousTickerError: ticker 不唯一
        IdentifierNotFoundError: 标识符无效

    """
    # 优先级 1: instrument_id
    if instrument_id is not None:
        result = instrument_reader.get_source_ticker(instrument_id, source, asof)
        if result is None:
            raise IdentifierNotFoundError(
                identifier=str(instrument_id),
                identifier_type="instrument_id",
            )
        return result

    # 优先级 2: standard_ticker
    if standard_ticker is not None:
        return _resolve_from_standard_ticker(
            exchange_transformers, standard_ticker, source
        )

    # 优先级 3: ticker
    if ticker is not None:
        return _resolve_from_ticker(
            instrument_reader, ticker, asset_class, source, asof
        )

    raise ValueError("必须指定 ticker / standard_ticker / instrument_id 之一")


def _resolve_from_standard_ticker(
    exchange_transformers: ExchangeTransformers,
    standard_ticker: str,
    source: str,
) -> str:
    """
    从 standard_ticker 解析 source_ticker.

    Args:
        exchange_transformers: 交易所转换器.
        standard_ticker: Ditto 标准格式（如 "000001.XSHE"）
        source: 数据源名称

    Returns:
        source_ticker 字符串

    """
    # 使用 transformer 转换 standard_ticker 到 source_ticker
    transformer = exchange_transformers.get(source)
    return transformer.from_standard(standard_ticker)


def _resolve_from_ticker(
    instrument_reader: InstrumentReader,
    ticker: str,
    asset_class: str,
    source: str,
    asof: str | None = None,
) -> str:
    """
    从裸 ticker 解析 source_ticker.

    Args:
        instrument_reader: 证券元数据读取器.
        ticker: 裸代码
        asset_class: 资产类型
        source: 数据源名称
        asof: Point-in-Time 日期，None 表示当前

    Returns:
        source_ticker 字符串

    Raises:
        AmbiguousTickerError: 多个匹配
        IdentifierNotFoundError: 无匹配

    """
    df = instrument_reader.find_securities(
        SecurityQuery(
            asset_class=asset_class,
            is_active=True if asof is None else None,
            source=source,
            asof=asof,
        ),
    )

    if df.is_empty():
        raise IdentifierNotFoundError(
            identifier=ticker,
            identifier_type="ticker",
        )

    # 过滤 ticker 匹配的记录
    matches_df = df.filter(pl.col("ticker") == ticker)

    if matches_df.is_empty():
        raise IdentifierNotFoundError(
            identifier=ticker,
            identifier_type="ticker",
        )

    rows = matches_df.to_dicts()
    if len(rows) > 1:
        matches: list[dict[str, Any]] = [
            {
                "source_ticker": row.get("source_ticker", ""),
                "instrument_id": row.get("instrument_id", 0),
                "name": row.get("name", ""),
            }
            for row in rows
        ]
        raise AmbiguousTickerError(ticker=ticker, matches=matches)

    source_ticker = rows[0].get("source_ticker")
    if source_ticker is None:
        raise IdentifierNotFoundError(
            identifier=ticker,
            identifier_type="ticker",
        )
    return str(source_ticker)
