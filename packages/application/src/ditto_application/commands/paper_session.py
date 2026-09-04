"""Idempotent create/start/pause commands for formal paper sessions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

import orjson
from ditto_execution.paper.session import (
    PaperSession,
    PaperSessionConflictError,
    PaperSessionMutation,
    PaperSessionStatus,
    PaperSessionStorePort,
)
from ditto_portfolio.account_ledger import AccountEventJournalPort, AccountKind

from ditto_application.exceptions import (
    AppCommandError,
    AppConflictError,
    AppNotFoundError,
)
from ditto_application.paper_contracts import (
    PaperReconciliationInfo,
    PaperSessionInfo,
    to_paper_reconciliation_info,
    to_paper_session_info,
)
from ditto_application.processes.execution.reconcile_paper_account import (
    ReconcilePaperAccount,
)

__all__ = [
    "CreatePaperSessionCommand",
    "PaperSessionCommandHandler",
    "PaperSessionCommandReceipt",
    "PausePaperSessionCommand",
    "ReconcilePaperSessionCommand",
    "StartPaperSessionCommand",
]


@dataclass(frozen=True, kw_only=True)
class CreatePaperSessionCommand:
    """Create one session against an immutable PAPER account."""

    session_id: str
    account_id: str
    strategy_id: str
    trade_date: str
    idempotency_key: str


@dataclass(frozen=True, kw_only=True)
class StartPaperSessionCommand:
    """Start a created or paused paper session."""

    session_id: str
    idempotency_key: str


@dataclass(frozen=True, kw_only=True)
class PausePaperSessionCommand:
    """Pause a running paper session with an operational reason."""

    session_id: str
    idempotency_key: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class ReconcilePaperSessionCommand:
    """Request one exactly identified EOD reconciliation."""

    session_id: str
    idempotency_key: str


@dataclass(frozen=True, kw_only=True)
class PaperSessionCommandReceipt:
    """Created or replayed lifecycle mutation receipt."""

    status: str
    action: str
    session: PaperSessionInfo


class PaperSessionCommandHandler:
    """Own session lifecycle policy while depending only on execution ports."""

    def __init__(
        self,
        *,
        store: PaperSessionStorePort,
        account_journal: AccountEventJournalPort,
        clock: Callable[[], datetime],
        reconciler: ReconcilePaperAccount | None = None,
    ) -> None:
        self._store = store
        self._account_journal = account_journal
        self._clock = clock
        self._reconciler = reconciler

    def create(self, command: CreatePaperSessionCommand) -> PaperSessionCommandReceipt:
        """Create or exactly replay one paper session."""
        request_hash = _hash("create", command)
        replay = self._replay(
            command.session_id,
            command.idempotency_key,
            "create",
            request_hash,
        )
        if replay is not None:
            return replay
        account = self._account_journal.get_account(command.account_id)
        if account is None:
            raise AppNotFoundError(f"paper account not found: {command.account_id}")
        if account.kind is not AccountKind.PAPER:
            raise AppConflictError("paper session requires a PAPER account")
        timestamp = self._clock()
        try:
            session = PaperSession(
                session_id=command.session_id,
                account_id=command.account_id,
                strategy_id=command.strategy_id,
                trade_date=command.trade_date,
                status=PaperSessionStatus.CREATED,
                revision=0,
                created_at=timestamp,
                updated_at=timestamp,
            )
            mutation = PaperSessionMutation(
                session_id=command.session_id,
                idempotency_key=command.idempotency_key,
                action="create",
                request_hash=request_hash,
                resulting_session=session,
            )
            self._store.create_session(session, mutation)
        except ValueError as exc:
            raise AppCommandError(str(exc)) from exc
        except PaperSessionConflictError as exc:
            raise AppConflictError(str(exc)) from exc
        return PaperSessionCommandReceipt(
            status="created",
            action="create",
            session=to_paper_session_info(session),
        )

    def start(self, command: StartPaperSessionCommand) -> PaperSessionCommandReceipt:
        """Start or exactly replay one lifecycle transition."""
        return self._transition(
            session_id=command.session_id,
            idempotency_key=command.idempotency_key,
            action="start",
            payload=command,
        )

    def pause(self, command: PausePaperSessionCommand) -> PaperSessionCommandReceipt:
        """Pause or exactly replay one lifecycle transition."""
        return self._transition(
            session_id=command.session_id,
            idempotency_key=command.idempotency_key,
            action="pause",
            payload=command,
            reason=command.reason,
        )

    def reconcile(
        self,
        command: ReconcilePaperSessionCommand,
    ) -> PaperReconciliationInfo:
        """Run one exactly identified EOD reconciliation."""
        if self._reconciler is None:
            raise AppCommandError("paper reconciler is not configured")
        return to_paper_reconciliation_info(
            self._reconciler.reconcile(
                session_id=command.session_id,
                idempotency_key=command.idempotency_key,
                reconciled_at=self._clock(),
            )
        )

    def _transition(
        self,
        *,
        session_id: str,
        idempotency_key: str,
        action: str,
        payload: object,
        reason: str | None = None,
    ) -> PaperSessionCommandReceipt:
        request_hash = _hash(action, payload)
        replay = self._replay(
            session_id,
            idempotency_key,
            action,
            request_hash,
        )
        if replay is not None:
            return replay
        current = self._store.get_session(session_id)
        if current is None:
            raise AppNotFoundError(f"paper session not found: {session_id}")
        try:
            updated = (
                current.start(updated_at=self._clock())
                if action == "start"
                else current.pause(
                    updated_at=self._clock(),
                    reason=reason or "",
                )
            )
            mutation = PaperSessionMutation(
                session_id=session_id,
                idempotency_key=idempotency_key,
                action=action,
                request_hash=request_hash,
                resulting_session=updated,
            )
            self._store.update_session(
                updated,
                expected_revision=current.revision,
                mutation=mutation,
            )
        except ValueError as exc:
            raise AppCommandError(str(exc)) from exc
        except PaperSessionConflictError as exc:
            raise AppConflictError(str(exc)) from exc
        return PaperSessionCommandReceipt(
            status="created",
            action=action,
            session=to_paper_session_info(updated),
        )

    def _replay(
        self,
        session_id: str,
        idempotency_key: str,
        action: str,
        request_hash: str,
    ) -> PaperSessionCommandReceipt | None:
        existing = self._store.get_mutation(session_id, idempotency_key)
        if existing is None:
            return None
        if existing.action != action or existing.request_hash != request_hash:
            raise AppConflictError("paper session idempotency payload conflict")
        return PaperSessionCommandReceipt(
            status="replayed",
            action=action,
            session=to_paper_session_info(existing.resulting_session),
        )


def _hash(action: str, payload: object) -> str:
    encoded = orjson.dumps(
        {"action": action, "payload": payload},
        option=orjson.OPT_SERIALIZE_DATACLASS | orjson.OPT_SORT_KEYS,
    )
    return f"paper-command:sha256:{sha256(encoded).hexdigest()}"
