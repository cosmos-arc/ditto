from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.tools.research import (
    BacktestEvidenceTool,
    ExperimentEvidenceTool,
    FactorEvidenceTool,
    StrategyEvidenceTool,
)
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
    FactorEvidenceQuery,
    ResearchEvidenceKind,
    ResearchEvidenceQueryPort,
    ResearchEvidenceReadModel,
)


def _context(*, snapshot_id: str = "snapshot-20260812") -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 12, 7, 0, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 12, 6, 55, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 12, 6, 50, tzinfo=UTC),
            source_snapshot_id=snapshot_id,
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH", "510500.SH"),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def _application_context(context: TemporalToolContext) -> EvidenceTemporalContext:
    return EvidenceTemporalContext(
        decision_time=context.decision_time,
        knowledge_cutoff=context.knowledge_cutoff,
        publication_cutoff=context.publication_cutoff,
        source_snapshot_id=context.source_snapshot_id,
    )


def _read_model(
    *,
    context: TemporalToolContext,
    kind: ResearchEvidenceKind,
    subject_id: str,
    subject_version: str,
) -> ResearchEvidenceReadModel:
    payload = EvidencePayloadReadModel.seal(
        schema_version=1,
        value={"metric": {"name": "information_ratio", "value": 0.73}},
    )
    return ResearchEvidenceReadModel(
        kind=kind,
        subject_id=subject_id,
        subject_version=subject_version,
        strategy_id="strategy-001" if kind is not ResearchEvidenceKind.FACTOR else None,
        strategy_version="3" if kind is not ResearchEvidenceKind.FACTOR else None,
        dataset_id="dataset-001",
        temporal_context=_application_context(context),
        payload=payload,
        artifact_refs=(
            EvidenceArtifactReference(
                artifact_id=f"{kind.value}:{subject_id}",
                artifact_kind=f"{kind.value}_evidence",
                content_hash=payload.payload_hash,
            ),
        ),
        lineage=(f"{kind.value}:{subject_id}:v{subject_version}",),
    )


class _ResearchFacade:
    def __init__(self, *, context: TemporalToolContext) -> None:
        self._context = context
        self.calls: list[tuple[str, object]] = []

    def get_experiment_evidence(
        self,
        *,
        experiment_id: str,
        context: EvidenceTemporalContext,
        candidate_id: str | None = None,
        fold_id: str | None = None,
    ) -> ResearchEvidenceReadModel:
        self.calls.append(
            (
                "experiment",
                (experiment_id, context, candidate_id, fold_id),
            )
        )
        return _read_model(
            context=self._context,
            kind=ResearchEvidenceKind.EXPERIMENT,
            subject_id=experiment_id,
            subject_version="4",
        )

    def get_factor_evidence(
        self,
        *,
        query: FactorEvidenceQuery,
        context: EvidenceTemporalContext,
    ) -> ResearchEvidenceReadModel:
        self.calls.append(("factor", (query, context)))
        return _read_model(
            context=self._context,
            kind=ResearchEvidenceKind.FACTOR,
            subject_id=query.factor_id,
            subject_version=str(query.factor_version),
        )

    def get_strategy_evidence(
        self,
        *,
        strategy_id: str,
        version: int,
        context: EvidenceTemporalContext,
    ) -> ResearchEvidenceReadModel:
        self.calls.append(("strategy", (strategy_id, version, context)))
        return _read_model(
            context=self._context,
            kind=ResearchEvidenceKind.STRATEGY,
            subject_id=strategy_id,
            subject_version=str(version),
        )

    def get_backtest_evidence(
        self,
        *,
        run_id: str,
        strategy_id: str,
        strategy_version: str,
        dataset_id: str,
        context: EvidenceTemporalContext,
        include_replay_proof: bool = False,
    ) -> ResearchEvidenceReadModel:
        self.calls.append(
            (
                "backtest",
                (
                    run_id,
                    strategy_id,
                    strategy_version,
                    dataset_id,
                    context,
                    include_replay_proof,
                ),
            )
        )
        return _read_model(
            context=self._context,
            kind=ResearchEvidenceKind.BACKTEST,
            subject_id=run_id,
            subject_version=strategy_version,
        )


@pytest.mark.parametrize(
    ("tool_type", "arguments", "expected_kind"),
    [
        (
            ExperimentEvidenceTool,
            {"experiment_id": "experiment-001", "candidate_id": "candidate-002"},
            ResearchEvidenceKind.EXPERIMENT,
        ),
        (
            FactorEvidenceTool,
            {
                "factor_id": "momentum",
                "factor_version": 2,
                "dataset_id": "dataset-001",
                "universe": "csi-etf",
            },
            ResearchEvidenceKind.FACTOR,
        ),
        (
            StrategyEvidenceTool,
            {"strategy_id": "strategy-001", "version": 3},
            ResearchEvidenceKind.STRATEGY,
        ),
        (
            BacktestEvidenceTool,
            {
                "run_id": "backtest-001",
                "strategy_id": "strategy-001",
                "strategy_version": "3",
                "dataset_id": "dataset-001",
                "include_replay_proof": True,
            },
            ResearchEvidenceKind.BACKTEST,
        ),
    ],
)
def test_research_tools_are_thin_pit_bound_facade_adapters(
    tool_type: type[
        ExperimentEvidenceTool
        | FactorEvidenceTool
        | StrategyEvidenceTool
        | BacktestEvidenceTool
    ],
    arguments: dict[str, object],
    expected_kind: ResearchEvidenceKind,
) -> None:
    context = _context()
    facade = _ResearchFacade(context=context)
    tool = tool_type(facade=cast(ResearchEvidenceQueryPort, facade))

    envelope = tool.invoke(arguments=arguments, context=context)

    assert envelope.tool_name == tool.spec.name
    assert envelope.temporal_context == context
    assert envelope.result["kind"] == expected_kind.value
    assert envelope.result["payload_hash"]
    assert envelope.artifact_refs
    assert envelope.verify_integrity()
    assert facade.calls[0][0] == expected_kind.value


@pytest.mark.pit
def test_factor_tool_injects_snapshot_and_does_not_expose_trusted_context() -> None:
    context = _context()
    facade = _ResearchFacade(context=context)
    tool = FactorEvidenceTool(facade=cast(ResearchEvidenceQueryPort, facade))

    assert "source_snapshot_id" not in tool.spec.input_schema["properties"]
    assert "catalog_snapshot_id" not in tool.spec.input_schema["properties"]
    with pytest.raises(ValueError, match="unexpected arguments"):
        tool.invoke(
            arguments={
                "factor_id": "momentum",
                "factor_version": 2,
                "dataset_id": "dataset-001",
                "universe": "csi-etf",
                "source_snapshot_id": "future-snapshot",
            },
            context=context,
        )

    envelope = tool.invoke(
        arguments={
            "factor_id": "momentum",
            "factor_version": 2,
            "dataset_id": "dataset-001",
            "universe": "csi-etf",
        },
        context=context,
    )
    query, application_context = cast(tuple[object, object], facade.calls[-1][1])
    assert isinstance(query, FactorEvidenceQuery)
    assert query.catalog_snapshot_id == context.source_snapshot_id
    assert application_context == _application_context(context)
    assert envelope.temporal_context.source_snapshot_id != "future-snapshot"


def test_research_tool_propagates_domain_errors_without_fabricating_evidence() -> None:
    class _FailingFacade(_ResearchFacade):
        def get_strategy_evidence(
            self,
            *,
            strategy_id: str,
            version: int,
            context: EvidenceTemporalContext,
        ) -> ResearchEvidenceReadModel:
            del strategy_id, version, context
            raise AppQueryError(
                "strategy evidence failed closed",
                details={"code": "EVIDENCE_SNAPSHOT_MISMATCH"},
            )

    context = _context()
    tool = StrategyEvidenceTool(
        facade=cast(ResearchEvidenceQueryPort, _FailingFacade(context=context))
    )

    with pytest.raises(AppQueryError, match="failed closed"):
        tool.invoke(
            arguments={"strategy_id": "strategy-001", "version": 3},
            context=context,
        )


@pytest.mark.pit
def test_research_tool_rejects_a_facade_result_from_another_temporal_context() -> None:
    trusted = _context()
    future = _context(snapshot_id="future-snapshot")
    facade = _ResearchFacade(context=future)
    tool = ExperimentEvidenceTool(facade=cast(ResearchEvidenceQueryPort, facade))

    with pytest.raises(ValueError, match="temporal context mismatch"):
        tool.invoke(arguments={"experiment_id": "experiment-001"}, context=trusted)
