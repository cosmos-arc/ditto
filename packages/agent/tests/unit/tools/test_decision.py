from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.tools.decision import DecisionEvidenceTool
from ditto_agent.tools.portfolio import PortfolioEvidenceTool
from ditto_agent.tools.risk import RiskEvidenceTool
from ditto_application.queries.evidence_contracts import (
    DecisionEvidenceQueryPort,
    DecisionEvidenceReadModel,
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 12, 7, 0, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 12, 6, 55, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 12, 6, 50, tzinfo=UTC),
            source_snapshot_id="snapshot-20260812",
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH", "510500.SH"),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


class _DecisionFacade:
    def __init__(self, *, context: TemporalToolContext) -> None:
        self._context = context
        self.calls: list[dict[str, object]] = []

    def get_evidence(
        self,
        *,
        strategy_id: str,
        strategy_version: str,
        trade_date: str,
        account_id: str,
        sleeve_id: str,
        context: EvidenceTemporalContext,
    ) -> DecisionEvidenceReadModel:
        self.calls.append(
            {
                "strategy_id": strategy_id,
                "strategy_version": strategy_version,
                "trade_date": trade_date,
                "account_id": account_id,
                "sleeve_id": sleeve_id,
                "context": context,
            }
        )
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value={
                "portfolio_construction": {"gross_exposure": 0.8},
                "tail_risk": {"expected_shortfall": 0.03},
                "readiness": "ready",
            },
        )
        return DecisionEvidenceReadModel(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            trade_date=trade_date,
            account_id=account_id,
            sleeve_id=sleeve_id,
            readiness="ready",
            temporal_context=context,
            payload=payload,
            artifact_refs=(
                EvidenceArtifactReference(
                    artifact_id=(
                        f"daily-decision-v3:{strategy_id}:{trade_date}:{account_id}"
                    ),
                    artifact_kind="daily_decision_v3",
                    content_hash=payload.payload_hash,
                ),
            ),
            lineage=(
                f"strategy:{strategy_id}:v{strategy_version}",
                f"decision:{trade_date}:{account_id}",
            ),
        )


@pytest.mark.parametrize(
    ("tool_type", "expected_kind"),
    [
        (PortfolioEvidenceTool, "portfolio"),
        (RiskEvidenceTool, "risk"),
        (DecisionEvidenceTool, "daily_decision_v3"),
    ],
)
def test_decision_projection_tools_use_one_exact_application_facade(
    tool_type: type[PortfolioEvidenceTool | RiskEvidenceTool | DecisionEvidenceTool],
    expected_kind: str,
) -> None:
    context = _context()
    facade = _DecisionFacade(context=context)
    tool = tool_type(facade=cast(DecisionEvidenceQueryPort, facade))
    arguments = {
        "strategy_id": "strategy-001",
        "strategy_version": "3",
        "trade_date": "2026-08-12",
        "account_id": "account-001",
        "sleeve_id": "core",
    }

    envelope = tool.invoke(arguments=arguments, context=context)

    assert envelope.result["kind"] == expected_kind
    assert envelope.result["readiness"] == "ready"
    assert envelope.temporal_context == context
    assert envelope.verify_integrity()
    assert facade.calls == [
        {
            **arguments,
            "context": EvidenceTemporalContext(
                decision_time=context.decision_time,
                knowledge_cutoff=context.knowledge_cutoff,
                publication_cutoff=context.publication_cutoff,
                source_snapshot_id=context.source_snapshot_id,
            ),
        }
    ]


def test_decision_projection_schema_cannot_override_host_context() -> None:
    context = _context()
    facade = _DecisionFacade(context=context)
    tool = DecisionEvidenceTool(facade=cast(DecisionEvidenceQueryPort, facade))

    properties = cast(dict[str, object], tool.spec.input_schema["properties"])
    assert {
        "decision_time",
        "knowledge_cutoff",
        "publication_cutoff",
        "source_snapshot_id",
    }.isdisjoint(properties)
    with pytest.raises(ValueError, match="unexpected arguments"):
        tool.invoke(
            arguments={
                "strategy_id": "strategy-001",
                "strategy_version": "3",
                "trade_date": "2026-08-12",
                "account_id": "account-001",
                "sleeve_id": "core",
                "knowledge_cutoff": "2026-08-13T00:00:00Z",
            },
            context=context,
        )
