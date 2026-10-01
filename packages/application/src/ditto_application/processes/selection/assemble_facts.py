"""
Server-side selection fact assembly from certified catalog evidence.

The selection workspace contract requires the caller to provide every PIT
fact (per-instrument factor values, hard-filter facts, source snapshots).
This process assembles those facts from the local catalog so a policy-only
request (universe, temporal identity, factor weights) can run without
hand-built JSON payloads.

Boundaries kept honest on purpose:

- Factors come from the governed factor registry; the dependency closure is
  resolved transitively (cycle-guarded) and only market-bar leaves are
  allowed. Fundamental dependencies stay fail-closed until those datasets
  are certified for formal research. Requested factors are emitted as
  cross-sectional fractional ranks (unit scores) because the selection
  contract scores weighted sums of unit-normalized values.
- Bars are read through the live market read model at the request's as-of
  instant. Backdated knowledge/publication cutoffs are therefore rejected:
  the live store cannot prove sub-day visibility for past instants. The
  certified replay lane remains the exact-payload path for evidence.
- Admission range claims follow the established per-observation-day
  semantics (``required_from == required_to == cross-section day``, as the
  historical universe query and the reviewed selection contract do);
  lookback provenance rides the frozen consumer payload digests.
- Industry rotation is assembled as an empty observation set; the rotation
  snapshot then lands BLOCKED with ``industries`` declared missing, which is
  the honest state while industry data is not ingested.
- ``is_st`` is derived from the current registry name marker ("ST") because
  the local ``st_change_history`` table is not ingested yet; once it is, the
  identity port can switch to that PIT reader.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

import polars as pl
from ditto_data.provider import BarQuery, DataProvider
from ditto_features.expression.compiler import ExpressionCompiler
from ditto_features.expression.contracts import CompiledDerivedExpression
from ditto_features.expression.diagnostics import ExpressionCompileError
from ditto_features.factors.spec import FactorSpec
from ditto_kernel.identity import InstrumentId

from ditto_application.exceptions import AppProcessError, AppQueryError
from ditto_application.processes.execution._factor_signal_spec import (
    build_signal_spec,
)
from ditto_application.processes.selection.facade import (
    CreateSelectionRunRequest,
    SelectionFactorValueDraft,
    SelectionFactorWeightDraft,
    SelectionInstrumentDraft,
    StockSelectionSpecDraft,
)
from ditto_application.queries.field_admission import FieldRequirement
from ditto_application.queries.historical_universe import (
    HistoricalUniverseQuery,
    HistoricalUniverseResult,
    HistoricalUniverseSources,
)

__all__ = [
    "AssembleSelectionFacts",
    "AssembleSelectionFactsRequest",
    "CertifiedSnapshotIndex",
    "CertifiedSnapshotWindow",
]

_MARKET_BAR_COLUMNS: Mapping[str, str] = {
    "market.open": "open",
    "market.high": "high",
    "market.low": "low",
    "market.close": "close",
    "market.volume": "volume",
    "market.amount": "amount",
}
_REQUIRED_BAR_COLUMNS = frozenset(
    {"instrument_id", "trade_date", "close", "pre_close", "amount"}
)
_BAR_LINEAGE_COLUMN = "source_snapshot_id"
_RESERVED_FACTOR_COLUMNS = frozenset(
    {
        *_MARKET_BAR_COLUMNS,
        *_MARKET_BAR_COLUMNS.values(),
        "instrument_id",
        "trade_date",
        "source",
        "source_ticker",
        "knowledge_date",
        "pct_change",
    }
)
_ROTATION_ALGORITHM_VERSION = "industry-rotation-v1"
_TURNOVER_WINDOW = 20
_MAIN_LIMIT_THRESHOLD = 0.095
_ST_LIMIT_THRESHOLD = 0.045
_CALENDAR_BUFFER_DAYS = 14
_DEFAULT_LOOKBACK_DAYS = 400
_SHANGHAI = ZoneInfo("Asia/Shanghai")


class UniverseSourcesDiscovery(Protocol):
    """Discover retained snapshot chains for one universe at a cutoff."""

    def __call__(
        self,
        *,
        universe_id: str,
        asset_kind: Literal["stock", "etf"],
        knowledge_cutoff: datetime,
    ) -> HistoricalUniverseSources: ...


class InstrumentIdentityReader(Protocol):
    """Resolve durable instrument identities to names and source tickers."""

    def names(self, instrument_ids: Sequence[int]) -> Mapping[int, str]: ...

    def source_tickers(
        self, instrument_ids: Sequence[int], *, asof: date
    ) -> Mapping[int, str]: ...


class FactorRegistry(Protocol):
    """Read governed factor definitions by id."""

    def get(self, factor_id: str) -> FactorSpec | None: ...


@dataclass(frozen=True, slots=True)
class CertifiedSnapshotWindow:
    """One certified registry snapshot and the request range it answers."""

    snapshot_id: str
    request_start: date
    request_end: date


class CertifiedSnapshotIndex(Protocol):
    """Locate certified snapshots of one dataset under the selection profile."""

    def snapshot_ids(self, dataset_id: str) -> tuple[str, ...]:
        """All certified snapshot ids of one dataset."""
        ...

    def covering(
        self, *, dataset_id: str, day: date
    ) -> tuple[CertifiedSnapshotWindow, ...]:
        """Certified snapshots whose request range contains one day."""
        ...


@dataclass(frozen=True, slots=True)
class AssembleSelectionFactsRequest:
    """Policy-only selection input; every fact is resolved server-side."""

    universe_id: str
    asset_kind: Literal["stock", "etf"]
    as_of: datetime
    spec_id: str
    spec_version: str
    top_k: int
    min_average_turnover: float
    min_listing_days: int
    factor_weights: tuple[SelectionFactorWeightDraft, ...]
    excluded_limit_states: tuple[Literal["normal", "limit_up", "limit_down"], ...] = (
        "limit_up",
        "limit_down",
    )
    knowledge_cutoff: datetime | None = None
    publication_cutoff: datetime | None = None
    seed: int = 0
    lookback_days: int = _DEFAULT_LOOKBACK_DAYS

    def resolved_cutoffs(self) -> tuple[datetime, datetime]:
        """Default the PIT cutoffs conservatively to the as-of instant."""
        knowledge = self.knowledge_cutoff or self.as_of
        publication = self.publication_cutoff or knowledge
        return knowledge, publication


@dataclass(frozen=True, slots=True)
class _FactorNode:
    """One governed factor materialized in dependency order."""

    factor_id: str
    compiled: CompiledDerivedExpression
    requested: bool
    leaves: frozenset[str]


class AssembleSelectionFacts:
    """Assemble one CreateSelectionRunRequest from certified catalog evidence."""

    def __init__(
        self,
        *,
        provider: DataProvider,
        history: HistoricalUniverseQuery,
        discover_sources: UniverseSourcesDiscovery,
        identities: InstrumentIdentityReader,
        factors: FactorRegistry,
        snapshots: CertifiedSnapshotIndex,
        compiler: ExpressionCompiler | None = None,
    ) -> None:
        self._provider = provider
        self._history = history
        self._discover_sources = discover_sources
        self._identities = identities
        self._factors = factors
        self._snapshots = snapshots
        self._compiler = compiler or ExpressionCompiler()

    def assemble(
        self, request: AssembleSelectionFactsRequest
    ) -> CreateSelectionRunRequest:
        """Resolve roster, bars, factors and lineage for one policy request."""
        if request.asset_kind != "stock":
            raise AppProcessError(
                "server-side assembly currently supports the stock lane only",
                details={"reason": "ASSEMBLY_ASSET_KIND_UNSUPPORTED"},
            )
        if request.as_of.tzinfo is None:
            raise AppProcessError(
                "assembled selection as-of must carry a timezone",
                details={"reason": "ASSEMBLY_TIME_INVALID"},
            )
        knowledge, publication = request.resolved_cutoffs()
        if (
            publication.tzinfo is None
            or knowledge.tzinfo is None
            or publication > knowledge
            or knowledge > request.as_of
        ):
            raise AppProcessError(
                "assembled selection cutoffs violate causal order",
                details={"reason": "ASSEMBLY_CUTOFF_INVALID"},
            )
        if (
            request.knowledge_cutoff is not None
            and request.knowledge_cutoff < request.as_of
        ) or (
            request.publication_cutoff is not None
            and request.publication_cutoff < request.as_of
        ):
            raise AppProcessError(
                "backdated cutoffs cannot use the live read model; "
                + "use the certified replay lane for past instants",
                details={"reason": "ASSEMBLY_CUTOFF_BACKDATED"},
            )
        as_of_date = request.as_of.astimezone(_SHANGHAI).date()
        sources = self._roster_sources(request)
        roster = self._resolve_roster(request, sources, knowledge, publication)
        nodes = self._plan_factors(request)
        evaluation = self._load_bars(
            roster=roster,
            request=request,
            nodes=nodes,
            as_of_date=as_of_date,
        )
        cross_date = _cross_section_date(evaluation)
        instruments = self._project_instruments(
            roster=roster,
            evaluation=evaluation,
            nodes=nodes,
            as_of_date=as_of_date,
            cross_date=cross_date,
        )
        windows = self._binding_windows(cross_date)
        return CreateSelectionRunRequest(
            as_of=request.as_of,
            knowledge_cutoff=knowledge,
            publication_cutoff=publication,
            rotation_source_snapshot_ids=tuple(
                window.snapshot_id for window in windows["stock_daily"]
            ),
            market_context_feature_set_id=None,
            membership_version="catalog",
            rotation_algorithm_version=_ROTATION_ALGORITHM_VERSION,
            industries=(),
            rotation_missing_inputs=("industries",),
            universe_snapshot_id=roster.snapshot_id,
            selection_source_snapshot_ids=tuple(
                sorted(
                    {
                        *(
                            window.snapshot_id
                            for group in windows.values()
                            for window in group
                        ),
                        *sources.snapshot_ids,
                    }
                )
            ),
            selection_spec=StockSelectionSpecDraft(
                spec_id=request.spec_id,
                spec_version=request.spec_version,
                top_k=request.top_k,
                min_average_turnover=request.min_average_turnover,
                min_listing_days=request.min_listing_days,
                factor_weights=request.factor_weights,
                excluded_limit_states=request.excluded_limit_states,
            ),
            seed=request.seed,
            instruments=instruments,
            data_fields=data_fields(windows, nodes),
            data_from=claimed_from(evaluation, windows, cross_date),
            data_to=cross_date,
            universe_sources=sources,
        )

    def _roster_sources(
        self, request: AssembleSelectionFactsRequest
    ) -> HistoricalUniverseSources:
        """Retain the certified registry chains the roster resolves against."""
        try:
            return HistoricalUniverseSources(
                universe_id=request.universe_id,
                asset_kind=request.asset_kind,
                master_snapshot_ids=self._snapshots.snapshot_ids("stock_basic"),
                status_snapshot_ids=self._snapshots.snapshot_ids("stock_status"),
            )
        except AppQueryError as error:
            raise AppProcessError(
                str(error),
                details={"reason": "ASSEMBLY_SOURCES_MISSING", **error.details},
            ) from error

    def _resolve_roster(
        self,
        request: AssembleSelectionFactsRequest,
        sources: HistoricalUniverseSources,
        knowledge: datetime,
        publication: datetime,
    ) -> HistoricalUniverseResult:
        try:
            return self._history.resolve(
                sources,
                as_of=request.as_of.astimezone(_SHANGHAI).date(),
                knowledge_cutoff=knowledge,
                publication_cutoff=publication,
            )
        except AppQueryError as error:
            raise AppProcessError(str(error), details=error.details) from error

    def _plan_factors(
        self, request: AssembleSelectionFactsRequest
    ) -> tuple[_FactorNode, ...]:
        """Resolve the transitive factor closure in dependency order."""
        order: list[str] = []
        leaves: dict[str, frozenset[str]] = {}
        compiled: dict[str, CompiledDerivedExpression] = {}

        def visit(factor_id: str, path: tuple[str, ...]) -> frozenset[str]:
            if factor_id in leaves:
                return leaves[factor_id]
            if factor_id in path:
                cycle = (*path, factor_id)
                raise AppProcessError(
                    f"registered factor dependency cycle: {' -> '.join(cycle)}",
                    details={
                        "reason": "ASSEMBLY_FACTOR_CYCLE",
                        "factor_id": factor_id,
                        "dependency_path": cycle,
                    },
                )
            spec = self._factor_spec(factor_id)
            node_leaves = {
                leaf
                for dependency in spec.dependencies
                for leaf in self._dependency_leaves(dependency, factor_id, path, visit)
            }
            leaves[factor_id] = frozenset(node_leaves)
            compiled[factor_id] = self._compile_factor(factor_id, spec)
            order.append(factor_id)
            return leaves[factor_id]

        requested = {weight.name for weight in request.factor_weights}
        for weight in request.factor_weights:
            visit(weight.name, ())
        return tuple(
            _FactorNode(
                factor_id=factor_id,
                compiled=compiled[factor_id],
                requested=factor_id in requested,
                leaves=leaves[factor_id],
            )
            for factor_id in order
        )

    def _factor_spec(self, factor_id: str) -> FactorSpec:
        spec = self._factors.get(factor_id)
        if spec is None:
            raise AppProcessError(
                f"unknown registered factor: {factor_id}",
                details={"reason": "ASSEMBLY_FACTOR_UNKNOWN", "factor_id": factor_id},
            )
        if spec.computation_type != "expression":
            raise AppProcessError(
                f"research factor executor is unavailable: {factor_id}",
                details={
                    "reason": "ASSEMBLY_FACTOR_EXECUTOR_UNAVAILABLE",
                    "factor_id": factor_id,
                },
            )
        return spec

    def _dependency_leaves(
        self,
        dependency: str,
        factor_id: str,
        path: tuple[str, ...],
        visit: Callable[[str, tuple[str, ...]], frozenset[str]],
    ) -> frozenset[str]:
        """Classify one declared dependency as market leaf or nested factor."""
        if self._factors.get(dependency) is not None:
            return visit(dependency, (*path, factor_id))
        if dependency in _MARKET_BAR_COLUMNS:
            return frozenset({dependency})
        raise AppProcessError(
            "factor dependency is not certified for assembly: "
            + f"{factor_id} -> {dependency}",
            details={
                "reason": "ASSEMBLY_FACTOR_DEPENDENCY_UNSUPPORTED",
                "factor_id": factor_id,
                "dependency": dependency,
            },
        )

    def _compile_factor(
        self, factor_id: str, spec: FactorSpec
    ) -> CompiledDerivedExpression:
        try:
            return self._compiler.compile(
                build_signal_spec(spec.expression, 0, derived_id=factor_id, version=1)
            )
        except ExpressionCompileError as error:
            raise AppProcessError(
                f"registered factor failed to compile: {factor_id}",
                details={"reason": "ASSEMBLY_FACTOR_COMPILE", "factor_id": factor_id},
            ) from error

    def _load_bars(
        self,
        *,
        roster: HistoricalUniverseResult,
        request: AssembleSelectionFactsRequest,
        nodes: tuple[_FactorNode, ...],
        as_of_date: date,
    ) -> pl.DataFrame:
        roster_ids = [int(row["instrument_id"]) for row in roster.frame.to_dicts()]
        tickers = self._identities.source_tickers(roster_ids, asof=as_of_date)
        if not tickers:
            raise AppProcessError(
                "assembled selection found no resolvable instruments",
                details={"reason": "ASSEMBLY_UNIVERSE_EMPTY"},
            )
        max_lookback = max(
            _TURNOVER_WINDOW,
            *(node.compiled.analysis.lookback for node in nodes),
        )
        lookback_calendar_days = max(
            request.lookback_days,
            math.ceil(max_lookback * 7 / 5) + _CALENDAR_BUFFER_DAYS,
        )
        start = as_of_date - timedelta(days=lookback_calendar_days)
        frame = self._provider.get_bars(
            BarQuery(
                instruments=tuple(
                    tickers[instrument_id] for instrument_id in sorted(tickers)
                ),
                start=start.isoformat(),
                end=as_of_date.isoformat(),
                asof=as_of_date.isoformat(),
            )
        )
        if frame.is_empty():
            raise AppProcessError(
                "assembled selection found no bars in the lookback window",
                details={"reason": "ASSEMBLY_BARS_MISSING"},
            )
        needed_leaves = {
            leaf for node in nodes if node.requested for leaf in node.leaves
        }
        self._validate_bar_schema(frame, needed_leaves)
        frame = _without_future_knowledge(frame, as_of_date)
        if frame.is_empty():
            raise AppProcessError(
                "assembled selection bars only carry future knowledge",
                details={"reason": "ASSEMBLY_BARS_MISSING"},
            )
        evaluation = frame.sort(["instrument_id", "trade_date"])
        for leaf in sorted(needed_leaves):
            column = _MARKET_BAR_COLUMNS[leaf]
            evaluation = evaluation.with_columns(
                pl.col(column).cast(pl.Float64).alias(leaf)
            )
        reserved = _RESERVED_FACTOR_COLUMNS
        for node in nodes:
            if node.factor_id in reserved:
                raise AppProcessError(
                    "registered factor id collides with a bar column",
                    details={
                        "reason": "ASSEMBLY_FACTOR_COLUMN_CONFLICT",
                        "factor_id": node.factor_id,
                    },
                )
            evaluation = evaluation.with_columns(
                node.compiled.expr.alias(node.factor_id)
            )
        return evaluation

    def _validate_bar_schema(
        self, frame: pl.DataFrame, needed_leaves: frozenset[str] | set[str]
    ) -> None:
        """Fail closed when the read model cannot serve the assembly."""
        missing_columns = sorted(_REQUIRED_BAR_COLUMNS - set(frame.columns))
        if _BAR_LINEAGE_COLUMN not in frame.columns:
            missing_columns.append(_BAR_LINEAGE_COLUMN)
        if missing_columns:
            raise AppProcessError(
                "assembled selection bar schema is missing required columns",
                details={
                    "reason": "ASSEMBLY_BARS_SCHEMA",
                    "columns": tuple(missing_columns),
                },
            )
        missing_leaves = sorted(
            leaf
            for leaf in needed_leaves
            if _MARKET_BAR_COLUMNS[leaf] not in frame.columns
        )
        if missing_leaves:
            raise AppProcessError(
                "assembled selection bars cannot serve factor dependencies",
                details={
                    "reason": "ASSEMBLY_BARS_SCHEMA",
                    "dependencies": tuple(missing_leaves),
                },
            )

    def _project_instruments(
        self,
        *,
        roster: HistoricalUniverseResult,
        evaluation: pl.DataFrame,
        nodes: tuple[_FactorNode, ...],
        as_of_date: date,
        cross_date: date,
    ) -> tuple[SelectionInstrumentDraft, ...]:
        roster_rows = roster.frame.to_dicts()
        names = self._identities.names(
            [int(row["instrument_id"]) for row in roster_rows]
        )
        cross = _unit_normalized(
            evaluation.filter(pl.col("trade_date") == cross_date),
            nodes,
        )
        cross_rows = {int(row["instrument_id"]): row for row in cross.to_dicts()}
        turnover = {
            int(row["instrument_id"]): row["_average_turnover"]
            for row in evaluation.group_by("instrument_id")
            .agg(
                pl.col("amount")
                .rolling_mean(window_size=_TURNOVER_WINDOW)
                .last()
                .alias("_average_turnover")
            )
            .to_dicts()
        }
        drafts: list[SelectionInstrumentDraft] = []
        for row in roster_rows:
            instrument_id = int(row["instrument_id"])
            instrument_name = names.get(instrument_id, str(instrument_id))
            bar_row = cross_rows.get(instrument_id)
            lineage = bar_row.get(_BAR_LINEAGE_COLUMN) if bar_row is not None else None
            if bar_row is None or lineage is None:
                causes = ["bars"] if bar_row is None else ["source_snapshot"]
                drafts.append(
                    SelectionInstrumentDraft(
                        instrument_id=InstrumentId(instrument_id),
                        instrument_name=instrument_name,
                        industry_id=None,
                        factor_values=(),
                        average_turnover=None,
                        is_st=_is_st_from_name(instrument_name),
                        is_suspended=row["is_suspended"],
                        listing_days=_listing_days(row.get("list_date"), as_of_date),
                        limit_state=None,
                        tracking_error=None,
                        declared_missing_inputs=tuple(causes),
                    )
                )
                continue
            missing_factors: list[str] = []
            values: list[SelectionFactorValueDraft] = []
            for node in nodes:
                if not node.requested:
                    continue
                raw = bar_row.get(node.factor_id)
                if raw is None or float(raw) != float(raw):
                    missing_factors.append(f"factor:{node.factor_id}")
                    continue
                values.append(
                    SelectionFactorValueDraft(name=node.factor_id, value=float(raw))
                )
            drafts.append(
                SelectionInstrumentDraft(
                    instrument_id=InstrumentId(instrument_id),
                    instrument_name=instrument_name,
                    industry_id=None,
                    factor_values=tuple(values),
                    average_turnover=turnover.get(instrument_id),
                    is_st=_is_st_from_name(instrument_name),
                    is_suspended=row["is_suspended"],
                    listing_days=_listing_days(row.get("list_date"), as_of_date),
                    limit_state=_limit_state(
                        close=bar_row.get("close"),
                        pre_close=bar_row.get("pre_close"),
                        is_st=_is_st_from_name(instrument_name),
                    ),
                    tracking_error=None,
                    declared_missing_inputs=tuple(missing_factors),
                )
            )
        return tuple(drafts)

    def _binding_windows(
        self, cross_date: date
    ) -> dict[str, tuple[CertifiedSnapshotWindow, ...]]:
        return {
            dataset_id: self._snapshots.covering(dataset_id=dataset_id, day=cross_date)
            for dataset_id in ("stock_daily", "stock_status", "stock_basic")
        }


def _without_future_knowledge(frame: pl.DataFrame, as_of_date: date) -> pl.DataFrame:
    """Drop bar rows that claim knowledge strictly after the decision date."""
    if "knowledge_date" not in frame.columns:
        return frame
    knowledge = pl.col("knowledge_date")
    if frame.schema["knowledge_date"] == pl.String:
        knowledge = knowledge.str.to_date()
    return frame.filter(knowledge <= pl.lit(as_of_date))


def _unit_normalized(
    cross: pl.DataFrame, nodes: tuple[_FactorNode, ...]
) -> pl.DataFrame:
    """
    Rank each requested factor cross-section into a (0, 1] unit score.

    The selection contract scores weighted sums of unit-normalized values;
    raw factor magnitudes (for example a 252-day return above 1.0) would
    both break the domain bound and mix incomparable scales. Fractional
    average ranks keep ties deterministic and preserve ordering.
    """
    for node in nodes:
        if not node.requested:
            continue
        cross = cross.with_columns(
            (
                pl.col(node.factor_id).fill_nan(None).rank(method="average") / pl.len()
            ).alias(node.factor_id)
        )
    return cross


def _cross_section_date(evaluation: pl.DataFrame) -> date:
    """Return the latest visible trade date (frames here are never empty)."""
    cross_date = evaluation["trade_date"].max()
    if not isinstance(cross_date, date):
        raise AppProcessError(
            "assembled selection bars carry no observable trade date",
            details={"reason": "ASSEMBLY_BARS_MISSING"},
        )
    return cross_date


def _is_st_from_name(instrument_name: str) -> bool:
    """Read the exchange ST marking from the registry name (v1 source)."""
    return "ST" in instrument_name.upper()


def _listing_days(list_date: object, as_of_date: date) -> int | None:
    if not isinstance(list_date, date):
        return None
    return max(0, (as_of_date - list_date).days)


def _limit_state(
    *, close: object, pre_close: object, is_st: bool
) -> Literal["normal", "limit_up", "limit_down"] | None:
    """
    Classify the close against the exchange price-limit band.

    ST names use the ±4.5% band (5% cap with margin); regular names use
    ±9.5%. Wider boards (20%) are not modeled yet, so the conservative band
    classifies more moves as limited, never fewer.
    """
    if not isinstance(close, (int, float)) or not isinstance(pre_close, (int, float)):
        return None
    if pre_close <= 0:
        return None
    change = float(close) / float(pre_close) - 1.0
    threshold = _ST_LIMIT_THRESHOLD if is_st else _MAIN_LIMIT_THRESHOLD
    if change >= threshold:
        return "limit_up"
    if change <= -threshold:
        return "limit_down"
    return "normal"


def claimed_from(
    evaluation: pl.DataFrame,
    windows: Mapping[str, tuple[CertifiedSnapshotWindow, ...]],
    cross_date: date,
) -> date | None:
    """Claim the widest observation range every binding can prove together."""
    starts = [window.request_start for group in windows.values() for window in group]
    if not starts:
        return None
    first_observed = evaluation["trade_date"].min()
    if not isinstance(first_observed, date):
        return None
    claim = max(first_observed, *starts)
    return claim if claim <= cross_date else None


def data_fields(
    windows: Mapping[str, tuple[CertifiedSnapshotWindow, ...]],
    nodes: tuple[_FactorNode, ...],
) -> tuple[FieldRequirement, ...]:
    """Bind every consumed selection input to its reviewed source field."""
    fields: list[FieldRequirement] = []

    def bind(dataset_id: str, field: str, consumer_field: str) -> None:
        for window in windows.get(dataset_id, ()):
            fields.append(
                FieldRequirement(dataset_id, field, window.snapshot_id, consumer_field)
            )

    for consumer_field in (
        "universe_snapshot_id",
        "instruments.instrument_id",
        "instruments.instrument_name",
        "instruments.industry_id",
        "instruments.is_st",
        "instruments.listing_days",
    ):
        bind("stock_basic", "list_status", consumer_field)
    bind("stock_status", "is_suspended", "instruments.is_suspended")
    bind("stock_daily", "close", "instruments.limit_state")
    bind("stock_daily", "close", "membership_version")
    bind("stock_daily", "amount", "instruments.average_turnover")
    for node in nodes:
        if not node.requested:
            continue
        for leaf in sorted(node.leaves):
            bind(
                "stock_daily",
                _MARKET_BAR_COLUMNS[leaf],
                f"instruments.factor_values.{node.factor_id}",
            )
    return tuple(fields)
