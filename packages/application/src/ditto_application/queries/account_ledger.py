"""Exact as-of account ledger query facade."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import (
    AccountDefinition,
    AccountEvent,
    AccountEventJournalPort,
    AccountLedgerError,
    ledger_hash,
)
from ditto_portfolio.account_projection import (
    AccountLedgerRebuilder,
    PortfolioSnapshot,
)

from ditto_application.exceptions import AppQueryError

__all__ = [
    "AccountLedgerQuery",
    "AccountLedgerReadModel",
    "LedgerRevision",
]


@dataclass(frozen=True, kw_only=True)
class LedgerRevision:
    """Append-order prefix identity of one complete ledger stream."""

    event_count: int
    ledger_hash: str


@dataclass(frozen=True, kw_only=True)
class AccountLedgerReadModel:
    """Account identity, visible immutable events, and rebuilt projection."""

    account: AccountDefinition
    events: tuple[AccountEvent, ...]
    snapshot: PortfolioSnapshot
    ledger_revision: LedgerRevision


class AccountLedgerQuery:
    """Read one exact account at an explicit calendar date."""

    def __init__(
        self,
        *,
        journal: AccountEventJournalPort,
        rebuilder: AccountLedgerRebuilder | None = None,
    ) -> None:
        self._journal = journal
        self._rebuilder = rebuilder or AccountLedgerRebuilder()

    def get(
        self,
        *,
        account_id: str,
        as_of: str,
        valuation_prices: Mapping[InstrumentId, Decimal] | None = None,
        recorded_through: datetime | None = None,
    ) -> AccountLedgerReadModel:
        """
        Return the exact as-of ledger; never fall back to wall-clock latest.

        ``recorded_through`` additionally hides events whose ``recorded_at`` is
        after that instant, so backfills recorded after a PIT cutoff cannot
        leak into a cutoff-bound read.
        """
        try:
            date.fromisoformat(as_of)
        except ValueError as exc:
            raise AppQueryError(
                "account as_of must be YYYY-MM-DD",
                code="ACCOUNT_AS_OF_INVALID",
                account_id=account_id,
                as_of=as_of,
            ) from exc
        if recorded_through is not None and recorded_through.tzinfo is None:
            raise AppQueryError(
                "account recorded_through needs a timezone",
                code="ACCOUNT_RECORDED_THROUGH_INVALID",
                account_id=account_id,
                as_of=as_of,
            )
        account = self._journal.get_account(account_id)
        if account is None:
            raise AppQueryError(
                "account not found",
                code="ACCOUNT_NOT_FOUND",
                account_id=account_id,
            )
        full_stream = tuple(self._journal.list_events(account_id))
        events = tuple(
            event
            for event in full_stream
            if event.trade_date <= as_of
            and (recorded_through is None or event.recorded_at <= recorded_through)
        )
        try:
            snapshot = self._rebuilder.rebuild(
                account=account,
                events=events,
                as_of=as_of,
                valuation_prices=valuation_prices,
            )
        except AccountLedgerError as exc:
            raise AppQueryError(
                "account ledger rebuild failed",
                code="ACCOUNT_LEDGER_INVALID",
                account_id=account_id,
                as_of=as_of,
                reason=str(exc),
            ) from exc
        return AccountLedgerReadModel(
            account=account,
            events=events,
            snapshot=snapshot,
            ledger_revision=LedgerRevision(
                event_count=len(full_stream),
                ledger_hash=ledger_hash(full_stream),
            ),
        )

    def get_manual(
        self,
        *,
        account_id: str,
        as_of: str,
        valuation_prices: Mapping[InstrumentId, Decimal] | None = None,
        recorded_through: datetime | None = None,
    ) -> AccountLedgerReadModel:
        """Read an exact MANUAL ledger without exposing portfolio types to hosts."""
        result = self.get(
            account_id=account_id,
            as_of=as_of,
            valuation_prices=valuation_prices,
            recorded_through=recorded_through,
        )
        if result.account.kind.value != "manual":
            raise AppQueryError(
                "account is not a MANUAL account",
                code="ACCOUNT_KIND_MISMATCH",
                account_id=account_id,
            )
        return result

    def get_paper(
        self,
        *,
        account_id: str,
        as_of: str,
        valuation_prices: Mapping[InstrumentId, Decimal] | None = None,
        recorded_through: datetime | None = None,
    ) -> AccountLedgerReadModel:
        """Read an exact PAPER ledger without exposing portfolio types to hosts."""
        result = self.get(
            account_id=account_id,
            as_of=as_of,
            valuation_prices=valuation_prices,
            recorded_through=recorded_through,
        )
        if result.account.kind.value != "paper":
            raise AppQueryError(
                "account is not a PAPER account",
                code="ACCOUNT_KIND_MISMATCH",
                account_id=account_id,
            )
        return result
