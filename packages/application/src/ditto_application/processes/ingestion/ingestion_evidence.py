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
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotDraft,
    snapshot_identity,
)
from ditto_data.models.ingestion import IngestionLog, IngestionStatus
from ditto_platform.foundation import WriteResult

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.ingestion.evidence_commit import EvidenceCommitRequest

__all__ = [
    "CatalogWriteContext",
    "build_data_catalog_entry",
    "build_evidence_commit_request",
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
    start_date: str | None = None
    end_date: str | None = None
    l1_l2_attested: bool = False
    chunk_id: str | None = None
    payload_retained: bool = True
    provider_payload: ProviderPayloadArtifact | None = None


def _dataset_namespace(dataset: str) -> str:
    metadata = default_dataset_metadata().get(dataset)
    return "data" if metadata is None else metadata.domain


def _output_asset(dataset: str) -> DataAssetRef:
    """
    #394: catalog 收敛为数据集级描述行,partition_keys 恒为空。

    每 (namespace, dataset_id) 一行整行 replace;精确来源覆盖由
    provider_snapshots 承载,不再物化到 catalog 分区。
    """
    return DataAssetRef(
        dataset_id=dataset,
        namespace=_dataset_namespace(dataset),
        partition_keys=(),
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


def display_snapshot_id(ctx: CatalogWriteContext) -> str:
    """Canonical provider snapshot identity for this write, without storing it."""
    return snapshot_identity(
        ctx.dataset,
        ctx.source_name,
        ctx.start_date or ctx.trade_date,
        ctx.end_date or ctx.trade_date,
        dataset_schema_version(ctx.dataset),
        ctx.write_result.checksum,
    )


def build_data_catalog_entry(
    ctx: CatalogWriteContext,
    *,
    now: datetime,
    source_snapshot_id: str,
) -> DataCatalogEntry:
    """
    Build the dataset-level catalog entry for one persisted payload.

    整行 replace:freshness_at 取本次写入时刻,schema_* 取本次载荷,
    source_snapshot_id 保留最后写入的 canonical snapshot id 仅作展示。
    """
    return DataCatalogEntry(
        asset=_output_asset(ctx.dataset),
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
        source_snapshot_id=source_snapshot_id,
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
            canonical_asset=_output_asset(ctx.dataset),
            request_parameters_hash=f"sha256:{request_hash}",
            response_metadata=tuple(
                sorted(
                    (
                        (
                            "snapshot_layer",
                            (
                                "normalized_provider_payload"
                                if ctx.payload_retained
                                else "verified_empty_provider_observation"
                            ),
                        ),
                        # 数据集级 canonical asset 不再携带标的维度;按标的写入
                        # 仍把标的事实留在响应元数据里,行级 lineage 据此区分
                        # 标的专属窗口与全市场窗口。
                        *(
                            (("source_ticker", ctx.source_ticker),)
                            if ctx.source_ticker is not None
                            else ()
                        ),
                    )
                )
            ),
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
        catalog_entry=build_data_catalog_entry(
            ctx,
            now=now,
            source_snapshot_id=snapshot.snapshot_id,
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
