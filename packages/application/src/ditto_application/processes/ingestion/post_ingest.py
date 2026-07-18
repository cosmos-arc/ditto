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
    DataCatalogReader,
    DataCatalogWriter,
    DataSchemaFingerprint,
    ProviderSnapshot,
    ProviderSnapshotDraft,
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
from ditto_data.models.ingestion import (
    IngestionLog,
    IngestionQualityEvidence,
    IngestionResult,
    IngestionSnapshotEvidence,
    IngestionStatus,
)
from ditto_platform.foundation import OnDuplicate, WriteResult, logger

from ditto_application.catalog_freshness import catalog_source_snapshot_id
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_application.processes.ingestion.evidence_commit import (
    EvidenceCommitRequest,
    IngestionEvidenceCommitter,
)
from ditto_application.processes.ingestion.list_date_inference import (
    ListDateInferenceService,
)
from ditto_application.processes.ingestion.ports import QualityCheckerProtocol
from ditto_application.processes.ingestion.quality_gate import run_write_quality_gate
from ditto_application.processes.ingestion.result_handler import IngestionResultHandler
from ditto_application.processes.ingestion.sparse_pit import (
    is_sparse_pit_dataset,
    resolve_sparse_asof_snapshot,
    validate_sparse_pit_cutoff,
)

__all__ = [
    "CatalogWriteContext",
    "DataWriteContext",
    "PostIngestContext",
    "build_evidence_commit_request",
    "create_freeze_point",
    "handle_fetch_error",
    "is_sparse_pit_dataset",
    "process_fetched_data",
    "record_data_catalog_entry",
    "record_ingestion_lineage",
    "resolve_sparse_asof_snapshot",
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
    l1_l2_attested: bool = False


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
    catalog_reader: DataCatalogReader | None = None
    quality_checker: QualityCheckerProtocol | None = None
    cursor_store: IngestionCursorStore | None = None
    freeze_store: FreezeStore | None = None
    lineage_recorder: DataLineageRecorder | None = None
    catalog_writer: DataCatalogWriter | None = None
    evidence_committer: IngestionEvidenceCommitter | None = None
    license_record_id: str | None = None


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


def process_fetched_data(  # noqa: C901, PLR0911, PLR0912 - fail-closed stages
    df: pl.DataFrame,
    dataset: str,
    trade_date: str,
    force: bool,
    *,
    ctx: PostIngestContext,
) -> IngestionResult:
    """处理获取的数据：DQ 检查 + 写入 + 后置钩子."""
    if df.is_empty():
        if is_sparse_pit_dataset(dataset):
            snapshot = resolve_sparse_asof_snapshot(
                dataset=dataset,
                trade_date=trade_date,
                source_name=ctx.source_name,
                catalog_reader=ctx.catalog_reader,
            )
            if snapshot is None:
                return ctx.result_handler.handle_pit_snapshot_missing(
                    dataset,
                    trade_date,
                )
            return ctx.result_handler.handle_empty_success(
                dataset,
                trade_date,
                message="无新数据, 复用最近 PIT 快照",
                snapshot_evidence=snapshot,
                quality_evidence=IngestionQualityEvidence(
                    kind="no_new_rows",
                    status="not_applicable_no_new_rows",
                    source=ctx.source_name,
                    trade_date=trade_date,
                    levels=(),
                    row_count=0,
                ),
            )
        return ctx.result_handler.handle_empty_data(dataset, trade_date)

    sparse_pit = is_sparse_pit_dataset(dataset)
    cutoff_error = validate_sparse_pit_cutoff(
        df,
        dataset=dataset,
        trade_date=trade_date,
    )
    if cutoff_error is not None:
        return ctx.result_handler.handle_pit_cutoff_failure(
            dataset,
            trade_date,
            error=cutoff_error,
        )
    if (
        sparse_pit or ctx.evidence_committer is not None
    ) and ctx.quality_checker is None:
        return ctx.result_handler.handle_quality_check_required(dataset, trade_date)
    if ctx.evidence_committer is not None and not ctx.license_record_id:
        return IngestionResult(
            dataset=dataset,
            trade_date=trade_date,
            status="failed",
            error="R2_LICENSE_RECORD_REQUIRED",
            message="R2 证据模式缺少已审核 license record",
        )

    df, quality_failure = run_write_quality_gate(
        df,
        dataset=dataset,
        trade_date=trade_date,
        quality_checker=ctx.quality_checker,
        result_handler=ctx.result_handler,
    )
    if quality_failure is not None:
        return quality_failure

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

    catalog_ctx = CatalogWriteContext(
        dataset=dataset,
        trade_date=trade_date,
        source_name=ctx.source_name,
        write_result=write_result,
        df=df,
        l1_l2_attested=ctx.quality_checker is not None,
    )
    snapshot_evidence: IngestionSnapshotEvidence | None = None
    if ctx.evidence_committer is not None:
        outcome = ctx.evidence_committer.commit(
            build_evidence_commit_request(
                catalog_ctx,
                license_record_id=ctx.license_record_id,
            )
        )
        if not outcome.completed:
            return IngestionResult(
                dataset=dataset,
                trade_date=trade_date,
                status="failed",
                error=outcome.error_code or "R2_EVIDENCE_COMMIT_FAILED",
                message="R2 摄取证据提交失败, 分区已进入可修复状态",
            )
        if sparse_pit:
            snapshot_evidence = resolve_sparse_asof_snapshot(
                dataset=dataset,
                trade_date=trade_date,
                source_name=ctx.source_name,
                catalog_reader=ctx.catalog_reader,
            )
            if snapshot_evidence is None:
                return ctx.result_handler.handle_pit_snapshot_missing(
                    dataset,
                    trade_date,
                )
    elif sparse_pit:
        if not _record_required_data_catalog_entry(
            catalog_ctx,
            catalog_writer=ctx.catalog_writer,
        ):
            return ctx.result_handler.handle_catalog_evidence_failed(
                dataset,
                trade_date,
            )
        snapshot_evidence = resolve_sparse_asof_snapshot(
            dataset=dataset,
            trade_date=trade_date,
            source_name=ctx.source_name,
            catalog_reader=ctx.catalog_reader,
        )
        if snapshot_evidence is None:
            return ctx.result_handler.handle_pit_snapshot_missing(
                dataset,
                trade_date,
            )

    run_post_ingest_hooks(
        dataset,
        trade_date,
        cursor_store=ctx.cursor_store,
        freeze_store=ctx.freeze_store,
        source_name=ctx.source_name,
    )

    result = ctx.result_handler.handle_success(
        dataset,
        trade_date,
        df,
        write_result,
        snapshot_evidence=snapshot_evidence,
        quality_evidence=(
            IngestionQualityEvidence(
                kind="write_time_l1_l2",
                status="passed",
                source=ctx.source_name,
                trade_date=trade_date,
                levels=("l1", "l2"),
                row_count=write_result.rows_written,
                checksum=write_result.checksum,
            )
            if ctx.quality_checker is not None
            else None
        ),
        persist_log=ctx.evidence_committer is None,
    )
    if ctx.evidence_committer is None:
        record_ingestion_lineage(
            dataset,
            trade_date,
            source_name=ctx.source_name,
            lineage_recorder=ctx.lineage_recorder,
            write_result=write_result,
        )
        if not sparse_pit:
            record_data_catalog_entry(
                catalog_ctx,
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
    l1_l2_attested: bool = False,
) -> str:
    if source_ticker is not None:
        return (
            f"snapshot:{source_name}:{dataset}:{source_ticker}:"
            f"{trade_date}:{end_date or trade_date}:{checksum}"
        )
    return catalog_source_snapshot_id(
        dataset=dataset,
        trade_date=trade_date,
        source=source_name,
        checksum=checksum,
        l1_l2_attested=l1_l2_attested,
    )


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
            _lineage_event(
                dataset,
                trade_date,
                source_name=source_name,
                write_result=write_result,
                source_ticker=source_ticker,
                end_date=end_date,
                now=datetime.now(UTC),
            )
        ),
        log_tag="lineage_record_failed",
        event="lineage_record_error",
        dataset=dataset,
        trade_date=trade_date,
    )


def _lineage_event(
    dataset: str,
    trade_date: str,
    *,
    source_name: str,
    write_result: WriteResult,
    now: datetime,
    source_ticker: str | None = None,
    end_date: str | None = None,
) -> LineageEvent:
    return LineageEvent(
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
        timestamp=now,
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
            l1_l2_attested=ctx.l1_l2_attested,
        ),
    )


def build_evidence_commit_request(
    ctx: CatalogWriteContext,
    *,
    license_record_id: str | None,
) -> EvidenceCommitRequest:
    """Build immutable provider/catalog/lineage/log evidence for one payload."""
    if license_record_id is None:
        raise AppProcessError("R2 evidence commit requires license_record_id")
    now = datetime.now(UTC)
    request_end = ctx.end_date or ctx.trade_date
    catalog_entry = _data_catalog_entry(ctx, now=now)
    request_payload = orjson.dumps(
        [
            ctx.dataset,
            ctx.source_name,
            ctx.trade_date,
            request_end,
            ctx.source_ticker,
        ]
    )
    request_hash = hashlib.sha256(request_payload).hexdigest()
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id=ctx.dataset,
            source=ctx.source_name,
            request_start=ctx.trade_date,
            request_end=request_end,
            schema_version=_dataset_schema_version(ctx.dataset),
            checksum=ctx.write_result.checksum,
            canonical_asset=catalog_entry.asset,
            request_parameters_hash=f"sha256:{request_hash}",
            response_metadata=(("snapshot_layer", "normalized_provider_payload"),),
            license_record_id=license_record_id,
            row_count=ctx.write_result.rows_written,
            payload_uri=ctx.write_result.file_path,
            payload_retained=True,
            created_at=now,
        )
    )
    range_key = f":{ctx.source_ticker}" if ctx.source_ticker is not None else ""
    return EvidenceCommitRequest(
        chunk_id=(
            f"partition:{ctx.source_name}:{ctx.dataset}{range_key}:"
            f"{ctx.trade_date}:{request_end}"
        ),
        dataset_id=ctx.dataset,
        source=ctx.source_name,
        request_start=ctx.trade_date,
        request_end=request_end,
        provider_snapshot=snapshot,
        catalog_entry=catalog_entry,
        lineage_event=_lineage_event(
            ctx.dataset,
            ctx.trade_date,
            source_name=ctx.source_name,
            write_result=ctx.write_result,
            source_ticker=ctx.source_ticker,
            end_date=ctx.end_date,
            now=now,
        ),
        success_log=IngestionLog(
            dataset=ctx.dataset,
            source=ctx.source_name,
            trade_date=ctx.trade_date,
            status=IngestionStatus.SUCCESS,
            checksum=ctx.write_result.checksum,
            rows=ctx.write_result.rows_written,
        ),
        quality_attested=ctx.l1_l2_attested,
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


def _record_required_data_catalog_entry(
    ctx: CatalogWriteContext,
    *,
    catalog_writer: DataCatalogWriter | None,
) -> bool:
    """Persist evidence-critical sparse catalog metadata or fail closed."""
    if catalog_writer is None:
        logger.error(
            "required_catalog_writer_missing",
            event="catalog_evidence_error",
            dataset=ctx.dataset,
            trade_date=ctx.trade_date,
        )
        return False
    try:
        catalog_writer.upsert_asset(
            _data_catalog_entry(
                ctx,
                now=datetime.now(UTC),
            )
        )
    except Exception as error:
        logger.error(
            "required_catalog_upsert_failed",
            event="catalog_evidence_error",
            dataset=ctx.dataset,
            trade_date=ctx.trade_date,
            error_type=type(error).__name__,
        )
        return False
    return True


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
        return result_handler.handle_fetch_error(dataset, date_identifier, error)

    logger.exception(
        f"unexpected_error_{log_tag}",
        dataset=dataset,
        error_type=type(error).__name__,
    )
    return result_handler.handle_unknown_error(dataset, date_identifier, error)
