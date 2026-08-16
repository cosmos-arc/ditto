"""Read-only research evidence function tools."""

from __future__ import annotations

from collections.abc import Mapping

from ditto_application.queries.evidence_contracts import (
    FactorEvidenceQuery,
    ResearchEvidenceKind,
    ResearchEvidenceQueryPort,
)

from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext
from ditto_agent.tools._common import (
    Arguments,
    application_context,
    function_spec,
    seal_research_evidence,
)

_TEXT = {"type": "string", "minLength": 1}
_POSITIVE_INTEGER = {"type": "integer", "minimum": 1}
_BOOLEAN = {"type": "boolean"}


class ExperimentEvidenceTool:
    """Adapt an exact experiment read into a sealed evidence envelope."""

    spec = function_spec(
        name="research_experiment_evidence",
        description="Read one exact governed experiment, candidate, or fold.",
        properties={
            "experiment_id": _TEXT,
            "candidate_id": {"type": ["string", "null"], "minLength": 1},
            "fold_id": {"type": ["string", "null"], "minLength": 1},
        },
        required=("experiment_id",),
    )

    def __init__(self, *, facade: ResearchEvidenceQueryPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Invoke the application facade with host-owned PIT context."""
        parsed = Arguments(
            arguments,
            required=("experiment_id",),
            optional=("candidate_id", "fold_id"),
        )
        result = self._facade.get_experiment_evidence(
            experiment_id=parsed.text("experiment_id"),
            candidate_id=parsed.optional_text("candidate_id"),
            fold_id=parsed.optional_text("fold_id"),
            context=application_context(context),
        )
        return seal_research_evidence(
            tool_name=self.spec.name,
            expected_kind=ResearchEvidenceKind.EXPERIMENT.value,
            read_model=result,
            context=context,
        )


class FactorEvidenceTool:
    """Adapt an exact factor version while injecting the trusted snapshot."""

    spec = function_spec(
        name="research_factor_evidence",
        description="Read one exact factor evaluation for a dataset and universe.",
        properties={
            "factor_id": _TEXT,
            "factor_version": _POSITIVE_INTEGER,
            "dataset_id": _TEXT,
            "universe": _TEXT,
            "start": {"type": ["string", "null"], "minLength": 1},
            "end": {"type": ["string", "null"], "minLength": 1},
        },
        required=("factor_id", "factor_version", "dataset_id", "universe"),
    )

    def __init__(self, *, facade: ResearchEvidenceQueryPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Invoke the application facade without accepting a model snapshot."""
        parsed = Arguments(
            arguments,
            required=("factor_id", "factor_version", "dataset_id", "universe"),
            optional=("start", "end"),
        )
        result = self._facade.get_factor_evidence(
            query=FactorEvidenceQuery(
                factor_id=parsed.text("factor_id"),
                factor_version=parsed.positive_integer("factor_version"),
                dataset_id=parsed.text("dataset_id"),
                catalog_snapshot_id=context.source_snapshot_id,
                universe=parsed.text("universe"),
                start=parsed.optional_text("start"),
                end=parsed.optional_text("end"),
            ),
            context=application_context(context),
        )
        return seal_research_evidence(
            tool_name=self.spec.name,
            expected_kind=ResearchEvidenceKind.FACTOR.value,
            read_model=result,
            context=context,
        )


class StrategyEvidenceTool:
    """Adapt an immutable strategy-version evidence read."""

    spec = function_spec(
        name="research_strategy_evidence",
        description="Read one exact immutable strategy version.",
        properties={"strategy_id": _TEXT, "version": _POSITIVE_INTEGER},
        required=("strategy_id", "version"),
    )

    def __init__(self, *, facade: ResearchEvidenceQueryPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Invoke the exact-version application query."""
        parsed = Arguments(arguments, required=("strategy_id", "version"))
        result = self._facade.get_strategy_evidence(
            strategy_id=parsed.text("strategy_id"),
            version=parsed.positive_integer("version"),
            context=application_context(context),
        )
        return seal_research_evidence(
            tool_name=self.spec.name,
            expected_kind=ResearchEvidenceKind.STRATEGY.value,
            read_model=result,
            context=context,
        )


class BacktestEvidenceTool:
    """Adapt one completed backtest and optional replay proof."""

    spec = function_spec(
        name="research_backtest_evidence",
        description="Read one exact completed backtest and optional replay proof.",
        properties={
            "run_id": _TEXT,
            "strategy_id": _TEXT,
            "strategy_version": _TEXT,
            "dataset_id": _TEXT,
            "include_replay_proof": _BOOLEAN,
        },
        required=("run_id", "strategy_id", "strategy_version", "dataset_id"),
    )

    def __init__(self, *, facade: ResearchEvidenceQueryPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Invoke the exact-run application query."""
        parsed = Arguments(
            arguments,
            required=("run_id", "strategy_id", "strategy_version", "dataset_id"),
            optional=("include_replay_proof",),
        )
        result = self._facade.get_backtest_evidence(
            run_id=parsed.text("run_id"),
            strategy_id=parsed.text("strategy_id"),
            strategy_version=parsed.text("strategy_version"),
            dataset_id=parsed.text("dataset_id"),
            include_replay_proof=parsed.boolean("include_replay_proof"),
            context=application_context(context),
        )
        return seal_research_evidence(
            tool_name=self.spec.name,
            expected_kind=ResearchEvidenceKind.BACKTEST.value,
            read_model=result,
            context=context,
        )


__all__ = [
    "BacktestEvidenceTool",
    "ExperimentEvidenceTool",
    "FactorEvidenceTool",
    "StrategyEvidenceTool",
]
