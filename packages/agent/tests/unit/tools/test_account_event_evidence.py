"""The Manual Account tool derives privacy and as-of scope from host authority."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.tools.account_event import AccountEventEvidenceTool
from ditto_application.queries.account_event_evidence_contracts import (
    AccountEventEvidenceQueryPort,
    AccountEventEvidenceReadModel,
    AccountEventEvidenceRedaction,
)
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)


class _Facade:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, AccountEventEvidenceRedaction]] = []

    def get_evidence(
        self,
        *,
        account_id: str,
        as_of: str,
        redaction: AccountEventEvidenceRedaction,
        context: EvidenceTemporalContext,
    ) -> AccountEventEvidenceReadModel:
        self.calls.append((account_id, as_of, redaction))
        ledger_hash = "account-ledger:sha256:" + "b" * 64
        return AccountEventEvidenceReadModel(
            account_id=account_id,
            as_of=as_of,
            ledger_hash=ledger_hash,
            redaction=redaction,
            temporal_context=context,
            payload=EvidencePayloadReadModel.seal(
                schema_version=1,
                value={
                    "account_id": account_id,
                    "as_of": as_of,
                    "ledger_hash": ledger_hash,
                    "redaction": redaction.value,
                    "events": (),
                },
            ),
            artifact_refs=(
                EvidenceArtifactReference(
                    artifact_id=f"{account_id}:{as_of}",
                    artifact_kind="manual_account_ledger",
                    content_hash="b" * 64,
                ),
            ),
            lineage=(f"account-ledger:{ledger_hash}",),
        )


def _context(egress: EgressClass) -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 31, 7, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 30, 16, 30, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 30, 16, tzinfo=UTC),
            source_snapshot_id="portfolio-context:sha256:" + "a" * 64,
            execution_eligible_at="not_applicable",
            allowed_universe=("600519.SH",),
            license_class="approved-private-summary",
            egress_class=egress,
        )
    )


def test_tool_derives_shanghai_date_and_cloud_redaction_from_host_context() -> None:
    facade = _Facade()
    tool = AccountEventEvidenceTool(facade=cast(AccountEventEvidenceQueryPort, facade))

    evidence = tool.invoke(
        arguments={"account_id": "manual-main"},
        context=_context(EgressClass.CLOUD_ALLOWED),
    )

    assert facade.calls == [
        (
            "manual-main",
            "2026-08-31",
            AccountEventEvidenceRedaction.CLOUD_REDACTED,
        )
    ]
    assert evidence.result["kind"] == "manual_account_events"
    assert evidence.verify_integrity()
    assert set(tool.spec.input_schema["properties"]) == {"account_id"}


def test_tool_fails_before_query_when_egress_is_prohibited() -> None:
    facade = _Facade()
    tool = AccountEventEvidenceTool(facade=cast(AccountEventEvidenceQueryPort, facade))

    with pytest.raises(PermissionError, match="prohibited"):
        tool.invoke(
            arguments={"account_id": "manual-main"},
            context=_context(EgressClass.PROHIBITED),
        )

    assert facade.calls == []
