"""Fail-closed provenance edges for application-to-Agent evidence sealing."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.tools._common import (
    application_context,
    seal_account_event_evidence,
    seal_authoring_preview,
    seal_decision_evidence,
    seal_industry_rotation_evidence,
    seal_instrument_technical_evidence,
    seal_market_context_evidence,
    seal_portfolio_comparison_evidence,
    seal_portfolio_scenario_evidence,
    seal_research_evidence,
    seal_selection_run_evidence,
)
from ditto_application.queries.account_event_evidence_contracts import (
    AccountEventEvidenceReadModel,
    AccountEventEvidenceRedaction,
)
from ditto_application.queries.authoring_preview_contracts import (
    AuthoringPreviewKind,
    AuthoringPreviewReadModel,
)
from ditto_application.queries.evidence_contracts import (
    DecisionEvidenceReadModel,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
    IndustryRotationEvidenceReadModel,
    InstrumentTechnicalEvidenceReadModel,
    MarketContextEvidenceReadModel,
    ResearchEvidenceKind,
    ResearchEvidenceReadModel,
    SelectionRunEvidenceReadModel,
)
from ditto_application.queries.portfolio_comparison_evidence_contracts import (
    PortfolioComparisonEvidenceIdentity,
    PortfolioComparisonEvidenceReadModel,
    PortfolioScenarioEvidenceReadModel,
)

pytestmark = pytest.mark.pit


def _context() -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 31, 9, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 31, 8, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 31, 7, tzinfo=UTC),
            source_snapshot_id="snapshot-set",
            execution_eligible_at="not_applicable",
            allowed_universe=("600000.SH",),
            license_class="internal_research",
            egress_class=EgressClass.LOCAL_ONLY,
        )
    )


def _other_context() -> EvidenceTemporalContext:
    return replace(
        application_context(_context()), source_snapshot_id="snapshot-future"
    )


def _payload(value: dict[str, object]) -> EvidencePayloadReadModel:
    return EvidencePayloadReadModel.seal(schema_version=1, value=value)


def test_research_and_decision_evidence_reject_context_or_kind_drift() -> None:
    context = _context()
    research = ResearchEvidenceReadModel(
        kind=ResearchEvidenceKind.EXPERIMENT,
        subject_id="experiment-1",
        subject_version="1",
        strategy_id=None,
        strategy_version=None,
        dataset_id="dataset-1",
        temporal_context=application_context(context),
        payload=_payload({"status": "ready"}),
        artifact_refs=(),
        lineage=("experiment-1",),
    )
    with pytest.raises(ValueError, match="temporal context mismatch"):
        seal_research_evidence(
            tool_name="research",
            expected_kind="experiment",
            read_model=replace(research, temporal_context=_other_context()),
            context=context,
        )
    with pytest.raises(ValueError, match="kind mismatch"):
        seal_research_evidence(
            tool_name="research",
            expected_kind="factor",
            read_model=research,
            context=context,
        )

    decision = DecisionEvidenceReadModel(
        strategy_id="strategy-1",
        strategy_version="1",
        trade_date="2026-08-31",
        account_id="account-1",
        sleeve_id="sleeve-1",
        readiness="ready",
        temporal_context=application_context(context),
        payload=_payload({"status": "ready"}),
        artifact_refs=(),
        lineage=("decision-1",),
    )
    with pytest.raises(ValueError, match="temporal context mismatch"):
        seal_decision_evidence(
            tool_name="decision",
            kind="decision",
            read_model=replace(decision, temporal_context=_other_context()),
            context=context,
        )


def _market_model() -> MarketContextEvidenceReadModel:
    context = _context()
    return MarketContextEvidenceReadModel(
        status="ready",
        source_snapshot_set_id=context.source_snapshot_id,
        source_snapshot_ids=("snapshot-one",),
        temporal_context=application_context(context),
        payload=_payload(
            {
                "status": "ready",
                "source_snapshot_set_id": context.source_snapshot_id,
                "source_snapshot_ids": ("snapshot-one",),
            }
        ),
        artifact_refs=(),
        lineage=("snapshot-one",),
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("context", "temporal context mismatch"),
        ("snapshot_set", "snapshot set mismatch"),
        ("payload_snapshot_set", "payload snapshot set mismatch"),
        ("payload_snapshots", "payload source snapshots mismatch"),
        ("payload_status", "payload status mismatch"),
    ],
)
def test_market_context_seal_rejects_every_snapshot_identity_drift(
    mutation: str,
    message: str,
) -> None:
    model = _market_model()
    if mutation == "context":
        model = replace(model, temporal_context=_other_context())
    elif mutation == "snapshot_set":
        model = replace(model, source_snapshot_set_id="snapshot-other")
    else:
        value = dict(model.payload.value)
        key = {
            "payload_snapshot_set": "source_snapshot_set_id",
            "payload_snapshots": "source_snapshot_ids",
            "payload_status": "status",
        }[mutation]
        value[key] = "drifted"
        model = replace(model, payload=_payload(value))

    with pytest.raises(ValueError, match=message):
        seal_market_context_evidence(
            tool_name="market-context",
            read_model=model,
            context=_context(),
        )


def _rotation_model() -> IndustryRotationEvidenceReadModel:
    return IndustryRotationEvidenceReadModel(
        snapshot_id="rotation-1",
        status="ready",
        temporal_context=application_context(_context()),
        payload=_payload({"snapshot_id": "rotation-1", "status": "ready"}),
        artifact_refs=(),
        lineage=("rotation-1",),
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("context", "temporal context mismatch"),
        ("snapshot", "payload identity mismatch"),
        ("status", "payload status mismatch"),
    ],
)
def test_industry_rotation_seal_rejects_projection_drift(
    mutation: str,
    message: str,
) -> None:
    model = _rotation_model()
    if mutation == "context":
        model = replace(model, temporal_context=_other_context())
    else:
        value = dict(model.payload.value)
        value["snapshot_id" if mutation == "snapshot" else "status"] = "drifted"
        model = replace(model, payload=_payload(value))
    with pytest.raises(ValueError, match=message):
        seal_industry_rotation_evidence(
            tool_name="rotation",
            read_model=model,
            context=_context(),
        )


def _selection_model() -> SelectionRunEvidenceReadModel:
    return SelectionRunEvidenceReadModel(
        run_id="selection-1",
        status="ready",
        temporal_context=application_context(_context()),
        payload=_payload({"run_id": "selection-1", "status": "ready"}),
        artifact_refs=(),
        lineage=("selection-1",),
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("context", "temporal context mismatch"),
        ("run", "payload identity mismatch"),
        ("status", "payload status mismatch"),
    ],
)
def test_selection_run_seal_rejects_projection_drift(
    mutation: str,
    message: str,
) -> None:
    model = _selection_model()
    if mutation == "context":
        model = replace(model, temporal_context=_other_context())
    else:
        value = dict(model.payload.value)
        value["run_id" if mutation == "run" else "status"] = "drifted"
        model = replace(model, payload=_payload(value))
    with pytest.raises(ValueError, match=message):
        seal_selection_run_evidence(
            tool_name="selection",
            read_model=model,
            context=_context(),
        )


def _technical_model() -> InstrumentTechnicalEvidenceReadModel:
    return InstrumentTechnicalEvidenceReadModel(
        snapshot_id="technical-1",
        instrument_id=600000,
        instrument_name="浦发银行",
        status="ready",
        source_snapshot_ids=("snapshot-one",),
        temporal_context=application_context(_context()),
        payload=_payload(
            {
                "snapshot_id": "technical-1",
                "instrument_id": 600000,
                "status": "ready",
                "source_snapshot_ids": ("snapshot-one",),
            }
        ),
        artifact_refs=(),
        lineage=("technical-1",),
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("context", "temporal context mismatch"),
        ("snapshot", "payload identity mismatch"),
        ("instrument", "payload instrument mismatch"),
        ("status", "payload status mismatch"),
        ("source_snapshots", "payload source snapshots mismatch"),
    ],
)
def test_technical_seal_rejects_projection_drift(
    mutation: str,
    message: str,
) -> None:
    model = _technical_model()
    if mutation == "context":
        model = replace(model, temporal_context=_other_context())
    else:
        value = dict(model.payload.value)
        key = {
            "snapshot": "snapshot_id",
            "instrument": "instrument_id",
            "status": "status",
            "source_snapshots": "source_snapshot_ids",
        }[mutation]
        value[key] = "drifted"
        model = replace(model, payload=_payload(value))
    with pytest.raises(ValueError, match=message):
        seal_instrument_technical_evidence(
            tool_name="technical",
            read_model=model,
            context=_context(),
        )


def _portfolio_identity() -> PortfolioComparisonEvidenceIdentity:
    return PortfolioComparisonEvidenceIdentity(
        strategy_id="strategy-1",
        model_portfolio_id="model-1",
        paper_account_id="paper-1",
        manual_account_id="manual-1",
        paper_session_id="session-1",
    )


def _comparison_model() -> PortfolioComparisonEvidenceReadModel:
    return PortfolioComparisonEvidenceReadModel(
        identity=_portfolio_identity(),
        as_of="2026-08-31",
        valuation_snapshot_id="valuation-1",
        source_snapshot_set_id=_context().source_snapshot_id,
        source_snapshot_ids=("snapshot-one",),
        temporal_context=application_context(_context()),
        payload=_payload(
            {
                "as_of": "2026-08-31",
                "valuation_snapshot_id": "valuation-1",
                "source_snapshot_ids": ("snapshot-one",),
            }
        ),
        artifact_refs=(),
        lineage=("comparison-1",),
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("context", "temporal context mismatch"),
        ("snapshot_set", "snapshot set mismatch"),
        ("as_of", "payload as_of mismatch"),
        ("valuation", "payload valuation mismatch"),
        ("snapshots", "payload snapshots mismatch"),
    ],
)
def test_portfolio_comparison_seal_rejects_projection_drift(
    mutation: str,
    message: str,
) -> None:
    model = _comparison_model()
    if mutation == "context":
        model = replace(model, temporal_context=_other_context())
    elif mutation == "snapshot_set":
        model = replace(model, source_snapshot_set_id="snapshot-other")
    else:
        value = dict(model.payload.value)
        key = {
            "as_of": "as_of",
            "valuation": "valuation_snapshot_id",
            "snapshots": "source_snapshot_ids",
        }[mutation]
        value[key] = "drifted"
        model = replace(model, payload=_payload(value))
    with pytest.raises(ValueError, match=message):
        seal_portfolio_comparison_evidence(
            tool_name="comparison",
            read_model=model,
            context=_context(),
        )


def _scenario_model() -> PortfolioScenarioEvidenceReadModel:
    return PortfolioScenarioEvidenceReadModel(
        identity=_portfolio_identity(),
        baseline_kind="model",
        as_of="2026-08-31",
        valuation_snapshot_id="valuation-1",
        source_snapshot_set_id=_context().source_snapshot_id,
        source_snapshot_ids=("snapshot-one",),
        temporal_context=application_context(_context()),
        payload=_payload(
            {
                "baseline_kind": "model",
                "risk": {
                    "as_of": "2026-08-31",
                    "valuation_snapshot_id": "valuation-1",
                    "source_snapshot_ids": ("snapshot-one",),
                },
            }
        ),
        artifact_refs=(),
        lineage=("scenario-1",),
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("context", "temporal context mismatch"),
        ("snapshot_set", "snapshot set mismatch"),
        ("baseline", "payload baseline mismatch"),
        ("risk", "risk payload is invalid"),
        ("as_of", "payload as_of mismatch"),
        ("valuation", "payload valuation mismatch"),
        ("snapshots", "payload snapshots mismatch"),
    ],
)
def test_portfolio_scenario_seal_rejects_projection_drift(
    mutation: str,
    message: str,
) -> None:
    model = _scenario_model()
    if mutation == "context":
        model = replace(model, temporal_context=_other_context())
    elif mutation == "snapshot_set":
        model = replace(model, source_snapshot_set_id="snapshot-other")
    else:
        value = dict(model.payload.value)
        if mutation == "baseline":
            value["baseline_kind"] = "drifted"
        elif mutation == "risk":
            value["risk"] = "drifted"
        else:
            risk = dict(value["risk"])
            key = {
                "as_of": "as_of",
                "valuation": "valuation_snapshot_id",
                "snapshots": "source_snapshot_ids",
            }[mutation]
            risk[key] = "drifted"
            value["risk"] = risk
        model = replace(model, payload=_payload(value))
    with pytest.raises(ValueError, match=message):
        seal_portfolio_scenario_evidence(
            tool_name="scenario",
            read_model=model,
            context=_context(),
        )


def _account_model() -> AccountEventEvidenceReadModel:
    return AccountEventEvidenceReadModel(
        account_id="account-1",
        as_of="2026-08-31",
        ledger_hash="a" * 64,
        redaction=AccountEventEvidenceRedaction.LOCAL_DETAIL,
        temporal_context=application_context(_context()),
        payload=_payload(
            {
                "account_id": "account-1",
                "as_of": "2026-08-31",
                "ledger_hash": "a" * 64,
                "redaction": "local_detail",
            }
        ),
        artifact_refs=(),
        lineage=("account-1",),
    )


def test_account_event_seal_rejects_context_and_payload_identity_drift() -> None:
    model = _account_model()
    with pytest.raises(ValueError, match="temporal context mismatch"):
        seal_account_event_evidence(
            tool_name="account",
            read_model=replace(model, temporal_context=_other_context()),
            context=_context(),
        )
    value = dict(model.payload.value)
    value["ledger_hash"] = "b" * 64
    with pytest.raises(ValueError, match="payload identity mismatch"):
        seal_account_event_evidence(
            tool_name="account",
            read_model=replace(model, payload=_payload(value)),
            context=_context(),
        )


def _author_model() -> AuthoringPreviewReadModel:
    return AuthoringPreviewReadModel(
        kind=AuthoringPreviewKind.DRAFT,
        subject_id="strategy-1",
        subject_version="1",
        valid=True,
        changed=False,
        payload=_payload(
            {
                "operation": "draft",
                "valid": True,
                "changed": False,
                "publishable": False,
            }
        ),
        lineage=("strategy-1",),
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("kind", "kind mismatch"),
        ("hash", "payload hash mismatch"),
        ("operation", "operation mismatch"),
        ("valid", "validity mismatch"),
        ("changed", "change flag mismatch"),
        ("publishable", "must not be publishable"),
    ],
)
def test_authoring_preview_seal_rejects_executable_identity_drift(
    mutation: str,
    message: str,
) -> None:
    model = _author_model()
    expected_kind = "draft"
    if mutation == "kind":
        expected_kind = "compile"
    elif mutation == "hash":
        model = replace(model, payload=replace(model.payload, payload_hash="0" * 64))
    else:
        value = dict(model.payload.value)
        value[mutation] = not value[mutation] if mutation != "operation" else "compile"
        model = replace(model, payload=_payload(value))
    with pytest.raises(ValueError, match=message):
        seal_authoring_preview(
            tool_name="author",
            expected_kind=expected_kind,
            read_model=model,
            context=_context(),
        )
