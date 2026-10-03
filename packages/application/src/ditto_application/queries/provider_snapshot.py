"""Application entrypoint for retained provider evidence and qualified replay."""

from dataclasses import dataclass
from datetime import date, datetime

import polars as pl
from ditto_data.catalog.metadata import default_dataset_metadata
from ditto_data.catalog.snapshot_reader import (
    SnapshotContents,
    SnapshotReadService,
    SourceTickerResolver,
)

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.snapshot_readiness import (
    FieldRequirement,
    SnapshotReadinessQuery,
    SnapshotReadinessReport,
    SnapshotReadinessRequest,
)

__all__ = [
    "ProviderSnapshotQuery",
    "SnapshotReplay",
    "SnapshotReplayRequest",
]


@dataclass(frozen=True, slots=True)
class SnapshotReplay:
    """Pinned read result with the exact readiness findings used."""

    readiness: SnapshotReadinessReport
    frames: dict[str, pl.DataFrame]


@dataclass(frozen=True, slots=True)
class SnapshotReplayRequest:
    """Pinned replay projection: exact fields, instruments, interval, cutoff."""

    fields: tuple[FieldRequirement, ...]
    instrument_ids: tuple[int, ...]
    required_from: date
    required_to: date
    knowledge_cutoff: datetime

    def __post_init__(self) -> None:
        """Fail closed on ambiguous or empty replay scopes."""
        if self.required_from > self.required_to:
            raise AppQueryError("snapshot replay interval is reversed")
        if not self.instrument_ids or not self.fields:
            raise AppQueryError("snapshot replay requires fields and instruments")
        if self.knowledge_cutoff.tzinfo is None:
            raise AppQueryError("snapshot replay requires a knowledge cutoff")


class ProviderSnapshotQuery:
    """Keep audit access distinct from permission to start new research."""

    def __init__(
        self,
        reader: SnapshotReadService,
        readiness: SnapshotReadinessQuery,
        *,
        ticker_resolver: SourceTickerResolver | None = None,
    ) -> None:
        self._reader = reader
        self._readiness = readiness
        self._ticker_resolver = ticker_resolver

    def read_for_audit(self, snapshot_id: str) -> SnapshotContents:
        """Read exact completed bytes without claiming current research eligibility."""
        try:
            return self._reader.read(snapshot_id)
        except ValueError as error:
            raise AppQueryError(str(error)) from error

    def replay(self, request: SnapshotReplayRequest) -> SnapshotReplay:
        """Read only the ready fields, instruments and interval at pinned cutoffs."""
        if any(
            _replay_identity_unsupported(item.dataset_id) for item in request.fields
        ):
            raise AppQueryError(
                "snapshot replay requires instrument- and trade-date-keyed datasets",
            )
        report = self._readiness.assess(
            SnapshotReadinessRequest(
                fields=request.fields,
                required_from=request.required_from,
                required_to=request.required_to,
            )
        )
        if not report.ready:
            raise AppQueryError("snapshot replay data is incomplete", report=report)
        frames: dict[str, pl.DataFrame] = {}
        for snapshot_id in dict.fromkeys(item.snapshot_id for item in request.fields):
            columns = tuple(
                item.field for item in request.fields if item.snapshot_id == snapshot_id
            )
            try:
                frames[snapshot_id] = self._reader.read_fields(
                    snapshot_id,
                    columns,
                    instrument_ids=request.instrument_ids,
                    date_range=(request.required_from, request.required_to),
                    knowledge_cutoff=request.knowledge_cutoff,
                    ticker_resolver=self._ticker_resolver,
                )
            except ValueError as error:
                raise AppQueryError(str(error)) from error
        return SnapshotReplay(report, frames)


def _replay_identity_unsupported(dataset_id: str) -> bool:
    """Only this projector is instrument/date-shaped; readiness is not restricted."""
    metadata = default_dataset_metadata().get(dataset_id)
    return (
        metadata is None
        or metadata.dataset_spec is None
        or not {"instrument_id", "trade_date"}.issubset(
            metadata.dataset_spec.primary_key
        )
    )
