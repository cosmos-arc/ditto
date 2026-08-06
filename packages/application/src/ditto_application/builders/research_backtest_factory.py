"""Closed construction of one real research ``BacktestService`` from an audit."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Protocol, cast

import polars as pl
from ditto_features.expression.contracts import CompiledDerivedExpression
from ditto_kernel.order import OrderType
from ditto_strategy.alpha.parameters import CandidateParameter
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.selection_evidence import (
    SelectionEvidenceCollector,
    SelectionEvidenceSink,
)
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunCheckpointReaderProtocol,
    StrategyRunCheckpointWriterProtocol,
)

from ditto_application.builders.research_backtest_components import (
    FrozenBacktestStrategyBuild,
    build_research_backtest_service,
)
from ditto_application.builders.research_factor_registry import (
    ResearchFactorBinding,
    analysis_execution_hash,
)
from ditto_application.builders.research_runtime_builder import (
    ResearchSnapshotIdentity,
    ResearchStrategyRuntime,
)
from ditto_application.builders.service_factory import build_frozen_baseline_pipeline
from ditto_application.exceptions import AppBuilderError, AppProcessError
from ditto_application.processes.execution.factor_bridge import (
    CompiledExpressions,
    compiled_expressions_execution_hash,
)
from ditto_application.processes.experiments._execution_bundle_inputs import (
    BaselineExecutorBinding,
    ResearchSnapshotBinding,
)
from ditto_application.processes.experiments._worker_attestation import (
    ResearchBacktestBuildAttestation,
    ResearchBacktestBuildSource,
    VerifiedResearchBacktestBuild,
    seal_verified_research_backtest_build,
)
from ditto_application.processes.experiments.execution_bundle import (
    BacktestExecutionConfigBinding,
    CodeEnvironmentLock,
    ContentAddressedResearchInput,
    ExactBenchmarkBinding,
    ResearchExecutionAudit,
    ResearchExecutionSemantics,
    ResearchFactorExecutionBinding,
    StrategyExecutionBinding,
    canonical_payload,
)
from ditto_application.processes.experiments.execution_contracts import (
    ResearchAssetLane,
)
from ditto_application.processes.experiments.research_backtest_checkpoint import (
    ResearchBacktestCheckpointControl,
    resolve_research_backtest_resume,
)
from ditto_application.processes.experiments.research_data_feed import (
    FrozenResearchDataFrames,
    ResearchDataFeed,
    ResearchFrameKind,
    VerifiedResearchFrame,
)
from ditto_application.processes.experiments.research_policy_artifact import (
    VerifiedInstrumentRulesArtifact,
)

__all__ = [
    "ExactPublishedBaselineRuntimeBuilder",
    "ExactResearchArtifactLoader",
    "ExactResearchRuntimeBuilder",
    "ExactResearchStrategyReader",
    "FrozenAuditResearchBacktestFactory",
]

_FREQUENCIES = {"D": "daily", "W": "weekly", "M": "monthly"}
_FEED_KINDS = (
    ResearchFrameKind.BARS,
    ResearchFrameKind.CALENDAR,
    ResearchFrameKind.MEMBERSHIP,
    ResearchFrameKind.FUNDAMENTAL,
    ResearchFrameKind.CLASSIFICATION,
)


def _error(reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        "frozen research backtest construction failed",
        details={
            "code": "REPRODUCIBILITY_FAILED",
            "reason": reason,
            **details,
        },
    )


def _require_compiled_expression_parity(
    binding: ResearchFactorBinding,
    expression: object,
) -> None:
    if type(expression) is not CompiledDerivedExpression:
        raise _error("compiled_factor_runtime_drift")
    try:
        serialized = expression.expr.meta.serialize()
    except (AttributeError, TypeError, ValueError, pl.exceptions.PolarsError):
        raise _error("compiled_factor_serialization_unavailable") from None
    if type(serialized) is not bytes:
        raise _error("compiled_factor_serialization_unavailable")
    actual_hash = hashlib.sha256(serialized).hexdigest()
    try:
        actual_analysis_hash = analysis_execution_hash(expression.analysis)
    except AppBuilderError:
        raise _error("compiled_factor_analysis_unavailable") from None
    if (
        expression.derived_id != binding.factor_id
        or expression.version != binding.version
        or expression.compile_identity != binding.compile_identity
        or actual_hash != binding.compiled_expression_hash
        or actual_analysis_hash != binding.analysis_execution_hash
    ):
        raise _error("compiled_factor_runtime_drift")


class ExactResearchStrategyReader(Protocol):
    """Read exactly one strategy version's payload and governance lifecycle state."""

    def get_spec(self, strategy_id: str, version: int) -> StrategySpecRecord | None:
        """Return the requested immutable catalog record only."""
        ...

    def get_version_state(self, strategy_id: str, version: int) -> str | None:
        """Return the version's governance lifecycle state."""
        ...


class ExactResearchRuntimeBuilder(Protocol):
    """Build a runtime from an already-read exact strategy record."""

    def build(
        self,
        *,
        record: StrategySpecRecord,
        candidate_parameters: tuple[CandidateParameter, ...],
        snapshot_identity: ResearchSnapshotIdentity,
        version_status: str,
        evidence_sink: SelectionEvidenceSink | None = None,
    ) -> ResearchStrategyRuntime:
        """Build without performing catalog or provider lookup."""
        ...


class ExactPublishedBaselineRuntimeBuilder(Protocol):
    """Build only an already-read exact published baseline record."""

    def build(
        self,
        *,
        record: StrategySpecRecord,
        candidate_parameters: tuple[CandidateParameter, ...],
        snapshot_identity: ResearchSnapshotIdentity,
        version_status: str,
        evidence_sink: SelectionEvidenceSink | None = None,
    ) -> ResearchStrategyRuntime:
        """Build without catalog lookup, moving pointers, or candidate tuning."""
        ...


class ExactResearchArtifactLoader(Protocol):
    """Load only artifacts addressed by the complete frozen input identity."""

    def load_frame(
        self,
        evidence: ContentAddressedResearchInput,
    ) -> VerifiedResearchFrame:
        """Return exact verified Parquet frame evidence."""
        ...

    def load_instrument_rules(
        self,
        evidence: ContentAddressedResearchInput,
    ) -> VerifiedInstrumentRulesArtifact:
        """Return exact verified rules evidence."""
        ...


@dataclass(frozen=True, slots=True)
class _LoadedArtifacts:
    frames: FrozenResearchDataFrames
    rules: VerifiedInstrumentRulesArtifact


class FrozenAuditResearchBacktestFactory:
    """Build one provider-free real backtest from a complete immutable audit."""

    def __init__(
        self,
        *,
        strategy_reader: ExactResearchStrategyReader,
        runtime_builder: ExactResearchRuntimeBuilder,
        published_baseline_builder: ExactPublishedBaselineRuntimeBuilder | None = None,
        artifact_loader: ExactResearchArtifactLoader,
        environment: CodeEnvironmentLock,
        checkpoint_reader: StrategyRunCheckpointReaderProtocol,
        checkpoint_writer: StrategyRunCheckpointWriterProtocol,
    ) -> None:
        if type(environment) is not CodeEnvironmentLock:
            raise _error("invalid_actual_code_environment_lock")
        self._strategies = strategy_reader
        self._candidate_runtime_builder = runtime_builder
        self._published_baseline_builder = published_baseline_builder
        self._artifacts = artifact_loader
        self._environment = environment
        self._checkpoint_reader = checkpoint_reader
        self._checkpoint_writer = checkpoint_writer

    def build(
        self,
        audit: ResearchExecutionAudit,
        *,
        external_should_stop: Callable[[], bool],
    ) -> VerifiedResearchBacktestBuild:
        """Construct and attest a real service without moving-data fallbacks."""
        if not callable(external_should_stop):
            raise _error("invalid_external_stop_callback")
        audit = self._require_audit(audit)
        if audit.semantics.environment != self._environment:
            raise _error("actual_code_environment_lock_drift")
        semantics = audit.semantics
        evidence_collector = SelectionEvidenceCollector()
        loaded = self._load_artifacts(semantics.snapshot)
        built_strategy = self._build_strategy(
            semantics,
            loaded.rules,
            evidence_collector=evidence_collector,
        )
        benchmark = self._build_benchmark(
            semantics,
            built_strategy,
            loaded,
        )
        feed = ResearchDataFeed(
            snapshot=semantics.snapshot,
            frames=loaded.frames,
            start_date=semantics.test_start.isoformat(),
            end_date=semantics.test_end.isoformat(),
            knowledge_lag_days=semantics.knowledge_lag_days,
            benchmark=benchmark,
            expected_manifest_hash=semantics.backtest.data_feed_manifest_hash,
        )
        checkpoint_control = ResearchBacktestCheckpointControl(
            writer=self._checkpoint_writer,
            resume=resolve_research_backtest_resume(
                audit=audit,
                strategy=built_strategy.binding,
                trading_days=tuple(feed.trading_days()),
                checkpoint_reader=self._checkpoint_reader,
            ),
        )
        component_build = build_research_backtest_service(
            audit=audit,
            strategy=built_strategy,
            rules_artifact=loaded.rules,
            feed=feed,
            benchmark=benchmark,
            external_should_stop=external_should_stop,
            checkpoint_control=checkpoint_control,
        )
        service = component_build.service
        actual_backtest = component_build.execution_config
        actual_semantics = replace(
            semantics,
            strategy=built_strategy.binding,
            backtest=actual_backtest,
            environment=self._environment,
        )
        if (
            actual_semantics.canonical_payload != semantics.canonical_payload
            or actual_semantics.reproduction_fingerprint
            != semantics.reproduction_fingerprint
        ):
            raise _error("constructed_execution_semantics_drift")
        rebuilt_audit = ResearchExecutionAudit.create(
            semantics=actual_semantics,
            attempt_id=audit.attempt_id,
            attempt_ordinal=audit.attempt_ordinal,
            backtest_run_id=audit.backtest_run_id,
            parent_attempt_id=audit.parent_attempt_id,
            resume_from_run_id=audit.resume_from_run_id,
            created_at=audit.created_at,
        )
        if (
            rebuilt_audit.canonical_payload != audit.canonical_payload
            or rebuilt_audit.bundle_hash != audit.bundle_hash
        ):
            raise _error("audit_bundle_integrity_drift")
        attestation = self._attest(
            rebuilt_audit,
            built_strategy.binding,
            actual_backtest,
            feed,
            self._environment,
        )
        return seal_verified_research_backtest_build(
            service=service,
            attestation=attestation,
            graph=component_build.graph,
            audit=audit,
            external_should_stop=external_should_stop,
        )

    @staticmethod
    def _require_audit(audit: object) -> ResearchExecutionAudit:
        if type(audit) is not ResearchExecutionAudit:
            raise _error("invalid_research_execution_audit")
        typed = audit
        if typed.resume_from_run_id is not None and typed.parent_attempt_id is None:
            raise _error("research_resume_lineage_incomplete")
        rebuilt = ResearchExecutionAudit.create(
            semantics=typed.semantics,
            attempt_id=typed.attempt_id,
            attempt_ordinal=typed.attempt_ordinal,
            backtest_run_id=typed.backtest_run_id,
            parent_attempt_id=typed.parent_attempt_id,
            resume_from_run_id=typed.resume_from_run_id,
            created_at=typed.created_at,
        )
        if (
            rebuilt.canonical_payload != typed.canonical_payload
            or rebuilt.bundle_hash != typed.bundle_hash
        ):
            raise _error("audit_bundle_integrity_drift")
        return typed

    def _load_artifacts(
        self,
        snapshot: ResearchSnapshotBinding,
    ) -> _LoadedArtifacts:
        by_kind: dict[str, ContentAddressedResearchInput] = {}
        for evidence in snapshot.inputs:
            if evidence.artifact_kind in {item.value for item in _FEED_KINDS} | {
                "instrument_rules"
            }:
                if evidence.artifact_kind in by_kind:
                    raise _error(
                        "duplicate_executable_artifact_kind",
                        artifact_kind=evidence.artifact_kind,
                    )
                by_kind[evidence.artifact_kind] = evidence
        required = {
            ResearchFrameKind.BARS.value,
            ResearchFrameKind.CALENDAR.value,
            ResearchFrameKind.MEMBERSHIP.value,
            "instrument_rules",
        }
        missing = tuple(sorted(required - set(by_kind)))
        if missing:
            raise _error("required_executable_artifact_missing", artifact_kinds=missing)

        loaded_frames: dict[ResearchFrameKind, VerifiedResearchFrame] = {}
        for kind in _FEED_KINDS:
            evidence = by_kind.get(kind.value)
            if evidence is None:
                continue
            frame = self._artifacts.load_frame(evidence)
            if (
                type(frame) is not VerifiedResearchFrame
                or frame.input_evidence != evidence
            ):
                raise _error(
                    "artifact_loader_identity_drift",
                    input_id=evidence.input_id,
                )
            loaded_frames[kind] = VerifiedResearchFrame(
                input_evidence=evidence,
                source_snapshot_ids=frame.source_snapshot_ids,
                artifact_bytes=frame.artifact_bytes,
            )
        rules_evidence = by_kind["instrument_rules"]
        loaded_rules = self._artifacts.load_instrument_rules(rules_evidence)
        if (
            type(loaded_rules) is not VerifiedInstrumentRulesArtifact
            or loaded_rules.input_evidence != rules_evidence
        ):
            raise _error(
                "artifact_loader_identity_drift",
                input_id=rules_evidence.input_id,
            )
        rules = VerifiedInstrumentRulesArtifact(
            input_evidence=rules_evidence,
            artifact_bytes=loaded_rules.artifact_bytes,
        )
        if not set(rules.source_snapshot_ids).issubset(
            snapshot.source_snapshot_ids,
        ):
            raise _error(
                "artifact_loader_identity_drift",
                input_id=rules_evidence.input_id,
            )
        return _LoadedArtifacts(
            frames=FrozenResearchDataFrames(
                bars=loaded_frames[ResearchFrameKind.BARS],
                calendar=loaded_frames[ResearchFrameKind.CALENDAR],
                membership=loaded_frames[ResearchFrameKind.MEMBERSHIP],
                fundamental=loaded_frames.get(ResearchFrameKind.FUNDAMENTAL),
                classification=loaded_frames.get(ResearchFrameKind.CLASSIFICATION),
            ),
            rules=rules,
        )

    def _build_strategy(
        self,
        semantics: ResearchExecutionSemantics,
        rules: VerifiedInstrumentRulesArtifact,
        *,
        evidence_collector: SelectionEvidenceCollector,
    ) -> FrozenBacktestStrategyBuild:
        declared = semantics.strategy
        if type(declared) is BaselineExecutorBinding:
            if semantics.baseline_plan is None:
                raise _error("synthetic_baseline_plan_missing")
            actual = BaselineExecutorBinding(
                baseline_ref=declared.baseline_ref,
                kind=declared.kind,
                descriptor_hash=declared.descriptor_hash,
                implementation_key=declared.implementation_key,
                executor_contract_version=declared.executor_contract_version,
                registry_manifest_hash=declared.registry_manifest_hash,
                factor_versions=declared.factor_versions,
            )
            pipeline = build_frozen_baseline_pipeline(
                actual,
                evidence_sink=evidence_collector,
            )
            if actual != declared or semantics.backtest.benchmark is not None:
                raise _error("synthetic_baseline_execution_drift")
            return FrozenBacktestStrategyBuild(
                binding=actual,
                pipeline=pipeline,
                pipeline_attestation=None,
                compiled_expressions=None,
                effective_parameters=(),
                planner_order_type=OrderType.MARKET,
                rebalance_frequency="fold_schedule",
                selection_evidence_collector=evidence_collector,
            )
        if type(declared) is not StrategyExecutionBinding:
            raise _error("invalid_strategy_execution_binding")
        runtime = self._build_exact_strategy_runtime(
            semantics,
            declared,
            evidence_collector=evidence_collector,
        )
        pipeline = self._verified_runtime_pipeline(runtime, declared)
        actual = self._binding_from_runtime(
            runtime,
            declared,
            semantics.snapshot,
        )
        if actual != declared:
            raise _error("rebuilt_strategy_binding_drift")
        order_type = self._runtime_order_type(runtime)
        frequency = self._runtime_frequency(runtime)
        self._runtime_benchmark(
            runtime,
            semantics.backtest.benchmark,
            rules,
            knowledge_date=(
                semantics.test_start - timedelta(days=semantics.knowledge_lag_days)
            ),
        )
        return FrozenBacktestStrategyBuild(
            binding=actual,
            pipeline=pipeline,
            pipeline_attestation=runtime.attested_pipeline,
            compiled_expressions=runtime.compiled_expressions,
            effective_parameters=runtime.effective_parameters,
            planner_order_type=order_type,
            rebalance_frequency=frequency,
            selection_evidence_collector=evidence_collector,
        )

    def _build_exact_strategy_runtime(
        self,
        semantics: ResearchExecutionSemantics,
        declared: StrategyExecutionBinding,
        *,
        evidence_collector: SelectionEvidenceCollector,
    ) -> ResearchStrategyRuntime:
        record = self._strategies.get_spec(
            declared.exact_strategy.strategy_id,
            declared.exact_strategy.version,
        )
        if (
            type(record) is not StrategySpecRecord
            or record.strategy_id != declared.exact_strategy.strategy_id
            or record.version != declared.exact_strategy.version
        ):
            raise _error("exact_strategy_version_missing")
        version_status = self._strategies.get_version_state(
            record.strategy_id, record.version
        )
        if version_status is None:
            raise _error("exact_strategy_version_state_missing")
        runtime_builder = self._select_runtime_builder(
            semantics, declared, version_status
        )
        runtime = runtime_builder.build(
            record=record,
            candidate_parameters=declared.candidate_parameters,
            snapshot_identity=ResearchSnapshotIdentity(
                semantics.snapshot.exact_snapshot.snapshot_id,
                semantics.snapshot.exact_snapshot.manifest_hash,
            ),
            version_status=version_status,
            evidence_sink=evidence_collector,
        )
        if type(runtime) is not ResearchStrategyRuntime:
            raise _error("exact_strategy_runtime_unavailable")
        if runtime.version_status != version_status:
            raise _error("rebuilt_strategy_runtime_type_drift")
        runtime_lane = self._runtime_lane(runtime)
        if semantics.is_baseline and runtime_lane is not ResearchAssetLane.ETF:
            raise _error("published_baseline_lane_not_supported")
        if runtime_lane is not semantics.policy.lane:
            raise _error("rebuilt_strategy_lane_drift")
        return runtime

    def _select_runtime_builder(
        self,
        semantics: ResearchExecutionSemantics,
        declared: StrategyExecutionBinding,
        version_status: str,
    ) -> ExactResearchRuntimeBuilder | ExactPublishedBaselineRuntimeBuilder:
        if semantics.is_baseline:
            if version_status != "published":
                raise _error(
                    "published_baseline_version_required",
                    version_status=version_status,
                )
            if declared.candidate_parameters:
                raise _error("published_baseline_parameters_forbidden")
            if self._published_baseline_builder is None:
                raise _error("published_baseline_runtime_builder_unavailable")
            return self._published_baseline_builder
        if version_status not in {"draft", "review"}:
            raise _error(
                "candidate_strategy_version_not_researchable",
                version_status=version_status,
            )
        return self._candidate_runtime_builder

    @staticmethod
    def _runtime_lane(runtime: ResearchStrategyRuntime) -> ResearchAssetLane:
        try:
            lane_name = runtime.resolved_spec.strategy_kind.value
        except AttributeError:
            raise _error("rebuilt_strategy_lane_unavailable") from None
        lane = {
            "etf_rotation": ResearchAssetLane.ETF,
            "stock_selection": ResearchAssetLane.STOCK,
        }.get(lane_name)
        if lane is None:
            raise _error("rebuilt_strategy_lane_unavailable", actual_lane=lane_name)
        return lane

    @staticmethod
    def _verified_runtime_pipeline(
        runtime: ResearchStrategyRuntime,
        declared: StrategyExecutionBinding,
    ) -> StrategyPipeline:
        try:
            pipeline = runtime.require_verified_pipeline(
                expected_execution_hash=declared.pipeline_execution_hash,
            )
        except AppBuilderError as exc:
            raise _error(
                "rebuilt_pipeline_execution_drift",
                builder_reason=exc.details.get("reason"),
            ) from exc
        if type(pipeline) is not StrategyPipeline:
            raise _error("rebuilt_strategy_runtime_type_drift")
        return pipeline

    @staticmethod
    def _binding_from_runtime(
        runtime: ResearchStrategyRuntime,
        declared: StrategyExecutionBinding,
        snapshot: ResearchSnapshotBinding,
    ) -> StrategyExecutionBinding:
        if (
            runtime.strategy_id != declared.exact_strategy.strategy_id
            or runtime.strategy_version != declared.exact_strategy.version
            or runtime.base_spec_hash != declared.exact_strategy.spec_hash
            or runtime.snapshot_identity.snapshot_id
            != snapshot.exact_snapshot.snapshot_id
            or runtime.snapshot_identity.manifest_hash
            != snapshot.exact_snapshot.manifest_hash
        ):
            raise _error("rebuilt_strategy_identity_drift")
        artifacts = {
            item.input_id: item
            for item in snapshot.inputs
            if item.artifact_kind == "factor"
        }
        raw_bindings: object = runtime.used_factor_bindings
        if type(raw_bindings) is not tuple or any(
            type(item) is not ResearchFactorBinding
            for item in cast("tuple[object, ...]", raw_bindings)
        ):
            raise _error("invalid_authoritative_factor_bindings")
        bindings: list[ResearchFactorExecutionBinding] = []
        runtime_bindings = raw_bindings
        FrozenAuditResearchBacktestFactory._require_compiled_factor_parity(
            runtime,
            runtime_bindings,
        )
        for factor in runtime_bindings:
            artifact = artifacts.get(f"{factor.factor_id}@{factor.version}")
            if artifact is None:
                raise _error("factor_artifact_identity_missing")
            binding = ResearchFactorExecutionBinding(
                factor_id=factor.factor_id,
                version=factor.version,
                spec_hash=factor.spec_hash,
                compiled_expression_hash=factor.compiled_expression_hash,
                analysis_execution_hash=factor.analysis_execution_hash,
                compile_identity=factor.compile_identity,
                artifact=artifact,
            )
            if binding.binding_hash != factor.binding_hash:
                raise _error("factor_compiler_binding_drift")
            bindings.append(binding)
        return StrategyExecutionBinding(
            exact_strategy=declared.exact_strategy,
            resolved_spec_hash=runtime.resolved_spec_hash,
            parameter_hash=runtime.parameter_hash,
            node_registry_manifest_hash=runtime.node_registry_manifest_hash,
            pipeline_execution_hash=runtime.pipeline_execution_hash,
            factor_registry_manifest_hash=runtime.factor_registry_manifest_hash,
            compiled_factor_set_hash=compiled_expressions_execution_hash(
                runtime.compiled_expressions
            ),
            factor_bindings=tuple(bindings),
            candidate_parameters=declared.candidate_parameters,
        )

    @staticmethod
    def _require_compiled_factor_parity(
        runtime: ResearchStrategyRuntime,
        bindings: tuple[ResearchFactorBinding, ...],
    ) -> None:
        compiled = runtime.compiled_expressions
        try:
            declared_ids = runtime.legacy_spec.signal_expressions
            declared_weights = runtime.legacy_spec.signal_weights
        except AttributeError:
            raise _error("rebuilt_factor_runtime_evidence_missing") from None
        if not bindings:
            if compiled is not None or declared_ids or declared_weights:
                raise _error("compiled_factor_runtime_drift")
            return
        if (
            type(compiled) is not CompiledExpressions
            or type(declared_ids) is not tuple
            or tuple(declared_ids) != tuple(item.factor_id for item in bindings)
        ):
            raise _error("compiled_factor_runtime_drift")
        expressions = compiled.expressions
        if type(expressions) is not tuple or len(expressions) != len(bindings):
            raise _error("compiled_factor_runtime_drift")
        expected_weights = declared_weights or (1.0,) * len(bindings)
        if compiled.weights != expected_weights:
            raise _error("compiled_factor_weight_drift")
        for binding, expression in zip(bindings, expressions, strict=True):
            _require_compiled_expression_parity(binding, expression)

    @staticmethod
    def _runtime_order_type(runtime: ResearchStrategyRuntime) -> OrderType:
        try:
            raw = runtime.legacy_spec.execution.default_order_type.value
            return OrderType(raw)
        except (AttributeError, ValueError):
            raise _error("rebuilt_runtime_order_type_unavailable") from None

    @staticmethod
    def _runtime_frequency(runtime: ResearchStrategyRuntime) -> str:
        try:
            raw = runtime.legacy_spec.execution.frequency
        except AttributeError:
            raise _error("rebuilt_runtime_frequency_unavailable") from None
        frequency = _FREQUENCIES.get(raw)
        if frequency is None:
            raise _error("rebuilt_runtime_frequency_unavailable")
        return frequency

    @staticmethod
    def _runtime_benchmark(
        runtime: ResearchStrategyRuntime,
        declared: ExactBenchmarkBinding | None,
        rules: VerifiedInstrumentRulesArtifact,
        *,
        knowledge_date: date,
    ) -> None:
        try:
            code = runtime.legacy_spec.benchmark
        except AttributeError:
            raise _error("rebuilt_runtime_benchmark_unavailable") from None
        if code is None:
            if declared is not None:
                raise _error("benchmark_binding_drift")
            return
        if type(code) is not str or not code or declared is None:
            raise _error("benchmark_binding_drift")
        try:
            instrument_id = rules.resolve_instrument_id_at(
                code,
                knowledge_date=knowledge_date,
            )
        except AppProcessError:
            raise _error("benchmark_mapping_knowledge_drift") from None
        expected_identity = str(
            canonical_payload(
                {
                    "instrument_code": code,
                    "instrument_id": int(instrument_id),
                    "mapping_input": rules.input_evidence.as_payload(),
                }
            ).content_hash
        )
        if (
            declared.instrument_id != int(instrument_id)
            or declared.instrument_identity_hash != expected_identity
            or declared.mapping_input != rules.input_evidence
        ):
            raise _error("benchmark_binding_drift")

    @staticmethod
    def _build_benchmark(
        semantics: ResearchExecutionSemantics,
        built: FrozenBacktestStrategyBuild,
        loaded: _LoadedArtifacts,
    ) -> ExactBenchmarkBinding | None:
        declared = semantics.backtest.benchmark
        if type(built.binding) is BaselineExecutorBinding:
            if declared is not None:
                raise _error("synthetic_baseline_execution_drift")
            return None
        if declared is None:
            return None
        actual = ExactBenchmarkBinding(
            instrument_id=declared.instrument_id,
            instrument_identity_hash=declared.instrument_identity_hash,
            mapping_input=loaded.rules.input_evidence,
            bars_input=loaded.frames.bars.input_evidence,
        )
        if actual != declared:
            raise _error("benchmark_binding_drift")
        return actual

    @staticmethod
    def _attest(
        audit: ResearchExecutionAudit,
        strategy: StrategyExecutionBinding | BaselineExecutorBinding,
        backtest: BacktestExecutionConfigBinding,
        feed: ResearchDataFeed,
        environment: CodeEnvironmentLock,
    ) -> ResearchBacktestBuildAttestation:
        benchmark_hash = (
            None if backtest.benchmark is None else backtest.benchmark.canonical_hash
        )
        return ResearchBacktestBuildAttestation(
            source=ResearchBacktestBuildSource.FROZEN_AUDIT_BUNDLE,
            audit_bundle_hash=audit.bundle_hash,
            reproduction_fingerprint=audit.reproduction_fingerprint,
            backtest_run_id=audit.backtest_run_id,
            strategy=strategy,
            snapshot=audit.semantics.snapshot,
            execution_config=backtest,
            execution_config_hash=backtest.canonical_hash,
            feed_manifest_hash=feed.evidence_manifest.canonical_hash,
            policy_hash=audit.semantics.policy.canonical_hash,
            model_evidence_hash=backtest.policy_model_evidence_hash,
            benchmark_binding_hash=benchmark_hash,
            environment=environment,
        )
