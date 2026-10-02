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
  instant. Any past instant — backdated cutoffs or a past as-of with omitted
  cutoffs — is rejected because the live store cannot prove sub-day
  visibility for it; the certified replay lane remains the exact-payload
  path for historical evidence. Rows carry a required ``knowledge_date``
  column, and rows claiming future knowledge are dropped fail-closed.
- The admission claim covers the full consumed read range (earliest
  observed bar through cross-section day): the computed values already
  consumed that history, so insufficient snapshot coverage must surface as
  admission reasons instead of being narrowed away.
- Bars are read with ``hfq`` adjustment because the governed stock-lane
  price factors require adjusted prices; the adjustment lineage binds to
  the ``adj_factor`` dataset, which stays fail-closed until certified.
  The live adjustment table is read at execution time — adjustment
  knowledge provenance, like exact per-payload bar provenance, belongs to
  the certified replay lane. The exchange price-limit band is judged on a
  separate raw (unadjusted) read because hfq keeps ``pre_close`` as the
  ex-rights reference.
  Expressions nesting a time-series operator under a cross-sectional one
  are rejected — the governed production recipes with materialized
  intermediates remain the future execution path.
- Every consumed bar date must sit inside a certified stock_daily window
  and every consumed row must carry catalog lineage; per-row catalog
  identities are ticker/date-granular and differ from the registry
  snapshot identities, so exact per-payload provenance remains the
  certified replay lane's job.
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
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

import polars as pl
from ditto_data.helpers.limit_state import derive_limit_state
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
    {"instrument_id", "trade_date", "close", "pre_close", "amount", "knowledge_date"}
)
# Facts with a concrete dataset derivation bind to their real source field;
# the structural consumers (universe identity, membership tag, instrument id,
# industry slot) anchor on the registry build that produced the roster.
_BASIC_FACT_FIELDS: Mapping[str, str] = {
    "instruments.instrument_name": "name",
    "instruments.is_st": "name",
    "instruments.listing_days": "list_date",
}
# Price-series leaves derive their adjusted values from the adjustment
# dataset; their bindings must qualify that lineage alongside the raw field.
_PRICE_LEAVES = frozenset({"market.open", "market.high", "market.low", "market.close"})
_ADJUSTMENT_DATASET = "adj_factor"
_ADJUSTMENT_FIELD = "adj_factor"
_STRUCTURAL_CONSUMERS = (
    "universe_snapshot_id",
    "instruments.instrument_id",
    "instruments.industry_id",
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
# Certified stock_daily publication claim (Batch 2 evidence): bars for a
# trade date become visible 18:00 Asia/Shanghai on that date.
_BAR_PUBLICATION_TIME = time(18, 0)
# Client and server clocks drift by seconds; only instants older than this
# window count as genuinely past for the live read model.
_LIVE_SKEW = timedelta(minutes=5)
_TURNOVER_WINDOW = 20
_CALENDAR_BUFFER_DAYS = 14
_SESSION_BUFFER = 5
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

    def names(
        self, instrument_ids: Sequence[int], *, asof: date
    ) -> Mapping[int, str]: ...

    def source_tickers(
        self,
        instrument_ids: Sequence[int],
        *,
        asof: date,
        cutoff: datetime,
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
    lookback: int


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
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider = provider
        self._history = history
        self._discover_sources = discover_sources
        self._identities = identities
        self._factors = factors
        self._snapshots = snapshots
        self._compiler = ExpressionCompiler()
        self._clock = clock or (lambda: datetime.now(UTC))

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
        knowledge, publication = self._resolve_cutoffs(request)
        self._validate_policy(request)
        as_of_date = request.as_of.astimezone(_SHANGHAI).date()
        sources = self._roster_sources(request, knowledge)
        roster = self._resolve_roster(request, sources, knowledge, publication)
        nodes = self._plan_factors(request)
        evaluation, tickers = self._load_bars(
            roster=roster,
            request=request,
            nodes=nodes,
            as_of_date=as_of_date,
            knowledge=knowledge,
            # Bars become publishable at the earlier declared boundary.
            visible_through=_knowledge_visible_through(publication),
        )
        self._require_certified_coverage(evaluation)
        cross_date = _cross_section_date(evaluation)
        raw_cross = self._load_raw_cross(
            tickers=tickers,
            cross_date=cross_date,
            knowledge=knowledge,
            visible_through=_knowledge_visible_through(publication),
        )
        instruments = self._project_instruments(
            roster=roster,
            evaluation=evaluation,
            nodes=nodes,
            as_of_date=as_of_date,
            cross_date=cross_date,
            raw_cross=raw_cross,
        )
        windows = self._binding_windows(
            evaluation=evaluation, cross_date=cross_date, as_of_date=as_of_date
        )
        consumes_adjustment = any(
            node.requested and node.leaves & _PRICE_LEAVES for node in nodes
        )
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
                            for dataset_id, group in windows.items()
                            # Adjustment snapshots are declared sources only
                            # when adjusted prices were actually consumed;
                            # otherwise admission reports them unbound.
                            if dataset_id != _ADJUSTMENT_DATASET or consumes_adjustment
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
            data_from=claimed_from(evaluation),
            data_to=cross_date,
            universe_sources=sources,
        )

    def _resolve_cutoffs(
        self, request: AssembleSelectionFactsRequest
    ) -> tuple[datetime, datetime]:
        """
        Issue live cutoffs from one server instant, skew-tolerant.

        Omitted cutoffs default to a single ``clock()`` read rather than the
        client as-of, which may already be seconds old by comparison time.
        Explicit cutoffs must still obey causal order and may only antedate
        the server clock by the tolerated live skew; anything older belongs
        to the certified replay lane.
        """
        now = self._clock()
        for declared in (request.knowledge_cutoff, request.publication_cutoff):
            if declared is not None and declared.tzinfo is None:
                raise AppProcessError(
                    "assembled selection cutoffs must carry a timezone",
                    details={"reason": "ASSEMBLY_CUTOFF_INVALID"},
                )
        if request.as_of > now + _LIVE_SKEW:
            raise AppProcessError(
                "future decision instants cannot use the live read model",
                details={"reason": "ASSEMBLY_TIME_INVALID"},
            )
        # Never later than the decision instant, even by milliseconds of
        # client-to-server latency.
        knowledge = min(request.knowledge_cutoff or now, request.as_of)
        if request.knowledge_cutoff is not None and (
            knowledge.tzinfo is None or knowledge != request.knowledge_cutoff
        ):
            raise AppProcessError(
                "assembled selection cutoffs violate causal order",
                details={"reason": "ASSEMBLY_CUTOFF_INVALID"},
            )
        if knowledge < now - _LIVE_SKEW:
            raise AppProcessError(
                "past instants cannot use the live read model; "
                + "use the certified replay lane",
                details={"reason": "ASSEMBLY_CUTOFF_BACKDATED"},
            )
        publication = request.publication_cutoff or knowledge
        if publication.tzinfo is None or publication > knowledge:
            raise AppProcessError(
                "assembled selection cutoffs violate causal order",
                details={"reason": "ASSEMBLY_CUTOFF_INVALID"},
            )
        if request.publication_cutoff is not None and publication < now - _LIVE_SKEW:
            raise AppProcessError(
                "backdated publication cutoffs cannot use the live read model",
                details={"reason": "ASSEMBLY_CUTOFF_BACKDATED"},
            )
        return knowledge, publication

    def _require_certified_coverage(self, evaluation: pl.DataFrame) -> None:
        """Every consumed bar date must sit inside a certified window."""
        uncovered = sorted(
            {
                trade_date
                for trade_date in evaluation["trade_date"].unique().to_list()
                if not self._snapshots.covering(
                    dataset_id="stock_daily", day=trade_date
                )
            }
        )
        if uncovered:
            raise AppProcessError(
                "bar dates outside every certified stock_daily window",
                details={
                    "reason": "ASSEMBLY_SNAPSHOT_COVERAGE_MISSING",
                    "dataset_id": "stock_daily",
                    "uncovered_dates": tuple(
                        value.isoformat() for value in uncovered[:10]
                    ),
                    "uncovered_count": len(uncovered),
                },
            )

    def _roster_sources(
        self, request: AssembleSelectionFactsRequest, knowledge: datetime
    ) -> HistoricalUniverseSources:
        """Delegate universe semantics to the discovery port, fail-closed."""
        try:
            return self._discover_sources(
                universe_id=request.universe_id,
                asset_kind=request.asset_kind,
                knowledge_cutoff=knowledge,
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

    def _validate_policy(self, request: AssembleSelectionFactsRequest) -> None:
        """Mirror the strategy spec invariants before assembling facts."""
        names = [weight.name for weight in request.factor_weights]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise AppProcessError(
                "assembly factor weights contain duplicate names",
                details={
                    "reason": "ASSEMBLY_FACTOR_DUPLICATE",
                    "factor_ids": tuple(duplicates),
                },
            )
        total = sum(weight.weight for weight in request.factor_weights)
        if not math.isclose(total, 1.0, abs_tol=1e-12):
            raise AppProcessError(
                "assembly factor weights must sum to one",
                details={
                    "reason": "ASSEMBLY_FACTOR_WEIGHT_TOTAL",
                    "total": total,
                },
            )
        states = request.excluded_limit_states
        if "normal" in states or len(set(states)) != len(states):
            raise AppProcessError(
                "excluded limit states must be unique non-normal states",
                details={
                    "reason": "ASSEMBLY_LIMIT_POLICY_INVALID",
                    "excluded_limit_states": tuple(states),
                },
            )

    def _plan_factors(
        self, request: AssembleSelectionFactsRequest
    ) -> tuple[_FactorNode, ...]:
        """Resolve the transitive factor closure in dependency order."""
        order: list[str] = []
        leaves: dict[str, frozenset[str]] = {}
        compiled: dict[str, CompiledDerivedExpression] = {}
        lookbacks: dict[str, int] = {}

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
            node_leaves: set[str] = set()
            for dependency in spec.dependencies:
                node_leaves |= self._dependency_leaves(
                    dependency, factor_id, path, visit
                )
            leaves[factor_id] = frozenset(node_leaves)
            compiled[factor_id] = self._compile_factor(factor_id, spec)
            operators = compiled[factor_id].analysis.operator_names
            if any(op.startswith("cs_") for op in operators) and any(
                op.startswith("ts_") for op in operators
            ):
                raise AppProcessError(
                    "factor nests a time-series operator under a "
                    + "cross-sectional operator; the production recipe with "
                    + "materialized intermediates is required",
                    details={
                        "reason": "ASSEMBLY_FACTOR_EXPRESSION_UNSUPPORTED",
                        "factor_id": factor_id,
                    },
                )
            # Time-series windows compose across registered dependencies, so
            # the required history is this node's window plus the deepest
            # dependency chain below it.
            lookbacks[factor_id] = compiled[factor_id].analysis.lookback + max(
                (
                    lookbacks[dependency]
                    for dependency in spec.dependencies
                    if dependency in lookbacks
                ),
                default=0,
            )
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
                lookback=lookbacks[factor_id],
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
        knowledge: datetime,
        visible_through: date,
    ) -> tuple[pl.DataFrame, Mapping[int, str]]:
        roster_ids = [int(row["instrument_id"]) for row in roster.frame.to_dicts()]
        tickers = self._identities.source_tickers(
            roster_ids, asof=as_of_date, cutoff=knowledge
        )
        if not tickers:
            raise AppProcessError(
                "assembled selection found no resolvable instruments",
                details={"reason": "ASSEMBLY_UNIVERSE_EMPTY"},
            )
        max_lookback = max(
            _TURNOVER_WINDOW,
            *(node.lookback for node in nodes),
        )
        start = self._lookback_start(
            max_lookback=max_lookback,
            request_lookback=request.lookback_days,
            as_of=as_of_date,
        )
        frame = self._provider.get_bars(
            BarQuery(
                instruments=tuple(
                    tickers[instrument_id] for instrument_id in sorted(tickers)
                ),
                start=start.isoformat(),
                end=as_of_date.isoformat(),
                asof=as_of_date.isoformat(),
                # Governed stock-lane price factors require adjusted prices;
                # the adjustment lineage binds separately below.
                adj="hfq",
            )
        )
        if frame.is_empty():
            raise AppProcessError(
                "assembled selection found no bars in the lookback window",
                details={"reason": "ASSEMBLY_BARS_MISSING"},
            )
        # The provider re-resolves tickers internally without a knowledge
        # cutoff; any row whose (instrument_id, source_ticker) pair disagrees
        # with the cutoff-resolved mapping is dropped so a post-cutoff
        # mapping correction can never swap an instrument's price series.
        if "source_ticker" in frame.columns:
            frame = _filter_identity_consistent(frame, tickers)
            if frame.is_empty():
                raise AppProcessError(
                    "assembled selection bars resolved to unexpected identities",
                    details={"reason": "ASSEMBLY_BARS_MISSING"},
                )
        needed_leaves = {
            leaf for node in nodes if node.requested for leaf in node.leaves
        }
        self._validate_bar_schema(frame, needed_leaves)
        frame = _without_future_knowledge(frame, visible_through)
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
        return evaluation, tickers

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

    def _lookback_start(
        self, *, max_lookback: int, request_lookback: int, as_of: date
    ) -> date:
        """
        Resolve the read start on the trading calendar when available.

        A weekday approximation (7/5) under-covers A-share years once Spring
        Festival and National Day closures are taken into account, leaving a
        252-session factor null despite available history; the calendar
        count guarantees the sessions plus a small suspension margin. A
        provider without calendar evidence falls back to the approximation.
        """
        needed = max_lookback + _SESSION_BUFFER
        approx_calendar = max(
            request_lookback,
            math.ceil(needed * 7 / 5) + _CALENDAR_BUFFER_DAYS,
        )
        fallback = as_of - timedelta(days=approx_calendar)
        try:
            schedule = self._provider.get_schedule(
                start=(as_of - timedelta(days=approx_calendar * 2)).isoformat(),
                end=as_of.isoformat(),
            )
        except Exception:
            return fallback
        if schedule.is_empty() or "trade_date" not in schedule.columns:
            return fallback
        sessions_column = schedule["trade_date"]
        if sessions_column.dtype == pl.String:
            sessions_column = sessions_column.str.to_date()
        sessions = sorted(
            session for session in sessions_column.to_list() if session <= as_of
        )
        if not sessions:
            return fallback
        # The wider of the two boundaries: the caller's requested calendar
        # window (default 400 days) must not be narrowed by the factor
        # requirement, and a long suspension inside the requested window
        # must not starve a per-instrument rolling window either.
        requested_start = as_of - timedelta(days=request_lookback)
        if len(sessions) >= needed:
            return min(requested_start, sessions[-needed])
        return min(requested_start, sessions[0])

    def _load_raw_cross(
        self,
        *,
        tickers: Mapping[int, str],
        cross_date: date,
        knowledge: datetime,
        visible_through: date,
    ) -> Mapping[int, Mapping[str, object]]:
        """
        Read raw (unadjusted) closes for the exchange price-limit band.

        HFQ bars adjust open/high/low/close but keep ``pre_close`` as the
        ex-rights reference, so the limit-state ratio must come from a raw
        read; adjusted ratios would misclassify ex-dividend days.
        """
        window_start = cross_date - timedelta(days=10)
        frame = self._provider.get_bars(
            BarQuery(
                instruments=tuple(tickers[key] for key in sorted(tickers)),
                start=window_start.isoformat(),
                end=cross_date.isoformat(),
                asof=cross_date.isoformat(),
                adj="none",
            )
        )
        required = {
            "instrument_id",
            "trade_date",
            "close",
            "pre_close",
            "high",
            "low",
            "source_ticker",
            "knowledge_date",
            _BAR_LINEAGE_COLUMN,
        }
        if frame.is_empty() or not required.issubset(frame.columns):
            return {}
        if "source_ticker" in frame.columns:
            frame = _filter_identity_consistent(frame, tickers).filter(
                pl.col(_BAR_LINEAGE_COLUMN).is_not_null()
            )
        knowledge_column = pl.col("knowledge_date")
        if frame.schema["knowledge_date"] == pl.String:
            knowledge_column = knowledge_column.str.to_date()
        frame = frame.filter(knowledge_column <= pl.lit(visible_through))
        rows = frame.filter(pl.col("trade_date") == pl.lit(cross_date))
        return {int(row["instrument_id"]): row for row in rows.to_dicts()}

    def _project_instruments(
        self,
        *,
        roster: HistoricalUniverseResult,
        evaluation: pl.DataFrame,
        nodes: tuple[_FactorNode, ...],
        as_of_date: date,
        cross_date: date,
        raw_cross: Mapping[int, Mapping[str, object]],
    ) -> tuple[SelectionInstrumentDraft, ...]:
        roster_rows = roster.frame.to_dicts()
        names = self._identities.names(
            [int(row["instrument_id"]) for row in roster_rows],
            asof=as_of_date,
        )
        cross_section = evaluation.filter(pl.col("trade_date") == cross_date)
        # Unattributable instruments never contribute to the ranking
        # population: an extreme uncertified value must not shift every
        # other instrument's normalized score.
        unattributable = set(
            evaluation.filter(pl.col(_BAR_LINEAGE_COLUMN).is_null())[
                "instrument_id"
            ].to_list()
        )
        if unattributable:
            cross_section = cross_section.with_columns(
                [
                    pl.when(pl.col("instrument_id").is_in(sorted(unattributable)))
                    .then(None)
                    .otherwise(pl.col(node.factor_id))
                    .alias(node.factor_id)
                    for node in nodes
                    if node.requested
                ]
            )
        cross = _unit_normalized(cross_section, nodes)
        cross_rows = {int(row["instrument_id"]): row for row in cross.to_dicts()}
        # Non-finite amounts (NaN/inf in the window) make the rolling mean
        # unusable; treat them as a missing turnover observation.
        turnover = {
            int(row["instrument_id"]): row["_average_turnover"]
            for row in evaluation.group_by("instrument_id")
            .agg(
                pl.when(
                    pl.col("amount")
                    .rolling_mean(window_size=_TURNOVER_WINDOW)
                    .last()
                    .is_finite()
                    & (
                        pl.col("amount")
                        .rolling_mean(window_size=_TURNOVER_WINDOW)
                        .last()
                        >= 0
                    )
                )
                .then(
                    pl.col("amount").rolling_mean(window_size=_TURNOVER_WINDOW).last()
                )
                .otherwise(None)
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
            if bar_row is None or lineage is None or instrument_id in unattributable:
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
                        source_ticker=(raw_cross.get(instrument_id) or {}).get(
                            "source_ticker"
                        ),
                        close=(raw_cross.get(instrument_id) or {}).get("close"),
                        pre_close=(raw_cross.get(instrument_id) or {}).get("pre_close"),
                        high=(raw_cross.get(instrument_id) or {}).get("high"),
                        low=(raw_cross.get(instrument_id) or {}).get("low"),
                        is_st=_is_st_from_name(instrument_name),
                    ),
                    tracking_error=None,
                    declared_missing_inputs=tuple(missing_factors),
                )
            )
        return tuple(drafts)

    def _binding_windows(
        self,
        *,
        evaluation: pl.DataFrame,
        cross_date: date,
        as_of_date: date,
    ) -> dict[str, tuple[CertifiedSnapshotWindow, ...]]:
        """
        Bar facts bind their whole consumed chain, roster facts at as-of.

        Names, ST flags and listing state are read as of the decision date,
        so their certified coverage must contain that date. Daily bars and
        adjustments are certified in partitioned snapshots, so the binding
        carries every window covering any consumed date; today's admission
        mechanics check each snapshot against the full claimed interval and
        therefore still report coverage reasons under partitioned
        certification until union-aware coverage lands.
        """
        consumed_dates = sorted(set(evaluation["trade_date"].unique().to_list()))
        return {
            "stock_daily": _covering_chain(
                self._snapshots, "stock_daily", consumed_dates
            ),
            _ADJUSTMENT_DATASET: _covering_chain(
                self._snapshots, _ADJUSTMENT_DATASET, consumed_dates
            ),
            "stock_status": self._snapshots.covering(
                dataset_id="stock_status", day=as_of_date
            ),
            "stock_basic": self._snapshots.covering(
                dataset_id="stock_basic", day=as_of_date
            ),
        }


def _filter_identity_consistent(
    frame: pl.DataFrame, tickers: Mapping[int, str]
) -> pl.DataFrame:
    """
    Keep only rows whose (instrument_id, source_ticker) matches the map.

    A joined mapping frame keeps this O(rows) even for the full registered
    market, where a nested conditional per instrument would explode.
    """
    expected = pl.DataFrame(
        {
            "instrument_id": sorted(tickers),
            "_expected_ticker": [tickers[key] for key in sorted(tickers)],
        },
        schema={"instrument_id": pl.Int64, "_expected_ticker": pl.String},
    )
    return (
        frame.join(expected, on="instrument_id", how="left")
        .filter(pl.col("source_ticker") == pl.col("_expected_ticker"))
        .drop("_expected_ticker")
    )


def _covering_chain(
    snapshots: CertifiedSnapshotIndex,
    dataset_id: str,
    days: Sequence[date],
) -> tuple[CertifiedSnapshotWindow, ...]:
    """Union of certified windows covering any consumed date, deduplicated."""
    chain: dict[str, CertifiedSnapshotWindow] = {}
    for day in days:
        for window in snapshots.covering(dataset_id=dataset_id, day=day):
            chain[window.snapshot_id] = window
    return tuple(
        sorted(chain.values(), key=lambda item: (item.request_start, item.snapshot_id))
    )


def _without_future_knowledge(
    frame: pl.DataFrame, visible_through: date
) -> pl.DataFrame:
    """
    Drop bar rows whose knowledge is not provably within the cutoff.

    ``knowledge_date`` is a required schema column, so this filter always
    applies: a provider that cannot prove per-row knowledge is rejected
    during schema validation instead of silently passing future rows.
    """
    knowledge = pl.col("knowledge_date")
    if frame.schema["knowledge_date"] == pl.String:
        knowledge = knowledge.str.to_date()
    return frame.filter(knowledge <= pl.lit(visible_through))


def _knowledge_visible_through(knowledge: datetime) -> date:
    """
    Resolve the last bar trade date provably known at the cutoff.

    Per-row ``knowledge_date`` is the authoritative visibility record —
    production Tushare daily bars map it to ``trade_date + 1`` (T+1
    knowledge), which this filter already honors strictly. The 18:00
    Asia/Shanghai refinement only matters for providers that record
    same-day knowledge: a cutoff before 18:00 cannot see that day's bars.
    """
    local = knowledge.astimezone(_SHANGHAI)
    visible = local.date()
    if local.timetz().replace(tzinfo=None) < _BAR_PUBLICATION_TIME:
        visible -= timedelta(days=1)
    return visible


def _unit_normalized(
    cross: pl.DataFrame, nodes: tuple[_FactorNode, ...]
) -> pl.DataFrame:
    """
    Rank each requested factor cross-section into a (0, 1] unit score.

    The selection contract scores weighted sums of unit-normalized values;
    raw factor magnitudes (for example a 252-day return above 1.0) would
    both break the domain bound and mix incomparable scales. Fractional
    average ranks keep ties deterministic and preserve ordering; the
    denominator counts only valid observations so a factor's missing
    cross-sections do not silently down-weight its peers.
    """
    for node in nodes:
        if not node.requested:
            continue
        values = pl.col(node.factor_id).fill_nan(None)
        finite = pl.when(values.is_finite()).then(values).otherwise(None)
        cross = cross.with_columns(
            (finite.rank(method="average") / finite.count()).alias(node.factor_id)
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
    *,
    source_ticker: object,
    close: object,
    pre_close: object,
    high: object,
    low: object,
    is_st: bool,
) -> Literal["normal", "limit_up", "limit_down"] | None:
    """
    Classify the close against the board/ST price-limit band.

    Delegates to the shared board-aware authority (ST ±4.8%, ChiNext/STAR
    ±19.5%, Beijing ±29.5%, main boards ±9.5%); a limit additionally
    requires the close at the session extreme. Non-finite or missing price
    facts return None so the pipeline fails closed on them.
    """
    if (
        not isinstance(close, (int, float))
        or not isinstance(pre_close, (int, float))
        or not isinstance(high, (int, float))
        or not isinstance(low, (int, float))
    ):
        return None
    prices = (float(close), float(pre_close), float(high), float(low))
    # NaN passes the type check but every comparison against it is false,
    # which would silently classify an unusable price fact as "normal".
    if not all(math.isfinite(value) for value in prices):
        return None
    if prices[1] <= 0 or not isinstance(source_ticker, str):
        return None
    pct_change = (prices[0] / prices[1] - 1.0) * 100.0
    return derive_limit_state(
        source_ticker=source_ticker,
        pct_change=pct_change,
        close=prices[0],
        high=prices[2],
        low=prices[3],
        is_st=is_st,
    )


def claimed_from(evaluation: pl.DataFrame) -> date | None:
    """
    Claim the full consumed read range; coverage gaps fail at admission.

    The factor and turnover values already consumed every row of the
    evaluation window, so the claim must start at the earliest observed
    trade date — narrowing it to a snapshot's request range would let
    admission pass without qualifying rows that shaped the output.
    """
    first_observed = evaluation["trade_date"].min()
    return first_observed if isinstance(first_observed, date) else None


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

    for consumer_field in _STRUCTURAL_CONSUMERS:
        bind("stock_basic", "list_status", consumer_field)
    for consumer_field, field in _BASIC_FACT_FIELDS.items():
        bind("stock_basic", field, consumer_field)
    bind("stock_status", "is_suspended", "instruments.is_suspended")
    # The facade classifies membership_version as a rotation-stage input, so
    # its binding must reference the rotation (stock_daily) source set.
    bind("stock_daily", "close", "membership_version")
    bind("stock_daily", "amount", "instruments.average_turnover")
    # limit_state consumes both legs of the close/pre_close ratio.
    # limit_state is judged on the raw (unadjusted) read, so it never
    # depends on adjustment lineage.
    bind("stock_daily", "close", "instruments.limit_state")
    bind("stock_daily", "pre_close", "instruments.limit_state")
    price_consumers = sorted(
        f"instruments.factor_values.{node.factor_id}"
        for node in nodes
        if node.requested and node.leaves & _PRICE_LEAVES
    )
    if price_consumers and not windows.get(_ADJUSTMENT_DATASET):
        # Without a certified adjustment window the binding would silently
        # vanish while the raw-field binding still satisfies admission.
        raise AppProcessError(
            "price factors require a certified adj_factor window",
            details={
                "reason": "ASSEMBLY_ADJUSTMENT_WINDOW_MISSING",
                "dataset_id": _ADJUSTMENT_DATASET,
                "consumers": tuple(price_consumers),
            },
        )
    for node in nodes:
        if not node.requested:
            continue
        for leaf in sorted(node.leaves):
            bind(
                "stock_daily",
                _MARKET_BAR_COLUMNS[leaf],
                f"instruments.factor_values.{node.factor_id}",
            )
        if node.leaves & _PRICE_LEAVES:
            bind(
                _ADJUSTMENT_DATASET,
                _ADJUSTMENT_FIELD,
                f"instruments.factor_values.{node.factor_id}",
            )
    return tuple(fields)
