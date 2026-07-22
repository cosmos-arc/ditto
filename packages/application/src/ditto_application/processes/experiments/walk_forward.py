# pyright: reportPrivateUsage=false
"""Deterministic R3 walk-forward aggregation over one unified equity curve."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import InitVar, dataclass, replace
from datetime import date
from statistics import stdev
from types import MappingProxyType

from ditto_analysis.experiments import (
    R3_COMPARISON_METRIC_IDS as _R3_COMPARISON_METRIC_IDS,
)
from ditto_analysis.experiments import (
    R3_DIAGNOSTIC_METRIC_IDS as _R3_DIAGNOSTIC_METRIC_IDS,
)
from ditto_analysis.experiments import (
    R3_RESEARCH_METRIC_SCHEMA as _R3_RESEARCH_METRIC_SCHEMA,
)
from ditto_analysis.experiments import (
    CandidateId as _CandidateId,
)
from ditto_analysis.experiments import (
    ContentHash as _ContentHash,
)
from ditto_analysis.experiments import (
    FoldId as _FoldId,
)
from ditto_analysis.experiments import (
    ResearchMetricId as _ResearchMetricId,
)
from ditto_analysis.experiments import (
    ResearchMetricSchema as _ResearchMetricSchema,
)
from ditto_analysis.experiments import (
    canonical_payload as _canonical_payload,
)

from ditto_application.processes.experiments._comparison_evidence import (
    CandidateWalkForwardStatus,
    _candidate_status,
    _drawdown,
    _evaluated,
    _lineage,
    _merge_refs,
    _not_evaluated,
    _unavailable_reason,
)
from ditto_application.processes.experiments._walk_forward_evidence import (
    _REQUIRED_FOLD_COUNT,
    FoldStabilityEvidence,
    WalkForwardDiagnosticEvidence,
    _finite,
    _walk_forward_error,
)
from ditto_application.processes.experiments.comparison import (
    BaselineComparisonIdentity,
    CandidateComparisonProjection,
    EvidenceStatus,
    FoldComparison,
    ScalarEvidence,
)

__all__ = [
    "R3_WALK_FORWARD_ARTIFACT_SCHEMA_ID",
    "R3_WALK_FORWARD_ARTIFACT_SCHEMA_VERSION",
    "CandidateWalkForwardStatus",
    "FoldStabilityEvidence",
    "StitchedReturnEvidence",
    "WalkForwardAggregation",
    "WalkForwardCandidate",
    "WalkForwardDiagnosticEvidence",
    "aggregate_walk_forward",
]

_TRADING_DAYS_PER_YEAR = 252
_MIN_RETURN_OBSERVATIONS = 2
_STITCHED_ROW_SIZE = 3
R3_WALK_FORWARD_ARTIFACT_SCHEMA_ID = "ditto.r3.walk-forward-aggregation"
R3_WALK_FORWARD_ARTIFACT_SCHEMA_VERSION = 1
_WALK_FORWARD_FACTORY_TOKEN = object()


@dataclass(frozen=True, slots=True)
class StitchedReturnEvidence:
    """Daily returns, recurrent equity, and paired source lineage."""

    daily_returns: tuple[tuple[_FoldId, str, float], ...]
    equity_curve: tuple[tuple[_FoldId, str, float], ...]
    evidence_refs: tuple[str, ...]
    evidence_hashes: tuple[_ContentHash, ...]

    def __post_init__(self) -> None:  # noqa: C901 - exact recurrence fence
        """Validate identity, fold order, and every equity recurrence step."""
        raw_daily, raw_curve = tuple(self.daily_returns), tuple(self.equity_curve)
        if any(
            type(item) is not tuple or len(item) != _STITCHED_ROW_SIZE
            for item in (*raw_daily, *raw_curve)
        ):
            _walk_forward_error("invalid_stitched_return_evidence")
        daily = tuple(
            (fold_id, trade_date, _finite(value))
            for fold_id, trade_date, value in raw_daily
        )
        curve = tuple(
            (fold_id, trade_date, _finite(value))
            for fold_id, trade_date, value in raw_curve
        )
        if (
            not daily
            or len(daily) != len(curve)
            or any(type(item[0]) is not _FoldId for item in (*daily, *curve))
            or any(type(item[1]) is not str for item in (*daily, *curve))
            or any(value <= -1.0 for _, _, value in daily)
            or any(value <= 0.0 for _, _, value in curve)
        ):
            _walk_forward_error("invalid_stitched_return_evidence")
        equity = 1.0
        prior_dates: dict[_FoldId, str] = {}
        closed_folds: set[_FoldId] = set()
        active_fold: _FoldId | None = None
        for daily_item, curve_item in zip(daily, curve, strict=True):
            fold_id, trade_date, daily_return = daily_item
            if daily_item[:2] != curve_item[:2]:
                _walk_forward_error("stitched_return_equity_identity_drift")
            try:
                parsed = date.fromisoformat(trade_date)
            except ValueError:
                _walk_forward_error("invalid_stitched_return_evidence")
            if parsed.isoformat() != trade_date or trade_date <= prior_dates.get(
                fold_id, ""
            ):
                _walk_forward_error("invalid_stitched_return_evidence")
            if active_fold is not None and fold_id != active_fold:
                closed_folds.add(active_fold)
            if fold_id in closed_folds:
                _walk_forward_error("invalid_stitched_fold_order")
            active_fold = fold_id
            prior_dates[fold_id] = trade_date
            equity *= 1.0 + daily_return
            if not math.isclose(curve_item[2], equity, rel_tol=1e-12, abs_tol=1e-12):
                _walk_forward_error("stitched_return_equity_identity_drift")
        refs, hashes = _lineage(self.evidence_refs, self.evidence_hashes)
        if not refs or not hashes:
            _walk_forward_error("stitched_return_evidence_source_required")
        object.__setattr__(self, "daily_returns", daily)
        object.__setattr__(self, "equity_curve", curve)
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "evidence_hashes", hashes)

    def canonical_payload(self) -> dict[str, object]:
        """Return the deterministic stitched-return evidence payload."""
        return {
            "daily_returns": [
                [str(fold_id), trade_date, value]
                for fold_id, trade_date, value in self.daily_returns
            ],
            "equity_curve": [
                [str(fold_id), trade_date, value]
                for fold_id, trade_date, value in self.equity_curve
            ],
            "evidence_hashes": [str(item) for item in self.evidence_hashes],
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class WalkForwardCandidate:
    """One candidate's complete cross-fold walk-forward projection."""

    candidate_id: _CandidateId
    candidate_ordinal: int
    is_baseline: bool
    status: CandidateWalkForwardStatus
    folds: tuple[FoldComparison, ...]
    metrics: Mapping[_ResearchMetricId, ScalarEvidence]
    factor_diagnostics: Mapping[_ResearchMetricId, WalkForwardDiagnosticEvidence]
    fold_stability: FoldStabilityEvidence
    relative_baseline_stability: FoldStabilityEvidence
    stitched_returns: StitchedReturnEvidence | None

    def __post_init__(self) -> None:
        """Freeze fixed-schema metrics and validate exact candidate folds."""
        if type(self.candidate_id) is not _CandidateId:
            _walk_forward_error("invalid_candidate_identity")
        if type(self.candidate_ordinal) is not int or self.candidate_ordinal <= 0:
            _walk_forward_error("invalid_candidate_identity")
        folds = tuple(self.folds)
        if any(type(item) is not FoldComparison for item in folds) or any(
            item.candidate_id != self.candidate_id
            or item.candidate_ordinal != self.candidate_ordinal
            or item.is_baseline is not self.is_baseline
            for item in folds
        ):
            _walk_forward_error("invalid_candidate_fold_rows")
        metrics = dict(self.metrics)
        if tuple(metrics) != _R3_COMPARISON_METRIC_IDS or any(
            type(item) is not ScalarEvidence
            or (
                item.metric_value is not None
                and item.metric_value.metric_id is not metric_id
            )
            for metric_id, item in metrics.items()
        ):
            _walk_forward_error("walk_forward_metric_schema_drift")
        diagnostics = dict(self.factor_diagnostics)
        if tuple(diagnostics) != _R3_DIAGNOSTIC_METRIC_IDS or any(
            type(item) is not WalkForwardDiagnosticEvidence
            for item in diagnostics.values()
        ):
            _walk_forward_error("walk_forward_diagnostic_schema_drift")
        if type(self.status) is not CandidateWalkForwardStatus:
            _walk_forward_error("invalid_candidate_walk_forward_status")
        if (
            type(self.fold_stability) is not FoldStabilityEvidence
            or type(self.relative_baseline_stability) is not FoldStabilityEvidence
        ):
            _walk_forward_error("invalid_fold_stability_evidence")
        object.__setattr__(self, "folds", folds)
        object.__setattr__(self, "metrics", MappingProxyType(metrics))
        object.__setattr__(self, "factor_diagnostics", MappingProxyType(diagnostics))

    def canonical_payload(self) -> dict[str, object]:
        """Return a deterministic candidate walk-forward payload."""
        return {
            "candidate_id": str(self.candidate_id),
            "candidate_ordinal": self.candidate_ordinal,
            "factor_diagnostics": [
                {
                    "evidence": self.factor_diagnostics[metric_id].canonical_payload(),
                    "metric_id": metric_id.value,
                }
                for metric_id in _R3_DIAGNOSTIC_METRIC_IDS
            ],
            "fold_stability": self.fold_stability.canonical_payload(),
            "folds": [item.canonical_payload() for item in self.folds],
            "is_baseline": self.is_baseline,
            "metrics": [
                {
                    "evidence": self.metrics[metric_id].canonical_payload(),
                    "metric_id": metric_id.value,
                }
                for metric_id in _R3_COMPARISON_METRIC_IDS
            ],
            "relative_baseline_stability": (
                self.relative_baseline_stability.canonical_payload()
            ),
            "status": self.status.value,
            "stitched_returns": (
                None
                if self.stitched_returns is None
                else self.stitched_returns.canonical_payload()
            ),
        }


@dataclass(frozen=True, slots=True)
class WalkForwardAggregation:
    """Factory-built versioned aggregation for the exact candidate family."""

    baseline: BaselineComparisonIdentity
    metric_schema: _ResearchMetricSchema
    candidates: tuple[WalkForwardCandidate, ...]
    _factory_token: InitVar[object | None] = None

    def __post_init__(self, _factory_token: object | None) -> None:
        """Enforce factory construction, schema identity, order, and baseline."""
        if _factory_token is not _WALK_FORWARD_FACTORY_TOKEN:
            _walk_forward_error("walk_forward_factory_required")
        if type(self.baseline) is not BaselineComparisonIdentity:
            _walk_forward_error("invalid_baseline_identity")
        if self.metric_schema is not _R3_RESEARCH_METRIC_SCHEMA:
            _walk_forward_error("walk_forward_metric_schema_drift")
        candidates = tuple(self.candidates)
        if any(type(item) is not WalkForwardCandidate for item in candidates):
            _walk_forward_error("invalid_walk_forward_candidates")
        if not candidates or tuple(
            (item.candidate_ordinal, str(item.candidate_id)) for item in candidates
        ) != tuple(
            sorted(
                (item.candidate_ordinal, str(item.candidate_id)) for item in candidates
            )
        ):
            _walk_forward_error("noncanonical_walk_forward_candidate_order")
        if len({item.candidate_id for item in candidates}) != len(candidates) or len(
            {item.candidate_ordinal for item in candidates}
        ) != len(candidates):
            _walk_forward_error("duplicate_walk_forward_candidate_identity")
        baselines = tuple(item for item in candidates if item.is_baseline)
        if (
            len(baselines) != 1
            or baselines[0].candidate_id != self.baseline.candidate_id
            or baselines[0].candidate_ordinal != 1
        ):
            _walk_forward_error("invalid_walk_forward_baseline")
        object.__setattr__(self, "candidates", candidates)

    def canonical_payload(self) -> dict[str, object]:
        """Return the complete versioned walk-forward artifact payload."""
        return {
            "artifact_schema": {
                "id": R3_WALK_FORWARD_ARTIFACT_SCHEMA_ID,
                "version": R3_WALK_FORWARD_ARTIFACT_SCHEMA_VERSION,
            },
            "baseline": self.baseline.canonical_payload(),
            "candidates": [item.canonical_payload() for item in self.candidates],
            "metric_schema": self.metric_schema.canonical_payload(),
        }

    @property
    def content_hash(self) -> _ContentHash:
        """Return the authoritative walk-forward artifact content hash."""
        return _canonical_payload(self.canonical_payload()).content_hash


def _stitch_returns(
    folds: tuple[FoldComparison, ...],
    status: CandidateWalkForwardStatus,
) -> StitchedReturnEvidence | None:
    if status is not CandidateWalkForwardStatus.COMPLETED or any(
        fold.return_evidence is None for fold in folds
    ):
        return None
    equity = 1.0
    daily: list[tuple[_FoldId, str, float]] = []
    curve: list[tuple[_FoldId, str, float]] = []
    refs: list[str] = []
    hashes: list[_ContentHash] = []
    for fold in folds:
        evidence = fold.return_evidence
        if evidence is None:
            _walk_forward_error("missing_fold_return_evidence")
        for trade_date, daily_return in evidence.daily_returns:
            equity *= 1.0 + daily_return
            daily.append((fold.fold_id, trade_date, daily_return))
            curve.append((fold.fold_id, trade_date, equity))
        refs.extend(evidence.evidence_refs)
        hashes.extend(evidence.evidence_hashes)
    evidence_refs, evidence_hashes = _lineage(refs, hashes)
    return StitchedReturnEvidence(
        tuple(daily),
        tuple(curve),
        evidence_refs,
        evidence_hashes,
    )


def _stitched_metrics(
    evidence: StitchedReturnEvidence | None,
) -> dict[_ResearchMetricId, ScalarEvidence]:
    ids = (
        _ResearchMetricId.NET_RETURN,
        _ResearchMetricId.SHARPE_RATIO,
        _ResearchMetricId.CALMAR_RATIO,
        _ResearchMetricId.MAX_DRAWDOWN,
    )
    if evidence is None:
        return {
            metric_id: _not_evaluated("fold_return_evidence_missing")
            for metric_id in ids
        }
    returns = tuple(item[2] for item in evidence.daily_returns)
    growth = math.prod(1.0 + value for value in returns)
    net_return = (growth - 1.0) * 100.0
    max_drawdown = _drawdown(
        tuple(item[2] for item in evidence.equity_curve), initial_peak=1.0
    )
    result = {
        _ResearchMetricId.NET_RETURN: _evaluated(
            _ResearchMetricId.NET_RETURN,
            net_return,
            evidence.evidence_refs,
            evidence.evidence_hashes,
        ),
        _ResearchMetricId.MAX_DRAWDOWN: _evaluated(
            _ResearchMetricId.MAX_DRAWDOWN,
            max_drawdown,
            evidence.evidence_refs,
            evidence.evidence_hashes,
        ),
    }
    volatility = stdev(returns) if len(returns) >= _MIN_RETURN_OBSERVATIONS else 0.0
    result[_ResearchMetricId.SHARPE_RATIO] = (
        _not_evaluated("insufficient_daily_return_evidence")
        if len(returns) < _MIN_RETURN_OBSERVATIONS
        else _not_evaluated("zero_return_volatility")
        if volatility == 0.0
        else _evaluated(
            _ResearchMetricId.SHARPE_RATIO,
            sum(returns)
            / len(returns)
            / volatility
            * math.sqrt(_TRADING_DAYS_PER_YEAR),
            evidence.evidence_refs,
            evidence.evidence_hashes,
        )
    )
    result[_ResearchMetricId.CALMAR_RATIO] = (
        _not_evaluated("zero_max_drawdown")
        if max_drawdown == 0.0
        else _evaluated(
            _ResearchMetricId.CALMAR_RATIO,
            ((growth ** (_TRADING_DAYS_PER_YEAR / len(returns))) - 1.0)
            * 100.0
            / abs(max_drawdown),
            evidence.evidence_refs,
            evidence.evidence_hashes,
        )
    )
    return result


def _aggregate_fold_metric(
    metric_id: _ResearchMetricId,
    folds: tuple[FoldComparison, ...],
) -> ScalarEvidence:
    evidence = tuple(fold.metrics[metric_id] for fold in folds)
    if any(item.status is EvidenceStatus.NOT_EVALUATED for item in evidence):
        reason = (
            "capacity_evidence_missing"
            if metric_id is _ResearchMetricId.CAPACITY
            and any(item.reason == "capacity_evidence_missing" for item in evidence)
            else "fold_metric_not_evaluated"
        )
        return _not_evaluated(reason)
    values = tuple(_finite(item.value) for item in evidence)
    aggregate = min(values) if metric_id is _ResearchMetricId.CAPACITY else sum(values)
    refs, hashes = _merge_refs(evidence)
    return _evaluated(metric_id, aggregate, refs, hashes)


def _aggregate_execution_metrics(
    folds: tuple[FoldComparison, ...],
    stitched: StitchedReturnEvidence | None,
) -> dict[_ResearchMetricId, ScalarEvidence]:
    if stitched is None or any(fold.execution_evidence is None for fold in folds):
        reason = "fold_execution_evidence_missing"
        return {
            metric_id: _not_evaluated(reason)
            for metric_id in (_ResearchMetricId.TURNOVER, _ResearchMetricId.COST_DRAG)
        }
    equity = 1.0
    scaled_navs: list[float] = []
    total_notional = 0.0
    total_cost = 0.0
    refs: list[str] = []
    hashes: list[_ContentHash] = []
    for fold in folds:
        evidence = fold.execution_evidence
        if evidence is None:
            _walk_forward_error("fold_execution_evidence_missing")
        scale = equity / evidence.initial_capital
        total_notional += evidence.fill_notional * scale
        total_cost += evidence.explicit_cost * scale
        fold_navs = tuple(nav * scale for _, nav in evidence.nav_series)
        scaled_navs.extend(fold_navs)
        equity = fold_navs[-1]
        refs.extend(evidence.evidence_refs)
        hashes.extend(evidence.evidence_hashes)
    expected_curve = tuple(item[2] for item in stitched.equity_curve)
    if len(scaled_navs) != len(expected_curve) or any(
        not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
        for actual, expected in zip(scaled_navs, expected_curve, strict=True)
    ):
        reason = "fold_execution_equity_drift"
        return {
            metric_id: _not_evaluated(reason)
            for metric_id in (_ResearchMetricId.TURNOVER, _ResearchMetricId.COST_DRAG)
        }
    average_nav = sum(scaled_navs) / len(scaled_navs)
    evidence_refs, evidence_hashes = _lineage(refs, hashes)
    return {
        _ResearchMetricId.TURNOVER: _evaluated(
            _ResearchMetricId.TURNOVER,
            total_notional / average_nav,
            evidence_refs,
            evidence_hashes,
        ),
        _ResearchMetricId.COST_DRAG: _evaluated(
            _ResearchMetricId.COST_DRAG,
            total_cost * 100.0,
            evidence_refs,
            evidence_hashes,
        ),
    }


def _aggregate_metrics(
    folds: tuple[FoldComparison, ...],
    status: CandidateWalkForwardStatus,
    stitched: StitchedReturnEvidence | None,
) -> dict[_ResearchMetricId, ScalarEvidence]:
    unavailable = _unavailable_reason(status)
    if unavailable is not None:
        return {
            metric_id: _not_evaluated(unavailable)
            for metric_id in _R3_COMPARISON_METRIC_IDS
        }
    metrics = {
        **_stitched_metrics(stitched),
        **_aggregate_execution_metrics(folds, stitched),
        _ResearchMetricId.RELATIVE_NET_RETURN: _not_evaluated(
            "baseline_comparison_pending"
        ),
        _ResearchMetricId.CAPACITY: _aggregate_fold_metric(
            _ResearchMetricId.CAPACITY, folds
        ),
    }
    return {metric_id: metrics[metric_id] for metric_id in _R3_COMPARISON_METRIC_IDS}


def _aggregate_diagnostics(
    folds: tuple[FoldComparison, ...],
    status: CandidateWalkForwardStatus,
) -> dict[_ResearchMetricId, WalkForwardDiagnosticEvidence]:
    unavailable = _unavailable_reason(status)
    if unavailable is not None:
        return {
            metric_id: WalkForwardDiagnosticEvidence(
                EvidenceStatus.NOT_EVALUATED, (), unavailable
            )
            for metric_id in _R3_DIAGNOSTIC_METRIC_IDS
        }
    result: dict[_ResearchMetricId, WalkForwardDiagnosticEvidence] = {}
    for metric_id in _R3_DIAGNOSTIC_METRIC_IDS:
        evidence = tuple(fold.factor_diagnostics[metric_id] for fold in folds)
        evaluated = tuple(
            (fold.fold_id, item.value)
            for fold, item in zip(folds, evidence, strict=True)
            if item.status is EvidenceStatus.EVALUATED
        )
        status_value = (
            EvidenceStatus.EVALUATED
            if len(evaluated) == _REQUIRED_FOLD_COUNT
            else EvidenceStatus.NOT_EVALUATED
        )
        refs, hashes = _merge_refs(evidence)
        result[metric_id] = WalkForwardDiagnosticEvidence(
            status_value,
            evaluated,
            None
            if status_value is EvidenceStatus.EVALUATED
            else "fold_diagnostic_not_evaluated",
            refs,
            hashes,
        )
    return result


def _fold_stability(
    folds: tuple[FoldComparison, ...],
    status: CandidateWalkForwardStatus,
    metric_id: _ResearchMetricId,
) -> FoldStabilityEvidence:
    unavailable = _unavailable_reason(status)
    if unavailable is not None:
        return FoldStabilityEvidence(
            EvidenceStatus.NOT_EVALUATED, (), None, 0, 0, 0, None, unavailable
        )
    evaluated = tuple(
        (fold.fold_id, _finite(fold.metrics[metric_id].value))
        for fold in folds
        if fold.metrics[metric_id].status is EvidenceStatus.EVALUATED
    )
    if len(evaluated) != _REQUIRED_FOLD_COUNT:
        return FoldStabilityEvidence(
            EvidenceStatus.NOT_EVALUATED,
            evaluated,
            None,
            0,
            0,
            0,
            None,
            "fold_metric_not_evaluated",
        )
    returns = tuple(value for _, value in evaluated)
    positive = sum(value > 0.0 for value in returns)
    negative = sum(value < 0.0 for value in returns)
    zero = len(returns) - positive - negative
    signs = {1 if value > 0.0 else -1 if value < 0.0 else 0 for value in returns}
    return FoldStabilityEvidence(
        EvidenceStatus.EVALUATED,
        evaluated,
        len(signs) == 1,
        positive,
        negative,
        zero,
        max(returns) - min(returns),
        None,
    )


def _candidate_projection(
    folds: tuple[FoldComparison, ...],
    expected: tuple[tuple[_FoldId, int], ...],
    baseline_grid: tuple[tuple[_FoldId, str], ...] | None,
    *,
    baseline_ready: bool,
) -> WalkForwardCandidate:
    first = folds[0]
    status = _candidate_status(folds, expected)
    if (
        status is CandidateWalkForwardStatus.COMPLETED
        and baseline_grid is not None
        and _return_grid(folds) != baseline_grid
    ):
        _walk_forward_error("candidate_return_grid_drift")
    if not baseline_ready and status is CandidateWalkForwardStatus.COMPLETED:
        status = CandidateWalkForwardStatus.NOT_EVALUATED
    stitched = _stitch_returns(folds, status)
    return WalkForwardCandidate(
        first.candidate_id,
        first.candidate_ordinal,
        first.is_baseline,
        status,
        folds,
        _aggregate_metrics(folds, status, stitched),
        _aggregate_diagnostics(folds, status),
        _fold_stability(folds, status, _ResearchMetricId.NET_RETURN),
        _fold_stability(folds, status, _ResearchMetricId.RELATIVE_NET_RETURN),
        stitched,
    )


def _return_grid(
    folds: tuple[FoldComparison, ...],
) -> tuple[tuple[_FoldId, str], ...] | None:
    grid: list[tuple[_FoldId, str]] = []
    for fold in folds:
        evidence = fold.return_evidence
        if evidence is None:
            return None
        grid.extend(
            (fold.fold_id, trade_date) for trade_date, _ in evidence.daily_returns
        )
    return tuple(grid)


def _relative_metric(
    candidate: WalkForwardCandidate,
    baseline: WalkForwardCandidate,
) -> ScalarEvidence:
    unavailable = _unavailable_reason(candidate.status)
    if unavailable is not None:
        return _not_evaluated(unavailable)
    candidate_net = candidate.metrics[_ResearchMetricId.NET_RETURN]
    baseline_net = baseline.metrics[_ResearchMetricId.NET_RETURN]
    if candidate_net.status is EvidenceStatus.NOT_EVALUATED:
        return _not_evaluated("candidate_net_return_not_evaluated")
    if baseline_net.status is EvidenceStatus.NOT_EVALUATED:
        return _not_evaluated("baseline_net_return_not_evaluated")
    refs, hashes = _merge_refs((candidate_net, baseline_net))
    value = (
        0.0
        if candidate.is_baseline
        else _finite(candidate_net.value) - _finite(baseline_net.value)
    )
    return _evaluated(_ResearchMetricId.RELATIVE_NET_RETURN, value, refs, hashes)


def aggregate_walk_forward(
    comparison: CandidateComparisonProjection,
) -> WalkForwardAggregation:
    """Aggregate exact persisted OOS rows against the registered baseline."""
    if type(comparison) is not CandidateComparisonProjection:
        _walk_forward_error("invalid_candidate_comparison")
    expected = tuple(
        (item.fold_id, item.fold_ordinal) for item in comparison.baseline.oos_folds
    )
    grouped: dict[_CandidateId, list[FoldComparison]] = {}
    for row in comparison.folds:
        grouped.setdefault(row.candidate_id, []).append(row)
    baseline_rows = tuple(
        sorted(
            grouped.get(comparison.baseline.candidate_id, ()),
            key=lambda row: row.fold_ordinal,
        )
    )
    if not baseline_rows:
        _walk_forward_error("baseline_candidate_evidence_missing")
    baseline_ready = (
        _candidate_status(baseline_rows, expected)
        is CandidateWalkForwardStatus.COMPLETED
    )
    baseline_grid = _return_grid(baseline_rows) if baseline_ready else None
    candidates = tuple(
        sorted(
            (
                _candidate_projection(
                    tuple(sorted(rows, key=lambda row: row.fold_ordinal)),
                    expected,
                    baseline_grid,
                    baseline_ready=baseline_ready,
                )
                for rows in grouped.values()
            ),
            key=lambda item: (item.candidate_ordinal, str(item.candidate_id)),
        )
    )
    baseline = next(
        (
            item
            for item in candidates
            if item.candidate_id == comparison.baseline.candidate_id
        ),
        None,
    )
    if baseline is None:
        _walk_forward_error("baseline_candidate_evidence_missing")
    resolved: list[WalkForwardCandidate] = []
    for candidate in candidates:
        metrics = dict(candidate.metrics)
        metrics[_ResearchMetricId.RELATIVE_NET_RETURN] = _relative_metric(
            candidate, baseline
        )
        updated = replace(candidate, metrics=metrics)
        updated = replace(
            updated,
            relative_baseline_stability=_fold_stability(
                updated.folds,
                updated.status,
                _ResearchMetricId.RELATIVE_NET_RETURN,
            ),
        )
        resolved.append(updated)
    return WalkForwardAggregation(
        comparison.baseline,
        _R3_RESEARCH_METRIC_SCHEMA,
        tuple(resolved),
        _WALK_FORWARD_FACTORY_TOKEN,
    )
