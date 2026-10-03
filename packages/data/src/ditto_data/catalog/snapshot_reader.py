"""Exact immutable snapshot reads; never fall back to the mutable canonical asset."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

import polars as pl

from ditto_data.catalog.provider_payload import (
    ProviderPayloadArtifact,
    ProviderPayloadReader,
)
from ditto_data.catalog.snapshot_completion import snapshot_completed
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotReader
from ditto_data.ingestion.partition_state import PartitionLifecycleReader

__all__ = [
    "SnapshotContents",
    "SnapshotReadService",
    "SourceTickerResolver",
]


class SourceTickerResolver(Protocol):
    """
    Resolve durable instrument identities to one provider's source tickers.

    Retained provider payloads keep the provider's native identity grain
    (``source_ticker``); qualified replay scopes are expressed in resolved
    instrument identities. The caller supplies this port so the catalog reader
    stays free of metadata-store dependencies. Resolution is per qualified
    date under the replay request's knowledge cutoff, so identity changes and
    later-recorded mappings stay PIT-correct.
    """

    def __call__(
        self,
        instrument_ids: Sequence[int],
        *,
        source: str,
        asofs: Sequence[date],
        cutoff: datetime,
    ) -> Mapping[str, Mapping[int, str]]:
        """Return per-ISO-date mappings of instrument identity to source ticker."""
        ...


@dataclass(frozen=True, slots=True)
class SnapshotContents:
    """Pinned raw evidence for audit; qualification is a separate application check."""

    snapshot: ProviderSnapshot
    previous_snapshot_id: str | None
    observed_at: datetime | None
    frame: pl.DataFrame


class SnapshotReadService:
    """Read retained content only after its own ingestion completed."""

    def __init__(
        self,
        snapshots: ProviderSnapshotReader,
        payloads: ProviderPayloadReader,
        lifecycle: PartitionLifecycleReader,
    ) -> None:
        self._snapshots = snapshots
        self._payloads = payloads
        self._lifecycle = lifecycle

    def read(self, snapshot_id: str) -> SnapshotContents:
        """Verify the exact content identity and completion before reading bytes."""
        snapshot = self._snapshots.get_snapshot(snapshot_id)
        if snapshot is None or snapshot.snapshot_id != snapshot.expected_snapshot_id():
            raise ValueError("provider snapshot is missing or has invalid identity")
        if not snapshot_completed(snapshot, self._lifecycle):
            raise ValueError("provider snapshot has no COMPLETE checkpoint")
        if not snapshot.payload_retained or snapshot.payload_uri is None:
            raise ValueError("provider snapshot has no retained payload")
        # Sharing one artifact across schema versions is legitimate when the
        # physical bytes are the schema; the payload read pins them via the
        # persisted schema fingerprint, so exactness is proven there.
        frame = self._payloads.read_payload(
            ProviderPayloadArtifact(
                dataset_id=snapshot.dataset_id,
                source=snapshot.source,
                checksum=snapshot.checksum,
                row_count=snapshot.row_count,
                uri=snapshot.payload_uri,
                schema_fingerprint=snapshot.schema_fingerprint,
            )
        )
        return SnapshotContents(
            snapshot,
            self._snapshots.get_predecessor(snapshot_id),
            self._snapshots.get_observed_at(snapshot_id),
            frame,
        )

    def read_fields(
        self,
        snapshot_id: str,
        columns: tuple[str, ...],
        *,
        instrument_ids: tuple[int, ...],
        date_range: tuple[date, date],
        knowledge_cutoff: datetime | None = None,
        ticker_resolver: SourceTickerResolver | None = None,
    ) -> pl.DataFrame:
        """
        Project only the caller-qualified instrument, interval and field scope.

        Payloads keyed by resolved ``instrument_id`` filter directly. Payloads
        kept at the provider's native ``source_ticker`` grain filter through
        the supplied resolver, which must resolve every requested instrument
        on at least one qualified date under the request's knowledge cutoff;
        without a resolver the read fails closed because the qualified scope
        cannot be expressed.
        """
        contents = self.read(snapshot_id)
        if knowledge_cutoff is not None and (
            knowledge_cutoff.tzinfo is None
            or contents.snapshot.created_at > knowledge_cutoff
        ):
            raise ValueError("snapshot was not observable at the knowledge cutoff")
        frame = contents.frame
        if not {"trade_date", *columns}.issubset(frame.columns):
            raise ValueError(
                "snapshot replay requires retained instrument/date/field columns"
            )
        if "instrument_id" in frame.columns:
            identity = pl.col("instrument_id").is_in(instrument_ids)
            selected = tuple(dict.fromkeys(("instrument_id", "trade_date", *columns)))
            return frame.filter(
                identity & pl.col("trade_date").is_between(*date_range)
            ).select(selected)
        if ticker_resolver is None or "source_ticker" not in frame.columns:
            raise ValueError(
                "snapshot replay requires retained instrument/date/field columns"
            )
        selected = tuple(dict.fromkeys(("source_ticker", "trade_date", *columns)))
        if knowledge_cutoff is None:
            raise ValueError("ticker-keyed snapshot replay requires a knowledge cutoff")
        in_range = frame.filter(pl.col("trade_date").is_between(*date_range))
        asofs = sorted(
            value.date() if isinstance(value, datetime) else value
            for value in in_range["trade_date"].unique().to_list()
        )
        resolved_by_date = ticker_resolver(
            instrument_ids,
            source=contents.snapshot.source,
            asofs=asofs,
            cutoff=knowledge_cutoff,
        )
        resolved_anywhere = {
            instrument_id
            for per_date in resolved_by_date.values()
            for instrument_id in per_date
        }
        unresolved = [
            instrument_id
            for instrument_id in instrument_ids
            if instrument_id not in resolved_anywhere
        ]
        if unresolved:
            rendered = ", ".join(str(item) for item in unresolved)
            raise ValueError(
                "snapshot replay cannot resolve instrument identities: " + rendered
            )
        pairs = pl.DataFrame(
            {
                "trade_date": [
                    asof
                    for asof in asofs
                    for _ in resolved_by_date.get(asof.isoformat(), {})
                ],
                "source_ticker": [
                    ticker
                    for asof in asofs
                    for ticker in resolved_by_date.get(asof.isoformat(), {}).values()
                ],
            },
            schema={"trade_date": pl.Date, "source_ticker": pl.String},
        ).cast({"trade_date": in_range.schema["trade_date"]})
        return in_range.join(pairs, on=["trade_date", "source_ticker"], how="semi")[
            list(selected)
        ]
