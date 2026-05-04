"""Source 数据查询 API 路由."""

from __future__ import annotations

import asyncio
import time
from typing import Annotated, Any

import polars as pl
from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_application.queries.source import SourceQueryFacade
from ditto_platform.foundation import logger
from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field

from ditto_apps.api.errors import APIError, BadRequestError
from ditto_apps.models.common import APIResponse

router = APIRouter(prefix="/source", tags=["source"])


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _infer_asset_class(facade: SourceQueryFacade, dataset: str) -> str:
    """
    从数据集推断资产类型.

    Args:
        facade: Source 查询 facade.
        dataset: 数据集名称.

    Returns:
        资产类别字符串（如 "stock"）.

    Raises:
        BadRequestError: 不支持的数据集或不支持按标的查询.

    """
    try:
        asset_class = facade.get_dataset_asset_class(dataset)
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc

    if asset_class is None:
        raise BadRequestError(f"数据集 {dataset} 不支持按标的查询")

    return asset_class


def _resolve_source_ticker(
    facade: SourceQueryFacade,
    params: SourceDataQueryParams,
    asset_class: str,
    source: str,
) -> str:
    """
    解析标识符为 source ticker.

    Args:
        facade: Source 查询 facade.
        params: 查询参数（含 ticker / standard_ticker / instrument_id）.
        asset_class: 资产类别.
        source: 数据源名称.

    Returns:
        解析后的 source ticker 字符串.

    Raises:
        BadRequestError: 标识符歧义或未找到.
        APIError: 未预期的解析错误.

    """
    try:
        return facade.resolve_source_ticker(
            ticker=params.ticker,
            standard_ticker=params.standard_ticker,
            instrument_id=params.instrument_id,
            asset_class=asset_class,
            source=source,
        )
    except Exception as exc:
        exc_name = type(exc).__name__
        if exc_name in ("AmbiguousTickerError", "IdentifierNotFoundError"):
            raise BadRequestError(str(exc)) from exc
        logger.exception("Unexpected error resolving ticker")
        raise APIError("Failed to resolve ticker") from exc


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class SourceDataQueryParams(BaseModel):
    """
    Source 数据查询参数.

    将标识符和时间范围查询参数组合为单一模型，
    通过 FastAPI Depends() 注入路由函数。
    """

    ticker: str | None = Field(None, description="裸代码 (如 000001)")
    standard_ticker: str | None = Field(
        None, description="Ditto 标准格式 (如 000001.XSHE)"
    )
    instrument_id: int | None = Field(None, description="内部 ID")
    start_date: str = Field(..., description="开始日期 (YYYY-MM-DD)")
    end_date: str = Field(..., description="结束日期 (YYYY-MM-DD)")

    model_config = {"extra": "ignore"}


class SourceDataResponse(APIResponse[list[dict[str, Any]]]):
    """Source API 响应模型."""

    dataset: str
    source: str
    ticker: str | None = None
    standard_ticker: str | None = None
    instrument_id: int | None = None
    resolved_source_ticker: str
    start_date: str
    end_date: str
    row_count: int
    query_time_ms: float


@router.get("/{source}/{dataset}", response_model=SourceDataResponse)
@inject
async def get_source_data(
    # 依赖注入
    facade: Annotated[SourceQueryFacade, FromComponent()],
    # 查询参数（分组注入）
    params: Annotated[SourceDataQueryParams, Depends()],
    # 路径参数
    source: str = Path(..., description="数据源名称 (如 tushare)"),
    dataset: str = Path(..., description="数据集名称 (如 stock_daily)"),
) -> SourceDataResponse:
    """
    查询 Source 层数据.

    用途: 验证 ETL 逻辑、调试适配器、数据探索

    标识符三选一（优先级: instrument_id > standard_ticker > ticker）:
    - ticker: 裸代码，如 "000001"
    - standard_ticker: Ditto 标准格式，如 "000001.XSHE"
    - instrument_id: 内部 ID，如 1000001

    示例:
        GET /api/source/tushare/stock_daily
            ?ticker=000001
            &start_date=2024-01-01
            &end_date=2024-01-31

        GET /api/source/tushare/stock_daily
            ?standard_ticker=000001.XSHE
            &start_date=2024-01-01
            &end_date=2024-01-31

        GET /api/source/tushare/stock_daily
            ?instrument_id=1000001
            &start_date=2024-01-01
            &end_date=2024-01-31

    """
    start_time = time.monotonic()

    # 验证必须提供至少一个标识符
    if not (params.ticker or params.standard_ticker or params.instrument_id):
        raise BadRequestError("必须提供 ticker、standard_ticker 或 instrument_id 之一")

    # 从数据集推断资产类型
    asset_class = _infer_asset_class(facade, dataset)

    # 解析标识符为 source_ticker
    resolved_source_ticker = _resolve_source_ticker(facade, params, asset_class, source)

    # 通过 application facade 调用 Source 获取数据
    try:
        df = await asyncio.to_thread(
            _fetch_source_data,
            facade,
            source,
            dataset,
            resolved_source_ticker,
            params.start_date,
            params.end_date,
        )
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc

    query_time_ms = (time.monotonic() - start_time) * 1000

    return SourceDataResponse(
        dataset=dataset,
        source=source,
        ticker=params.ticker,
        standard_ticker=params.standard_ticker,
        instrument_id=params.instrument_id,
        resolved_source_ticker=resolved_source_ticker,
        start_date=params.start_date,
        end_date=params.end_date,
        data=df.to_dicts() if not df.is_empty() else [],
        row_count=len(df),
        query_time_ms=query_time_ms,
    )


def _fetch_source_data(
    facade: SourceQueryFacade,
    source: str,
    dataset: str,
    source_ticker: str,
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    """同步获取 Source 数据."""
    return facade.fetch_source_data(
        source=source,
        dataset=dataset,
        source_ticker=source_ticker,
        start_date=start_date,
        end_date=end_date,
    )
