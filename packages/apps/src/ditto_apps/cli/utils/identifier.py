"""CLI 标识符解析共享工具."""

from __future__ import annotations

import typer
from ditto_application.query.metadata import MetadataQueryFacade


def resolve_identifier_for_cli(
    metadata_facade: MetadataQueryFacade,
    *,
    instrument_id: int | None,
    ticker: str | None,
    standard_ticker: str | None,
    as_of_date: str | None = None,
) -> int | None:
    """
    解析标识符为 canonical instrument_id.

    至少提供一个标识符，委托给 MetadataQueryFacade.resolve_instrument_identifier。

    Args:
        metadata_facade: MetadataQueryFacade 实例.
        instrument_id: 内部 ID.
        ticker: 裸代码，如 "000001".
        standard_ticker: Ditto 标准格式，如 "000001.XSHE".
        as_of_date: 可选日期字符串.

    Returns:
        解析后的 canonical instrument_id (int)，查不到返回 None.

    Raises:
        typer.Exit: 标识符缺失时（code=1）.

    """
    if not any([instrument_id, standard_ticker, ticker]):
        typer.echo("错误: 必须提供 --instrument-id、--ticker 或 --standard-ticker 之一")
        raise typer.Exit(code=1)

    return metadata_facade.resolve_instrument_identifier(
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
        asof=as_of_date,
    )
