"""
Model-portfolio historical target replay (read-only, exact identities).

The query replays saved SIGNAL_PACKAGE artifacts — never the current
weights — against retained PIT-visible prices: from an explicit initial
capital, targets are applied at their own signal-date close and the
portfolio drifts at raw closes in between.  Rebalancing is cost-free and
dividend-free by construction; no registered cost rule exists today, so
none is simulated.  Days without an effective saved target stay explicit
gaps (``target_missing``); history is never back-filled from the present.

Replay identity: artifacts are immutable rows, so a request that pins the
exact ``artifact_ids`` replays byte-identically even after the same dates
were superseded by newer publishes.  An empty ``artifact_ids`` resolves the
knowledge-cutoff-visible active packages inside the range and returns the
resolved ids in ``targets`` for later pinning.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from hashlib import sha256
from typing import Protocol, cast

import orjson
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotReader,
)
from ditto_data.query.contracts import PITQueryContext
from ditto_features.technical_analysis.contracts import TechnicalBar
from ditto_portfolio.account_ledger import AccountLedgerError, ledger_parse_date
from ditto_portfolio.account_returns import (
    ReturnSeries,
    ValuationObservation,
    compute_return_series,
)
from ditto_portfolio.errors import PortfolioError
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.history_valuation import (
    VALUATION_POLICY_VERSION,
    HistoryPointView,
    HistoryQuality,
    HistorySegmentView,
    PricedBar,
    bars_by_instrument,
    build_history_points,
    build_history_segments,
    end_of_day,
    price_at,
    trade_day,
)
from ditto_application.queries.pit_snapshots import group_dataset_snapshots
from ditto_application.queries.technical_analysis import (
    TechnicalAnalysisSourcePort,
)
from ditto_application.signal_package_contract import (
    canonical_signal_package_metadata,
    verify_signal_package_metadata,
)

__all__ = [
    "GetModelHistoryQuery",
    "ModelHistoryRequest",
    "ModelHistoryView",
    "ModelTargetView",
]

_RESULT_ID_PREFIX = "model-history:sha256:"
_CODE_PREFIX = "MODEL_HISTORY"
_MONEY = Decimal("0.01")
_QUANTITY = Decimal("0.0001")
_WEIGHT_SUM_TOLERANCE = Decimal("1.00000001")
_ZERO = Decimal("0")
_TARGET_MISSING = (HistoryQuality(code="target_missing", detail=""),)


class ModelArtifactReaderPort(Protocol):
    """Minimal artifact read surface the replay depends on."""

    def list_by_strategy(self, strategy_id: str) -> Sequence[StrategyArtifactRecord]:
        """List artifacts of one strategy in persistence order."""
        ...


@dataclass(frozen=True, kw_only=True)
class ModelHistoryRequest:
    """
    Exact read identity for one MODEL replay.

    ``artifact_ids`` empty resolves fresh (active, knowledge-visible, in
    range); non-empty pins the exact replayed target set.
    """

    strategy_id: str
    start_date: str
    end_date: str
    initial_capital: Decimal
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    artifact_ids: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ModelTargetView:
    """One replayed saved target and its verifiable identity."""

    signal_date: str
    artifact_id: str
    checksum: str


@dataclass(frozen=True, kw_only=True)
class ModelHistoryView:
    """
    Complete replayable MODEL result for one strategy and range.

    ``empty_reason`` is None for a normal replay and explains an empty
    result (``no_visible_targets``) instead of fabricating days.
    """

    result_id: str
    strategy_id: str
    currency: str
    start_date: str
    end_date: str
    initial_capital: Decimal
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    empty_reason: str | None
    targets: tuple[ModelTargetView, ...]
    method: str
    valuation_policy_version: str
    points: tuple[HistoryPointView, ...]
    segments: tuple[HistorySegmentView, ...]


@dataclass(frozen=True)
class _ReplayPackage:
    """One resolved saved target with its parsed facts."""

    signal_date: date
    artifact_id: str
    checksum: str
    weights: dict[int, Decimal]
    snapshot_ids: tuple[str, ...]


@dataclass
class _ReplayWalk:
    """Mutable replay state threaded across valuation dates."""

    quantities: dict[int, Decimal]
    cash: Decimal
    effective_index: int


def _error(code_suffix: str, reason: str, **details: object) -> AppQueryError:
    return AppQueryError(
        f"model history query failed closed: {reason}",
        details={"code": f"{_CODE_PREFIX}_{code_suffix}", "reason": reason, **details},
    )


def _parse_date(value: str, field: str) -> date:
    try:
        return ledger_parse_date(value, field)
    except AccountLedgerError as exc:
        raise _error(
            "REQUEST_INVALID", f"{field} must be YYYY-MM-DD", field=field
        ) from exc


def _validate_request(request: ModelHistoryRequest) -> None:
    if not request.strategy_id.strip():
        raise _error("REQUEST_INVALID", "strategy_id must be non-empty")
    start = _parse_date(request.start_date, "start_date")
    end = _parse_date(request.end_date, "end_date")
    if start > end:
        raise _error("REQUEST_INVALID", "start_date cannot be after end_date")
    if request.knowledge_cutoff.tzinfo is None:
        raise _error("REQUEST_INVALID", "knowledge_cutoff must be timezone-aware")
    if request.publication_cutoff.tzinfo is None:
        raise _error("REQUEST_INVALID", "publication_cutoff must be timezone-aware")
    if request.publication_cutoff > request.knowledge_cutoff:
        raise _error(
            "REQUEST_INVALID", "publication_cutoff cannot exceed knowledge_cutoff"
        )
    capital = request.initial_capital
    if not capital.is_finite() or capital <= _ZERO:
        raise _error("REQUEST_INVALID", "initial_capital must be positive")
    if len(set(request.artifact_ids)) != len(request.artifact_ids):
        raise _error("REQUEST_INVALID", "artifact_ids must be unique")


def _created_at(record: StrategyArtifactRecord) -> datetime:
    try:
        created = datetime.fromisoformat(record.created_at)
    except ValueError as exc:
        raise _error(
            "ARTIFACT_INVALID",
            "signal package created_at is not an ISO timestamp",
            artifact_id=record.artifact_id,
        ) from exc
    if created.tzinfo is None:
        raise _error(
            "ARTIFACT_INVALID",
            "signal package created_at must be timezone-aware",
            artifact_id=record.artifact_id,
        )
    return created


def _target_weights(
    metadata: Mapping[str, object],
    artifact_id: str,
) -> dict[int, Decimal]:
    raw_reasons = metadata.get("selection_reasons")
    if not isinstance(raw_reasons, dict):
        raise _error(
            "TARGET_INVALID", "selection reasons are absent", artifact_id=artifact_id
        )
    weights: dict[int, Decimal] = {}
    for raw_id, raw_reason in cast(dict[object, object], raw_reasons).items():
        if not isinstance(raw_reason, dict):
            raise _error(
                "TARGET_INVALID",
                "selection reason is malformed",
                artifact_id=artifact_id,
            )
        try:
            instrument_id = int(cast(str | int, raw_id))
            weight = Decimal(
                str(cast(dict[object, object], raw_reason)["target_weight"])
            )
        except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
            raise _error(
                "TARGET_INVALID",
                "target weight is malformed",
                artifact_id=artifact_id,
            ) from exc
        if instrument_id <= 0 or not weight.is_finite() or weight < _ZERO:
            raise _error(
                "TARGET_INVALID", "target weight is invalid", artifact_id=artifact_id
            )
        weights[instrument_id] = weight
    if not weights or sum(weights.values()) > _WEIGHT_SUM_TOLERANCE:
        raise _error(
            "TARGET_INVALID",
            "target weights are empty or exceed one",
            artifact_id=artifact_id,
        )
    return dict(sorted(weights.items()))


def _package(record: StrategyArtifactRecord) -> _ReplayPackage:
    """Verify one artifact and extract its replayable saved facts."""
    if record.artifact_type is not ArtifactKind.SIGNAL_PACKAGE:
        raise _error(
            "ARTIFACT_INVALID",
            "artifact is not a signal package",
            artifact_id=record.artifact_id,
        )
    if not verify_signal_package_metadata(record.metadata):
        raise _error(
            "ARTIFACT_INTEGRITY_INVALID",
            "signal package checksum is invalid",
            artifact_id=record.artifact_id,
        )
    metadata = canonical_signal_package_metadata(record.metadata)
    raw_signal_date = metadata.get("signal_date")
    if not isinstance(raw_signal_date, str):
        raise _error(
            "ARTIFACT_INVALID",
            "signal package signal_date is absent",
            artifact_id=record.artifact_id,
        )
    try:
        signal_date = ledger_parse_date(raw_signal_date, "signal_date")
    except AccountLedgerError as exc:
        raise _error(
            "ARTIFACT_INVALID",
            "signal package signal_date must be YYYY-MM-DD",
            artifact_id=record.artifact_id,
        ) from exc
    raw_snapshots = metadata.get("dataset_snapshot_ids")
    if not isinstance(raw_snapshots, dict) or not raw_snapshots:
        raise _error(
            "ARTIFACT_LINEAGE_INVALID",
            "signal package dataset snapshots are absent",
            artifact_id=record.artifact_id,
        )
    checksum = record.metadata.get("checksum")
    if not isinstance(checksum, str) or not checksum:
        raise _error(
            "ARTIFACT_INVALID",
            "signal package checksum is absent",
            artifact_id=record.artifact_id,
        )
    return _ReplayPackage(
        signal_date=signal_date,
        artifact_id=record.artifact_id,
        checksum=checksum,
        weights=_target_weights(metadata, record.artifact_id),
        snapshot_ids=tuple(
            sorted(
                str(value)
                for value in cast(dict[object, object], raw_snapshots).values()
            )
        ),
    )


def _resolve_packages(
    reader: ModelArtifactReaderPort,
    request: ModelHistoryRequest,
    *,
    start: date,
    end: date,
) -> tuple[_ReplayPackage, ...]:
    """Pin the exact artifact set, or resolve knowledge-visible actives."""
    records = tuple(
        record
        for record in reader.list_by_strategy(request.strategy_id)
        if record.artifact_type is ArtifactKind.SIGNAL_PACKAGE
    )
    if request.artifact_ids:
        return _pin_packages(records, request.artifact_ids, start=start, end=end)
    return _resolve_active_packages(records, request, start=start, end=end)


def _pin_packages(
    records: tuple[StrategyArtifactRecord, ...],
    artifact_ids: tuple[str, ...],
    *,
    start: date,
    end: date,
) -> tuple[_ReplayPackage, ...]:
    by_id = {record.artifact_id: record for record in records}
    pinned: list[_ReplayPackage] = []
    for artifact_id in artifact_ids:
        record = by_id.get(artifact_id)
        if record is None:
            raise _error(
                "ARTIFACT_NOT_FOUND",
                "pinned signal package was not found for this strategy",
                artifact_id=artifact_id,
            )
        package = _package(record)
        if not (start <= package.signal_date <= end):
            raise _error(
                "ARTIFACT_DATE_OUT_OF_RANGE",
                "pinned signal package falls outside the requested range",
                artifact_id=artifact_id,
            )
        pinned.append(package)
    pinned.sort(key=lambda item: (item.signal_date, item.artifact_id))
    dates = [item.signal_date for item in pinned]
    if len(set(dates)) != len(dates):
        raise _error(
            "REQUEST_INVALID",
            "pinned signal packages must cover unique signal dates",
        )
    return tuple(pinned)


def _resolve_active_packages(
    records: tuple[StrategyArtifactRecord, ...],
    request: ModelHistoryRequest,
    *,
    start: date,
    end: date,
) -> tuple[_ReplayPackage, ...]:
    if not records:
        raise _error(
            "STRATEGY_NOT_FOUND",
            "strategy has no saved signal packages",
            strategy_id=request.strategy_id,
        )
    visible: dict[date, list[_ReplayPackage]] = {}
    for record in records:
        if record.status != "active":
            continue
        if _created_at(record) > request.knowledge_cutoff:
            continue
        package = _package(record)
        if not (start <= package.signal_date <= end):
            continue
        visible.setdefault(package.signal_date, []).append(package)
    resolved: list[_ReplayPackage] = []
    for signal_date in sorted(visible):
        same_date = visible[signal_date]
        if len(same_date) > 1:
            raise _error(
                "ARTIFACT_DATE_AMBIGUOUS",
                "multiple active signal packages share one signal date",
                signal_date=signal_date.isoformat(),
            )
        resolved.append(same_date[0])
    return tuple(resolved)


def _pit_context(
    package: _ReplayPackage,
    request: ModelHistoryRequest,
    snapshot_reader: ProviderSnapshotReader,
    *,
    end: date,
) -> PITQueryContext:
    """Build the PIT context pinned to this package's declared snapshots."""
    snapshots: list[ProviderSnapshot] = []
    for snapshot_id in package.snapshot_ids:
        snapshot = snapshot_reader.get_snapshot(snapshot_id)
        if snapshot is None or snapshot.snapshot_id != snapshot_id:
            raise _error(
                "SOURCE_SNAPSHOT_NOT_FOUND",
                "declared price source snapshot was not found",
                snapshot_id=snapshot_id,
                artifact_id=package.artifact_id,
            )
        if snapshot.created_at > request.knowledge_cutoff:
            raise _error(
                "SOURCE_SNAPSHOT_FUTURE",
                "declared price source snapshot is after knowledge cutoff",
                snapshot_id=snapshot_id,
                artifact_id=package.artifact_id,
            )
        snapshots.append(snapshot)

    def snapshot_error(code: str, reason: str, **details: object) -> AppQueryError:
        return _error(code, reason, **details)

    try:
        return PITQueryContext(
            as_of=max(end_of_day(end), request.knowledge_cutoff),
            knowledge_cutoff=request.knowledge_cutoff,
            publication_cutoff=request.publication_cutoff,
            source_snapshots=group_dataset_snapshots(
                snapshots,
                error=snapshot_error,
                mixed_version_code=f"{_CODE_PREFIX}_SNAPSHOT_SCHEMA_MIXED",
            ),
        )
    except ValueError as exc:
        raise _error(
            "PIT_CONTEXT_INVALID", str(exc), artifact_id=package.artifact_id
        ) from exc


def _held_prices_or_missing(
    quantities: Mapping[int, Decimal],
    bars: Mapping[int, tuple[TechnicalBar, ...]],
    day: date,
) -> tuple[list[PricedBar], list[HistoryQuality]]:
    """Price every held instrument, collecting missing-price reasons."""
    held = sorted(i for i, quantity in quantities.items() if quantity > _ZERO)
    priced: list[PricedBar] = []
    missing: list[HistoryQuality] = []
    for instrument_id in held:
        outcome = price_at(
            instrument_id=instrument_id,
            bars=bars.get(instrument_id, ()),
            on_date=day,
            market_traded_on_date=True,
        )
        if isinstance(outcome, PricedBar):
            priced.append(outcome)
        else:
            missing.append(outcome)
    return priced, missing


def _price_targets(
    weights: Mapping[int, Decimal],
    bars: Mapping[int, tuple[TechnicalBar, ...]],
    day: date,
) -> tuple[list[PricedBar | None], list[HistoryQuality]]:
    """Price every target instrument; None marks an unpriceable target."""
    priced: list[PricedBar | None] = []
    missing: list[HistoryQuality] = []
    for instrument_id in weights:
        outcome = price_at(
            instrument_id=instrument_id,
            bars=bars.get(instrument_id, ()),
            on_date=day,
            market_traded_on_date=True,
        )
        if isinstance(outcome, PricedBar):
            priced.append(outcome)
        else:
            priced.append(None)
            missing.append(outcome)
    return priced, missing


class GetModelHistoryQuery:
    """Replay saved strategy targets into a cost-free historical series."""

    def __init__(
        self,
        *,
        artifact_reader: ModelArtifactReaderPort,
        snapshot_reader: ProviderSnapshotReader,
        valuation_source: TechnicalAnalysisSourcePort,
    ) -> None:
        self._artifact_reader = artifact_reader
        self._snapshot_reader = snapshot_reader
        self._valuation_source = valuation_source

    def history(self, request: ModelHistoryRequest) -> ModelHistoryView:
        """Return the exact replayable series or fail closed."""
        _validate_request(request)
        start = _parse_date(request.start_date, "start_date")
        end = _parse_date(request.end_date, "end_date")
        packages = _resolve_packages(
            self._artifact_reader, request, start=start, end=end
        )
        return self._replay(request, packages, start=start, end=end)

    def _replay(
        self,
        request: ModelHistoryRequest,
        packages: tuple[_ReplayPackage, ...],
        *,
        start: date,
        end: date,
    ) -> ModelHistoryView:
        instrument_ids = tuple(
            sorted({i for package in packages for i in package.weights})
        )
        bars = {
            package.artifact_id: bars_by_instrument(
                self._valuation_source,
                _pit_context(package, request, self._snapshot_reader, end=end),
                instrument_ids,
            )
            for package in packages
        }
        bar_dates = {
            trade_day(bar.occurred_at)
            for package_bars in bars.values()
            for instrument_bars in package_bars.values()
            for bar in instrument_bars
        }
        valuation_dates = sorted(day for day in bar_dates if start <= day <= end)
        walk = _ReplayWalk(
            quantities={},
            cash=request.initial_capital.quantize(_MONEY, rounding=ROUND_HALF_UP),
            effective_index=-1,
        )
        observations: list[ValuationObservation] = []
        priced_dates: list[tuple[str, tuple[PricedBar, ...]]] = []
        display_cash: dict[str, Decimal] = {}
        gap_quality: dict[str, tuple[HistoryQuality, ...]] = {}
        previous_valued = False
        for day in valuation_dates:
            effective_at = _effective_index(packages, day)
            if effective_at is None:
                # No saved target is effective yet: an explicit gap, never a
                # back-fill from later weights or current positions.
                gap_quality[day.isoformat()] = _TARGET_MISSING
                previous_valued = False
                continue
            package = packages[effective_at]
            package_bars = bars[package.artifact_id]
            held_prices, missing = _held_prices_or_missing(
                walk.quantities, package_bars, day
            )
            if effective_at > walk.effective_index:
                # A switch day needs every held and every target instrument
                # priced; otherwise the rebalance defers to the next priced
                # day as an explicit gap, exactly like a drift-day gap.
                target_prices, target_missing = _price_targets(
                    package.weights, package_bars, day
                )
                if target_missing:
                    missing = [*missing, *target_missing]
                if not missing:
                    self._apply_rebalance(
                        walk,
                        effective_at,
                        package,
                        held_prices,
                        target_prices,
                    )
                    held_prices = [bar for bar in target_prices if bar is not None]
            if missing:
                day_key = day.isoformat()
                display_cash[day_key] = walk.cash
                gap_quality[day_key] = tuple(missing)
                previous_valued = False
                continue
            day_total = walk.cash + sum(
                (
                    (walk.quantities[bar.instrument_id] * bar.price).quantize(
                        _MONEY, rounding=ROUND_HALF_UP
                    )
                    for bar in held_prices
                ),
                _ZERO,
            )
            observations.append(
                ValuationObservation(
                    on_date=day.isoformat(),
                    total_value=day_total,
                    gap_before=not previous_valued and bool(observations),
                )
            )
            priced_dates.append((day.isoformat(), tuple(held_prices)))
            display_cash[day.isoformat()] = walk.cash
            previous_valued = True

        try:
            series = compute_return_series(
                observations=tuple(observations),
                flows=(),
            )
        except PortfolioError as exc:
            raise _error("RETURN_SERIES_INVALID", str(exc)) from exc
        points = build_history_points(
            series=series,
            valuation_dates=valuation_dates,
            priced_dates=dict(priced_dates),
            display_cash=display_cash,
            gap_quality=gap_quality,
            flows_by_date={},
        )
        return self._view(request, packages, series, points, tuple(priced_dates))

    @staticmethod
    def _apply_rebalance(
        walk: _ReplayWalk,
        effective_at: int,
        package: _ReplayPackage,
        held_prices: Sequence[PricedBar],
        target_prices: Sequence[PricedBar | None],
    ) -> None:
        """Roll holdings to current capital, then apply the saved weights."""
        capital = walk.cash + sum(
            (
                (walk.quantities[bar.instrument_id] * bar.price).quantize(
                    _MONEY, rounding=ROUND_HALF_UP
                )
                for bar in held_prices
            ),
            _ZERO,
        )
        quantities: dict[int, Decimal] = {}
        invested = _ZERO
        for priced in target_prices:
            if priced is None:
                continue
            target_value = (capital * package.weights[priced.instrument_id]).quantize(
                _MONEY, rounding=ROUND_HALF_UP
            )
            quantity = (target_value / priced.price).quantize(
                _QUANTITY, rounding=ROUND_HALF_UP
            )
            quantities[priced.instrument_id] = quantity
            invested += (quantity * priced.price).quantize(
                _MONEY, rounding=ROUND_HALF_UP
            )
        cash = (capital - invested).quantize(_MONEY, rounding=ROUND_HALF_UP)
        if cash < _ZERO:
            raise _error(
                "TARGET_INVALID",
                "rounded target values exceed the replay capital",
                artifact_id=package.artifact_id,
            )
        walk.quantities = quantities
        walk.cash = cash
        walk.effective_index = effective_at

    def _view(
        self,
        request: ModelHistoryRequest,
        packages: tuple[_ReplayPackage, ...],
        series: ReturnSeries,
        points: tuple[HistoryPointView, ...],
        priced_dates: tuple[tuple[str, tuple[PricedBar, ...]], ...],
    ) -> ModelHistoryView:
        return ModelHistoryView(
            result_id=self._result_id(request, packages, series, priced_dates),
            strategy_id=request.strategy_id,
            currency="CNY",
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital.quantize(
                _MONEY, rounding=ROUND_HALF_UP
            ),
            knowledge_cutoff=request.knowledge_cutoff,
            publication_cutoff=request.publication_cutoff,
            empty_reason=None if packages else "no_visible_targets",
            targets=tuple(
                ModelTargetView(
                    signal_date=package.signal_date.isoformat(),
                    artifact_id=package.artifact_id,
                    checksum=package.checksum,
                )
                for package in packages
            ),
            method=series.method,
            valuation_policy_version=VALUATION_POLICY_VERSION,
            points=points,
            segments=build_history_segments(series),
        )

    @staticmethod
    def _result_id(
        request: ModelHistoryRequest,
        packages: tuple[_ReplayPackage, ...],
        series: ReturnSeries,
        priced_dates: tuple[tuple[str, tuple[PricedBar, ...]], ...],
    ) -> str:
        payload = {
            "strategy_id": request.strategy_id,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "initial_capital": str(
                request.initial_capital.quantize(_MONEY, rounding=ROUND_HALF_UP)
            ),
            "knowledge_cutoff": request.knowledge_cutoff.isoformat(),
            "publication_cutoff": request.publication_cutoff.isoformat(),
            "targets": [
                (p.signal_date.isoformat(), p.artifact_id, p.checksum) for p in packages
            ],
            "method": series.method,
            "policy": VALUATION_POLICY_VERSION,
            "priced_dates": [
                (
                    on_date,
                    [
                        (
                            bar.instrument_id,
                            str(bar.price),
                            bar.occurred_at.isoformat(),
                            bar.source_snapshot_id,
                            bar.carried,
                        )
                        for bar in sorted(prices, key=lambda item: item.instrument_id)
                    ],
                )
                for on_date, prices in priced_dates
            ],
        }
        digest = sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()
        return f"{_RESULT_ID_PREFIX}{digest}"


def _effective_index(
    packages: tuple[_ReplayPackage, ...],
    day: date,
) -> int | None:
    """Index of the latest saved target effective at or before the day."""
    effective: int | None = None
    for index, package in enumerate(packages):
        if package.signal_date <= day:
            effective = index
        else:
            break
    return effective
