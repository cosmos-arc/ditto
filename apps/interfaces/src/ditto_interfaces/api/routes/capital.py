"""Capital 域 API 路由."""

import asyncio
from datetime import date
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_data.errors import AmbiguousTickerError, NoIdentifierProvidedError
from ditto_data.services.capital_service import CapitalService
from ditto_data.services.metadata_service import MetadataService
from ditto_infra.foundation import logger
from fastapi import APIRouter, HTTPException, Query

from ditto_interfaces.models.capital import (
    Margin,
    Valuation,
    to_margin_list,
    to_valuation_list,
)
from ditto_interfaces.models.common import APIResponse
from ditto_interfaces.models.identifier import resolve_instrument_identifier

router = APIRouter(prefix="/capital", tags=["capital"])


def _resolve_identifier(
    metadata_service: MetadataService,
    *,
    instrument_id: int | None,
    standard_ticker: str | None,
    ticker: str | None,
    as_of_date: date | None = None,
) -> int | None:
    """
    解析标识符为 canonical instrument_id.

    至少提供一个标识符（instrument_id / standard_ticker / ticker），
    委托给共享的 resolve_instrument_identifier 进行统一解析。

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
        return resolve_instrument_identifier(
            metadata_service,
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
        logger.exception("Unexpected error resolving capital identifier")
        raise HTTPException(
            status_code=500, detail="Failed to resolve identifier"
        ) from exc


@router.get("/margin", response_model=APIResponse[list[Margin]])
@inject
async def get_margin(
    service: Annotated[CapitalService, FromComponent()],
    metadata_service: Annotated[MetadataService, FromComponent()],
    instrument_id: int | None = Query(None, description="Canonical 标的 ID"),
    ticker: str | None = Query(None, description="裸代码, 如 000001"),
    standard_ticker: str | None = Query(None, description="标准代码, 如 000001.XSHE"),
    as_of_date: date = Query(..., description="时间点查询日期"),
) -> APIResponse[list[Margin]]:
    """
    获取融资融券数据.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
    - instrument_id: 内部 ID，如 1000001
    - standard_ticker: Ditto 标准格式，如 "000001.XSHE"
    - ticker: 裸代码，如 "000001"

    """
    resolved_id = _resolve_identifier(
        metadata_service,
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
        as_of_date=as_of_date,
    )

    if resolved_id is None:
        return APIResponse(data=[])

    # 调用 service（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(service.get_margin_trading, resolved_id, as_of_date)

    # 转换为模型列表
    margins = to_margin_list(df)

    return APIResponse(data=margins)


@router.get("/valuation", response_model=APIResponse[list[Valuation]])
@inject
async def get_valuation(
    service: Annotated[CapitalService, FromComponent()],
    metadata_service: Annotated[MetadataService, FromComponent()],
    instrument_id: int | None = Query(None, description="Canonical 标的 ID"),
    ticker: str | None = Query(None, description="裸代码, 如 000001"),
    standard_ticker: str | None = Query(None, description="标准代码, 如 000001.XSHE"),
    as_of_date: date = Query(..., description="时间点查询日期"),
) -> APIResponse[list[Valuation]]:
    """
    获取估值指标数据.

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
    - instrument_id: 内部 ID，如 1000001
    - standard_ticker: Ditto 标准格式，如 "000001.XSHE"
    - ticker: 裸代码，如 "000001"

    """
    resolved_id = _resolve_identifier(
        metadata_service,
        instrument_id=instrument_id,
        standard_ticker=standard_ticker,
        ticker=ticker,
        as_of_date=as_of_date,
    )

    if resolved_id is None:
        return APIResponse(data=[])

    # 调用 service（在线程池中执行，避免阻塞事件循环）
    df = await asyncio.to_thread(service.get_valuation_metrics, resolved_id, as_of_date)

    # 转换为模型列表
    valuations = to_valuation_list(df)

    return APIResponse(data=valuations)
