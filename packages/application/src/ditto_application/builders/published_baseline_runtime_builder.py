"""Exact published ETF baseline runtime assembly for R3 experiments."""

from __future__ import annotations

from ditto_features.expression.compiler import ExpressionCompiler
from ditto_strategy.alpha.node_registry import NodeRegistry
from ditto_strategy.alpha.parameters import CandidateParameter
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceSink
from ditto_strategy.models import StrategySpecRecord

from ditto_application.builders.node_pipeline_builder import NodePipelineBuilder
from ditto_application.builders.research_factor_registry import ResearchFactorRegistry
from ditto_application.builders.research_runtime_builder import (
    ConstrainedResearchRuntimeCompiler,
    ResearchSnapshotIdentity,
    ResearchStrategyRuntime,
    require_exact_research_record,
    require_research_snapshot_identity,
    research_runtime_error,
)

__all__ = ["PublishedBaselineRuntimeBuilder"]

_PUBLISHED_STATUS = "published"
_ETF_RUNTIME_LANE = "etf_rotation"


class PublishedBaselineRuntimeBuilder:
    """Build one exact published ETF baseline, never a candidate or moving version."""

    def __init__(
        self,
        *,
        node_registry: NodeRegistry | None = None,
        node_pipeline_builder: NodePipelineBuilder | None = None,
        factor_registry: ResearchFactorRegistry | None = None,
        factor_compiler: ExpressionCompiler | None = None,
    ) -> None:
        self._compiler = ConstrainedResearchRuntimeCompiler(
            node_registry=node_registry,
            node_pipeline_builder=node_pipeline_builder,
            factor_registry=factor_registry,
            factor_compiler=factor_compiler,
        )

    def build(
        self,
        *,
        record: StrategySpecRecord,
        candidate_parameters: tuple[CandidateParameter, ...],
        snapshot_identity: ResearchSnapshotIdentity,
        evidence_sink: SelectionEvidenceSink | None = None,
    ) -> ResearchStrategyRuntime:
        """Compile an explicit published ETF record with no catalog lookup or tuning."""
        record = require_exact_research_record(record)
        snapshot_identity = require_research_snapshot_identity(snapshot_identity)
        if record.status != _PUBLISHED_STATUS:
            raise research_runtime_error(
                "exact baseline strategy version must be published",
                reason="published_baseline_version_required",
                path="record.status",
                strategy_id=record.strategy_id,
                strategy_version=record.version,
                version_status=record.status,
            )
        if candidate_parameters:
            raise research_runtime_error(
                "published baseline runtime cannot bind candidate parameters",
                reason="published_baseline_parameters_forbidden",
                strategy_id=record.strategy_id,
                strategy_version=record.version,
            )
        runtime = self._compiler.compile(
            record=record,
            candidate_parameters=(),
            snapshot_identity=snapshot_identity,
            evidence_sink=evidence_sink,
        )
        actual_lane = runtime.resolved_spec.strategy_kind.value
        if actual_lane != _ETF_RUNTIME_LANE:
            raise research_runtime_error(
                "published baseline runtime supports only the exact ETF lane",
                reason="published_baseline_lane_not_supported",
                strategy_id=record.strategy_id,
                strategy_version=record.version,
                actual_lane=actual_lane,
                expected_lane=_ETF_RUNTIME_LANE,
            )
        return runtime
