"""Canonical catalog, provider snapshot, and lineage evidence builders."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

import orjson
import polars as pl
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
    default_dataset_metadata,
)
from ditto_data.catalog.provider_payload import ProviderPayloadArtifact
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.lineage import (
    DataLineageRecorder,
    LineageEvent,
    LineageInputRef,
    LineageOutputRef,
)
from ditto_data.models.ingestion import IngestionLog, IngestionStatus
from ditto_platform.foundation import WriteResult, logger

from ditto_application.catalog_freshness import catalog_source_snapshot_id
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.evidence_commit import EvidenceCommitRequest

__all__ = [
    "CatalogWriteContext",
    "build_data_catalog_entry",
    "build_evidence_commit_request",
    "record_ingestion_lineage",
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
    chunk_id: str | None = None
    payload_retained: bool = True
    provider_payload: ProviderPayloadArtifact | None = None


def _dataset_namespace(dataset: str) -> str:
    metadata = default_dataset_metadata().get(dataset)
    return "data" if metadata is None else metadata.domain


def _source_asset(
    dataset: str,
    trade_date: str,
    source_name: str,
    *,
    source_ticker: str | None = None,
    end_date: str | None = None,
) -> DataAssetRef:
    if source_ticker is not None or end_date is not None:
        range_end = end_date or trade_date
        range_keys = (
            f"source={source_name}",
            f"start_date={trade_date}",
            f"end_date={range_end}",
        )
        if source_ticker is None:
            return DataAssetRef(
                dataset_id=dataset,
                namespace="source",
                partition_keys=range_keys,
            )
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
    if source_ticker is not None or end_date is not None:
        range_end = end_date or trade_date
        range_keys = (
            f"start_date={trade_date}",
            f"end_date={range_end}",
        )
        if source_ticker is None:
            return DataAssetRef(
                dataset_id=dataset,
                namespace=_dataset_namespace(dataset),
                partition_keys=range_keys,
            )
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
    if source_ticker is not None or end_date is not None:
        return (
            f"ingest:{source_name}:{dataset}:{source_ticker or 'all'}:"
            f"{trade_date}:{end_date or trade_date}:{checksum}"
        )
    return f"ingest:{source_name}:{dataset}:{trade_date}:{checksum}"


def _source_snapshot_id(
    ctx: CatalogWriteContext,
) -> str:
    if ctx.source_ticker is not None or ctx.end_date is not None:
        snapshot_id = (
            f"snapshot:{ctx.source_name}:{ctx.dataset}:{ctx.source_ticker or 'all'}:"
            f"{ctx.trade_date}:{ctx.end_date or ctx.trade_date}:"
            f"{ctx.write_result.checksum}"
        )
        return f"{snapshot_id}:quality=l1-l2" if ctx.l1_l2_attested else snapshot_id
    return catalog_source_snapshot_id(
        dataset=ctx.dataset,
        trade_date=ctx.trade_date,
        source=ctx.source_name,
        checksum=ctx.write_result.checksum,
        l1_l2_attested=ctx.l1_l2_attested,
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
    """Record source-to-payload lineage without failing an otherwise valid write."""
    if lineage_recorder is None:
        return
    try:
        lineage_recorder.record_event(
            _lineage_event(
                dataset,
                trade_date,
                source_name=source_name,
                write_result=write_result,
                source_ticker=source_ticker,
                end_date=end_date,
                now=datetime.now(UTC),
            )
        )
    except (AppProcessError, ValueError, KeyError, TypeError, OSError) as error:
        logger.warning(
            "lineage_record_failed",
            event="lineage_record_error",
            dataset=dataset,
            trade_date=trade_date,
            error_type=type(error).__name__,
            error=str(error),
        )
    except Exception:
        logger.exception(
            "lineage_record_failed_unexpected",
            event="lineage_record_error",
            dataset=dataset,
            trade_date=trade_date,
        )


def _schema_hash_from_dataframe(df: pl.DataFrame) -> str:
    fields = [
        (name, str(dtype)) for name, dtype in zip(df.columns, df.dtypes, strict=True)
    ]
    payload = orjson.dumps(fields).decode()
    return f"schema:sha256:{hashlib.sha256(payload.encode()).hexdigest()}"


def _dataset_schema_version(dataset: str) -> str:
    metadata = default_dataset_metadata().get(dataset)
    if metadata is None or metadata.schema_version is None:
        raise AppProcessError(
            f"Missing DataCatalog schema_version for dataset={dataset!r}"
        )
    return metadata.schema_version


def build_data_catalog_entry(
    ctx: CatalogWriteContext,
    *,
    now: datetime,
) -> DataCatalogEntry:
    """Build the canonical catalog entry for one persisted payload."""
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
        source_snapshot_id=_source_snapshot_id(ctx),
    )


def build_evidence_commit_request(
    ctx: CatalogWriteContext,
    *,
    license_record_id: str | None,
) -> EvidenceCommitRequest:
    """Build immutable provider/catalog/lineage/log evidence for one payload."""
    if license_record_id is None:
        raise AppProcessError("R2 evidence commit requires license_record_id")
    if ctx.payload_retained and ctx.provider_payload is None:
        raise AppProcessError("R2 evidence commit requires immutable provider payload")
    now = datetime.now(UTC)
    request_end = ctx.end_date or ctx.trade_date
    catalog_entry = build_data_catalog_entry(ctx, now=now)
    request_hash = hashlib.sha256(
        orjson.dumps(
            [
                ctx.dataset,
                ctx.source_name,
                ctx.trade_date,
                request_end,
                ctx.source_ticker,
            ]
        )
    ).hexdigest()
    payload_checksum = (
        ctx.provider_payload.checksum
        if ctx.provider_payload is not None
        else ctx.write_result.checksum
    )
    payload_row_count = (
        ctx.provider_payload.row_count
        if ctx.provider_payload is not None
        else ctx.write_result.rows_written
    )
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id=ctx.dataset,
            source=ctx.source_name,
            request_start=ctx.trade_date,
            request_end=request_end,
            schema_version=_dataset_schema_version(ctx.dataset),
            checksum=payload_checksum,
            canonical_asset=catalog_entry.asset,
            request_parameters_hash=f"sha256:{request_hash}",
            response_metadata=(
                (
                    "snapshot_layer",
                    (
                        "normalized_provider_payload"
                        if ctx.payload_retained
                        else "verified_empty_provider_observation"
                    ),
                ),
            ),
            license_record_id=license_record_id,
            row_count=payload_row_count,
            payload_uri=(
                ctx.provider_payload.uri
                if ctx.provider_payload is not None and ctx.payload_retained
                else None
            ),
            payload_retained=ctx.payload_retained,
            created_at=now,
        )
    )
    range_key = f":{ctx.source_ticker}" if ctx.source_ticker is not None else ""
    return EvidenceCommitRequest(
        chunk_id=ctx.chunk_id
        or (
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
