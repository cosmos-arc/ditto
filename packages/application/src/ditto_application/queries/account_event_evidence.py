"""Manual Account event evidence with deterministic pre-model redaction."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from ditto_portfolio.account_ledger import AccountEvent

from ditto_application.exceptions import AppQueryError
from ditto_application.queries.account_event_evidence_contracts import (
    AccountEventEvidenceReadModel,
    AccountEventEvidenceRedaction,
)
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.evidence_contracts import (
    EvidenceArtifactReference,
    EvidencePayloadReadModel,
    EvidenceTemporalContext,
)

__all__ = ["AccountEventEvidenceQueryFacade"]

_LEDGER_HASH_PREFIX = "account-ledger:sha256:"


def _decimal(value: Decimal) -> str:
    return format(value, "f")


def _event_payload(
    event: AccountEvent,
    *,
    redaction: AccountEventEvidenceRedaction,
) -> Mapping[str, object]:
    # event_hash authenticates the full immutable source event. Free text and
    # operator/broker identifiers are intentionally absent from both modes.
    payload: dict[str, object] = {
        "event_hash": event.event_hash,
        "event_type": event.event_type.value,
        "trade_date": event.trade_date,
        "settlement_date": event.settlement_date,
        "source": event.source.value,
        "instrument_id": int(event.instrument_id) if event.instrument_id else None,
        "is_reversal": event.reverses_event_id is not None,
        "is_correction": event.corrects_event_id is not None,
    }
    if redaction is AccountEventEvidenceRedaction.LOCAL_DETAIL:
        payload.update(
            {
                "currency": event.currency,
                "quantity": _decimal(event.quantity),
                "price": _decimal(event.price),
                "gross_amount": _decimal(event.gross_amount),
                "fees": _decimal(event.fees),
                "tax": _decimal(event.tax),
                "net_cash": _decimal(event.net_cash),
            }
        )
    else:
        payload["financial_terms"] = "redacted"
    return payload


class AccountEventEvidenceQueryFacade:
    """Project an exact Manual ledger without leaking private user annotations."""

    def __init__(self, *, query: AccountLedgerQuery) -> None:
        self._query = query

    def get_evidence(
        self,
        *,
        account_id: str,
        as_of: str,
        redaction: AccountEventEvidenceRedaction,
        context: EvidenceTemporalContext,
    ) -> AccountEventEvidenceReadModel:
        """Read one exact date and apply the host-selected redaction before return."""
        result = self._query.get_manual(account_id=account_id, as_of=as_of)
        ledger_hash = result.snapshot.ledger_hash
        if not ledger_hash.startswith(_LEDGER_HASH_PREFIX):
            raise AppQueryError(
                "manual account ledger hash is invalid",
                reason="invalid_manual_account_ledger_hash",
                account_id=account_id,
                as_of=as_of,
            )
        content_hash = ledger_hash.removeprefix(_LEDGER_HASH_PREFIX)
        events = tuple(
            _event_payload(event, redaction=redaction) for event in result.events
        )
        payload = EvidencePayloadReadModel.seal(
            schema_version=1,
            value={
                "account_id": account_id,
                "as_of": as_of,
                "ledger_hash": ledger_hash,
                "redaction": redaction.value,
                "event_count": len(events),
                "events": events,
            },
        )
        return AccountEventEvidenceReadModel(
            account_id=account_id,
            as_of=as_of,
            ledger_hash=ledger_hash,
            redaction=redaction,
            temporal_context=context,
            payload=payload,
            artifact_refs=(
                EvidenceArtifactReference(
                    artifact_id=f"{account_id}:{as_of}",
                    artifact_kind="manual_account_ledger",
                    content_hash=content_hash,
                ),
            ),
            lineage=(ledger_hash, *(event.event_hash for event in result.events)),
        )
