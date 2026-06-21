"""摄取后置处理 — list_date 推断、游标更新、冻结点创建、错误处理."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

import httpx
import orjson
import polars as pl
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataCatalogWriter,
    DataSchemaFingerprint,
    default_dataset_metadata,
)
from ditto_data.errors import (
    NetworkError,
    SourceFetchError,
)
from ditto_data.ingestion.freeze_store import FreezeStore
from ditto_data.ingestion.ingestion_cursor_store import (
    IngestionCursorStore,
)
from ditto_data.lineage import (
    DataLineageRecorder,
    LineageEvent,
    LineageInputRef,
    LineageOutputRef,
)
from ditto_data.models.ingestion import IngestionResult
from ditto_platform.foundation import OnDuplicate, WriteResult, logger

from ditto_application.contracts import CheckDataQualityCommand
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_application.processes.ingestion.list_date_inference import (
    ListDateInferenceService,
)
from ditto_application.processes.ingestion.ports import QualityCheckerProtocol
from ditto_application.processes.ingestion.result_handler import IngestionResultHandler

__all__ = [
    "CatalogWriteContext",
    "DataWriteContext",
    "PostIngestContext",
    "create_freeze_point",
    "handle_fetch_error",
    "process_fetched_data",
    "record_data_catalog_entry",
    "record_ingestion_lineage",
    "run_list_date_inference",
    "run_post_ingest_hooks",
    "safe_side_effect",
    "update_ingestion_cursor",
    "write_data_safe",
]


@dataclass(frozen=True)
class CatalogWriteContext:
    """Catalog metadata context for one successful ingestion write."""

    dataset: str
    trade_date: str
    source_name: str
    write_result: WriteResult
    df: pl.DataFrame
    source_ticker: str | None = None
    end_date: str | None = None


@dataclass(frozen=True)
class DataWriteContext:
    """Data writer context for one ingestion storage operation."""

    dataset: str
    df: pl.DataFrame
    trade_date: str
    on_duplicate: OnDuplicate
    source_ticker: str | None = None
    event_suffix: str = ""


@dataclass(frozen=True)
class PostIngestContext:
    """Runtime dependencies for date-level post-ingest processing."""

    result_handler: IngestionResultHandler
    data_writer: IngestionDataWriter
    list_date_inference: ListDateInferenceService
    source_name: str
    quality_checker: QualityCheckerProtocol | None = None
    cursor_store: IngestionCursorStore | None = None
    freeze_store: FreezeStore | None = None
    lineage_recorder: DataLineageRecorder | None = None
    catalog_writer: DataCatalogWriter | None = None


def run_list_date_inference(
    list_date_inference: ListDateInferenceService,
    dataset: str,
) -> None:
    """
    在 basic 数据摄取后执行 list_date 推断补偿。

    针对 list_date 为 NULL 的证券，从历史行情数据推断上市日期。
    """
    asset_class_map = {
        "stock_basic": "stock",
        "etf_basic": "etf",
        "index_basic": "index",
    }

    asset_class = asset_class_map.get(dataset)
    if asset_class is None:
        return

    try:
        logger.info(
            "Running list_date inference after basic ingestion",
            event="list_date_inference_start",
            dataset=dataset,
            asset_class=asset_class,
        )
        count = list_date_inference.infer_for_asset_class(
            cast('Literal["stock", "etf", "index"]', asset_class)
        )
        logger.info(
            "Completed list_date inference",
            event="list_date_inference_complete",
            dataset=dataset,
            asset_class=asset_class,
            inferred_count=count,
        )
    except (
        pl.exceptions.ComputeError,
        pl.exceptions.SchemaError,
        ValueError,
        KeyError,
        TypeError,
        httpx.NetworkError,
        httpx.TimeoutException,
    ) as e:
        logger.warning(
            f"list_date inference failed for {asset_class}",
            event="list_date_inference_error",
            dataset=dataset,
            asset_class=asset_class,
            error=str(e),
        )
    except Exception:
        logger.exception(
            "Unexpected error in list_date inference",
            event="list_date_inference_error",
            dataset=dataset,
            asset_class=asset_class,
        )


def process_fetched_data(
    df: pl.DataFrame,
    dataset: str,
    trade_date: str,
    force: bool,
    *,
    ctx: PostIngestContext,
) -> IngestionResult:
    """处理获取的数据：DQ 检查 + 写入 + 后置钩子."""
    if df.is_empty():
        return ctx.result_handler.handle_empty_data(dataset, trade_date)

    if ctx.quality_checker is not None:
        checked_df, should_block = ctx.quality_checker.handle(
            CheckDataQualityCommand(
                df=df,
                dataset=dataset,
                context={"trade_date": trade_date},
            ),
        )
        if should_block:
            return ctx.result_handler.handle_dq_blocked(
                dataset,
                trade_date,
                WriteResult(
                    file_path="",
                    checksum="",
                    rows_written=0,
                    rows_total=df.height,
                    blocked=True,
                ),
            )
        df = checked_df

    on_duplicate = OnDuplicate.KEEP_LAST if force else OnDuplicate.ERROR

    write_result = write_data_safe(
        DataWriteContext(
            dataset=dataset,
            df=df,
            trade_date=trade_date,
            on_duplicate=on_duplicate,
        ),
        result_handler=ctx.result_handler,
        data_writer=ctx.data_writer,
    )
    if isinstance(write_result, IngestionResult):
        return write_result

    if write_result.blocked:
        return ctx.result_handler.handle_dq_blocked(dataset, trade_date, write_result)

    run_post_ingest_hooks(
        dataset,
        trade_date,
        cursor_store=ctx.cursor_store,
        freeze_store=ctx.freeze_store,
        source_name=ctx.source_name,
    )

    result = ctx.result_handler.handle_success(dataset, trade_date, df, write_result)
    record_ingestion_lineage(
        dataset,
        trade_date,
        source_name=ctx.source_name,
        lineage_recorder=ctx.lineage_recorder,
        write_result=write_result,
    )
    record_data_catalog_entry(
        CatalogWriteContext(
            dataset=dataset,
            trade_date=trade_date,
            source_name=ctx.source_name,
            write_result=write_result,
            df=df,
        ),
        catalog_writer=ctx.catalog_writer,
    )
    run_list_date_inference(ctx.list_date_inference, dataset)
    return result


def _dataset_namespace(dataset: str) -> str:
    metadata = default_dataset_metadata().get(dataset)
    if metadata is None:
        return "data"
    return metadata.domain


def _source_asset(
    dataset: str,
    trade_date: str,
    source_name: str,
    *,
    source_ticker: str | None = None,
    end_date: str | None = None,
) -> DataAssetRef:
    if source_ticker is not None:
        range_end = end_date or trade_date
        return DataAssetRef(
            dataset_id=dataset,
            namespace="source",
            partition_keys=(
                f"source={source_name}",
                f"source_ticker={source_ticker}",
                f"start_date={trade_date}",
                f"end_date={range_end}",
            ),
        )
    return DataAssetRef(
        dataset_id=dataset,
        namespace="source",
        partition_keys=(f"source={source_name}", f"trade_date={trade_date}"),
    )


def _output_asset(
    dataset: str,
    trade_date: str,
    *,
    source_ticker: str | None = None,
    end_date: str | None = None,
) -> DataAssetRef:
    if source_ticker is not None:
        range_end = end_date or trade_date
        return DataAssetRef(
            dataset_id=dataset,
            namespace=_dataset_namespace(dataset),
            partition_keys=(
                f"source_ticker={source_ticker}",
                f"start_date={trade_date}",
                f"end_date={range_end}",
            ),
        )
    return DataAssetRef(
        dataset_id=dataset,
        namespace=_dataset_namespace(dataset),
        partition_keys=(f"trade_date={trade_date}",),
    )


def _ingestion_run_id(
    dataset: str,
    trade_date: str,
    source_name: str,
    checksum: str,
    *,
    source_ticker: str | None = None,
    end_date: str | None = None,
) -> str:
    if source_ticker is not None:
        return (
            f"ingest:{source_name}:{dataset}:{source_ticker}:"
            f"{trade_date}:{end_date or trade_date}:{checksum}"
        )
    return f"ingest:{source_name}:{dataset}:{trade_date}:{checksum}"


def _source_snapshot_id(
    dataset: str,
    trade_date: str,
    source_name: str,
    checksum: str,
    *,
    source_ticker: str | None = None,
    end_date: str | None = None,
) -> str:
    if source_ticker is not None:
        return (
            f"snapshot:{source_name}:{dataset}:{source_ticker}:"
            f"{trade_date}:{end_date or trade_date}:{checksum}"
        )
    return f"snapshot:{source_name}:{dataset}:{trade_date}:{checksum}"


def record_ingestion_lineage(
    dataset: str,
    trade_date: str,
    *,
    source_name: str,
    lineage_recorder: DataLineageRecorder | None,
    write_result: WriteResult,
    source_ticker: str | None = None,
    end_date: str | None = None,
) -> None:
    """记录源数据到落库资产的 lineage（失败仅记录警告，不影响摄取成功）。"""
    if lineage_recorder is None:
        return
    recorder = lineage_recorder
    safe_side_effect(
        lambda: recorder.record_event(
            LineageEvent(
                run_id=_ingestion_run_id(
                    dataset,
                    trade_date,
                    source_name,
                    write_result.checksum,
                    source_ticker=source_ticker,
                    end_date=end_date,
                ),
                operation="ingest",
                inputs=(
                    LineageInputRef(
                        asset=_source_asset(
                            dataset,
                            trade_date,
                            source_name,
                            source_ticker=source_ticker,
                            end_date=end_date,
                        ),
                        role="source",
                    ),
                ),
                outputs=(
                    LineageOutputRef(
                        asset=_output_asset(
                            dataset,
                            trade_date,
                            source_ticker=source_ticker,
                            end_date=end_date,
                        ),
                        role="dataset",
                    ),
                ),
                timestamp=datetime.now(UTC),
            )
        ),
        log_tag="lineage_record_failed",
        event="lineage_record_error",
        dataset=dataset,
        trade_date=trade_date,
    )


def _schema_hash_from_dataframe(df: pl.DataFrame) -> str:
    fields = [
        (name, str(dtype)) for name, dtype in zip(df.columns, df.dtypes, strict=True)
    ]
    payload = orjson.dumps(fields).decode()
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"schema:sha256:{digest}"


def _dataset_schema_version(dataset: str) -> str:
    metadata = default_dataset_metadata().get(dataset)
    if metadata is None or metadata.schema_version is None:
        msg = f"Missing DataCatalog schema_version for dataset={dataset!r}"
        raise AppProcessError(msg)
    return metadata.schema_version


def _data_catalog_entry(
    ctx: CatalogWriteContext,
    *,
    now: datetime,
) -> DataCatalogEntry:
    return DataCatalogEntry(
        asset=_output_asset(
            ctx.dataset,
            ctx.trade_date,
            source_ticker=ctx.source_ticker,
            end_date=ctx.end_date,
        ),
        storage_uri=ctx.write_result.file_path,
        schema=DataSchemaFingerprint(
            schema_hash=_schema_hash_from_dataframe(ctx.df),
            row_count=ctx.write_result.rows_written,
            created_at=now,
            schema_version=_dataset_schema_version(ctx.dataset),
            columns=tuple(ctx.df.columns),
        ),
        source=ctx.source_name,
        freshness_at=now,
        source_snapshot_id=_source_snapshot_id(
            ctx.dataset,
            ctx.trade_date,
            ctx.source_name,
            ctx.write_result.checksum,
            source_ticker=ctx.source_ticker,
            end_date=ctx.end_date,
        ),
    )


def record_data_catalog_entry(
    ctx: CatalogWriteContext,
    *,
    catalog_writer: DataCatalogWriter | None,
) -> None:
    """记录落库资产 catalog 元数据（失败仅记录警告，不影响摄取成功）。"""
    if catalog_writer is None:
        return
    writer = catalog_writer
    safe_side_effect(
        lambda: writer.upsert_asset(
            _data_catalog_entry(
                ctx,
                now=datetime.now(UTC),
            )
        ),
        log_tag="catalog_upsert_failed",
        event="catalog_upsert_error",
        dataset=ctx.dataset,
        trade_date=ctx.trade_date,
    )


def run_post_ingest_hooks(
    dataset: str,
    trade_date: str,
    *,
    cursor_store: IngestionCursorStore | None,
    freeze_store: FreezeStore | None,
    source_name: str,
) -> None:
    """执行摄取后的副作用：游标更新、冻结点创建。"""
    update_ingestion_cursor(
        dataset,
        trade_date,
        cursor_store=cursor_store,
        source_name=source_name,
    )
    create_freeze_point(
        dataset,
        trade_date,
        freeze_store=freeze_store,
    )


def safe_side_effect(
    action: Callable[[], object],
    *,
    log_tag: str,
    event: str,
    dataset: str,
    trade_date: str,
) -> None:
    """执行副作用操作，失败仅记录警告，不影响主流程。"""
    try:
        action()
    except (AppProcessError, ValueError, KeyError, TypeError, OSError) as e:
        logger.warning(
            log_tag,
            event=event,
            dataset=dataset,
            trade_date=trade_date,
            error_type=type(e).__name__,
            error=str(e),
        )
    except Exception:
        logger.exception(
            f"{log_tag}_unexpected",
            event=event,
            dataset=dataset,
            trade_date=trade_date,
        )


def update_ingestion_cursor(
    dataset: str,
    trade_date: str,
    *,
    cursor_store: IngestionCursorStore | None,
    source_name: str,
) -> None:
    """更新摄入游标（失败仅记录警告，不影响主流程）。"""
    if cursor_store is None:
        return
    svc = cursor_store
    safe_side_effect(
        lambda: svc.update_cursor(
            dataset=dataset,
            source=source_name,
            last_success=trade_date,
            last_attempted=trade_date,
        ),
        log_tag="cursor_update_failed",
        event="cursor_update_error",
        dataset=dataset,
        trade_date=trade_date,
    )


def create_freeze_point(
    dataset: str,
    trade_date: str,
    *,
    freeze_store: FreezeStore | None,
) -> None:
    """创建冻结点 — 轻量级版本追踪（失败仅记录警告，不影响主流程）。"""
    if freeze_store is None:
        return
    svc = freeze_store
    safe_side_effect(
        lambda: svc.create_freeze(
            freeze_id=f"{dataset}_{trade_date}",
            description=f"Auto-freeze: {dataset} @ {trade_date}",
            datasets=[dataset],
        ),
        log_tag="freeze_create_failed",
        event="freeze_create_error",
        dataset=dataset,
        trade_date=trade_date,
    )


def write_data_safe(
    ctx: DataWriteContext,
    *,
    result_handler: IngestionResultHandler,
    data_writer: IngestionDataWriter,
) -> WriteResult | IngestionResult:
    """安全写入数据，统一异常处理。"""
    try:
        return data_writer.write_data(
            ctx.dataset,
            ctx.df,
            ctx.trade_date,
            ctx.on_duplicate,
        )
    except (
        pl.exceptions.ComputeError,
        pl.exceptions.SchemaError,
        ValueError,
        KeyError,
        TypeError,
        OSError,
    ) as e:
        logger.warning(
            f"write_data_failed{ctx.event_suffix}",
            event="write_data_error",
            dataset=ctx.dataset,
            trade_date=ctx.trade_date,
            **({"source_ticker": ctx.source_ticker} if ctx.source_ticker else {}),
            error_type=type(e).__name__,
            error=str(e),
        )
        return result_handler.handle_unknown_error(ctx.dataset, ctx.trade_date, e)
    except Exception as e:
        logger.exception(
            f"write_data_failed{ctx.event_suffix}_unexpected",
            event="write_data_error",
            dataset=ctx.dataset,
            trade_date=ctx.trade_date,
            **({"source_ticker": ctx.source_ticker} if ctx.source_ticker else {}),
            error_type=type(e).__name__,
        )
        return result_handler.handle_unknown_error(ctx.dataset, ctx.trade_date, e)


def handle_fetch_error(
    error: Exception,
    *,
    dataset: str,
    date_identifier: str,
    context: str,
    log_tag: str,
    source_name: str,
    result_handler: IngestionResultHandler,
) -> IngestionResult:
    """统一的 fetch 错误处理。"""
    if isinstance(error, (httpx.NetworkError, httpx.TimeoutException)):
        logger.exception(
            f"network_error_{log_tag}",
            dataset=dataset,
            error_type=type(error).__name__,
        )
        network_error = NetworkError.from_httpx(
            error=error,
            source=source_name,
            context=context,
        )
        fetch_error = SourceFetchError(
            message=str(network_error),
            source=source_name,
            cause=network_error,
        )
        return result_handler.handle_fetch_error(dataset, date_identifier, fetch_error)

    if isinstance(error, SourceFetchError):
        normalized = _normalize_source_fetch_error(error)
        return result_handler.handle_fetch_error(dataset, date_identifier, normalized)

    logger.exception(
        f"unexpected_error_{log_tag}",
        dataset=dataset,
        error_type=type(error).__name__,
    )
    return result_handler.handle_unknown_error(dataset, date_identifier, error)


def _normalize_source_fetch_error(error: Exception) -> SourceFetchError:
    """Normalize external fetch error into app-level SourceFetchError."""
    source_name = getattr(error, "source", "unknown")
    return SourceFetchError(message=str(error), source=str(source_name))
