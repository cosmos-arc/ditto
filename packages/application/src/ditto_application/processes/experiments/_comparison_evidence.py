# pyright: reportPrivateUsage=false, reportUnusedFunction=false, reportUnusedImport=false
"""Validated evidence value objects shared by R3 comparison projections."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from statistics import stdev
from typing import Protocol, cast

from ditto_analysis.experiments import (
    R3_COMPARISON_METRIC_IDS as _R3_COMPARISON_METRIC_IDS,
)
from ditto_analysis.experiments import (
    CandidateId as _CandidateId,
)
from ditto_analysis.experiments import (
    ContentHash as _ContentHash,
)
from ditto_analysis.experiments import (
    DateWindow as _DateWindow,
)
from ditto_analysis.experiments import (
    ExperimentId as _ExperimentId,
)
from ditto_analysis.experiments import (
    FoldId as _FoldId,
)
from ditto_analysis.experiments import (
    ResearchMetricId as _ResearchMetricId,
)
from ditto_analysis.experiments import (
    ResearchMetricUnit as _ResearchMetricUnit,
)
from ditto_analysis.experiments import (
    ResearchMetricValue as _ResearchMetricValue,
)
from ditto_analysis.experiments import (
    SnapshotId as _SnapshotId,
)
from ditto_analysis.experiments import (
    canonical_payload as _canonical_payload,
)

from ditto_application.processes.experiments._evidence_values import (
    _canonical_text,
    _canonical_value,
    _comparison_error,
    _deep_freeze,
    _finite,
)
from ditto_application.processes.experiments._report_evidence import (
    BacktestFillEvidence,
    LoadedBacktestReportArtifact,
)

_TRADING_DAYS_PER_YEAR = 252
_EVIDENCE_PAIR_SIZE = 2
_MIN_RETURN_OBSERVATIONS = 2
R3_CAPACITY_EVIDENCE_SCHEMA_ID = "ditto.r3.capacity-evidence"
R3_CAPACITY_EVIDENCE_SCHEMA_VERSION = 1


class EvidenceStatus(StrEnum):
    """Whether an evidence item was honestly evaluated."""

    EVALUATED = "evaluated"
    NOT_EVALUATED = "not_evaluated"


class FoldOutcome(StrEnum):
    """Terminal outcome of one candidate/fold execution."""

    COMPLETED = "completed"
    FAILED = "failed"


class CandidateWalkForwardStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_EVALUATED = "not_evaluated"


def _positive_ordinal(value: object, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        _comparison_error("invalid_comparison_ordinal", field=field_name)
    return value


def _hashes(value: object) -> tuple[_ContentHash, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _comparison_error("invalid_evidence_hashes")
    hashes = tuple(cast("Sequence[object]", value))
    if any(type(item) is not _ContentHash for item in hashes):
        _comparison_error("invalid_evidence_hashes")
    return cast("tuple[_ContentHash, ...]", hashes)


def _refs(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _comparison_error("invalid_evidence_refs")
    refs = tuple(
        _canonical_text(item, "evidence_ref")
        for item in cast("Sequence[object]", value)
    )
    if len(set(refs)) != len(refs):
        _comparison_error("duplicate_evidence_ref")
    return refs


def _lineage(
    refs_value: object,
    hashes_value: object,
) -> tuple[tuple[str, ...], tuple[_ContentHash, ...]]:
    refs, hashes = _refs(refs_value), _hashes(hashes_value)
    if len(refs) != len(hashes):
        _comparison_error("evidence_lineage_length_mismatch")
    pairs = tuple(zip(refs, hashes, strict=True))
    if len(set(pairs)) != len(pairs):
        _comparison_error("duplicate_evidence_lineage_pair")
    return refs, hashes


@dataclass(frozen=True, slots=True)
class CapacityEvidence:
    """Versioned capacity estimate bound to one exact candidate/fold source."""

    experiment_id: _ExperimentId
    candidate_id: _CandidateId
    fold_id: _FoldId
    snapshot_id: _SnapshotId
    snapshot_hash: _ContentHash
    parameter_hash: _ContentHash
    resolved_spec_hash: _ContentHash
    test_window: _DateWindow
    value_cny: float
    evidence_ref: str
    method: str
    content_hash: _ContentHash = field(init=False)

    def __post_init__(self) -> None:
        """Validate typed lineage and derive content identity from the envelope."""
        typed = (
            (self.experiment_id, _ExperimentId),
            (self.candidate_id, _CandidateId),
            (self.fold_id, _FoldId),
            (self.snapshot_id, _SnapshotId),
            (self.snapshot_hash, _ContentHash),
            (self.parameter_hash, _ContentHash),
            (self.resolved_spec_hash, _ContentHash),
            (self.test_window, _DateWindow),
        )
        value = _finite(self.value_cny)
        if any(type(item) is not expected for item, expected in typed):
            _comparison_error("invalid_capacity_evidence_identity")
        if value is None or value < 0.0:
            _comparison_error("invalid_capacity_evidence")
        _canonical_text(self.evidence_ref, "capacity_evidence_ref")
        _canonical_text(self.method, "capacity_method")
        object.__setattr__(self, "value_cny", value)
        object.__setattr__(
            self,
            "content_hash",
            _canonical_payload(self.canonical_payload()).content_hash,
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return the complete versioned preimage for this capacity estimate."""
        return {
            "capacity_schema": {
                "id": R3_CAPACITY_EVIDENCE_SCHEMA_ID,
                "version": R3_CAPACITY_EVIDENCE_SCHEMA_VERSION,
            },
            "candidate_id": str(self.candidate_id),
            "evidence_ref": self.evidence_ref,
            "experiment_id": str(self.experiment_id),
            "fold_id": str(self.fold_id),
            "method": self.method,
            "parameter_hash": str(self.parameter_hash),
            "resolved_spec_hash": str(self.resolved_spec_hash),
            "snapshot_hash": str(self.snapshot_hash),
            "snapshot_id": str(self.snapshot_id),
            "test_window": {
                "end": self.test_window.end.isoformat(),
                "start": self.test_window.start.isoformat(),
            },
            "value_cny": self.value_cny,
        }


class _CapacityFoldSource(Protocol):
    @property
    def experiment_id(self) -> _ExperimentId: ...

    @property
    def candidate_id(self) -> _CandidateId: ...

    @property
    def fold_id(self) -> _FoldId: ...

    @property
    def snapshot_id(self) -> _SnapshotId: ...

    @property
    def snapshot_hash(self) -> _ContentHash: ...

    @property
    def parameter_hash(self) -> _ContentHash: ...

    @property
    def resolved_spec_hash(self) -> _ContentHash: ...

    @property
    def test_window(self) -> _DateWindow: ...

    @property
    def capacity(self) -> CapacityEvidence | None: ...


def _validate_capacity_evidence(value: _CapacityFoldSource) -> None:
    capacity = value.capacity
    if capacity is None:
        return
    if type(capacity) is not CapacityEvidence:
        _comparison_error("invalid_capacity_evidence")
    expected = (
        value.experiment_id,
        value.candidate_id,
        value.fold_id,
        value.snapshot_id,
        value.snapshot_hash,
        value.parameter_hash,
        value.resolved_spec_hash,
        value.test_window,
    )
    actual = (
        capacity.experiment_id,
        capacity.candidate_id,
        capacity.fold_id,
        capacity.snapshot_id,
        capacity.snapshot_hash,
        capacity.parameter_hash,
        capacity.resolved_spec_hash,
        capacity.test_window,
    )
    if actual != expected:
        _comparison_error("capacity_evidence_identity_drift")
    if (
        capacity.content_hash
        != _canonical_payload(capacity.canonical_payload()).content_hash
    ):
        _comparison_error("capacity_content_hash_drift")


@dataclass(frozen=True, slots=True)
class ScalarEvidence:
    """Typed scalar value or an explicit non-evaluation reason."""

    status: EvidenceStatus
    metric_value: _ResearchMetricValue | None
    reason: str | None
    evidence_refs: tuple[str, ...] = ()
    evidence_hashes: tuple[_ContentHash, ...] = ()

    def __post_init__(self) -> None:
        if type(self.status) is not EvidenceStatus:
            _comparison_error("invalid_evidence_status")
        if self.status is EvidenceStatus.EVALUATED:
            if (
                type(self.metric_value) is not _ResearchMetricValue
                or self.reason is not None
            ):
                _comparison_error("invalid_evaluated_scalar_evidence")
        elif self.metric_value is not None or self.reason is None:
            _comparison_error("invalid_not_evaluated_scalar_evidence")
        else:
            _canonical_text(self.reason, "evidence_reason")
        refs, hashes = _lineage(self.evidence_refs, self.evidence_hashes)
        if self.status is EvidenceStatus.EVALUATED and (not refs or not hashes):
            _comparison_error("evaluated_evidence_source_required")
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "evidence_hashes", hashes)

    @property
    def value(self) -> float | None:
        return None if self.metric_value is None else self.metric_value.value

    @property
    def unit(self) -> _ResearchMetricUnit | None:
        return None if self.metric_value is None else self.metric_value.unit

    def canonical_payload(self) -> dict[str, object]:
        return {
            "evidence_hashes": [str(item) for item in self.evidence_hashes],
            "evidence_refs": list(self.evidence_refs),
            "metric_value": (
                None
                if self.metric_value is None
                else self.metric_value.canonical_payload()
            ),
            "reason": self.reason,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class DiagnosticEvidence:
    """One fixed diagnostic value with immutable artifact evidence."""

    status: EvidenceStatus
    value: object | None
    reason: str | None
    evidence_refs: tuple[str, ...] = ()
    evidence_hashes: tuple[_ContentHash, ...] = ()

    def __post_init__(self) -> None:
        if type(self.status) is not EvidenceStatus:
            _comparison_error("invalid_diagnostic_status")
        if self.status is EvidenceStatus.EVALUATED:
            if self.value is None or self.reason is not None:
                _comparison_error("invalid_evaluated_diagnostic")
            object.__setattr__(self, "value", _deep_freeze(self.value))
        elif self.value is not None or self.reason is None:
            _comparison_error("invalid_not_evaluated_diagnostic")
        else:
            _canonical_text(self.reason, "diagnostic_reason")
        refs, hashes = _lineage(self.evidence_refs, self.evidence_hashes)
        if self.status is EvidenceStatus.EVALUATED and (not refs or not hashes):
            _comparison_error("evaluated_evidence_source_required")
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "evidence_hashes", hashes)

    def canonical_payload(self) -> dict[str, object]:
        return {
            "evidence_hashes": [str(item) for item in self.evidence_hashes],
            "evidence_refs": list(self.evidence_refs),
            "reason": self.reason,
            "status": self.status.value,
            "value": _canonical_value(self.value),
        }


def _ordered_nav(
    value: object,
    *,
    reason: str,
) -> tuple[tuple[str, float], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _comparison_error(reason)
    rows: list[tuple[str, float]] = []
    previous = ""
    for raw in cast("Sequence[object]", value):
        if type(raw) is not tuple:
            _comparison_error(reason)
        raw_tuple = cast("tuple[object, ...]", raw)
        if len(raw_tuple) != _EVIDENCE_PAIR_SIZE:
            _comparison_error(reason)
        raw_date, raw_nav = raw_tuple
        nav = _finite(raw_nav)
        if type(raw_date) is not str or nav is None or nav <= 0.0:
            _comparison_error(reason)
        try:
            parsed = date.fromisoformat(raw_date)
        except ValueError:
            _comparison_error(reason)
        if parsed.isoformat() != raw_date or raw_date <= previous:
            _comparison_error(reason)
        rows.append((raw_date, nav))
        previous = raw_date
    if not rows:
        _comparison_error(reason)
    return tuple(rows)


@dataclass(frozen=True, slots=True)
class FoldReturnEvidence:
    """Ordered NAV and decimal daily returns retained from one report."""

    initial_capital: float
    nav_series: tuple[tuple[str, float], ...]
    daily_returns: tuple[tuple[str, float], ...]
    evidence_refs: tuple[str, ...]
    evidence_hashes: tuple[_ContentHash, ...]

    def __post_init__(self) -> None:
        initial = _finite(self.initial_capital)
        navs = _ordered_nav(self.nav_series, reason="invalid_fold_return_evidence")
        returns = tuple(self.daily_returns)
        if initial is None or initial <= 0.0 or len(returns) != len(navs):
            _comparison_error("invalid_fold_return_evidence")
        normalized: list[tuple[str, float]] = []
        prior = initial
        for raw, nav in zip(returns, navs, strict=True):
            if (
                type(raw) is not tuple
                or len(raw) != _EVIDENCE_PAIR_SIZE
                or raw[0] != nav[0]
            ):
                _comparison_error("invalid_fold_return_evidence")
            daily_return = _finite(raw[1])
            if (
                daily_return is None
                or daily_return <= -1.0
                or not math.isclose(
                    daily_return,
                    nav[1] / prior - 1.0,
                    rel_tol=1e-12,
                    abs_tol=1e-12,
                )
            ):
                _comparison_error("invalid_fold_return_evidence")
            normalized.append((raw[0], daily_return))
            prior = nav[1]
        refs, hashes = _lineage(self.evidence_refs, self.evidence_hashes)
        if not refs or not hashes:
            _comparison_error("fold_return_evidence_source_required")
        object.__setattr__(self, "initial_capital", initial)
        object.__setattr__(self, "nav_series", navs)
        object.__setattr__(self, "daily_returns", tuple(normalized))
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "evidence_hashes", hashes)

    def canonical_payload(self) -> dict[str, object]:
        return {
            "daily_returns": [list(item) for item in self.daily_returns],
            "evidence_hashes": [str(item) for item in self.evidence_hashes],
            "evidence_refs": list(self.evidence_refs),
            "initial_capital": self.initial_capital,
            "nav_series": [list(item) for item in self.nav_series],
        }


@dataclass(frozen=True, slots=True)
class FoldExecutionEvidence:
    """Sufficient fill, cost, NAV, and capital totals for recomputation."""

    initial_capital: float
    nav_series: tuple[tuple[str, float], ...]
    fill_notional: float
    explicit_cost: float
    evidence_refs: tuple[str, ...]
    evidence_hashes: tuple[_ContentHash, ...]

    def __post_init__(self) -> None:
        initial = _finite(self.initial_capital)
        fill_notional = _finite(self.fill_notional)
        explicit_cost = _finite(self.explicit_cost)
        navs = _ordered_nav(self.nav_series, reason="invalid_fold_execution_evidence")
        if (
            initial is None
            or initial <= 0.0
            or fill_notional is None
            or fill_notional < 0.0
            or explicit_cost is None
            or explicit_cost < 0.0
        ):
            _comparison_error("invalid_fold_execution_evidence")
        refs, hashes = _lineage(self.evidence_refs, self.evidence_hashes)
        if not refs or not hashes:
            _comparison_error("fold_execution_evidence_source_required")
        object.__setattr__(self, "initial_capital", initial)
        object.__setattr__(self, "fill_notional", fill_notional)
        object.__setattr__(self, "explicit_cost", explicit_cost)
        object.__setattr__(self, "nav_series", navs)
        object.__setattr__(self, "evidence_refs", refs)
        object.__setattr__(self, "evidence_hashes", hashes)

    def canonical_payload(self) -> dict[str, object]:
        return {
            "evidence_hashes": [str(item) for item in self.evidence_hashes],
            "evidence_refs": list(self.evidence_refs),
            "explicit_cost": self.explicit_cost,
            "fill_notional": self.fill_notional,
            "initial_capital": self.initial_capital,
            "nav_series": [list(item) for item in self.nav_series],
        }


class _FoldMetricSource(Protocol):
    @property
    def outcome(self) -> FoldOutcome: ...

    @property
    def report_artifact(self) -> LoadedBacktestReportArtifact | None: ...

    @property
    def test_window(self) -> _DateWindow: ...

    @property
    def capacity(self) -> CapacityEvidence | None: ...


class _WalkForwardFoldSource(Protocol):
    @property
    def fold_id(self) -> _FoldId: ...

    @property
    def fold_ordinal(self) -> int: ...

    @property
    def outcome(self) -> FoldOutcome: ...

    @property
    def return_evidence(self) -> FoldReturnEvidence | None: ...


def _candidate_status(
    folds: tuple[_WalkForwardFoldSource, ...],
    expected: tuple[tuple[_FoldId, int], ...],
) -> CandidateWalkForwardStatus:
    if any(fold.outcome is FoldOutcome.FAILED for fold in folds):
        return CandidateWalkForwardStatus.FAILED
    observed = tuple((fold.fold_id, fold.fold_ordinal) for fold in folds)
    if observed != expected or any(fold.return_evidence is None for fold in folds):
        return CandidateWalkForwardStatus.NOT_EVALUATED
    return CandidateWalkForwardStatus.COMPLETED


def _unavailable_reason(status: CandidateWalkForwardStatus) -> str | None:
    return {
        CandidateWalkForwardStatus.FAILED: "candidate_failed",
        CandidateWalkForwardStatus.NOT_EVALUATED: "incomplete_walk_forward_folds",
    }.get(status)


def _not_evaluated(reason: str) -> ScalarEvidence:
    return ScalarEvidence(EvidenceStatus.NOT_EVALUATED, None, reason)


def _evaluated(
    metric_id: _ResearchMetricId,
    value: float,
    refs: tuple[str, ...],
    hashes: tuple[_ContentHash, ...],
) -> ScalarEvidence:
    return ScalarEvidence(
        EvidenceStatus.EVALUATED,
        _ResearchMetricValue(metric_id, value),
        None,
        refs,
        hashes,
    )


def _source_refs(value: _FoldMetricSource) -> tuple[str, ...]:
    artifact = value.report_artifact
    if artifact is None:
        _comparison_error("backtest_report_missing")
    return (artifact.record.relative_path,)


def _source_hashes(value: _FoldMetricSource) -> tuple[_ContentHash, ...]:
    artifact = value.report_artifact
    if artifact is None:
        _comparison_error("backtest_report_missing")
    return (artifact.record.content_hash,)


def _return_evidence(  # noqa: C901, PLR0911 - fail-closed report parser
    value: _FoldMetricSource,
) -> FoldReturnEvidence | None:
    artifact = value.report_artifact
    if artifact is None:
        return None
    report = artifact.evidence
    initial, final = _finite(report.initial_cash), _finite(report.final_nav)
    raw_nav = tuple(report.nav_series)
    if initial is None or initial <= 0.0 or final is None or not raw_nav:
        return None
    normalized: list[tuple[str, float]] = []
    previous_date = ""
    for raw in raw_nav:
        if type(raw) is not tuple or len(raw) != _EVIDENCE_PAIR_SIZE:
            return None
        raw_date, raw_value = raw
        nav = _finite(raw_value)
        if type(raw_date) is not str or nav is None or nav <= 0.0:
            return None
        try:
            parsed = date.fromisoformat(raw_date)
        except ValueError:
            return None
        if raw_date != parsed.isoformat() or raw_date <= previous_date:
            return None
        if not value.test_window.start <= parsed <= value.test_window.end:
            return None
        normalized.append((raw_date, nav))
        previous_date = raw_date
    if (
        normalized[0][0] != value.test_window.start.isoformat()
        or normalized[-1][0] != value.test_window.end.isoformat()
        or not math.isclose(normalized[-1][1], final, rel_tol=1e-12, abs_tol=1e-9)
    ):
        return None
    returns: list[tuple[str, float]] = []
    prior = initial
    for trade_date, nav in normalized:
        returns.append((trade_date, nav / prior - 1.0))
        prior = nav
    return FoldReturnEvidence(
        initial,
        tuple(normalized),
        tuple(returns),
        _source_refs(value),
        _source_hashes(value),
    )


def _drawdown(
    navs: Sequence[float],
    *,
    initial_peak: float | None = None,
) -> float:
    peak, worst = navs[0] if initial_peak is None else initial_peak, 0.0
    for nav in navs:
        peak = max(peak, nav)
        worst = min(worst, nav / peak - 1.0)
    return worst * 100.0


def _merge_refs(
    values: Sequence[ScalarEvidence | DiagnosticEvidence],
) -> tuple[tuple[str, ...], tuple[_ContentHash, ...]]:
    pairs = tuple(
        dict.fromkeys(
            pair
            for value in values
            for pair in zip(
                value.evidence_refs,
                value.evidence_hashes,
                strict=True,
            )
        )
    )
    return (
        tuple(ref for ref, _ in pairs),
        tuple(item_hash for _, item_hash in pairs),
    )


def _return_metrics(
    value: _FoldMetricSource,
    evidence: FoldReturnEvidence | None,
) -> dict[_ResearchMetricId, ScalarEvidence]:
    reason = (
        "backtest_report_missing"
        if value.report_artifact is None
        else "insufficient_nav_evidence"
    )
    ids = (
        _ResearchMetricId.NET_RETURN,
        _ResearchMetricId.SHARPE_RATIO,
        _ResearchMetricId.CALMAR_RATIO,
        _ResearchMetricId.MAX_DRAWDOWN,
    )
    if evidence is None:
        return {metric_id: _not_evaluated(reason) for metric_id in ids}
    returns = tuple(item[1] for item in evidence.daily_returns)
    growth = math.prod(1.0 + item for item in returns)
    max_drawdown = _drawdown(
        (evidence.initial_capital, *(item[1] for item in evidence.nav_series))
    )
    refs, hashes = evidence.evidence_refs, evidence.evidence_hashes
    result = {
        _ResearchMetricId.NET_RETURN: _evaluated(
            _ResearchMetricId.NET_RETURN, (growth - 1.0) * 100.0, refs, hashes
        ),
        _ResearchMetricId.MAX_DRAWDOWN: _evaluated(
            _ResearchMetricId.MAX_DRAWDOWN, max_drawdown, refs, hashes
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
            refs,
            hashes,
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
            refs,
            hashes,
        )
    )
    return result


def _execution_evidence(
    value: _FoldMetricSource,
    returns: FoldReturnEvidence | None,
) -> FoldExecutionEvidence | None:
    artifact = value.report_artifact
    if artifact is None or returns is None:
        return None
    report = artifact.evidence
    if not all(
        type(fill) is BacktestFillEvidence
        and _finite(fill.fill_price) is not None
        and fill.fill_price >= 0.0
        and type(fill.filled_quantity) is int
        and fill.filled_quantity >= 0
        and _finite(fill.fee) is not None
        and fill.fee >= 0.0
        and _finite(fill.slippage) is not None
        for fill in report.fill_log
    ):
        return None
    return FoldExecutionEvidence(
        returns.initial_capital,
        returns.nav_series,
        sum(fill.fill_price * fill.filled_quantity for fill in report.fill_log),
        sum(
            fill.fee + abs(fill.slippage) * fill.filled_quantity
            for fill in report.fill_log
        ),
        _source_refs(value),
        _source_hashes(value),
    )


def _execution_metrics(
    value: _FoldMetricSource,
    evidence: FoldExecutionEvidence | None,
) -> dict[_ResearchMetricId, ScalarEvidence]:
    ids = (_ResearchMetricId.TURNOVER, _ResearchMetricId.COST_DRAG)
    if value.report_artifact is None:
        return {item: _not_evaluated("backtest_report_missing") for item in ids}
    if evidence is None:
        return {
            item: _not_evaluated("insufficient_fill_nav_capital_evidence")
            for item in ids
        }
    average_nav = sum(item[1] for item in evidence.nav_series) / len(
        evidence.nav_series
    )
    refs, hashes = evidence.evidence_refs, evidence.evidence_hashes
    return {
        _ResearchMetricId.TURNOVER: _evaluated(
            _ResearchMetricId.TURNOVER,
            evidence.fill_notional / average_nav,
            refs,
            hashes,
        ),
        _ResearchMetricId.COST_DRAG: _evaluated(
            _ResearchMetricId.COST_DRAG,
            evidence.explicit_cost / evidence.initial_capital * 100.0,
            refs,
            hashes,
        ),
    }


def _project_metrics(
    value: _FoldMetricSource,
    returns: FoldReturnEvidence | None,
    execution: FoldExecutionEvidence | None,
) -> dict[_ResearchMetricId, ScalarEvidence]:
    if value.outcome is FoldOutcome.FAILED:
        return {
            metric_id: _not_evaluated("candidate_failed")
            for metric_id in _R3_COMPARISON_METRIC_IDS
        }
    projected = {
        **_return_metrics(value, returns),
        **_execution_metrics(value, execution),
        _ResearchMetricId.RELATIVE_NET_RETURN: _not_evaluated(
            "baseline_comparison_pending"
        ),
    }
    capacity = value.capacity
    projected[_ResearchMetricId.CAPACITY] = (
        _not_evaluated("capacity_evidence_missing")
        if capacity is None
        else _evaluated(
            _ResearchMetricId.CAPACITY,
            capacity.value_cny,
            (capacity.evidence_ref,),
            (capacity.content_hash,),
        )
    )
    return {metric_id: projected[metric_id] for metric_id in _R3_COMPARISON_METRIC_IDS}
