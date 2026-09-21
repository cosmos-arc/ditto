"""Application entrypoint for retained provider evidence and qualified replay."""

from dataclasses import dataclass

import polars as pl
from ditto_data.catalog.metadata import default_dataset_metadata
from ditto_data.catalog.snapshot_reader import SnapshotContents, SnapshotReadService

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.field_admission import (
    FieldAdmissionQuery,
    FieldAdmissionReport,
    FieldAdmissionRequest,
)


@dataclass(frozen=True, slots=True)
class SnapshotReplay:
    """Pinned read result with the exact certification and rule identities used."""

    admission: FieldAdmissionReport
    frames: dict[str, pl.DataFrame]


class ProviderSnapshotQuery:
    """Keep audit access distinct from permission to start new research."""

    def __init__(
        self, reader: SnapshotReadService, admission: FieldAdmissionQuery
    ) -> None:
        self._reader = reader
        self._admission = admission

    def read_for_audit(self, snapshot_id: str) -> SnapshotContents:
        """Read exact completed bytes without claiming current research eligibility."""
        try:
            return self._reader.read(snapshot_id)
        except ValueError as error:
            raise AppQueryError(str(error)) from error

    def replay(self, request: FieldAdmissionRequest) -> SnapshotReplay:
        """Read only the approved fields, instruments and interval at pinned cutoffs."""
        if any(
            _replay_identity_unsupported(item.dataset_id) for item in request.fields
        ):
            raise AppQueryError(
                "snapshot replay requires instrument- and trade-date-keyed datasets",
            )
        report = self._admission.assess(request)
        if not report.allowed:
            raise AppQueryError("snapshot replay field admission failed", report=report)
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
                )
            except ValueError as error:
                raise AppQueryError(str(error)) from error
        return SnapshotReplay(report, frames)


def _replay_identity_unsupported(dataset_id: str) -> bool:
    """Only this projector is instrument/date-shaped; admission is not restricted."""
    metadata = default_dataset_metadata().get(dataset_id)
    return (
        metadata is None
        or metadata.dataset_spec is None
        or not {"instrument_id", "trade_date"}.issubset(
            metadata.dataset_spec.primary_key
        )
    )
