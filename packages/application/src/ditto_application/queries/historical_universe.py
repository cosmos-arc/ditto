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
    """
    Explicit retained source chains; mutable metadata is never a fallback.

    Each chain is pinned up front; a resolution picks, per dataset, the latest
    member already observed locally by that point's knowledge cutoff, so a
    multi-day build replays exactly what the local catalog could see each day.
    """

    universe_id: str
    asset_kind: Literal["stock", "etf"]
    master_snapshot_ids: tuple[str, ...]
    status_snapshot_ids: tuple[str, ...]
    membership_snapshot_ids: tuple[str, ...] = ()
    index_id: str | None = None

    def __post_init__(self) -> None:
        """Reject incomplete source and relation bindings."""
        if not self.universe_id or self.asset_kind not in {"stock", "etf"}:
            raise AppQueryError("HISTORY_SCOPE_INVALID")
        chains = (
            self.master_snapshot_ids,
            self.status_snapshot_ids,
            self.membership_snapshot_ids,
        )
        if not self.master_snapshot_ids or not self.status_snapshot_ids:
            raise AppQueryError("HISTORY_SNAPSHOT_MISSING")
        if any(not item.strip() for chain in chains for item in chain):
            raise AppQueryError("HISTORY_SNAPSHOT_MISSING")
        if self.asset_kind == "stock":
            if bool(self.membership_snapshot_ids) != (self.index_id is not None):
                raise AppQueryError("MEMBERSHIP_SCOPE_MISSING")
        elif self.membership_snapshot_ids:
            raise AppQueryError("ETF_INDEX_MEMBERSHIP_UNSUPPORTED")
        if self.index_id is not None and not self.index_id.strip():
            raise AppQueryError("MEMBERSHIP_SCOPE_MISSING")

    @property
    def snapshot_ids(self) -> tuple[str, ...]:
        """All immutable identities entering the projection."""
        return tuple(
            sorted(
                {
                    *self.master_snapshot_ids,
                    *self.status_snapshot_ids,
                    *self.membership_snapshot_ids,
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


@dataclass(frozen=True, slots=True)
class PinnedHistoricalUniverse:
    """Pinned evidence loaded once; each resolve projects one exact time point."""

    sources: HistoricalUniverseSources
    admission: FieldAdmissionQuery
    master: tuple[SnapshotContents, ...]
    status: tuple[SnapshotContents, ...]
    membership: tuple[SnapshotContents, ...] = ()

    def resolve(
        self,
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
        definitions: list[
            tuple[str, tuple[SnapshotContents, ...], str, tuple[str, ...]]
        ] = [
            (
                "master",
                self.master,
                f"{self.sources.asset_kind}_basic",
                (
                    *MASTER_FIELDS,
                    *(("tracking_index",) if self.sources.asset_kind == "etf" else ()),
                ),
            ),
            (
                "status",
                self.status,
                "stock_status" if self.sources.asset_kind == "stock" else "etf_daily",
                STATUS_FIELDS,
            ),
        ]
        if self.membership:
            definitions.append(
                ("membership", self.membership, "index_weight", MEMBERSHIP_FIELDS)
            )
        frames: dict[str, pl.DataFrame] = {}
        reports: list[dict[str, object]] = []
        scope_ids: tuple[int, ...] = ()
        try:
            for _slot, chain, dataset_id, fields in definitions:
                contents = self._observed_by(chain, knowledge_cutoff)
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
                report = self.admission.assess(
                    FieldAdmissionRequest(
                        fields=tuple(
                            FieldRequirement(
                                dataset_id, field, contents.snapshot.snapshot_id
                            )
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
                        "snapshot_id": contents.snapshot.snapshot_id,
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
                frames[_slot] = contents.frame.select(fields)
            frame = project_historical_universe(
                frames["master"],
                frames["status"],
                as_of=as_of,
                knowledge_cutoff=knowledge_cutoff,
                publication_cutoff=publication_cutoff,
                membership=frames.get("membership"),
                index_id=self.sources.index_id,
            )
        except ValueError as error:
            raise AppQueryError(str(error)) from error
        # Evidence is persisted as JSON (spine manifests): normalize tuple chains
        # to lists so the round-tripped manifest still compares equal.
        sources_evidence = orjson.loads(orjson.dumps(asdict(self.sources)))
        return HistoricalUniverseResult(
            frame,
            {
                "sources": sources_evidence,
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
    def _observed_by(
        chain: tuple[SnapshotContents, ...], knowledge_cutoff: datetime
    ) -> SnapshotContents:
        """Pick the latest member already observed locally by the cutoff."""
        observed = [
            (contents.observed_at, contents.snapshot.snapshot_id, contents)
            for contents in chain
            if contents.observed_at is not None
            and contents.observed_at <= knowledge_cutoff
        ]
        if not observed:
            raise AppQueryError("HISTORY_NOT_OBSERVED")
        return max(observed, key=lambda item: (item[0], item[1]))[2]


def _validate_contents(
    contents: SnapshotContents,
    dataset_id: str,
    fields: tuple[str, ...],
) -> None:
    if contents.snapshot.dataset_id != dataset_id:
        raise AppQueryError("HISTORY_SNAPSHOT_CONFLICT")
    if contents.snapshot.schema_fingerprint is None:
        raise AppQueryError("HISTORY_SCHEMA_EVIDENCE_MISSING")
    if not set(fields).issubset(contents.frame.columns):
        raise AppQueryError("HISTORY_FIELDS_MISSING")


class HistoricalUniverseQuery:
    """Read exact completed artifacts, qualify fields, then project historical rows."""

    def __init__(
        self, reader: SnapshotReadService, admission: FieldAdmissionQuery
    ) -> None:
        self._reader = reader
        self._admission = admission

    def pin(self, sources: HistoricalUniverseSources) -> PinnedHistoricalUniverse:
        """Load and structurally validate every pinned member exactly once."""
        definitions: list[tuple[str, tuple[str, ...], str, tuple[str, ...]]] = [
            (
                "master",
                sources.master_snapshot_ids,
                f"{sources.asset_kind}_basic",
                (
                    *MASTER_FIELDS,
                    *(("tracking_index",) if sources.asset_kind == "etf" else ()),
                ),
            ),
            (
                "status",
                sources.status_snapshot_ids,
                "stock_status" if sources.asset_kind == "stock" else "etf_daily",
                STATUS_FIELDS,
            ),
        ]
        if sources.membership_snapshot_ids:
            definitions.append(
                (
                    "membership",
                    sources.membership_snapshot_ids,
                    "index_weight",
                    MEMBERSHIP_FIELDS,
                )
            )
        chains: dict[str, tuple[SnapshotContents, ...]] = {}
        try:
            for slot, snapshot_ids, dataset_id, fields in definitions:
                members: list[SnapshotContents] = []
                for snapshot_id in snapshot_ids:
                    contents = self._reader.read(snapshot_id)
                    _validate_contents(contents, dataset_id, fields)
                    members.append(contents)
                chains[slot] = tuple(members)
        except ValueError as error:
            raise AppQueryError(str(error)) from error
        return PinnedHistoricalUniverse(
            sources=sources,
            admission=self._admission,
            master=chains["master"],
            status=chains["status"],
            membership=chains.get("membership", ()),
        )

    def resolve(
        self,
        sources: HistoricalUniverseSources,
        *,
        as_of: date,
        knowledge_cutoff: datetime,
        publication_cutoff: datetime,
    ) -> HistoricalUniverseResult:
        """Return an auditable scope or refuse unproven historical evidence."""
        return self.pin(sources).resolve(
            as_of=as_of,
            knowledge_cutoff=knowledge_cutoff,
            publication_cutoff=publication_cutoff,
        )
