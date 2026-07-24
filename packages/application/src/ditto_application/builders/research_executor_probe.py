"""Build-only adapter for R3 research executor availability probes."""

from __future__ import annotations

from ditto_strategy.models import StrategySpecRecord

from ditto_application.builders.published_baseline_runtime_builder import (
    PublishedBaselineRuntimeBuilder,
)
from ditto_application.builders.research_runtime_builder import (
    ResearchRuntimeBuilder,
    ResearchSnapshotIdentity,
    ResearchStrategyRuntime,
)
from ditto_application.exceptions import AppBuilderError, AppProcessError
from ditto_application.processes.execution.factor_bridge import (
    compiled_expressions_actual_max_lookback,
    compiled_expressions_execution_hash,
)
from ditto_application.processes.experiments._execution_resolution_evidence import (
    ExactStrategyVersionReader,
)
from ditto_application.processes.experiments.baseline_planning import (
    resolve_planning_baseline,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselineRegistry,
    default_baseline_registry,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactStrategyIdentity,
    ResearchAssetLane,
)
from ditto_application.processes.experiments.planning import BinderCandidatePlan
from ditto_application.processes.experiments.planning_probes import (
    BaselineRuntimeExecutorEvidence,
    CandidateExecutorEvidence,
    ResearchExecutorProbeRequest,
    ResearchExecutorProbeResult,
)
from ditto_application.research_validation_contracts import RuntimeValidationEvidence

__all__ = ["BuilderBackedResearchExecutorProbe"]


def _candidate_evidence(
    runtimes: list[tuple[BinderCandidatePlan, ResearchStrategyRuntime]],
) -> tuple[CandidateExecutorEvidence, ...]:
    return tuple(
        CandidateExecutorEvidence(
            candidate_hash=candidate.candidate_hash,
            resolved_spec_hash=runtime.resolved_spec_hash,
            parameter_hash=runtime.parameter_hash,
            pipeline_execution_hash=runtime.pipeline_execution_hash,
            compiled_factor_set_hash=compiled_expressions_execution_hash(
                runtime.compiled_expressions
            ),
        )
        for candidate, runtime in runtimes
    )


def _baseline_runtime_evidence(
    runtime: ResearchStrategyRuntime,
) -> BaselineRuntimeExecutorEvidence:
    return BaselineRuntimeExecutorEvidence(
        base_spec_hash=runtime.base_spec_hash,
        resolved_spec_hash=runtime.resolved_spec_hash,
        parameter_hash=runtime.parameter_hash,
        pipeline_execution_hash=runtime.pipeline_execution_hash,
        compiled_factor_set_hash=compiled_expressions_execution_hash(
            runtime.compiled_expressions
        ),
        max_lookback_sessions=compiled_expressions_actual_max_lookback(
            runtime.compiled_expressions
        ),
        node_registry_manifest_hash=runtime.node_registry_manifest_hash,
        factor_registry_manifest_hash=runtime.factor_registry_manifest_hash,
        factor_binding_hashes=tuple(
            binding.binding_hash for binding in runtime.used_factor_bindings
        ),
    )


def _require_exact_baseline_record(
    reader: ExactStrategyVersionReader | None,
    identity: ExactStrategyIdentity,
) -> tuple[StrategySpecRecord, str]:
    if reader is None:
        raise AppProcessError(
            "exact baseline strategy reader is unavailable",
            details={
                "code": "EXECUTOR_UNAVAILABLE",
                "reason": "exact_baseline_strategy_reader_unavailable",
            },
        )
    record = reader.get_spec(identity.strategy_id, identity.version)
    if (
        type(record) is not StrategySpecRecord
        or record.strategy_id != identity.strategy_id
        or record.version != identity.version
    ):
        raise AppProcessError(
            "exact baseline strategy version is unavailable",
            details={
                "code": "EXECUTOR_UNAVAILABLE",
                "reason": "exact_baseline_strategy_version_missing",
            },
        )
    version_status = reader.get_version_state(identity.strategy_id, identity.version)
    if version_status is None:
        raise AppProcessError(
            "exact baseline strategy version state is unavailable",
            details={
                "code": "EXECUTOR_UNAVAILABLE",
                "reason": "exact_baseline_strategy_version_state_missing",
            },
        )
    return record, version_status


def _require_baseline_runtime_identity(
    runtime: ResearchStrategyRuntime,
    *,
    exact: ExactStrategyIdentity,
    expected_lane: str,
    expected_universe: str,
    expected_datasets: tuple[str, ...],
) -> BaselineRuntimeExecutorEvidence:
    try:
        evidence = _baseline_runtime_evidence(runtime)
        actual_strategy_id = runtime.strategy_id
        actual_strategy_version = runtime.strategy_version
        actual_lane = runtime.resolved_spec.strategy_kind.value
        actual_universe = runtime.legacy_spec.universe
        actual_datasets = tuple(sorted(runtime.legacy_spec.required_datasets))
    except (AttributeError, TypeError, ValueError, AppProcessError) as exc:
        raise AppProcessError(
            "exact baseline runtime identity is invalid",
            details={
                "code": "REPRODUCIBILITY_FAILED",
                "reason": "baseline_runtime_identity_invalid",
            },
        ) from exc
    if (
        actual_strategy_id != exact.strategy_id
        or actual_strategy_version != exact.version
        or evidence.base_spec_hash != exact.spec_hash
        or actual_lane != expected_lane
        or actual_universe != expected_universe
        or actual_datasets != expected_datasets
    ):
        raise AppProcessError(
            "exact baseline runtime drifted from its frozen strategy",
            details={
                "code": "REPRODUCIBILITY_FAILED",
                "reason": "baseline_runtime_identity_drift",
            },
        )
    return evidence


def _build_exact_baseline_runtime(
    *,
    builder: PublishedBaselineRuntimeBuilder | None,
    reader: ExactStrategyVersionReader | None,
    exact: ExactStrategyIdentity,
    request: ResearchExecutorProbeRequest,
    expected_lane: str,
    expected_universe: str,
    expected_datasets: tuple[str, ...],
) -> BaselineRuntimeExecutorEvidence:
    if builder is None:
        raise AppProcessError(
            "exact published baseline runtime builder is unavailable",
            details={
                "code": "EXECUTOR_UNAVAILABLE",
                "reason": "published_baseline_runtime_builder_unavailable",
            },
        )
    record, version_status = _require_exact_baseline_record(reader, exact)
    runtime = builder.build(
        record=record,
        candidate_parameters=(),
        snapshot_identity=ResearchSnapshotIdentity(
            request.snapshot_identity.snapshot_id,
            request.snapshot_identity.manifest_hash,
        ),
        version_status=version_status,
    )
    return _require_baseline_runtime_identity(
        runtime,
        exact=exact,
        expected_lane=expected_lane,
        expected_universe=expected_universe,
        expected_datasets=expected_datasets,
    )


class BuilderBackedResearchExecutorProbe:
    """Probe binder runtimes and one constrained baseline registration."""

    def __init__(
        self,
        builder: ResearchRuntimeBuilder,
        baseline_registry: BaselineRegistry | None = None,
        *,
        published_baseline_builder: PublishedBaselineRuntimeBuilder | None = None,
        strategy_reader: ExactStrategyVersionReader | None = None,
    ) -> None:
        self._builder = builder
        self._published_baseline_builder = published_baseline_builder
        self._baseline_registry = baseline_registry or default_baseline_registry()
        self._strategy_reader = strategy_reader

    def _require_version_status(self, record: StrategySpecRecord) -> str:
        """Resolve the governance version state for a candidate record."""
        if self._strategy_reader is None:
            raise AppProcessError(
                "strategy version state reader is unavailable",
                details={
                    "code": "EXECUTOR_UNAVAILABLE",
                    "reason": "strategy_version_state_reader_unavailable",
                },
            )
        version_status = self._strategy_reader.get_version_state(
            record.strategy_id, record.version
        )
        if version_status is None:
            raise AppProcessError(
                "strategy version state is unavailable",
                details={
                    "code": "EXECUTOR_UNAVAILABLE",
                    "reason": "strategy_version_state_missing",
                },
            )
        return version_status

    def probe(
        self,
        request: ResearchExecutorProbeRequest,
    ) -> ResearchExecutorProbeResult:
        """Return fail-closed evidence without touching persistence."""
        runtimes: list[tuple[BinderCandidatePlan, ResearchStrategyRuntime]] = []
        version_status = self._require_version_status(request.strategy_record)
        for candidate in request.candidates:
            try:
                runtimes.append(
                    (
                        candidate,
                        self._builder.build(
                            record=request.strategy_record,
                            candidate_parameters=candidate.binder_parameters,
                            snapshot_identity=ResearchSnapshotIdentity(
                                request.snapshot_identity.snapshot_id,
                                request.snapshot_identity.manifest_hash,
                            ),
                            version_status=version_status,
                        ),
                    )
                )
            except AppBuilderError as exc:
                reason = str(exc.details.get("reason", "runtime_build_failed"))
                unavailable = reason == "native_v2_executor_unavailable"
                return ResearchExecutorProbeResult(
                    available=False,
                    code=(
                        "EXECUTOR_UNAVAILABLE"
                        if unavailable
                        else str(exc.details.get("code", "SPEC_INVALID"))
                    ),
                    reason=reason,
                    remediation=(
                        "implement the native StrategySpec v2 executor"
                        if unavailable
                        else "fix the exact strategy version or candidate parameters"
                    ),
                    strategy_spec_hash=None,
                    node_registry_manifest_hash=None,
                    required_datasets=(),
                    candidates=(),
                )
        base_hashes = {runtime.base_spec_hash for _, runtime in runtimes}
        required_sets = {
            tuple(sorted(runtime.legacy_spec.required_datasets))
            for _, runtime in runtimes
        }
        registry_hashes = {
            runtime.node_registry_manifest_hash for _, runtime in runtimes
        }
        factor_registry_hashes = {
            runtime.factor_registry_manifest_hash for _, runtime in runtimes
        }
        factor_binding_hash_sets = {
            tuple(binding.binding_hash for binding in runtime.used_factor_bindings)
            for _, runtime in runtimes
        }
        lanes = {runtime.resolved_spec.strategy_kind.value for _, runtime in runtimes}
        universes = {runtime.legacy_spec.universe for _, runtime in runtimes}
        if (
            not runtimes
            or len(base_hashes) != 1
            or len(required_sets) != 1
            or len(registry_hashes) != 1
            or len(factor_registry_hashes) != 1
            or len(factor_binding_hash_sets) != 1
            or len(lanes) != 1
            or len(universes) != 1
        ):
            return ResearchExecutorProbeResult(
                available=False,
                code="REPRODUCIBILITY_FAILED",
                reason="candidate_runtime_identity_drift",
                remediation=(
                    "make candidate binding preserve one base spec and dataset set"
                ),
                strategy_spec_hash=None,
                node_registry_manifest_hash=None,
                required_datasets=(),
                candidates=(),
            )
        try:
            candidate_max_lookback = max(
                (
                    compiled_expressions_actual_max_lookback(
                        runtime.compiled_expressions
                    )
                    for _, runtime in runtimes
                ),
                default=0,
            )
            runtime_lane = next(iter(lanes))
            runtime_universe = next(iter(universes))
            runtime_required_datasets = next(iter(required_sets))
        except (AttributeError, TypeError, ValueError, AppProcessError):
            return ResearchExecutorProbeResult(
                available=False,
                code="REPRODUCIBILITY_FAILED",
                reason="candidate_runtime_validation_evidence_invalid",
                remediation=(
                    "register canonical runtime validation facts for every candidate"
                ),
                strategy_spec_hash=None,
                node_registry_manifest_hash=None,
                required_datasets=(),
                candidates=(),
            )
        try:
            baseline = resolve_planning_baseline(
                request.baseline,
                self._baseline_registry,
            )
        except AppProcessError as exc:
            return ResearchExecutorProbeResult(
                available=False,
                code=str(exc.details.get("code", "EXECUTOR_UNAVAILABLE")),
                reason=str(exc.details.get("reason", "baseline_executor_unavailable")),
                remediation="select one exact registered baseline descriptor",
                strategy_spec_hash=next(iter(base_hashes)),
                node_registry_manifest_hash=next(iter(registry_hashes)),
                required_datasets=tuple(sorted(next(iter(required_sets)))),
                candidates=_candidate_evidence(runtimes),
            )
        expected_lane = {
            "stock_selection": ResearchAssetLane.STOCK,
            "etf_rotation": ResearchAssetLane.ETF,
        }.get(runtime_lane)
        if (
            expected_lane is None
            or baseline.registration.descriptor.lane is not expected_lane
        ):
            return ResearchExecutorProbeResult(
                available=False,
                code="REPRODUCIBILITY_FAILED",
                reason="baseline_runtime_lane_mismatch",
                remediation=(
                    "select the registered baseline for the candidate strategy lane"
                ),
                strategy_spec_hash=next(iter(base_hashes)),
                node_registry_manifest_hash=next(iter(registry_hashes)),
                required_datasets=tuple(sorted(next(iter(required_sets)))),
                candidates=_candidate_evidence(runtimes),
            )
        baseline_runtime: BaselineRuntimeExecutorEvidence | None = None
        baseline_blocker: ResearchExecutorProbeResult | None = None
        if baseline.exact_strategy is not None:
            try:
                baseline_runtime = _build_exact_baseline_runtime(
                    builder=self._published_baseline_builder,
                    reader=self._strategy_reader,
                    exact=baseline.exact_strategy,
                    request=request,
                    expected_lane=runtime_lane,
                    expected_universe=runtime_universe,
                    expected_datasets=runtime_required_datasets,
                )
            except (AppBuilderError, AppProcessError) as exc:
                baseline_blocker = ResearchExecutorProbeResult(
                    available=False,
                    code=str(exc.details.get("code", "REPRODUCIBILITY_FAILED")),
                    reason=str(
                        exc.details.get("reason", "baseline_runtime_build_failed")
                    ),
                    remediation="restore the exact baseline strategy runtime",
                    strategy_spec_hash=next(iter(base_hashes)),
                    node_registry_manifest_hash=next(iter(registry_hashes)),
                    required_datasets=tuple(sorted(next(iter(required_sets)))),
                    candidates=_candidate_evidence(runtimes),
                    baseline_ref=baseline.ref.identity,
                    baseline_descriptor_hash=(
                        baseline.registration.descriptor.canonical_hash
                    ),
                    baseline_registry_manifest_hash=baseline.registry_manifest_hash,
                    baseline_exact_strategy_hash=(
                        baseline.exact_strategy.canonical_hash
                    ),
                    factor_registry_manifest_hash=next(iter(factor_registry_hashes)),
                    factor_binding_hashes=next(iter(factor_binding_hash_sets)),
                )
        if baseline_blocker is None:
            baseline_max_lookback = (
                0
                if baseline_runtime is None
                else baseline_runtime.max_lookback_sessions
            )
            runtime_validation = RuntimeValidationEvidence(
                lane=runtime_lane,
                universe_id=runtime_universe,
                required_datasets=runtime_required_datasets,
                max_lookback_sessions=max(
                    candidate_max_lookback,
                    baseline_max_lookback,
                ),
                requires_pit_universe=runtime_lane
                in {"stock_selection", "etf_rotation"},
            )
            baseline_blocker = ResearchExecutorProbeResult(
                available=True,
                code=None,
                reason=None,
                remediation=None,
                strategy_spec_hash=next(iter(base_hashes)),
                node_registry_manifest_hash=next(iter(registry_hashes)),
                required_datasets=tuple(sorted(next(iter(required_sets)))),
                candidates=_candidate_evidence(runtimes),
                runtime_validation_evidence=runtime_validation,
                baseline_ref=baseline.ref.identity,
                baseline_descriptor_hash=(
                    baseline.registration.descriptor.canonical_hash
                ),
                baseline_registry_manifest_hash=baseline.registry_manifest_hash,
                baseline_exact_strategy_hash=(
                    None
                    if baseline.exact_strategy is None
                    else baseline.exact_strategy.canonical_hash
                ),
                factor_registry_manifest_hash=next(iter(factor_registry_hashes)),
                factor_binding_hashes=next(iter(factor_binding_hash_sets)),
                baseline_runtime=baseline_runtime,
            )
        return baseline_blocker
