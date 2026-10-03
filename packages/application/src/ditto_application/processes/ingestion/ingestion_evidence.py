"""Canonical catalog and provider snapshot evidence builders."""

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
from ditto_data.catalog.provider_payload import (
    ProviderPayloadArtifact,
    schema_fingerprint,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.models.ingestion import IngestionLog, IngestionStatus
from ditto_platform.foundation import WriteResult

from ditto_application.catalog_freshness import catalog_source_snapshot_id
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.evidence_commit import EvidenceCommitRequest

__all__ = [
    "CatalogWriteContext",
    "build_data_catalog_entry",
    "build_evidence_commit_request",
]

# license 治理已删除;列保留给 #396 重置时移除,写入统一占位值。
UNUSED_LICENSE_RECORD_ID = "unused"


@dataclass(frozen=True)
class CatalogWriteContext:
    """Catalog metadata context for one successful ingestion write."""

    dataset: str
    trade_date: str
    source_name: str
    write_result: WriteResult
    df: pl.DataFrame
    source_ticker: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    l1_l2_attested: bool = False
    chunk_id: str | None = None
    payload_retained: bool = True
    provider_payload: ProviderPayloadArtifact | None = None


def _dataset_namespace(dataset: str) -> str:
    metadata = default_dataset_metadata().get(dataset)
    return "data" if metadata is None else metadata.domain


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


def _source_snapshot_id(
    ctx: CatalogWriteContext,
) -> str:
    start = ctx.start_date or ctx.trade_date
    if ctx.source_ticker is not None or ctx.end_date is not None:
        snapshot_id = (
            f"snapshot:{ctx.source_name}:{ctx.dataset}:{ctx.source_ticker or 'all'}:"
            f"{start}:{ctx.end_date or ctx.trade_date}:"
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


def _schema_hash_from_dataframe(df: pl.DataFrame) -> str:
    fields = [
        (name, str(dtype)) for name, dtype in zip(df.columns, df.dtypes, strict=True)
    ]
    payload = orjson.dumps(fields).decode()
    return f"schema:sha256:{hashlib.sha256(payload.encode()).hexdigest()}"


def dataset_schema_version(dataset: str) -> str:
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
            ctx.start_date or ctx.trade_date,
            source_ticker=ctx.source_ticker,
            end_date=ctx.end_date,
        ),
        storage_uri=ctx.write_result.file_path,
        schema=DataSchemaFingerprint(
            schema_hash=_schema_hash_from_dataframe(ctx.df),
            row_count=ctx.write_result.rows_written,
            created_at=now,
            schema_version=dataset_schema_version(ctx.dataset),
            columns=tuple(ctx.df.columns),
        ),
        source=ctx.source_name,
        freshness_at=now,
        source_snapshot_id=_source_snapshot_id(ctx),
    )


def build_evidence_commit_request(
    ctx: CatalogWriteContext,
) -> EvidenceCommitRequest:
    """Build immutable provider/catalog/log evidence for one payload."""
    if ctx.payload_retained and ctx.provider_payload is None:
        raise AppProcessError("R2 evidence commit requires immutable provider payload")
    now = datetime.now(UTC)
    request_start = ctx.start_date or ctx.trade_date
    request_end = ctx.end_date or ctx.trade_date
    catalog_entry = build_data_catalog_entry(ctx, now=now)
    request_hash = hashlib.sha256(
        orjson.dumps(
            [
                ctx.dataset,
                ctx.source_name,
                request_start,
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
            request_start=request_start,
            request_end=request_end,
            schema_version=dataset_schema_version(ctx.dataset),
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
            license_record_id=UNUSED_LICENSE_RECORD_ID,
            row_count=payload_row_count,
            payload_uri=(
                ctx.provider_payload.uri
                if ctx.provider_payload is not None and ctx.payload_retained
                else None
            ),
            payload_retained=ctx.payload_retained,
            created_at=now,
            schema_fingerprint=(
                schema_fingerprint(ctx.df) if ctx.payload_retained else None
            ),
        )
    )
    return EvidenceCommitRequest(
        chunk_id=ingestion_partition_id(
            source=ctx.source_name,
            dataset=ctx.dataset,
            start=request_start,
            end=request_end,
            source_ticker=ctx.source_ticker,
            chunk_id=ctx.chunk_id,
        ),
        dataset_id=ctx.dataset,
        source=ctx.source_name,
        request_start=request_start,
        request_end=request_end,
        ingestion_date=ctx.trade_date,
        provider_snapshot=snapshot,
        catalog_entry=catalog_entry,
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


def ingestion_partition_id(
    *,
    source: str,
    dataset: str,
    start: str,
    end: str,
    source_ticker: str | None = None,
    chunk_id: str | None = None,
) -> str:
    """Share request identity between write intent and committed evidence."""
    range_key = f":{source_ticker}" if source_ticker is not None else ""
    return chunk_id or f"partition:{source}:{dataset}{range_key}:{start}:{end}"
