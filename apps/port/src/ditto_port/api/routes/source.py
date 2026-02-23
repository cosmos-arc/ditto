"""Source 数据查询 API 路由."""

import asyncio
import time
from typing import Annotated, Any

import polars as pl
from dishka import FromComponent
from dishka.integrations.fastapi import inject
from ditto_datahub.models import Dataset
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.services.source_service import SourceService
from fastapi import APIRouter, HTTPException, Path, Query

from ditto_port.models.common import APIResponse

router = APIRouter(prefix="/source", tags=["source"])


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
async def get_source_data(  # noqa: PLR0913
    source: str = Path(..., description="数据源名称 (如 tushare)"),
    dataset: str = Path(..., description="数据集名称 (如 stock_daily)"),
    # 标识符（三选一）
    ticker: str | None = Query(None, description="裸代码 (如 000001)"),
    standard_ticker: str | None = Query(
        None, description="Ditto 标准格式 (如 000001.XSHE)"
    ),
    instrument_id: int | None = Query(None, description="内部 ID"),
    # 时间范围
    start_date: str = Query(..., description="开始日期 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="结束日期 (YYYY-MM-DD)"),
    # 依赖注入
    source_service: Annotated[SourceService, FromComponent()] = None,  # type: ignore[assignment]
    metadata_service: Annotated[MetadataService, FromComponent()] = None,  # type: ignore[assignment]
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
    if not any([ticker, standard_ticker, instrument_id]):
        raise HTTPException(
            status_code=400,
            detail="必须提供 ticker、standard_ticker 或 instrument_id 之一",
        )

    # 从数据集推断资产类型
    try:
        dataset_enum = Dataset(dataset)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"不支持的数据集: {dataset}"
        ) from exc

    asset_class = dataset_enum.asset_class
    if asset_class is None:
        raise HTTPException(
            status_code=400, detail=f"数据集 {dataset} 不支持按标的查询"
        )

    # 解析标识符为 source_ticker
    try:
        resolved_source_ticker = metadata_service.resolve_source_ticker(
            ticker=ticker,
            standard_ticker=standard_ticker,
            instrument_id=instrument_id,
            asset_class=asset_class,
            source=source,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 获取数据源
    data_source = _get_data_source(source_service, source)

    # 调用 Source 获取数据
    df = await asyncio.to_thread(
        _fetch_source_data,
        data_source,
        dataset,
        resolved_source_ticker,
        start_date,
        end_date,
    )

    query_time_ms = (time.monotonic() - start_time) * 1000

    return SourceDataResponse(
        dataset=dataset,
        source=source,
        ticker=ticker,
        standard_ticker=standard_ticker,
        instrument_id=instrument_id,
        resolved_source_ticker=resolved_source_ticker,
        start_date=start_date,
        end_date=end_date,
        data=df.to_dicts() if not df.is_empty() else [],
        row_count=len(df),
        query_time_ms=query_time_ms,
    )


def _get_data_source(source_service: SourceService, source: str) -> Any:
    """获取指定数据源."""
    if source == "tushare":
        return source_service.tushare
    # 后续扩展其他数据源
    raise ValueError(f"不支持的数据源: {source}")


def _fetch_source_data(
    source: Any,
    dataset: str,
    source_ticker: str,
    start_date: str,
    end_date: str,
) -> pl.DataFrame:
    """同步获取 Source 数据."""
    if dataset == "stock_daily":
        return source.fetch_stock_daily(
            source_ticker=source_ticker,
            start_date=start_date,
            end_date=end_date,
        )
    # 其他数据集暂不支持
    return pl.DataFrame()
