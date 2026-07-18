"""按标的摄取 — instrument-level 数据摄取逻辑."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl
from ditto_data.catalog import DataCatalogWriter
from ditto_data.catalog.metadata import dataset_asset_class
from ditto_data.lineage import DataLineageRecorder
from ditto_data.models import Dataset
from ditto_data.models.ingestion import IngestionQualityEvidence, IngestionResult
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
from ditto_application.processes.ingestion.evidence_commit import (
    IngestionEvidenceCommitter,
)
from ditto_application.processes.ingestion.fetch_handlers import (
    build_instrument_fetch_handlers,
)
from ditto_application.processes.ingestion.ports import QualityCheckerProtocol
from ditto_application.processes.ingestion.post_ingest import (
    CatalogWriteContext,
    DataWriteContext,
    build_evidence_commit_request,
    handle_fetch_error,
    record_data_catalog_entry,
    record_ingestion_lineage,
    write_data_safe,
)
from ditto_application.processes.ingestion.quality_gate import run_write_quality_gate
from ditto_application.processes.ingestion.result_handler import IngestionResultHandler
from ditto_application.processes.ingestion.source_capability import (
    ensure_source_supported,
)
from ditto_application.processes.ingestion.types import SourceFetchers

__all__ = [
    "InstrumentBackfillContext",
    "InstrumentIngestContext",
    "InstrumentPostIngestContext",
    "backfill_adj_factor",
    "ingest_by_instrument",
]


@dataclass(frozen=True)
class InstrumentBackfillContext:
    """Runtime dependencies for instrument backfill orchestration."""

    metadata_service: MetadataService
    market_service: MarketService
    fetchers: SourceFetchers
    source_name: str
    data_writer: IngestionDataWriter
    lineage_recorder: DataLineageRecorder | None = None


@dataclass(frozen=True)
class InstrumentIngestContext:
    """Runtime dependencies for instrument-range ingestion."""

    fetchers: SourceFetchers
    metadata_service: MetadataService
    source_name: str
    result_handler: IngestionResultHandler
    data_writer: IngestionDataWriter
    lineage_recorder: DataLineageRecorder | None = None
    catalog_writer: DataCatalogWriter | None = None
    quality_checker: QualityCheckerProtocol | None = None
    evidence_committer: IngestionEvidenceCommitter | None = None
    license_record_id: str | None = None


@dataclass(frozen=True)
class InstrumentPostIngestContext:
    """Runtime dependencies for instrument-range post-ingest processing."""

    result_handler: IngestionResultHandler
    data_writer: IngestionDataWriter
    source_name: str
    lineage_recorder: DataLineageRecorder | None = None
    catalog_writer: DataCatalogWriter | None = None
    quality_checker: QualityCheckerProtocol | None = None
    evidence_committer: IngestionEvidenceCommitter | None = None
    license_record_id: str | None = None


def ingest_by_instrument(
    dataset: str,
    params: InstrumentIngestParams,
    force: bool,
    *,
    ctx: InstrumentIngestContext,
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
    ensure_source_supported(dataset_enum, ctx.source_name)

    if dataset_enum not in SUPPORTED_INSTRUMENT_DATASETS:
        raise AppProcessError(
            f"数据集 {dataset} 不支持按标的摄取",
            field="dataset",
            value=dataset,
        )

    asset_class = dataset_asset_class(dataset)
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
        metadata_service=ctx.metadata_service,
        source=ctx.fetchers.metadata,
        source_name=ctx.source_name,
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
        ctx=ctx,
    )


def _fetch_and_ingest_by_instrument(
    dataset: str,
    dataset_enum: Dataset,
    source_ticker: str,
    params: InstrumentIngestParams,
    *,
    ctx: InstrumentIngestContext,
) -> IngestionResult:
    """按标的获取数据并执行摄取（统一错误处理）。"""
    df_or_result = _try_fetch_data_by_instrument(
        dataset,
        dataset_enum,
        source_ticker,
        params,
        fetchers=ctx.fetchers,
        result_handler=ctx.result_handler,
        source_name=ctx.source_name,
    )

    if isinstance(df_or_result, IngestionResult):
        return df_or_result

    return _process_fetched_data_by_instrument(
        df_or_result,
        dataset,
        source_ticker,
        params,
        ctx=InstrumentPostIngestContext(
            result_handler=ctx.result_handler,
            data_writer=ctx.data_writer,
            source_name=ctx.source_name,
            lineage_recorder=ctx.lineage_recorder,
            catalog_writer=ctx.catalog_writer,
            quality_checker=ctx.quality_checker,
            evidence_committer=ctx.evidence_committer,
            license_record_id=ctx.license_record_id,
        ),
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


def _process_fetched_data_by_instrument(  # noqa: PLR0911 - fail-closed stages
    df: pl.DataFrame,
    dataset: str,
    source_ticker: str,
    params: InstrumentIngestParams,
    *,
    ctx: InstrumentPostIngestContext,
) -> IngestionResult:
    """按标的处理获取的数据：写入。"""
    if df.is_empty():
        return ctx.result_handler.handle_empty_data(dataset, params.start_date)
    if ctx.evidence_committer is not None and ctx.quality_checker is None:
        return ctx.result_handler.handle_quality_check_required(
            dataset, params.start_date
        )
    if ctx.evidence_committer is not None and not ctx.license_record_id:
        return IngestionResult(
            dataset=dataset,
            trade_date=params.start_date,
            status="failed",
            error="R2_LICENSE_RECORD_REQUIRED",
            message="R2 证据模式缺少已审核 license record",
        )

    df, quality_failure = run_write_quality_gate(
        df,
        dataset=dataset,
        trade_date=params.start_date,
        quality_checker=ctx.quality_checker,
        result_handler=ctx.result_handler,
    )
    if quality_failure is not None:
        return quality_failure

    on_duplicate = OnDuplicate.KEEP_LAST

    write_result = write_data_safe(
        DataWriteContext(
            dataset=dataset,
            df=df,
            trade_date=params.start_date,
            on_duplicate=on_duplicate,
            source_ticker=source_ticker,
            event_suffix="_by_instrument",
        ),
        result_handler=ctx.result_handler,
        data_writer=ctx.data_writer,
    )
    if isinstance(write_result, IngestionResult):
        return write_result

    if write_result.blocked:
        return ctx.result_handler.handle_dq_blocked(
            dataset, params.start_date, write_result
        )
    catalog_ctx = CatalogWriteContext(
        dataset=dataset,
        trade_date=params.start_date,
        source_name=ctx.source_name,
        write_result=write_result,
        df=df,
        source_ticker=source_ticker,
        end_date=params.end_date,
        l1_l2_attested=ctx.quality_checker is not None,
    )
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
                trade_date=params.start_date,
                status="failed",
                error=outcome.error_code or "R2_EVIDENCE_COMMIT_FAILED",
                message="R2 摄取证据提交失败, 分区已进入可修复状态",
            )

    result = ctx.result_handler.handle_success(
        dataset,
        params.start_date,
        df,
        write_result,
        quality_evidence=(
            IngestionQualityEvidence(
                kind="write_time_l1_l2",
                status="passed",
                source=ctx.source_name,
                trade_date=params.start_date,
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
            params.start_date,
            source_name=ctx.source_name,
            lineage_recorder=ctx.lineage_recorder,
            write_result=write_result,
            source_ticker=source_ticker,
            end_date=params.end_date,
        )
        record_data_catalog_entry(
            catalog_ctx,
            catalog_writer=ctx.catalog_writer,
        )
    return result


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


def backfill_adj_factor(
    instrument_id: int,
    start: str,
    end: str,
    *,
    ctx: InstrumentBackfillContext,
) -> dict[str, object]:
    """按标的智能回补复权因子空洞，委托至 backfill_handler。"""
    return _backfill_adj_factor(
        instrument_id=instrument_id,
        start=start,
        end=end,
        ctx=BackfillContext(
            metadata_service=ctx.metadata_service,
            market_service=ctx.market_service,
            source=ctx.fetchers.market,
            source_name=ctx.source_name,
            data_writer=ctx.data_writer,
            lineage_recorder=ctx.lineage_recorder,
        ),
    )
