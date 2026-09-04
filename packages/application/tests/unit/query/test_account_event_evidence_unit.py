"""Manual account evidence is exact, immutable, and privacy-minimal."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from ditto_application.queries.account_event_evidence import (
    AccountEventEvidenceQueryFacade,
)
from ditto_application.queries.account_event_evidence_contracts import (
    AccountEventEvidenceRedaction,
)
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.evidence_contracts import EvidenceTemporalContext
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEvent,
    AccountEventDraft,
    AccountEventSource,
    AccountEventType,
    AccountKind,
    create_account_event,
)

_NOW = datetime(2026, 8, 31, 7, tzinfo=UTC)


class _Journal:
    def __init__(self, account: AccountDefinition, event: AccountEvent) -> None:
        self._account = account
        self._event = event

    def create_account(self, account: AccountDefinition) -> AccountDefinition:
        raise AssertionError("evidence query must not write")

    def get_account(self, account_id: str) -> AccountDefinition | None:
        return self._account if account_id == self._account.account_id else None

    def append(self, event: AccountEvent) -> AccountEvent:
        raise AssertionError("evidence query must not write")

    def get_event(self, account_id: str, event_id: str) -> AccountEvent | None:
        return self._event if account_id == self._account.account_id else None

    def find_by_idempotency_key(
        self,
        account_id: str,
        idempotency_key: str,
    ) -> AccountEvent | None:
        return None

    def list_events(self, account_id: str) -> tuple[AccountEvent, ...]:
        return (self._event,) if account_id == self._account.account_id else ()


def _facade() -> tuple[AccountEventEvidenceQueryFacade, AccountEvent]:
    account = AccountDefinition(
        account_id="manual-main",
        kind=AccountKind.MANUAL,
        name="private brokerage account",
        opened_at=_NOW,
    )
    event = create_account_event(
        account=account,
        draft=AccountEventDraft(
            event_type=AccountEventType.BUY,
            event_id="private-order-001",
            trade_date="2026-08-31",
            settlement_date="2026-09-01",
            recorded_at=_NOW,
            idempotency_key="private-idempotency-key",
            actor="user:private@example.com",
            source=AccountEventSource.MANUAL_ENTRY,
            instrument_id=InstrumentId(600519),
            quantity=Decimal("100"),
            price=Decimal("123.45"),
            fees=Decimal("5"),
            note="secret brokerage note 8848",
            attachment_refs=("/private/statement.pdf",),
            external_reference="broker-order-secret",
        ),
    )
    query = AccountLedgerQuery(journal=_Journal(account, event))
    return AccountEventEvidenceQueryFacade(query=query), event


def _context() -> EvidenceTemporalContext:
    return EvidenceTemporalContext(
        decision_time=_NOW,
        knowledge_cutoff=_NOW,
        publication_cutoff=_NOW,
        source_snapshot_id="portfolio-context:sha256:" + "a" * 64,
    )


def test_cloud_evidence_omits_free_text_identifiers_and_exact_amounts() -> None:
    facade, event = _facade()

    evidence = facade.get_evidence(
        account_id="manual-main",
        as_of="2026-08-31",
        redaction=AccountEventEvidenceRedaction.CLOUD_REDACTED,
        context=_context(),
    )

    serialized = repr(evidence.payload.value)
    for secret in (
        event.event_id,
        event.idempotency_key,
        event.actor,
        event.note,
        event.attachment_refs[0],
        event.external_reference,
        "123.45",
        "100",
    ):
        assert secret not in serialized
    assert evidence.payload.value["redaction"] == "cloud_redacted"
    assert evidence.payload.value["events"][0]["event_hash"] == event.event_hash
    assert evidence.payload.value["events"][0]["instrument_id"] == 600519
    assert evidence.artifact_refs[0].content_hash in evidence.ledger_hash


def test_local_detail_keeps_financial_terms_but_never_private_free_text() -> None:
    facade, event = _facade()

    evidence = facade.get_evidence(
        account_id="manual-main",
        as_of="2026-08-31",
        redaction=AccountEventEvidenceRedaction.LOCAL_DETAIL,
        context=_context(),
    )

    item = evidence.payload.value["events"][0]
    assert item["quantity"] == "100"
    assert item["price"] == "123.4500"
    assert item["fees"] == "5.00"
    serialized = repr(evidence.payload.value)
    assert event.note not in serialized
    assert event.actor not in serialized
    assert event.idempotency_key not in serialized
    assert event.external_reference not in serialized
