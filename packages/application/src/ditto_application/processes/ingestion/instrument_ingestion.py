"""按标的摄取 — instrument-level 数据摄取逻辑."""

from __future__ import annotations

import polars as pl
from ditto_data.models import Dataset
from ditto_data.models.ingestion import IngestionResult
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_kernel.instrument import InstrumentIngestParams
from ditto_platform.foundation import OnDuplicate, logger

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.auto_init import (
    resolve_identifier_with_auto_init,
)
from ditto_application.processes.ingestion.backfill_handler import (
    BackfillContext,
)
from ditto_application.processes.ingestion.backfill_handler import (
    backfill_adj_factor as _backfill_adj_factor,
)
from ditto_application.processes.ingestion.coordinator_constants import (
    SUPPORTED_INSTRUMENT_DATASETS,
)
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_application.processes.ingestion.fetch_handlers import (
    build_instrument_fetch_handlers,
)
from ditto_application.processes.ingestion.post_ingest import (
    handle_fetch_error,
    write_data_safe,
)
from ditto_application.processes.ingestion.result_handler import IngestionResultHandler
from ditto_application.processes.ingestion.types import SourceFetchers

__all__ = [
    "backfill_adj_factor",
    "ingest_by_instrument",
]


def ingest_by_instrument(  # noqa: PLR0913 — 入口函数：依赖 DI 注入的 fetchers/metadata/result_handler/data_writer
    dataset: str,
    params: InstrumentIngestParams,
    force: bool,
    *,
    fetchers: SourceFetchers,
    metadata_service: MetadataService,
    source_name: str,
    result_handler: IngestionResultHandler,
    data_writer: IngestionDataWriter,
) -> IngestionResult:
    """按标的 + 日期范围摄取数据."""
    try:
        dataset_enum = Dataset(dataset)
    except ValueError as e:
        raise AppProcessError(
            f"不支持的数据集: {dataset}",
            field="dataset",
            value=dataset,
        ) from e

    if dataset_enum not in SUPPORTED_INSTRUMENT_DATASETS:
        raise AppProcessError(
            f"数据集 {dataset} 不支持按标的摄取",
            field="dataset",
            value=dataset,
        )

    asset_class = dataset_enum.asset_class
    if asset_class is None:
        raise AppProcessError(
            f"数据集 {dataset} 缺少 asset_class 定义",
            field="dataset",
            value=dataset,
        )

    source_ticker = resolve_identifier_with_auto_init(
        params,
        asset_class,
        dataset,
        metadata_service=metadata_service,
        source=fetchers.metadata,
        source_name=source_name,
    )

    logger.info(
        "开始按标的摄取数据",
        event="ingestion_by_instrument_start",
        dataset=dataset,
        source_ticker=source_ticker,
        asset_class=asset_class,
        start_date=params.start_date,
        end_date=params.end_date,
        force=force,
    )

    return _fetch_and_ingest_by_instrument(
        dataset,
        dataset_enum,
        source_ticker,
        params,
        fetchers=fetchers,
        result_handler=result_handler,
        data_writer=data_writer,
        source_name=source_name,
    )


def _fetch_and_ingest_by_instrument(  # noqa: PLR0913 — 内部编排：透传 DI 服务 + dataset 上下文
    dataset: str,
    dataset_enum: Dataset,
    source_ticker: str,
    params: InstrumentIngestParams,
    *,
    fetchers: SourceFetchers,
    result_handler: IngestionResultHandler,
    data_writer: IngestionDataWriter,
    source_name: str,
) -> IngestionResult:
    """按标的获取数据并执行摄取（统一错误处理）。"""
    df_or_result = _try_fetch_data_by_instrument(
        dataset,
        dataset_enum,
        source_ticker,
        params,
        fetchers=fetchers,
        result_handler=result_handler,
        source_name=source_name,
    )

    if isinstance(df_or_result, IngestionResult):
        return df_or_result

    return _process_fetched_data_by_instrument(
        df_or_result,
        dataset,
        source_ticker,
        params,
        result_handler=result_handler,
        data_writer=data_writer,
    )


def _try_fetch_data_by_instrument(
    dataset: str,
    dataset_enum: Dataset,
    source_ticker: str,
    params: InstrumentIngestParams,
    *,
    fetchers: SourceFetchers,
    result_handler: IngestionResultHandler,
    source_name: str,
) -> pl.DataFrame | IngestionResult:
    """按标的尝试获取数据，失败时返回 IngestionResult。"""
    try:
        return _fetch_by_dataset(fetchers, dataset_enum, source_ticker, params)
    except Exception as e:
        return handle_fetch_error(
            e,
            dataset=dataset,
            date_identifier=params.start_date,
            context=f"fetching {dataset} for {source_ticker}",
            log_tag="during_fetch_by_instrument",
            source_name=source_name,
            result_handler=result_handler,
        )


def _process_fetched_data_by_instrument(
    df: pl.DataFrame,
    dataset: str,
    source_ticker: str,
    params: InstrumentIngestParams,
    *,
    result_handler: IngestionResultHandler,
    data_writer: IngestionDataWriter,
) -> IngestionResult:
    """按标的处理获取的数据：写入。"""
    if df.is_empty():
        return result_handler.handle_empty_data(dataset, params.start_date)

    on_duplicate = OnDuplicate.KEEP_LAST

    write_result = write_data_safe(
        dataset,
        df,
        params.start_date,
        on_duplicate,
        result_handler=result_handler,
        data_writer=data_writer,
        source_ticker=source_ticker,
        event_suffix="_by_instrument",
    )
    if isinstance(write_result, IngestionResult):
        return write_result

    if write_result.blocked:
        return result_handler.handle_dq_blocked(
            dataset, params.start_date, write_result
        )
    return result_handler.handle_success(dataset, params.start_date, df, write_result)


def _fetch_by_dataset(
    fetchers: SourceFetchers,
    dataset_enum: Dataset,
    source_ticker: str,
    params: InstrumentIngestParams,
) -> pl.DataFrame:
    """根据数据集类型调用对应的 fetch 方法（按标的）。"""
    handlers = build_instrument_fetch_handlers(
        fetchers,
        source_ticker,
        params,
    )

    if dataset_enum not in handlers:
        raise AppProcessError(
            f"不支持按标的摄取的数据集: {dataset_enum.value}",
            field="dataset",
            value=dataset_enum.value,
        )

    return handlers[dataset_enum]()


def backfill_adj_factor(  # noqa: PLR0913 — 回补入口：DI 服务 + BackfillContext 构造，参数已收敛至 BackfillContext
    instrument_id: int,
    start: str,
    end: str,
    *,
    metadata_service: MetadataService,
    market_service: MarketService,
    fetchers: SourceFetchers,
    source_name: str,
    data_writer: IngestionDataWriter,
) -> dict[str, object]:
    """按标的智能回补复权因子空洞，委托至 backfill_handler。"""
    return _backfill_adj_factor(
        instrument_id=instrument_id,
        start=start,
        end=end,
        ctx=BackfillContext(
            metadata_service=metadata_service,
            market_service=market_service,
            source=fetchers.market,
            source_name=source_name,
            data_writer=data_writer,
        ),
    )
