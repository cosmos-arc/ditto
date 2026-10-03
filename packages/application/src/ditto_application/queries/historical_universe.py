"""Qualified historical universe reads shared by research and selection."""

from collections.abc import Callable
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
    project_basic_master_intervals,
    project_daily_status_intervals,
    project_historical_universe,
    visible_history,
)

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.snapshot_readiness import (
    FieldRequirement,
    SnapshotReadinessQuery,
    SnapshotReadinessRequest,
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
    readiness: SnapshotReadinessQuery
    master: tuple[SnapshotContents, ...]
    status: tuple[SnapshotContents, ...]
    membership: tuple[SnapshotContents, ...] = ()
    ticker_resolver: Callable[..., dict[str, int]] | None = None

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
                frame = self._project_slot(_slot, contents, knowledge_cutoff)
                if not scope_ids:
                    ids = visible_history(
                        frame,
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
                # Coverage self-attests against the snapshot's own request
                # interval: daily datasets only cover their trade date, and
                # cross-date honesty is carried by the projected row filter
                # (missing status rows surface as TRADING_STATUS_MISSING).
                report = self.readiness.assess(
                    SnapshotReadinessRequest(
                        fields=tuple(
                            FieldRequirement(
                                dataset_id, field, contents.snapshot.snapshot_id
                            )
                            for field in fields
                        ),
                        required_from=date.fromisoformat(
                            contents.snapshot.request_start
                        ),
                        required_to=date.fromisoformat(contents.snapshot.request_end),
                    )
                )
                if not report.ready:
                    reasons = "; ".join(
                        f"{item.dataset_id}.{item.field}: "
                        + ", ".join(item.reason_codes)
                        for item in report.fields
                        if item.reason_codes
                    )
                    raise AppQueryError(
                        f"HISTORY_DATA_INCOMPLETE: {reasons}", report=report
                    )
                reports.append(
                    {
                        "snapshot_id": contents.snapshot.snapshot_id,
                        "rule_version": report.rule_version,
                    }
                )
                frames[_slot] = frame.select(fields)
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
                "readiness": reports,
                "observation_count": frame.height,
                "investable_count": frame.filter(pl.col("investable")).height,
            },
        )

    def _project_slot(
        self,
        slot: str,
        contents: SnapshotContents,
        knowledge_cutoff: datetime,
    ) -> pl.DataFrame:
        """
        Project raw provider frames into the PIT interval shape per slot.

        Real stock_basic/stock_status payloads carry the provider's native
        daily shapes; the projection is an honest same-observation mapping
        (no retroactive facts). Frames already carrying PIT intervals pass
        through unchanged, so golden fixtures keep their exact semantics.
        """
        # Golden PIT frames pass through; only source_ticker-keyed raw
        # payloads take the projection path.
        if "source_ticker" not in contents.frame.columns:
            return contents.frame
        resolver = self._resolver(contents)
        if resolver is None:
            return contents.frame
        observed_at = contents.observed_at or contents.snapshot.created_at
        if slot == "master":
            return project_basic_master_intervals(
                contents.frame,
                observed_at=observed_at,
                resolve_instrument=resolver,
            )
        if slot == "status":
            return project_daily_status_intervals(
                contents.frame,
                observed_at=observed_at,
                resolve_instrument=resolver,
            )
        return contents.frame

    def _resolver(
        self, contents: SnapshotContents
    ) -> Callable[[list[str], str], dict[str, int]] | None:
        if self.ticker_resolver is None:
            return None
        source = contents.snapshot.source
        ticker_resolver = self.ticker_resolver

        def resolve(tickers: list[str], asof: str) -> dict[str, int]:
            return ticker_resolver(tickers, source=source, asof=asof)

        return resolve

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
    # Raw provider shapes (source_ticker-keyed payloads) are validated after
    # their PIT projection at resolve time; golden PIT frames validate here.
    if "source_ticker" in contents.frame.columns:
        return
    if not set(fields).issubset(contents.frame.columns):
        raise AppQueryError("HISTORY_FIELDS_MISSING")


class HistoricalUniverseQuery:
    """Read exact completed artifacts, qualify fields, then project historical rows."""

    def __init__(
        self,
        reader: SnapshotReadService,
        readiness: SnapshotReadinessQuery,
        *,
        ticker_resolver: Callable[..., dict[str, int]] | None = None,
    ) -> None:
        self._reader = reader
        self._readiness = readiness
        self._ticker_resolver = ticker_resolver

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
            readiness=self._readiness,
            master=chains["master"],
            status=chains["status"],
            membership=chains.get("membership", ()),
            ticker_resolver=self._ticker_resolver,
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
