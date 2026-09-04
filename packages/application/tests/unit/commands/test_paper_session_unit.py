"""PAP-05: idempotent paper session command lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from ditto_application.commands.paper_session import (
    CreatePaperSessionCommand,
    PaperSessionCommandHandler,
    PausePaperSessionCommand,
    StartPaperSessionCommand,
)
from ditto_application.exceptions import AppConflictError
from ditto_execution.paper.session import InMemoryPaperSessionStore
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEventJournalPort,
    AccountKind,
)

NOW = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)


class _AccountJournal:
    def get_account(self, account_id: str) -> AccountDefinition | None:
        if account_id != "paper-account-1":
            return None
        return AccountDefinition(
            account_id=account_id,
            kind=AccountKind.PAPER,
            name="Paper Account",
            opened_at=NOW,
        )


def _handler() -> PaperSessionCommandHandler:
    return PaperSessionCommandHandler(
        store=InMemoryPaperSessionStore(),
        account_journal=cast(AccountEventJournalPort, _AccountJournal()),
        clock=lambda: NOW,
    )


def test_create_start_pause_and_exact_replay() -> None:
    handler = _handler()
    create = CreatePaperSessionCommand(
        session_id="session-1",
        account_id="paper-account-1",
        strategy_id="strategy-1",
        trade_date="2026-08-31",
        idempotency_key="create-1",
    )
    created = handler.create(create)
    assert created.session.status == "created"
    assert handler.create(create).status == "replayed"

    started = handler.start(
        StartPaperSessionCommand(
            session_id="session-1",
            idempotency_key="start-1",
        )
    )
    assert started.session.status == "running"
    assert (
        handler.start(
            StartPaperSessionCommand(
                session_id="session-1",
                idempotency_key="start-1",
            )
        ).status
        == "replayed"
    )

    paused = handler.pause(
        PausePaperSessionCommand(
            session_id="session-1",
            idempotency_key="pause-1",
            reason="EOD",
        )
    )
    assert paused.session.status == "paused"


def test_invalid_transition_and_idempotency_conflict_fail_closed() -> None:
    handler = _handler()
    create = CreatePaperSessionCommand(
        session_id="session-1",
        account_id="paper-account-1",
        strategy_id="strategy-1",
        trade_date="2026-08-31",
        idempotency_key="create-1",
    )
    handler.create(create)
    with pytest.raises(AppConflictError, match="running"):
        handler.pause(
            PausePaperSessionCommand(
                session_id="session-1",
                idempotency_key="pause-created",
                reason="invalid",
            )
        )
    with pytest.raises(AppConflictError, match="idempotency"):
        handler.create(
            CreatePaperSessionCommand(
                session_id="session-1",
                account_id="paper-account-1",
                strategy_id="changed-strategy",
                trade_date="2026-08-31",
                idempotency_key="create-1",
            )
        )
