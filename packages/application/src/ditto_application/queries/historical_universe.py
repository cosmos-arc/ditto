"""Qualified historical universe reads shared by research and selection."""

from dataclasses import asdict, dataclass
from datetime import date, datetime
from hashlib import sha256
from typing import Literal

import orjson
import polars as pl
from ditto_data.catalog.snapshot_reader import SnapshotContents, SnapshotReadService
from ditto_data.services.historical_universe import (
    MASTER_FIELDS,
    MEMBERSHIP_FIELDS,
    STATUS_FIELDS,
    project_historical_universe,
    visible_history,
)

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.field_admission import (
    FieldAdmissionQuery,
    FieldAdmissionRequest,
    FieldRequirement,
)


@dataclass(frozen=True, slots=True)
class HistoricalUniverseSources:
    """Explicit retained sources; mutable metadata is never a fallback."""

    universe_id: str
    asset_kind: Literal["stock", "etf"]
    master_snapshot_id: str
    status_snapshot_id: str
    membership_snapshot_id: str | None = None
    index_id: str | None = None

    def __post_init__(self) -> None:
        """Reject incomplete source and relation bindings."""
        if not self.universe_id or self.asset_kind not in {"stock", "etf"}:
            raise AppQueryError("HISTORY_SCOPE_INVALID")
        if not self.master_snapshot_id or not self.status_snapshot_id:
            raise AppQueryError("HISTORY_SNAPSHOT_MISSING")
        if self.asset_kind == "stock":
            if (self.membership_snapshot_id is None) != (self.index_id is None):
                raise AppQueryError("MEMBERSHIP_SCOPE_MISSING")
        elif self.membership_snapshot_id is not None:
            raise AppQueryError("ETF_INDEX_MEMBERSHIP_UNSUPPORTED")
        if self.index_id is not None and not self.index_id.strip():
            raise AppQueryError("MEMBERSHIP_SCOPE_MISSING")

    @property
    def snapshot_ids(self) -> tuple[str, ...]:
        """All immutable identities entering the projection."""
        return tuple(
            sorted(
                {
                    self.master_snapshot_id,
                    self.status_snapshot_id,
                    *(
                        ()
                        if self.membership_snapshot_id is None
                        else (self.membership_snapshot_id,)
                    ),
                }
            )
        )


@dataclass(frozen=True, slots=True)
class HistoricalUniverseResult:
    """Observation roster plus independently derived investment eligibility."""

    frame: pl.DataFrame
    evidence: dict[str, object]

    @property
    def snapshot_id(self) -> str:
        """Bind actual roster, exclusions, cutoffs and qualification identities."""
        payload = {"evidence": self.evidence, "rows": self.frame.to_dicts()}
        digest = sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()
        return f"universe:sha256:{digest}"


class HistoricalUniverseQuery:
    """Read exact completed artifacts, qualify fields, then project historical rows."""

    def __init__(
        self, reader: SnapshotReadService, admission: FieldAdmissionQuery
    ) -> None:
        self._reader = reader
        self._admission = admission

    def resolve(
        self,
        sources: HistoricalUniverseSources,
        *,
        as_of: date,
        knowledge_cutoff: datetime,
        publication_cutoff: datetime,
    ) -> HistoricalUniverseResult:
        """Return an auditable scope or refuse unproven historical evidence."""
        if (
            knowledge_cutoff.tzinfo is None
            or publication_cutoff.tzinfo is None
            or publication_cutoff > knowledge_cutoff
        ):
            raise AppQueryError("HISTORY_CUTOFF_INVALID")
        definitions: list[tuple[str, str, tuple[str, ...]]] = [
            (
                sources.master_snapshot_id,
                f"{sources.asset_kind}_basic",
                (
                    *MASTER_FIELDS,
                    *(("tracking_index",) if sources.asset_kind == "etf" else ()),
                ),
            ),
            (
                sources.status_snapshot_id,
                "stock_status" if sources.asset_kind == "stock" else "etf_daily",
                STATUS_FIELDS,
            ),
        ]
        if sources.membership_snapshot_id is not None:
            definitions.append(
                (sources.membership_snapshot_id, "index_weight", MEMBERSHIP_FIELDS)
            )
        frames: dict[str, pl.DataFrame] = {}
        reports: list[dict[str, object]] = []
        scope_ids: tuple[int, ...] = ()
        try:
            for snapshot_id, dataset_id, fields in definitions:
                contents = self._reader.read(snapshot_id)
                self._validate_contents(contents, dataset_id, fields, knowledge_cutoff)
                if not scope_ids:
                    ids = visible_history(
                        contents.frame,
                        fields=fields,
                        as_of=as_of,
                        knowledge_cutoff=knowledge_cutoff,
                        publication_cutoff=publication_cutoff,
                    )["instrument_id"]
                    if ids.dtype != pl.Int64 or ids.null_count():
                        raise AppQueryError("HISTORY_INSTRUMENT_INVALID")
                    scope_ids = tuple(sorted(set(ids.to_list())))
                    if not scope_ids:
                        raise AppQueryError("HISTORY_SCOPE_EMPTY")
                report = self._admission.assess(
                    FieldAdmissionRequest(
                        fields=tuple(
                            FieldRequirement(dataset_id, field, snapshot_id)
                            for field in fields
                        ),
                        instrument_ids=scope_ids,
                        required_from=as_of,
                        required_to=as_of,
                        knowledge_cutoff=knowledge_cutoff,
                        publication_cutoff=publication_cutoff,
                        purpose="formal_research",
                    )
                )
                if not report.allowed:
                    reasons = "; ".join(
                        f"{item.dataset_id}.{item.field}: "
                        + ", ".join(item.reason_codes)
                        for item in report.fields
                        if item.reason_codes
                    )
                    raise AppQueryError(
                        f"HISTORY_ADMISSION_BLOCKED: {reasons}", report=report
                    )
                reports.append(
                    {
                        "snapshot_id": snapshot_id,
                        "certification_report_ids": sorted(
                            {
                                item.certification_report_id
                                for item in report.fields
                                if item.certification_report_id is not None
                            }
                        ),
                        "license_record_ids": sorted(
                            {
                                item.license_record_id
                                for item in report.fields
                                if item.license_record_id is not None
                            }
                        ),
                        "rule_version": report.rule_version,
                    }
                )
                frames[snapshot_id] = contents.frame.select(fields)
            frame = project_historical_universe(
                frames[sources.master_snapshot_id],
                frames[sources.status_snapshot_id],
                as_of=as_of,
                knowledge_cutoff=knowledge_cutoff,
                publication_cutoff=publication_cutoff,
                membership=frames.get(sources.membership_snapshot_id or ""),
                index_id=sources.index_id,
            )
        except ValueError as error:
            raise AppQueryError(str(error)) from error
        return HistoricalUniverseResult(
            frame,
            {
                "sources": asdict(sources),
                "as_of": as_of.isoformat(),
                "knowledge_cutoff": knowledge_cutoff.isoformat(),
                "publication_cutoff": publication_cutoff.isoformat(),
                "rule_version": "historical-universe-v1",
                "admission": reports,
                "observation_count": frame.height,
                "investable_count": frame.filter(pl.col("investable")).height,
            },
        )

    @staticmethod
    def _validate_contents(
        contents: SnapshotContents,
        dataset_id: str,
        fields: tuple[str, ...],
        knowledge_cutoff: datetime,
    ) -> None:
        if contents.snapshot.dataset_id != dataset_id:
            raise AppQueryError("HISTORY_SNAPSHOT_CONFLICT")
        if contents.observed_at is None or contents.observed_at > knowledge_cutoff:
            raise AppQueryError("HISTORY_NOT_OBSERVED")
        if contents.snapshot.schema_fingerprint is None:
            raise AppQueryError("HISTORY_SCHEMA_EVIDENCE_MISSING")
        if not set(fields).issubset(contents.frame.columns):
            raise AppQueryError("HISTORY_FIELDS_MISSING")
