"""Build-only adapter for R3 research executor availability probes."""

from __future__ import annotations

from ditto_application.builders.research_runtime_builder import (
    ResearchRuntimeBuilder,
    ResearchSnapshotIdentity,
    ResearchStrategyRuntime,
)
from ditto_application.exceptions import AppBuilderError, AppProcessError
from ditto_application.processes.experiments.planning import BinderCandidatePlan
from ditto_application.processes.experiments.planning_probes import (
    CandidateExecutorEvidence,
    ResearchExecutorProbeRequest,
    ResearchExecutorProbeResult,
)
from ditto_application.research_validation_contracts import RuntimeValidationEvidence

__all__ = ["BuilderBackedResearchExecutorProbe"]


class BuilderBackedResearchExecutorProbe:
    """Probe binder runtimes and fail closed until a baseline runner is wired."""

    def __init__(self, builder: ResearchRuntimeBuilder) -> None:
        self._builder = builder

    def probe(
        self,
        request: ResearchExecutorProbeRequest,
    ) -> ResearchExecutorProbeResult:
        """Return fail-closed evidence without touching persistence."""
        runtimes: list[tuple[BinderCandidatePlan, ResearchStrategyRuntime]] = []
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
                        ),
                    )
                )
            except AppBuilderError as exc:
                reason = str(exc.details.get("reason", "runtime_build_failed"))
                unavailable = reason == "native_v2_executor_unavailable"
                return ResearchExecutorProbeResult(
                    False,
                    "EXECUTOR_UNAVAILABLE"
                    if unavailable
                    else str(exc.details.get("code", "SPEC_INVALID")),
                    reason,
                    (
                        "implement the native StrategySpec v2 executor"
                        if unavailable
                        else "fix the exact strategy version or candidate parameters"
                    ),
                    None,
                    None,
                    (),
                    (),
                )
        base_hashes = {runtime.base_spec_hash for _, runtime in runtimes}
        required_sets = {
            tuple(sorted(runtime.legacy_spec.required_datasets))
            for _, runtime in runtimes
        }
        registry_hashes = {
            runtime.node_registry_manifest_hash for _, runtime in runtimes
        }
        lanes = {runtime.resolved_spec.strategy_kind.value for _, runtime in runtimes}
        universes = {runtime.legacy_spec.universe for _, runtime in runtimes}
        if (
            not runtimes
            or len(base_hashes) != 1
            or len(required_sets) != 1
            or len(registry_hashes) != 1
            or len(lanes) != 1
            or len(universes) != 1
        ):
            return ResearchExecutorProbeResult(
                False,
                "REPRODUCIBILITY_FAILED",
                "candidate_runtime_identity_drift",
                "make candidate binding preserve one base spec and dataset set",
                None,
                None,
                (),
                (),
            )
        try:
            max_lookback = max(
                (
                    expression.analysis.lookback
                    for _, runtime in runtimes
                    if runtime.compiled_expressions is not None
                    for expression in runtime.compiled_expressions.expressions
                ),
                default=0,
            )
            runtime_validation = RuntimeValidationEvidence(
                lane=next(iter(lanes)),
                universe_id=next(iter(universes)),
                required_datasets=next(iter(required_sets)),
                max_lookback_sessions=max_lookback,
                requires_pit_universe=next(iter(lanes))
                in {"stock_selection", "etf_rotation"},
            )
        except (AttributeError, TypeError, ValueError, AppProcessError):
            return ResearchExecutorProbeResult(
                False,
                "REPRODUCIBILITY_FAILED",
                "candidate_runtime_validation_evidence_invalid",
                "register canonical runtime validation facts for every candidate",
                None,
                None,
                (),
                (),
            )
        return ResearchExecutorProbeResult(
            False,
            "EXECUTOR_UNAVAILABLE",
            "baseline_executor_unavailable",
            "register a typed baseline runner before launch",
            next(iter(base_hashes)),
            next(iter(registry_hashes)),
            tuple(sorted(next(iter(required_sets)))),
            tuple(
                CandidateExecutorEvidence(
                    candidate_hash=candidate.candidate_hash,
                    resolved_spec_hash=runtime.resolved_spec_hash,
                    parameter_hash=runtime.parameter_hash,
                )
                for candidate, runtime in runtimes
            ),
            runtime_validation,
        )
