"""Application account commands preserve immutable and idempotent semantics."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ditto_application.commands.account_ledger import (
    CorrectManualEventCommand,
    CreateAccountCommand,
    CreateAccountHandler,
    ManualAccountCommandHandler,
    ManualEventInput,
    RecordManualEventCommand,
    ReverseManualEventCommand,
    TradeEventTerms,
)
from ditto_application.exceptions import AppConflictError, AppNotFoundError
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import AccountDefinition, AccountEvent, AccountKind

NOW = datetime(2026, 8, 31, 9, 30, tzinfo=UTC)


class _MemoryJournal:
    def __init__(self) -> None:
        self.accounts: dict[str, AccountDefinition] = {}
        self.events: dict[str, list[AccountEvent]] = {}

    def create_account(self, account: AccountDefinition) -> AccountDefinition:
        existing = self.accounts.get(account.account_id)
        if existing is not None and existing != account:
            raise RuntimeError("identity conflict")
        self.accounts[account.account_id] = account
        self.events.setdefault(account.account_id, [])
        return account

    def get_account(self, account_id: str) -> AccountDefinition | None:
        return self.accounts.get(account_id)

    def append(self, event: AccountEvent) -> AccountEvent:
        self.events[event.account_id].append(event)
        return event

    def get_event(self, account_id: str, event_id: str) -> AccountEvent | None:
        return next(
            (
                event
                for event in self.events.get(account_id, [])
                if event.event_id == event_id
            ),
            None,
        )

    def find_by_idempotency_key(
        self,
        account_id: str,
        idempotency_key: str,
    ) -> AccountEvent | None:
        return next(
            (
                event
                for event in self.events.get(account_id, [])
                if event.idempotency_key == idempotency_key
            ),
            None,
        )

    def list_events(self, account_id: str) -> tuple[AccountEvent, ...]:
        return tuple(self.events.get(account_id, []))


def _create(journal: _MemoryJournal) -> CreateAccountHandler:
    return CreateAccountHandler(journal=journal)


def _manual(journal: _MemoryJournal) -> ManualAccountCommandHandler:
    return ManualAccountCommandHandler(journal=journal, clock=lambda: NOW)


def _create_manual_account(journal: _MemoryJournal) -> None:
    _create(journal).handle(
        CreateAccountCommand(
            account_id="manual-main",
            kind=AccountKind.MANUAL,
            name="我的账户",
            opened_at=NOW,
        )
    )


def test_create_account_is_idempotent_but_never_converts_kind() -> None:
    journal = _MemoryJournal()
    handler = _create(journal)
    command = CreateAccountCommand(
        account_id="manual-main",
        kind=AccountKind.MANUAL,
        name="我的账户",
        opened_at=NOW,
    )

    assert handler.handle(command).status == "created"
    assert handler.handle(command).status == "replayed"
    with pytest.raises(AppConflictError, match="immutable identity"):
        handler.handle(
            CreateAccountCommand(
                account_id=command.account_id,
                kind=AccountKind.PAPER,
                name="Paper",
                opened_at=NOW,
            )
        )


def test_record_manual_event_is_idempotent_and_conflict_detecting() -> None:
    journal = _MemoryJournal()
    _create_manual_account(journal)
    handler = _manual(journal)
    command = RecordManualEventCommand(
        account_id="manual-main",
        event=ManualEventInput.buy_or_sell(
            side="buy",
            trade_date="2026-08-31",
            settlement_date="2026-09-01",
            idempotency_key="buy-600519-1",
            actor="user:chevy",
            instrument_id=InstrumentId(600519),
            terms=TradeEventTerms(
                quantity=Decimal("100"),
                price=Decimal("100"),
                fees=Decimal("5"),
            ),
        ),
    )

    created = handler.record(command)
    replayed = handler.record(command)

    assert created.status == "created"
    assert replayed.status == "replayed"
    assert replayed.event == created.event
    assert len(journal.list_events(command.account_id)) == 1
    with pytest.raises(AppConflictError, match="idempotency_key"):
        handler.record(
            RecordManualEventCommand(
                account_id=command.account_id,
                event=ManualEventInput.buy_or_sell(
                    side="buy",
                    trade_date="2026-08-31",
                    settlement_date="2026-09-01",
                    idempotency_key="buy-600519-1",
                    actor="user:chevy",
                    instrument_id=InstrumentId(600519),
                    terms=TradeEventTerms(
                        quantity=Decimal("200"),
                        price=Decimal("100"),
                    ),
                ),
            )
        )


def test_correction_and_reversal_return_immutable_receipts() -> None:
    journal = _MemoryJournal()
    _create_manual_account(journal)
    handler = _manual(journal)
    opening = handler.record(
        RecordManualEventCommand(
            account_id="manual-main",
            event=ManualEventInput.cash(
                event_type="opening_cash",
                trade_date="2026-08-31",
                settlement_date="2026-08-31",
                idempotency_key="opening",
                actor="user:chevy",
                amount=Decimal("100000"),
            ),
        )
    )
    buy = handler.record(
        RecordManualEventCommand(
            account_id="manual-main",
            event=ManualEventInput.buy_or_sell(
                side="buy",
                trade_date="2026-08-31",
                settlement_date="2026-09-01",
                idempotency_key="buy",
                actor="user:chevy",
                instrument_id=InstrumentId(600519),
                terms=TradeEventTerms(
                    quantity=Decimal("100"),
                    price=Decimal("100"),
                ),
            ),
        )
    )

    correction = handler.correct(
        CorrectManualEventCommand(
            account_id="manual-main",
            corrects_event_id=buy.event.event_id,
            replacement=ManualEventInput.buy_or_sell(
                side="buy",
                trade_date="2026-08-31",
                settlement_date="2026-09-01",
                idempotency_key="correct-buy",
                actor="user:chevy",
                instrument_id=InstrumentId(600519),
                terms=TradeEventTerms(
                    quantity=Decimal("100"),
                    price=Decimal("90"),
                ),
            ),
        )
    )
    reversal = handler.reverse(
        ReverseManualEventCommand(
            account_id="manual-main",
            reverses_event_id=correction.event.event_id,
            trade_date="2026-08-31",
            settlement_date="2026-08-31",
            idempotency_key="reverse-correction",
            actor="user:chevy",
        )
    )

    assert opening.status == "created"
    assert correction.event.corrects_event_id == buy.event.event_id
    assert reversal.event.reverses_event_id == correction.event.event_id
    assert tuple(
        event.event_type.value for event in journal.list_events("manual-main")
    ) == (
        "opening_cash",
        "buy",
        "correction",
        "reversal",
    )


def test_record_manual_event_rejects_unknown_or_non_manual_account() -> None:
    journal = _MemoryJournal()
    handler = _manual(journal)
    deposit = RecordManualEventCommand(
        account_id="missing",
        event=ManualEventInput.cash(
            event_type="deposit",
            trade_date="2026-08-31",
            settlement_date="2026-08-31",
            idempotency_key="deposit",
            actor="user:chevy",
            amount=Decimal("100"),
        ),
    )

    with pytest.raises(AppNotFoundError, match="account not found"):
        handler.record(deposit)

    _create(journal).handle(
        CreateAccountCommand(
            account_id="paper-main",
            kind=AccountKind.PAPER,
            name="Paper",
            opened_at=NOW,
        )
    )
    with pytest.raises(AppConflictError, match="MANUAL account"):
        handler.record(
            RecordManualEventCommand(
                account_id="paper-main",
                event=deposit.event,
            )
        )
