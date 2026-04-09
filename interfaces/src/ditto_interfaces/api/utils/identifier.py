"""API 标识符解析共享工具."""

from __future__ import annotations

from datetime import date

from ditto_app.query.metadata import MetadataQueryFacade
from ditto_infra.foundation import logger
from ditto_kernel import AmbiguousTickerError, NoIdentifierProvidedError
from fastapi import HTTPException


def resolve_identifier_for_api(
    metadata_facade: MetadataQueryFacade,
    *,
    instrument_id: int | None,
    standard_ticker: str | None,
    ticker: str | None,
    as_of_date: date | None = None,
    domain: str = "",
) -> int | None:
    """
    解析标识符为 canonical instrument_id.

    至少提供一个标识符（instrument_id / standard_ticker / ticker），
    委托给 MetadataQueryFacade.resolve_instrument_identifier 进行统一解析。

    Args:
        metadata_facade: MetadataQueryFacade 实例.
        instrument_id: 内部 ID.
        standard_ticker: Ditto 标准格式，如 "000001.XSHE".
        ticker: 裸代码，如 "000001".
        as_of_date: 可选时间点.
        domain: 域名标识，用于异常日志（如 "capital", "fundamental"）.

    Returns:
        解析后的 canonical instrument_id (int)，查不到返回 None.

    Raises:
        HTTPException: 标识符缺失或解析失败时.

    """
    if not any([instrument_id, standard_ticker, ticker]):
        raise HTTPException(
            status_code=422,
            detail="必须提供 instrument_id、standard_ticker 或 ticker 之一",
        )

    try:
        return metadata_facade.resolve_instrument_identifier(
            instrument_id=instrument_id,
            standard_ticker=standard_ticker,
            ticker=ticker,
            asof=as_of_date.isoformat() if as_of_date else None,
        )
    except AmbiguousTickerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NoIdentifierProvidedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception(f"Unexpected error resolving {domain} identifier")
        raise HTTPException(
            status_code=500, detail="Failed to resolve identifier"
        ) from exc
