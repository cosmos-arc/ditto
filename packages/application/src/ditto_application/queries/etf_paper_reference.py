"""Compose exact ETF Paper inputs without relabeling their source identities."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime

from ditto_data.catalog.provider_payload import (
    ProviderPayloadArtifact,
    ProviderPayloadReader,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader

from ditto_application.etf_paper_contracts import canonical_cutoff
from ditto_application.exceptions import AppProcessError
from ditto_application.queries.etf_candidates import ETFCandidate
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.snapshot_readiness import SnapshotReadinessQuery

# Only fields actually supplied by each producer may supplement the primary
# reference. An ETF basic snapshot cannot assert execution fees or raw prices.
_INPUT_FIELDS = {
    "etf_daily": frozenset({"price_close"}),
    "etf_reference": frozenset(
        {
            "trading_currency",
            "trading_restriction",
            "lot_size",
            "tick_size",
            "settlement_cycle",
            "price_limit_pct",
            "commission_rate",
            "min_commission",
            "stamp_duty_rate",
            "transfer_fee_rate",
        }
    ),
}


@dataclass(frozen=True)
class ETFPaperReferenceQuery:
    """The pinned input collection and its shared visibility boundary."""

    asof: str
    cutoff: datetime
    snapshot_id: str
    input_snapshot_ids: dict[str, str]


def paper_reference_candidates(
    *,
    metadata: MetadataQueryFacade,
    readiness: SnapshotReadinessQuery,
    snapshots: ProviderSnapshotReader,
    payloads: ProviderPayloadReader,
    query: ETFPaperReferenceQuery,
) -> dict[int, ETFCandidate]:
    """Resolve each declared input under the same cutoff and its own identity."""
    asof, cutoff = query.asof, query.cutoff
    snapshot_id, input_snapshot_ids = query.snapshot_id, query.input_snapshot_ids
    candidates: dict[int, ETFCandidate] = {}
    for dataset, identity in [("", snapshot_id), *sorted(input_snapshot_ids.items())]:
        snapshot = snapshots.get_snapshot(identity)
        allowed = {"etf_basic", "etf_reference"} if not dataset else {dataset}
        if dataset and dataset not in _INPUT_FIELDS:
            raise AppProcessError(f"ETF Paper unsupported input dataset: {dataset}")
        if (
            snapshot is None
            or snapshot.snapshot_id != identity
            or snapshot.dataset_id not in allowed
            or snapshot.created_at > cutoff
            or not snapshot.payload_retained
            or snapshot.payload_uri is None
        ):
            raise AppProcessError(
                f"ETF Paper {dataset or 'reference'} snapshot "
                + "is absent, mismatched or future"
            )
        day = date.fromisoformat(asof)
        reasons = readiness.snapshot_reasons(snapshot.dataset_id, identity, day, day)
        if reasons:
            raise AppProcessError(
                f"ETF Paper {snapshot.dataset_id} snapshot is not consumable: "
                + ", ".join(reasons)
            )
        try:
            payloads.read_payload(
                ProviderPayloadArtifact(
                    dataset_id=snapshot.dataset_id,
                    source=snapshot.source,
                    checksum=snapshot.checksum,
                    row_count=snapshot.row_count,
                    uri=snapshot.payload_uri,
                )
            )
        except (ValueError, OSError) as error:
            raise AppProcessError(
                f"ETF Paper {snapshot.dataset_id} payload is unavailable"
            ) from error
        rows = metadata.list_etf_candidates(
            asof=asof,
            cutoff=canonical_cutoff(cutoff),
            source_snapshot_id=identity,
        )
        for row in rows:
            if any(
                field.source_snapshot_id == identity and field.source != snapshot.source
                for field in row.fields.values()
                if field.value is not None
            ):
                raise AppProcessError("ETF Paper reference field source mismatch")
        if not dataset:
            candidates = {row.instrument_id: row for row in rows}
            continue
        _supplement_candidates(candidates, rows, dataset, identity)
    return candidates


def _supplement_candidates(
    candidates: dict[int, ETFCandidate],
    rows: list[ETFCandidate],
    dataset: str,
    identity: str,
) -> None:
    """Merge only producer-owned fields, retaining every field's own identity."""
    for row in rows:
        primary = candidates.get(row.instrument_id)
        if primary is None:
            continue
        fields = dict(primary.fields)
        for name in _INPUT_FIELDS[dataset]:
            field = row.fields.get(name)
            if field is not None and field.source_snapshot_id == identity:
                fields[name] = field
        candidates[row.instrument_id] = replace(primary, fields=fields)
