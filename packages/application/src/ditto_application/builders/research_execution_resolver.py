"""Resolve durable launch evidence into exact pre-claim execution semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, timedelta
from datetime import datetime as dt_datetime

from ditto_application.builders._research_execution_bindings import (
    build_backtest_execution_binding,
    build_model_candidate_backtest_binding,
    build_research_runtime,
    build_strategy_execution_binding,
    build_synthetic_baseline_backtest_binding,
    build_synthetic_baseline_binding,
    execution_policy_for_lane,
    read_exact_strategy_record,
    require_baseline_runtime_parity,
    require_candidate_runtime_parity,
    resolve_persisted_runtime_lane,
)
from ditto_application.builders.published_baseline_runtime_builder import (
    PublishedBaselineRuntimeBuilder,
)
from ditto_application.builders.research_runtime_builder import (
    ResearchEvidenceReplayRuntimeBuilder,
    ResearchRuntimeBuilder,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.factor_bridge import (
    compiled_expressions_execution_hash,
)
from ditto_application.processes.execution.replay_context_inputs import (
    decode_replay_context_inputs,
)
from ditto_application.processes.experiments._execution_resolution_evidence import (
    DurableLaunchEvidence,
    ExactStrategyVersionReader,
    FrozenResearchExecutionInputs,
    FrozenResearchInputRequest,
    FrozenResearchInputsResolver,
    ResearchExperimentReader,
    ResearchFoldView,
    build_frozen_input_request,
    launch_spec_content_hash,
    read_durable_launch,
    require_evidence_integer,
    require_evidence_list,
    require_evidence_mapping,
    require_evidence_string,
    require_exact_fold_view,
    require_launch_parity,
    research_execution_error,
    select_planned_candidate,
    validate_frozen_inputs,
)
from ditto_application.processes.experiments.baseline_planning import (
    BaselinePlanningResolution,
    build_frozen_baseline_plan,
    resolve_planning_baseline,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselineExecutionPlan,
    BaselineRegistry,
    default_baseline_registry,
)
from ditto_application.processes.experiments.execution_bundle import (
    MODEL_CANDIDATE_IMPLEMENTATION_KEY,
    BacktestExecutionConfigBinding,
    BaselineExecutorBinding,
    CodeEnvironmentLock,
    ModelCandidateExecutionBinding,
    ResearchExecutionSemantics,
    StrategyExecutionBinding,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactStrategyIdentity,
    ResearchAssetLane,
    ResearchExecutionPolicy,
)
from ditto_application.processes.experiments.model_candidate_plans import (
    decode_model_candidate_descriptor,
    model_descriptor_hash,
)
from ditto_application.processes.experiments.planning import (
    BaselineCandidatePlan,
    BinderCandidatePlan,
    ModelCandidatePlan,
    PlannedCandidate,
)

__all__ = [
    "DurableResearchExecutionResolver",
    "ExactStrategyVersionReader",
    "FrozenResearchExecutionInputs",
    "FrozenResearchInputRequest",
    "FrozenResearchInputsResolver",
    "ResearchExecutionRuntimeBuilders",
]


@dataclass(frozen=True, slots=True)
class ResearchExecutionRuntimeBuilders:
    """Typed active, historical-replay, and published-baseline compiler lanes."""

    candidate: ResearchRuntimeBuilder
    candidate_replay: ResearchEvidenceReplayRuntimeBuilder
    published_baseline: PublishedBaselineRuntimeBuilder


_EPOCH_ORIGIN = dt_datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)


def _launch_clock_epoch_us(launch_spec: object) -> int:
    """Pin the model training clock from durable launch creation time."""
    created_at = getattr(launch_spec, "created_at", None)
    if not isinstance(created_at, dt_datetime) or created_at.tzinfo is None:
        raise research_execution_error("launch_creation_clock_missing")
    # Integer floor division avoids the float round trip documented against
    # in model_artifact_publication; the clock is a byte-stable identity input.
    return (created_at - _EPOCH_ORIGIN) // _MICROSECOND


def _knowledge_cutoff_epoch_us(knowledge_date: date) -> int:
    """
    Derive the fold's label-maturity cutoff from its knowledge date.

    The v1 convention freezes the cutoff at UTC midnight of the fold's
    ``test_start - knowledge_lag_days`` date, mirroring how the benchmark
    knowledge date is derived: only labels whose maturity stamps fall on or
    before that midnight count as usable at decision time.
    """
    return (
        dt_datetime(
            knowledge_date.year,
            knowledge_date.month,
            knowledge_date.day,
            tzinfo=UTC,
        )
        - _EPOCH_ORIGIN
    ) // _MICROSECOND


def _model_executor_evidence(
    launch: DurableLaunchEvidence,
    planned: ModelCandidatePlan,
) -> dict[str, object]:
    decoded = tuple(
        require_evidence_mapping(item, "executor.model")
        for item in require_evidence_list(
            launch.executor.get("model_candidates", []),
            "executor.model_candidates",
        )
    )
    evidence = tuple(
        item for item in decoded if item.get("candidate_hash") == planned.candidate_hash
    )
    if len(evidence) != 1:
        raise research_execution_error("model_executor_evidence_missing_or_ambiguous")
    return evidence[0]


class DurableResearchExecutionResolver:
    """Rebuild one fingerprint from exact persisted and content-addressed facts."""

    def __init__(
        self,
        *,
        experiment_reader: ResearchExperimentReader,
        strategy_reader: ExactStrategyVersionReader,
        runtime_builders: ResearchExecutionRuntimeBuilders,
        input_resolver: FrozenResearchInputsResolver,
        environment: CodeEnvironmentLock,
        baseline_registry: BaselineRegistry | None = None,
        knowledge_lag_days: int = 1,
    ) -> None:
        if type(knowledge_lag_days) is not int or knowledge_lag_days < 0:
            raise research_execution_error("invalid_knowledge_lag_days")
        self._experiments = experiment_reader
        self._strategies = strategy_reader
        self._candidate_runtime_builder = runtime_builders.candidate
        self._candidate_replay_runtime_builder = runtime_builders.candidate_replay
        self._published_baseline_builder = runtime_builders.published_baseline
        self._inputs = input_resolver
        self._environment = environment
        self._registry = baseline_registry or default_baseline_registry()
        self._knowledge_lag_days = knowledge_lag_days

    def resolve(self, fold: ResearchFoldView) -> ResearchExecutionSemantics:
        """Resolve exact strategy, snapshot, membership, policy, and controls."""
        fold = require_exact_fold_view(fold)
        launch_spec = self._experiments.get_launch_spec(fold.spec.key.experiment_id)
        if launch_spec is None:
            raise research_execution_error("experiment_launch_spec_missing")
        launch = read_durable_launch(self._experiments, fold)
        launch_spec_hash = launch_spec_content_hash(launch_spec)
        if launch.plan_preimage.get("launch_spec_hash") != launch_spec_hash:
            raise research_execution_error("launch_spec_hash_mismatch")
        fold_hashes = tuple(
            require_evidence_string(item, "plan_preimage.fold_payload_hash")
            for item in require_evidence_list(
                launch.plan_preimage.get("fold_payload_hashes"),
                "plan_preimage.fold_payload_hashes",
            )
        )
        if str(fold.spec.payload_hash) not in fold_hashes:
            raise research_execution_error("fold_payload_not_in_confirmed_plan")
        planned, is_baseline = select_planned_candidate(launch, fold)
        input_request = build_frozen_input_request(launch)
        require_launch_parity(
            launch_spec,
            launch,
            fold,
            planned,
            input_request,
            self._experiments.list_folds(fold.spec.key.experiment_id),
            is_baseline=is_baseline,
        )
        runtime_evidence = require_evidence_mapping(
            launch.executor.get("runtime_validation_evidence"),
            "executor.runtime_validation_evidence",
        )
        required_dataset_ids = tuple(
            require_evidence_string(item, "runtime_validation.required_dataset")
            for item in require_evidence_list(
                runtime_evidence.get("required_datasets"),
                "runtime_validation.required_datasets",
            )
        )
        inputs = validate_frozen_inputs(
            input_request,
            self._inputs.resolve(input_request),
            required_dataset_ids=required_dataset_ids,
        )
        baseline_resolution = self._baseline_resolution(launch)
        strategy, baseline_plan, policy, backtest = self._strategy_binding(
            launch=launch,
            planned=planned,
            is_baseline=is_baseline,
            inputs=inputs,
            baseline_resolution=baseline_resolution,
            benchmark_knowledge_date=(
                fold.spec.test_window.start - timedelta(days=self._knowledge_lag_days)
            ),
            trained_at_epoch_us=_launch_clock_epoch_us(launch_spec),
        )
        isolation = require_evidence_mapping(
            runtime_evidence.get("isolation"),
            "executor.runtime_validation_evidence.isolation",
        )
        execution_delay = isolation.get("execution_lag_sessions")
        if type(execution_delay) is not int or execution_delay < 0:
            raise research_execution_error("invalid_execution_lag_evidence")
        return ResearchExecutionSemantics(
            experiment_id=str(fold.spec.key.experiment_id),
            candidate_id=str(fold.spec.key.candidate_id),
            fold_id=str(fold.spec.key.fold_id),
            fold_role=fold.spec.fold_role.value,
            is_baseline=is_baseline,
            plan_hash=launch.report.plan_hash,
            launch_spec_hash=launch_spec_hash,
            fold_spec_hash=str(fold.spec.payload_hash),
            strategy=strategy,
            backtest=backtest,
            snapshot=inputs.snapshot_binding,
            membership_hash=inputs.universe.membership_hash,
            membership_projection_hash=inputs.membership_projection_hash,
            train_start=(
                None if fold.spec.train_window is None else fold.spec.train_window.start
            ),
            train_end=(
                None if fold.spec.train_window is None else fold.spec.train_window.end
            ),
            test_start=fold.spec.test_window.start,
            test_end=fold.spec.test_window.end,
            purge_sessions=fold.spec.purge_sessions,
            embargo_sessions=fold.spec.embargo_sessions,
            seed=launch_spec.seed,
            knowledge_lag_days=self._knowledge_lag_days,
            execution_delay_sessions=execution_delay,
            baseline_registry_manifest_hash=self._registry.manifest_hash,
            baseline_plan=baseline_plan,
            policy=policy,
            environment=self._environment,
            context_input_refs=decode_replay_context_inputs(
                launch.plan_preimage.get("context_input_refs", [])
            ),
        )

    def _strategy_binding(
        self,
        *,
        launch: DurableLaunchEvidence,
        planned: PlannedCandidate,
        is_baseline: bool,
        inputs: FrozenResearchExecutionInputs,
        baseline_resolution: BaselinePlanningResolution,
        benchmark_knowledge_date: date,
        trained_at_epoch_us: int,
    ) -> tuple[
        StrategyExecutionBinding
        | BaselineExecutorBinding
        | ModelCandidateExecutionBinding,
        BaselineExecutionPlan | None,
        ResearchExecutionPolicy,
        BacktestExecutionConfigBinding,
    ]:
        if is_baseline:
            return self._baseline_binding(
                launch,
                planned,
                inputs,
                baseline_resolution,
                benchmark_knowledge_date=benchmark_knowledge_date,
            )
        if type(planned) is ModelCandidatePlan:
            return self._model_candidate_binding(
                launch,
                planned,
                inputs,
                benchmark_knowledge_date=benchmark_knowledge_date,
                trained_at_epoch_us=trained_at_epoch_us,
            )
        if type(planned) is not BinderCandidatePlan:
            raise research_execution_error("invalid_binder_candidate_plan")
        strategy_id = require_evidence_string(
            launch.identities.get("strategy_id"),
            "identities.strategy_id",
        )
        strategy_version = require_evidence_integer(
            launch.identities.get("strategy_version"),
            "identities.strategy_version",
        )
        exact = ExactStrategyIdentity(
            strategy_id,
            strategy_version,
            require_evidence_string(
                launch.executor.get("strategy_spec_hash"),
                "executor.strategy_spec_hash",
            ),
        )
        record, version_status = read_exact_strategy_record(self._strategies, exact)
        runtime_builder = (
            self._candidate_replay_runtime_builder
            if version_status in {"deprecated", "published"}
            else self._candidate_runtime_builder
        )
        runtime = build_research_runtime(
            builder=runtime_builder,
            record=record,
            version_status=version_status,
            parameters=planned.binder_parameters,
            snapshot=inputs.snapshot_binding.exact_snapshot,
        )
        evidence = self._candidate_executor_evidence(launch, planned)
        if (
            runtime.resolved_spec_hash != evidence.get("resolved_spec_hash")
            or runtime.parameter_hash != evidence.get("parameter_hash")
            or runtime.pipeline_execution_hash
            != evidence.get("pipeline_execution_hash")
            or compiled_expressions_execution_hash(runtime.compiled_expressions)
            != evidence.get("compiled_factor_set_hash")
            or runtime.node_registry_manifest_hash
            != launch.executor.get("node_registry_manifest_hash")
        ):
            raise research_execution_error("candidate_runtime_identity_drift")
        lane = require_candidate_runtime_parity(runtime, launch)
        policy = execution_policy_for_lane(lane)
        return (
            build_strategy_execution_binding(
                runtime,
                exact=exact,
                snapshot=inputs.snapshot_binding,
                parameters=planned.binder_parameters,
            ),
            None,
            policy,
            build_backtest_execution_binding(
                runtime=runtime,
                inputs=inputs,
                policy=policy,
                knowledge_date=benchmark_knowledge_date,
            ),
        )

    @staticmethod
    def _candidate_executor_evidence(
        launch: DurableLaunchEvidence,
        planned: BinderCandidatePlan,
    ) -> dict[str, object]:
        decoded = tuple(
            require_evidence_mapping(item, "executor.candidate")
            for item in require_evidence_list(
                launch.executor.get("candidates"),
                "executor.candidates",
            )
        )
        evidence = tuple(
            item
            for item in decoded
            if item.get("candidate_hash") == planned.candidate_hash
        )
        if len(evidence) != 1:
            raise research_execution_error(
                "candidate_executor_evidence_missing_or_ambiguous"
            )
        return evidence[0]

    def _model_candidate_binding(
        self,
        launch: DurableLaunchEvidence,
        planned: ModelCandidatePlan,
        inputs: FrozenResearchExecutionInputs,
        *,
        benchmark_knowledge_date: date,
        trained_at_epoch_us: int,
    ) -> tuple[
        ModelCandidateExecutionBinding,
        None,
        ResearchExecutionPolicy,
        BacktestExecutionConfigBinding,
    ]:
        """Materialize the claim-time plan binding for one model candidate."""
        if resolve_persisted_runtime_lane(launch) is not ResearchAssetLane.STOCK:
            # v1 model candidates execute under the stock cost/participation
            # policy only; a model declared in another lane must not silently
            # ride stock semantics.
            raise research_execution_error("model_candidate_lane_mismatch")
        evidence = _model_executor_evidence(launch, planned)
        decoded = decode_model_candidate_descriptor(planned.descriptor)
        if (
            decoded.lineage.registration_hash != evidence.get("lineage_hash")
            or decoded.lineage.model_kind.value != evidence.get("model_kind")
            or model_descriptor_hash(planned.descriptor)
            != evidence.get("descriptor_hash")
        ):
            raise research_execution_error("model_executor_identity_drift")
        policy = execution_policy_for_lane(ResearchAssetLane.STOCK)
        binding = ModelCandidateExecutionBinding(
            model_kind=decoded.lineage.model_kind.value,
            lineage_hash=decoded.lineage.registration_hash,
            lineage_payload=decoded.lineage.canonical_payload(),
            inputs=decoded.inputs,
            top_k=decoded.top_k,
            trained_at_epoch_us=trained_at_epoch_us,
            knowledge_cutoff_epoch_us=_knowledge_cutoff_epoch_us(
                benchmark_knowledge_date,
            ),
            implementation_key=MODEL_CANDIDATE_IMPLEMENTATION_KEY,
            executor_contract_version=1,
        )
        return (
            binding,
            None,
            policy,
            build_model_candidate_backtest_binding(
                policy,
                inputs,
            ),
        )

    def _baseline_binding(
        self,
        launch: DurableLaunchEvidence,
        planned: PlannedCandidate,
        inputs: FrozenResearchExecutionInputs,
        resolution: BaselinePlanningResolution,
        *,
        benchmark_knowledge_date: date,
    ) -> tuple[
        StrategyExecutionBinding | BaselineExecutorBinding,
        BaselineExecutionPlan,
        ResearchExecutionPolicy,
        BacktestExecutionConfigBinding,
    ]:
        if type(planned) is not BaselineCandidatePlan:
            raise research_execution_error("invalid_baseline_candidate_plan")
        if (
            planned.descriptor
            != launch.report.work_plan.candidate_matrix.baseline_candidate.descriptor
        ):
            raise research_execution_error("baseline_candidate_descriptor_drift")
        plan = build_frozen_baseline_plan(
            resolution,
            registry=self._registry,
            snapshot=inputs.snapshot_binding.exact_snapshot,
            universe=inputs.universe,
        )
        if plan.execution_policy.lane is not resolve_persisted_runtime_lane(launch):
            raise research_execution_error("baseline_runtime_lane_drift")
        if resolution.exact_strategy is None:
            if launch.executor.get("baseline_runtime") is not None:
                raise research_execution_error(
                    "synthetic_baseline_runtime_identity_forbidden"
                )
            binding = build_synthetic_baseline_binding(
                plan,
                registry_manifest_hash=self._registry.manifest_hash,
            )
            backtest = build_synthetic_baseline_backtest_binding(plan, inputs)
        else:
            if launch.executor.get("baseline_runtime") is None:
                raise research_execution_error("baseline_runtime_identity_missing")
            baseline_record, baseline_version_status = read_exact_strategy_record(
                self._strategies, resolution.exact_strategy
            )
            runtime = build_research_runtime(
                builder=self._published_baseline_builder,
                record=baseline_record,
                version_status=baseline_version_status,
                parameters=(),
                snapshot=inputs.snapshot_binding.exact_snapshot,
            )
            require_baseline_runtime_parity(
                runtime,
                launch,
                inputs,
                exact=resolution.exact_strategy,
                expected_lane=plan.execution_policy.lane,
            )
            binding = build_strategy_execution_binding(
                runtime,
                exact=resolution.exact_strategy,
                snapshot=inputs.snapshot_binding,
                parameters=(),
            )
            backtest = build_backtest_execution_binding(
                runtime=runtime,
                inputs=inputs,
                policy=plan.execution_policy,
                knowledge_date=benchmark_knowledge_date,
            )
        return binding, plan, plan.execution_policy, backtest

    def _baseline_resolution(
        self,
        launch: DurableLaunchEvidence,
    ) -> BaselinePlanningResolution:
        try:
            resolution = resolve_planning_baseline(
                launch.report.work_plan.candidate_matrix.baseline_candidate.descriptor,
                self._registry,
            )
        except AppProcessError as exc:
            raise research_execution_error(
                "baseline_registry_resolution_failed",
                source_code=exc.details.get("code"),
                source_reason=exc.details.get("reason"),
            ) from exc
        if (
            launch.executor.get("baseline_ref") != resolution.ref.identity
            or launch.executor.get("baseline_descriptor_hash")
            != resolution.registration.descriptor.canonical_hash
            or launch.executor.get("baseline_registry_manifest_hash")
            != resolution.registry_manifest_hash
            or launch.executor.get("baseline_exact_strategy_hash")
            != (
                None
                if resolution.exact_strategy is None
                else resolution.exact_strategy.canonical_hash
            )
        ):
            raise research_execution_error("baseline_registry_identity_drift")
        return resolution
