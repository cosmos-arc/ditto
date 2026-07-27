# pyright: reportPrivateUsage=false
"""Immutable R3 comparison evidence over exact pre-registered OOS folds."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import InitVar, dataclass, replace
from types import MappingProxyType
from typing import cast

from ditto_analysis import experiments as _analysis_experiments
from ditto_features.evaluation.report import (
    R3_FACTOR_DIAGNOSTIC_METRIC_IDS as _FEATURE_DIAGNOSTIC_IDS,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._comparison_evidence import (
    R3_CAPACITY_EVIDENCE_SCHEMA_ID,
    R3_CAPACITY_EVIDENCE_SCHEMA_VERSION,
    CapacityEvidence,
    DiagnosticEvidence,
    EvidenceStatus,
    FoldExecutionEvidence,
    FoldOutcome,
    FoldReturnEvidence,
    ScalarEvidence,
    _canonical_text,
    _comparison_error,
    _evaluated,
    _execution_evidence,
    _merge_refs,
    _not_evaluated,
    _positive_ordinal,
    _project_metrics,
    _return_evidence,
    _validate_capacity_evidence,
)
from ditto_application.processes.experiments._factor_diagnostics_evidence import (
    FactorDiagnosticsArtifactEvidence,
)
from ditto_application.processes.experiments._oos_fold_registration import (
    OOSFoldRegistration,
)
from ditto_application.processes.experiments._persisted_execution_evidence import (
    PersistedFoldExecutionEvidence,
    _validate_persisted_fold_execution,
    load_persisted_fold_execution,
)
from ditto_application.processes.experiments._report_artifact_validation import (
    BacktestReportArtifactValidationError,
    validate_loaded_backtest_report_artifact,
)
from ditto_application.processes.experiments._report_evidence import (
    BacktestReportArtifactIdentity,
    BacktestReportEvidence,
    LoadedBacktestReportArtifact,
    backtest_report_content_hash,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselineExecutionPlan,
    BaselinePlanKind,
    BaselinePlanRequest,
    default_baseline_registry,
)

_AttemptId = _analysis_experiments.AttemptId
_BacktestRunId = _analysis_experiments.BacktestRunId
_CandidateId = _analysis_experiments.CandidateId
_ContentHash = _analysis_experiments.ContentHash
_DateWindow = _analysis_experiments.DateWindow
_ExperimentId = _analysis_experiments.ExperimentId
_FoldId = _analysis_experiments.FoldId
_R3_COMPARISON_METRIC_IDS = _analysis_experiments.R3_COMPARISON_METRIC_IDS
_R3_DIAGNOSTIC_METRIC_IDS = _analysis_experiments.R3_DIAGNOSTIC_METRIC_IDS
_R3_RESEARCH_METRIC_SCHEMA = _analysis_experiments.R3_RESEARCH_METRIC_SCHEMA
_ResearchMetricId = _analysis_experiments.ResearchMetricId
_ResearchMetricSchema = _analysis_experiments.ResearchMetricSchema
_SnapshotId = _analysis_experiments.SnapshotId
_canonical_payload = _analysis_experiments.canonical_payload

__all__ = [
    "R3_CAPACITY_EVIDENCE_SCHEMA_ID",
    "R3_CAPACITY_EVIDENCE_SCHEMA_VERSION",
    "R3_COMPARISON_ARTIFACT_SCHEMA_ID",
    "R3_COMPARISON_ARTIFACT_SCHEMA_VERSION",
    "BaselineComparisonIdentity",
    "CandidateComparisonProjection",
    "CandidateFoldEvidence",
    "CapacityEvidence",
    "DiagnosticEvidence",
    "EvidenceStatus",
    "FactorDiagnosticsArtifactEvidence",
    "FoldComparison",
    "FoldExecutionEvidence",
    "FoldOutcome",
    "FoldReturnEvidence",
    "OOSFoldRegistration",
    "PersistedFoldExecutionEvidence",
    "ScalarEvidence",
    "backtest_report_content_hash",
    "build_candidate_comparison",
    "load_persisted_fold_execution",
]

_REQUIRED_OOS_FOLDS = 2
R3_COMPARISON_ARTIFACT_SCHEMA_ID = "ditto.r3.candidate-comparison"
R3_COMPARISON_ARTIFACT_SCHEMA_VERSION = 1
_COMPARISON_FACTORY_TOKEN = object()


@dataclass(frozen=True, slots=True)
class BaselineComparisonIdentity:
    """Registered baseline and the exact two OOS windows it must execute."""

    experiment_id: _ExperimentId
    candidate_id: _CandidateId
    plan: BaselineExecutionPlan
    oos_folds: tuple[OOSFoldRegistration, ...]

    def __post_init__(self) -> None:
        """Validate the exact built-in plan and nonoverlapping OOS protocol."""
        if (
            type(self.experiment_id) is not _ExperimentId
            or type(self.candidate_id) is not _CandidateId
        ):
            _comparison_error("invalid_baseline_identity")
        if type(self.plan) is not BaselineExecutionPlan:
            _comparison_error("invalid_baseline_plan")
        if self.plan.kind not in {
            BaselinePlanKind.STOCK_UNIVERSE_EQUAL_WEIGHT,
            BaselinePlanKind.ETF_CURRENT_ACTIVE,
        }:
            _comparison_error("unsupported_r3_baseline_identity")
        try:
            expected = default_baseline_registry().plan(
                BaselinePlanRequest(
                    self.plan.baseline_ref,
                    self.plan.snapshot,
                    self.plan.universe,
                    self.plan.exact_strategy,
                )
            )
        except AppProcessError:
            _comparison_error("baseline_plan_identity_drift")
        if expected.canonical_hash != self.plan.canonical_hash:
            _comparison_error("baseline_plan_identity_drift")
        folds = tuple(self.oos_folds)
        if len(folds) != _REQUIRED_OOS_FOLDS or any(
            type(item) is not OOSFoldRegistration for item in folds
        ):
            _comparison_error("invalid_oos_fold_windows")
        ordinals = tuple(item.fold_ordinal for item in folds)
        if (
            any(ordinal <= 0 for ordinal in ordinals)
            or ordinals != tuple(sorted(set(ordinals)))
            or len({item.fold_id for item in folds}) != _REQUIRED_OOS_FOLDS
            or folds[0].test_window.end >= folds[1].test_window.start
        ):
            _comparison_error("invalid_oos_fold_windows")
        object.__setattr__(self, "oos_folds", folds)

    def canonical_payload(self) -> dict[str, object]:
        """Return the exact baseline plan and OOS registration payload."""
        return {
            "candidate_id": str(self.candidate_id),
            "experiment_id": str(self.experiment_id),
            "oos_folds": [item.canonical_payload() for item in self.oos_folds],
            "plan": self.plan.canonical_payload(),
            "plan_hash": self.plan.canonical_hash,
        }


@dataclass(frozen=True, slots=True)
class CandidateFoldEvidence:
    """Complete execution, input, result, and artifact identity for one fold."""

    execution_binding: PersistedFoldExecutionEvidence
    candidate_ordinal: int
    snapshot_id: _SnapshotId
    snapshot_hash: _ContentHash
    parameter_hash: _ContentHash
    resolved_spec_hash: _ContentHash
    report_artifact: LoadedBacktestReportArtifact | None = None
    factor_diagnostics: FactorDiagnosticsArtifactEvidence | None = None
    capacity: CapacityEvidence | None = None
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        """Fail closed on partial identity, report drift, or diagnostic drift."""
        _validate_persisted_fold_execution(self.execution_binding)
        typed = (
            (self.snapshot_id, _SnapshotId),
            (self.snapshot_hash, _ContentHash),
            (self.parameter_hash, _ContentHash),
            (self.resolved_spec_hash, _ContentHash),
        )
        if any(type(value) is not expected for value, expected in typed):
            _comparison_error("invalid_fold_evidence_identity")
        _positive_ordinal(self.candidate_ordinal, "candidate_ordinal")
        self._validate_outcome()
        self._validate_report_artifact()
        self._validate_diagnostics()
        _validate_capacity_evidence(self)

    @property
    def experiment_id(self) -> _ExperimentId:
        """Return the persisted experiment identity."""
        return self.execution_binding.experiment_id

    @property
    def candidate_id(self) -> _CandidateId:
        """Return the persisted candidate identity."""
        return self.execution_binding.candidate_id

    @property
    def fold_id(self) -> _FoldId:
        """Return the persisted fold identity."""
        return self.execution_binding.fold_id

    @property
    def fold_ordinal(self) -> int:
        """Return the persisted fold ordinal."""
        return self.execution_binding.fold_ordinal

    @property
    def attempt_id(self) -> _AttemptId:
        """Return the persisted attempt identity."""
        return self.execution_binding.attempt_id

    @property
    def run_id(self) -> _BacktestRunId:
        """Return the persisted backtest run identity."""
        return self.execution_binding.run_id

    @property
    def test_window(self) -> _DateWindow:
        """Return the persisted exact test window."""
        return self.execution_binding.test_window

    @property
    def reproduction_fingerprint(self) -> _ContentHash:
        """Return the persisted reproduction fingerprint."""
        return self.execution_binding.reproduction_fingerprint

    @property
    def backtest_report(self) -> BacktestReportEvidence | None:
        """Return only the verified report projection."""
        artifact = self.report_artifact
        return None if artifact is None else artifact.evidence

    @property
    def report_artifact_id(self) -> str | None:
        """Return the verified immutable index identity when present."""
        artifact = self.report_artifact
        return None if artifact is None else artifact.record.artifact_id

    @property
    def result_ref(self) -> str | None:
        """Derive result lineage from the verified immutable index fact."""
        artifact = self.report_artifact
        return None if artifact is None else artifact.record.relative_path

    @property
    def result_hash(self) -> _ContentHash | None:
        """Derive result content identity from the verified index fact."""
        artifact = self.report_artifact
        return None if artifact is None else artifact.record.content_hash

    @property
    def artifact_ref(self) -> str | None:
        """Return the same verified report path for Schema-v1 compatibility."""
        return self.result_ref

    @property
    def artifact_hash(self) -> _ContentHash | None:
        """Return the same verified report hash for Schema-v1 compatibility."""
        return self.result_hash

    @property
    def outcome(self) -> FoldOutcome:
        """Return the persisted terminal fold outcome."""
        return self.execution_binding.outcome

    def _validate_outcome(self) -> None:
        if self.outcome is FoldOutcome.FAILED:
            if self.failure_reason is None:
                _comparison_error("failed_fold_reason_required")
            _canonical_text(self.failure_reason, "failure_reason")
        elif self.failure_reason is not None:
            _comparison_error("completed_fold_cannot_have_failure_reason")

    def _validate_report_artifact(self) -> None:
        artifact = self.report_artifact
        if artifact is None:
            return
        identity = BacktestReportArtifactIdentity(
            experiment_id=self.experiment_id,
            candidate_id=self.candidate_id,
            fold_id=self.fold_id,
            attempt_id=self.attempt_id,
            attempt_created_at=self.execution_binding.attempt_view.spec.created_at,
            run_id=self.run_id,
            test_window=self.test_window,
            reproduction_fingerprint=self.reproduction_fingerprint,
        )
        try:
            validate_loaded_backtest_report_artifact(artifact, identity)
        except BacktestReportArtifactValidationError as error:
            _comparison_error(error.reason)

    def _validate_diagnostics(self) -> None:
        projection = self.factor_diagnostics
        if projection is None:
            return
        if type(projection) is not FactorDiagnosticsArtifactEvidence:
            _comparison_error("invalid_factor_diagnostics")
        expected = (
            self.experiment_id,
            self.candidate_id,
            self.fold_id,
            self.snapshot_id,
            self.snapshot_hash,
            self.test_window,
        )
        actual = (
            projection.experiment_id,
            projection.candidate_id,
            projection.fold_id,
            projection.snapshot_id,
            projection.snapshot_hash,
            projection.test_window,
        )
        if actual != expected:
            _comparison_error("factor_diagnostic_identity_drift")

    def canonical_payload(self) -> dict[str, object]:
        """Return complete source, artifact, and persisted execution lineage."""
        diagnostics = self.factor_diagnostics
        diagnostic_payload: dict[str, object] | None = None
        if diagnostics is not None:
            diagnostic_payload = {
                "artifact_hash": str(diagnostics.artifact_hash),
                "envelope": diagnostics.canonical_payload(),
            }
        report = self.backtest_report
        artifact_hash = self.artifact_hash
        result_hash = self.result_hash
        return {
            "artifact_hash": (None if artifact_hash is None else str(artifact_hash)),
            "artifact_ref": self.artifact_ref,
            "attempt_id": str(self.attempt_id),
            "backtest_report_identity": (
                None
                if report is None
                else {"period": list(report.period), "run_id": report.run_id}
            ),
            "candidate_id": str(self.candidate_id),
            "candidate_ordinal": self.candidate_ordinal,
            "capacity": (
                None
                if self.capacity is None
                else {
                    "content_hash": str(self.capacity.content_hash),
                    "envelope": self.capacity.canonical_payload(),
                }
            ),
            "experiment_id": str(self.experiment_id),
            "factor_diagnostics": diagnostic_payload,
            "failure_reason": self.failure_reason,
            "fold_id": str(self.fold_id),
            "fold_ordinal": self.fold_ordinal,
            "outcome": self.outcome.value,
            "parameter_hash": str(self.parameter_hash),
            "persisted_execution": {
                "content_hash": str(self.execution_binding.content_hash),
                "envelope": self.execution_binding.canonical_payload(),
            },
            "reproduction_fingerprint": str(self.reproduction_fingerprint),
            "result_hash": None if result_hash is None else str(result_hash),
            "result_ref": self.result_ref,
            "resolved_spec_hash": str(self.resolved_spec_hash),
            "run_id": str(self.run_id),
            "snapshot_hash": str(self.snapshot_hash),
            "snapshot_id": str(self.snapshot_id),
            "test_window": {
                "end": self.test_window.end.isoformat(),
                "start": self.test_window.start.isoformat(),
            },
        }


@dataclass(frozen=True, slots=True)
class FoldComparison:
    """Fixed-schema projection for one exact candidate/fold execution."""

    source: CandidateFoldEvidence
    is_baseline: bool
    metrics: Mapping[_ResearchMetricId, ScalarEvidence]
    factor_diagnostics: Mapping[_ResearchMetricId, DiagnosticEvidence]
    return_evidence: FoldReturnEvidence | None
    execution_evidence: FoldExecutionEvidence | None

    def __post_init__(self) -> None:
        """Freeze mappings and reject metric-schema drift."""
        if type(self.source) is not CandidateFoldEvidence:
            _comparison_error("invalid_fold_comparison")
        metrics = dict(self.metrics)
        if tuple(metrics) != _R3_COMPARISON_METRIC_IDS or any(
            type(item) is not ScalarEvidence
            or (
                item.metric_value is not None
                and item.metric_value.metric_id is not metric_id
            )
            for metric_id, item in metrics.items()
        ):
            _comparison_error("comparison_metric_schema_drift")
        diagnostics = dict(self.factor_diagnostics)
        if tuple(diagnostics) != _R3_DIAGNOSTIC_METRIC_IDS or any(
            type(item) is not DiagnosticEvidence for item in diagnostics.values()
        ):
            _comparison_error("factor_diagnostic_schema_drift")
        if (
            self.return_evidence is not None
            and type(self.return_evidence) is not FoldReturnEvidence
        ):
            _comparison_error("invalid_fold_return_evidence")
        if (
            self.execution_evidence is not None
            and type(self.execution_evidence) is not FoldExecutionEvidence
        ):
            _comparison_error("invalid_fold_execution_evidence")
        object.__setattr__(self, "metrics", MappingProxyType(metrics))
        object.__setattr__(self, "factor_diagnostics", MappingProxyType(diagnostics))

    @property
    def candidate_id(self) -> _CandidateId:
        """Return this row's candidate identity."""
        return self.source.candidate_id

    @property
    def candidate_ordinal(self) -> int:
        """Return this row's canonical candidate ordinal."""
        return self.source.candidate_ordinal

    @property
    def fold_id(self) -> _FoldId:
        """Return this row's persisted fold identity."""
        return self.source.fold_id

    @property
    def fold_ordinal(self) -> int:
        """Return this row's persisted fold ordinal."""
        return self.source.fold_ordinal

    @property
    def outcome(self) -> FoldOutcome:
        """Return this row's persisted terminal outcome."""
        return self.source.outcome

    @property
    def failure_reason(self) -> str | None:
        """Return the explicit failure reason when the fold failed."""
        return self.source.failure_reason

    def canonical_payload(self) -> dict[str, object]:
        """Return the deterministic projected fold evidence payload."""
        return {
            "execution_evidence": (
                None
                if self.execution_evidence is None
                else self.execution_evidence.canonical_payload()
            ),
            "factor_diagnostics": [
                {
                    "evidence": self.factor_diagnostics[metric_id].canonical_payload(),
                    "metric_id": metric_id.value,
                }
                for metric_id in _R3_DIAGNOSTIC_METRIC_IDS
            ],
            "is_baseline": self.is_baseline,
            "metrics": [
                {
                    "evidence": self.metrics[metric_id].canonical_payload(),
                    "metric_id": metric_id.value,
                }
                for metric_id in _R3_COMPARISON_METRIC_IDS
            ],
            "return_evidence": (
                None
                if self.return_evidence is None
                else self.return_evidence.canonical_payload()
            ),
            "source": self.source.canonical_payload(),
        }


@dataclass(frozen=True, slots=True)
class CandidateComparisonProjection:
    """Exact protocol, versioned schema, and stable candidate/fold rows."""

    baseline: BaselineComparisonIdentity
    metric_schema: _ResearchMetricSchema
    folds: tuple[FoldComparison, ...]
    _factory_token: InitVar[object | None] = None

    def __post_init__(self, _factory_token: object | None) -> None:
        """Require exact schema singleton and immutable comparison rows."""
        if _factory_token is not _COMPARISON_FACTORY_TOKEN:
            _comparison_error("comparison_factory_required")
        if type(self.baseline) is not BaselineComparisonIdentity:
            _comparison_error("invalid_baseline_identity")
        if self.metric_schema is not _R3_RESEARCH_METRIC_SCHEMA:
            _comparison_error("comparison_metric_schema_drift")
        rows = tuple(self.folds)
        if not rows or any(type(row) is not FoldComparison for row in rows):
            _comparison_error("invalid_fold_comparison")
        sources = tuple(row.source for row in rows)
        _validate_evidence(sources, self.baseline)
        expected_order = tuple(
            sorted(
                rows,
                key=lambda item: (
                    item.fold_ordinal,
                    item.candidate_ordinal,
                    str(item.fold_id),
                    str(item.candidate_id),
                ),
            )
        )
        if rows != expected_order or any(
            row.is_baseline is not (row.candidate_id == self.baseline.candidate_id)
            for row in rows
        ):
            _comparison_error("noncanonical_fold_comparison")
        object.__setattr__(self, "folds", rows)

    def canonical_payload(self) -> dict[str, object]:
        """Return the complete versioned comparison artifact payload."""
        return {
            "artifact_schema": {
                "id": R3_COMPARISON_ARTIFACT_SCHEMA_ID,
                "version": R3_COMPARISON_ARTIFACT_SCHEMA_VERSION,
            },
            "baseline": self.baseline.canonical_payload(),
            "folds": [item.canonical_payload() for item in self.folds],
            "metric_schema": self.metric_schema.canonical_payload(),
        }

    @property
    def content_hash(self) -> _ContentHash:
        """Return the authoritative comparison artifact content hash."""
        return _canonical_payload(self.canonical_payload()).content_hash


def _project_diagnostics(
    value: CandidateFoldEvidence,
) -> dict[_ResearchMetricId, DiagnosticEvidence]:
    reason = (
        "candidate_failed"
        if value.outcome is FoldOutcome.FAILED
        else "factor_diagnostics_missing"
    )
    projection = value.factor_diagnostics
    if projection is None or value.outcome is FoldOutcome.FAILED:
        return {
            metric_id: DiagnosticEvidence(EvidenceStatus.NOT_EVALUATED, None, reason)
            for metric_id in _R3_DIAGNOSTIC_METRIC_IDS
        }
    feature_projection = projection.projection
    computed = set(feature_projection.computed_metrics)
    return {
        metric_id: (
            DiagnosticEvidence(
                EvidenceStatus.EVALUATED,
                feature_projection.values[metric_id.value],
                None,
                (projection.artifact_ref,),
                (projection.artifact_hash,),
            )
            if metric_id.value in computed
            else DiagnosticEvidence(
                EvidenceStatus.NOT_EVALUATED,
                None,
                "factor_diagnostic_not_computed",
            )
        )
        for metric_id in _R3_DIAGNOSTIC_METRIC_IDS
    }


def _initial_row(
    value: CandidateFoldEvidence,
    baseline: BaselineComparisonIdentity,
) -> FoldComparison:
    returns = (
        _return_evidence(value) if value.outcome is FoldOutcome.COMPLETED else None
    )
    execution = _execution_evidence(value, returns)
    return FoldComparison(
        source=value,
        is_baseline=value.candidate_id == baseline.candidate_id,
        metrics=_project_metrics(value, returns, execution),
        factor_diagnostics=_project_diagnostics(value),
        return_evidence=returns,
        execution_evidence=execution,
    )


def _merge_scalar_evidence(
    *items: ScalarEvidence,
) -> tuple[tuple[str, ...], tuple[_ContentHash, ...]]:
    return _merge_refs(items)


def _relative_metric(
    row: FoldComparison,
    baseline: FoldComparison | None,
) -> ScalarEvidence:
    candidate = row.metrics[_ResearchMetricId.NET_RETURN]
    if candidate.status is EvidenceStatus.NOT_EVALUATED:
        return _not_evaluated("candidate_net_return_not_evaluated")
    if baseline is None:
        return _not_evaluated("baseline_fold_evidence_missing")
    baseline_value = baseline.metrics[_ResearchMetricId.NET_RETURN]
    if baseline_value.status is EvidenceStatus.NOT_EVALUATED:
        return _not_evaluated("baseline_net_return_not_evaluated")
    refs, hashes = _merge_scalar_evidence(candidate, baseline_value)
    value = (
        0.0
        if row.is_baseline
        else cast("float", candidate.value) - cast("float", baseline_value.value)
    )
    return _evaluated(_ResearchMetricId.RELATIVE_NET_RETURN, value, refs, hashes)


def _diagnostic_core_identity(
    value: CandidateFoldEvidence,
) -> tuple[object, ...] | None:
    projection = value.factor_diagnostics
    if projection is None:
        return None
    source = projection.projection.provenance
    return (
        source.factor_id,
        source.factor_version,
        source.dataset_id,
        source.catalog_snapshot_id,
        source.universe,
        source.cost_bps,
    )


def _validate_evidence(  # noqa: C901, PLR0912, PLR0915 - fail-closed identity fence
    values: tuple[CandidateFoldEvidence, ...],
    baseline: BaselineComparisonIdentity,
) -> None:
    registrations = {
        (item.fold_id, item.fold_ordinal, item.test_window)
        for item in baseline.oos_folds
    }
    expected_snapshot = (
        _SnapshotId(baseline.plan.snapshot.snapshot_id),
        _ContentHash(baseline.plan.snapshot.manifest_hash),
    )
    keys: set[tuple[_CandidateId, _FoldId]] = set()
    candidate_ordinals: dict[_CandidateId, int] = {}
    candidate_specs: dict[_CandidateId, tuple[_ContentHash, _ContentHash]] = {}
    ordinal_candidates: dict[int, _CandidateId] = {}
    attempts: set[_AttemptId] = set()
    runs: set[_BacktestRunId] = set()
    artifact_ids: set[str] = set()
    artifact_refs: set[str] = set()
    diagnostic_identity: tuple[object, ...] | None = None
    for value in values:
        _validate_persisted_fold_execution(value.execution_binding)
        value._validate_report_artifact()
        if value.experiment_id != baseline.experiment_id:
            _comparison_error("experiment_identity_drift")
        if (value.snapshot_id, value.snapshot_hash) != expected_snapshot:
            _comparison_error("snapshot_identity_drift")
        if (value.fold_id, value.fold_ordinal, value.test_window) not in registrations:
            _comparison_error("fold_window_drift")
        key = (value.candidate_id, value.fold_id)
        if key in keys:
            _comparison_error("duplicate_candidate_fold_evidence")
        keys.add(key)
        existing = candidate_ordinals.setdefault(
            value.candidate_id, value.candidate_ordinal
        )
        if existing != value.candidate_ordinal:
            _comparison_error("candidate_ordinal_drift")
        spec_identity = (value.parameter_hash, value.resolved_spec_hash)
        existing_spec = candidate_specs.setdefault(value.candidate_id, spec_identity)
        if existing_spec != spec_identity:
            _comparison_error("candidate_spec_identity_drift")
        ordinal_candidate = ordinal_candidates.setdefault(
            value.candidate_ordinal, value.candidate_id
        )
        if ordinal_candidate != value.candidate_id:
            _comparison_error("duplicate_candidate_ordinal")
        if value.attempt_id in attempts:
            _comparison_error("duplicate_attempt_evidence")
        attempts.add(value.attempt_id)
        if value.run_id in runs:
            _comparison_error("duplicate_run_evidence")
        runs.add(value.run_id)
        artifact_id = value.report_artifact_id
        artifact_ref = value.artifact_ref
        if artifact_id is not None and artifact_ref is not None:
            if artifact_id in artifact_ids:
                _comparison_error("duplicate_artifact_id")
            artifact_ids.add(artifact_id)
            if artifact_ref in artifact_refs:
                _comparison_error("duplicate_artifact_ref")
            artifact_refs.add(artifact_ref)
        current_diagnostic = _diagnostic_core_identity(value)
        if current_diagnostic is not None:
            if diagnostic_identity is None:
                diagnostic_identity = current_diagnostic
            elif diagnostic_identity != current_diagnostic:
                _comparison_error("factor_diagnostic_identity_drift")
    if candidate_ordinals.get(baseline.candidate_id) != 1:
        _comparison_error("baseline_candidate_must_be_first")
    baseline_folds = {
        (value.fold_id, value.fold_ordinal, value.test_window)
        for value in values
        if value.candidate_id == baseline.candidate_id
    }
    if baseline_folds != registrations:
        _comparison_error("baseline_two_fold_evidence_required")


def build_candidate_comparison(
    baseline: BaselineComparisonIdentity,
    evidence: Iterable[CandidateFoldEvidence],
) -> CandidateComparisonProjection:
    """Build a canonical comparison without trusting aggregate report metrics."""
    if type(baseline) is not BaselineComparisonIdentity:
        _comparison_error("invalid_baseline_identity")
    if tuple(_FEATURE_DIAGNOSTIC_IDS) != tuple(
        metric_id.value for metric_id in _R3_DIAGNOSTIC_METRIC_IDS
    ):
        _comparison_error("factor_diagnostic_schema_drift")
    if isinstance(evidence, (str, bytes, bytearray, Mapping, set, frozenset)):
        _comparison_error("invalid_fold_evidence_sequence")
    try:
        values = tuple(evidence)
    except TypeError:
        _comparison_error("invalid_fold_evidence_sequence")
    if not values or any(type(value) is not CandidateFoldEvidence for value in values):
        _comparison_error("invalid_fold_evidence_sequence")
    _validate_evidence(values, baseline)
    ordered = tuple(
        sorted(
            values,
            key=lambda item: (
                item.fold_ordinal,
                item.candidate_ordinal,
                str(item.fold_id),
                str(item.candidate_id),
            ),
        )
    )
    initial = tuple(_initial_row(value, baseline) for value in ordered)
    baseline_by_fold = {row.fold_id: row for row in initial if row.is_baseline}
    projected: list[FoldComparison] = []
    for row in initial:
        metrics = dict(row.metrics)
        metrics[_ResearchMetricId.RELATIVE_NET_RETURN] = _relative_metric(
            row,
            baseline_by_fold.get(row.fold_id),
        )
        projected.append(replace(row, metrics=metrics))
    return CandidateComparisonProjection(
        baseline,
        _R3_RESEARCH_METRIC_SCHEMA,
        tuple(projected),
        _COMPARISON_FACTORY_TOKEN,
    )
