"""Cash-share entitlements and daily-net FIFO tax, independent of price factors."""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from math import isfinite

from ditto_kernel.identity import InstrumentId


@dataclass(frozen=True)
class CashDividend:
    """An implemented, source-pinned CNY cash dividend for unrestricted A shares."""

    instrument_id: InstrumentId
    record_date: date
    ex_date: date
    pay_date: date
    gross_per_share: float
    announcement_date: date
    source_snapshot_id: str
    source_ticker: str = ""

    def __post_init__(self) -> None:
        """Require complete dates, cash units and an applicable tax regime."""
        if not (
            self.instrument_id > 0
            and date(2013, 1, 1) <= self.record_date
            and self.announcement_date
            < self.record_date
            < self.ex_date
            <= self.pay_date
            and isfinite(self.gross_per_share)
            and self.gross_per_share > 0
            and self.source_snapshot_id
        ):
            raise ValueError("unknown/invalid cash dividend facts or tax regime")
        object.__setattr__(self, "gross_per_share", float(self.gross_per_share))

    @property
    def identity(self) -> str:
        """One distribution per security and record date; conflicts are rejected."""
        return f"{self.instrument_id}:{self.record_date.isoformat()}"

    @property
    def withholding_rate(self) -> float:
        """Initial individual-share withholding under the dated tax regime."""
        return 0.05 if self.record_date < date(2015, 9, 8) else 0.0


def _anniversary(acquired: date, months: int) -> date:
    year, month = divmod(acquired.year * 12 + acquired.month - 1 + months, 12)
    return date(year, month + 1, min(acquired.day, monthrange(year, month + 1)[1]))


def dividend_tax_rate(acquired: date, disposed: date, record: date) -> float:
    """Calendar anniversaries, inclusive boundaries; never approximate by 30/365."""
    if disposed < acquired or record < date(2013, 1, 1):
        raise ValueError("unknown dividend holding period or tax regime")
    if disposed <= _anniversary(acquired, 1):
        return 0.20
    if disposed <= _anniversary(acquired, 12):
        return 0.10
    return 0.05 if record < date(2015, 9, 8) else 0.0


@dataclass(frozen=True)
class DividendLot:
    """Remaining shares acquired on one daily net acquisition date."""

    instrument_id: InstrumentId
    acquired: date
    quantity: int


@dataclass(frozen=True)
class DividendRight:
    """Frozen record-date shares, including rights retained after disposal."""

    event: CashDividend
    acquired: date
    quantity: int
    remaining: int
    accrued: bool = False
    paid: bool = False


@dataclass(frozen=True)
class DividendEntry:
    """Signed CNY movements; receivables are separate from cash movements."""

    event_id: str
    day: str
    kind: str
    amount: float
    quantity: int
    acquired: str = ""


@dataclass(frozen=True)
class DividendBook:
    """Immutable snapshot used by account views, checkpoints and reports."""

    events: tuple[CashDividend, ...] = ()
    lots: tuple[DividendLot, ...] = ()
    rights: tuple[DividendRight, ...] = ()
    entries: tuple[DividendEntry, ...] = ()
    tax_payable: float = 0.0
    closed_day: str = ""
    settled_day: str = ""

    @classmethod
    def start(cls, events: tuple[CashDividend, ...]) -> DividendBook:
        """Collapse identical events and reject conflicting identities."""
        unique: dict[str, CashDividend] = {}
        for event in events:
            previous = unique.setdefault(event.identity, event)
            if previous != event:
                raise ValueError(f"conflicting dividend revision: {event.identity}")
        return cls(events=tuple(sorted(unique.values(), key=lambda e: e.identity)))

    @property
    def receivable(self) -> float:
        """Net declared cash earned but not yet payable."""
        return sum(
            r.quantity * r.event.gross_per_share * (1 - r.event.withholding_rate)
            for r in self.rights
            if r.accrued and not r.paid
        )

    def settle(self, day: str) -> tuple[DividendBook, float]:
        """Accrue at ex date and pay only when due, before trading that session."""
        if not self.events or day == self.settled_day:
            return self, 0.0
        if day < self.settled_day or day < self.closed_day:
            raise ValueError("dividend clock cannot move backwards")
        current = date.fromisoformat(day)
        entries = list(self.entries)
        cash = -self.tax_payable
        if self.tax_payable:
            entries.append(DividendEntry("", day, "tax_payment", cash, 0))
        rights: list[DividendRight] = []
        for original in self.rights:
            right = original
            event = right.event
            amount = (
                right.quantity * event.gross_per_share * (1 - event.withholding_rate)
            )
            if not right.accrued and current >= event.ex_date:
                right = replace(right, accrued=True)
                entries.append(
                    DividendEntry(
                        event.identity,
                        day,
                        "receivable",
                        amount,
                        right.quantity,
                        right.acquired.isoformat(),
                    )
                )
            if not right.paid and current >= event.pay_date:
                right = replace(right, paid=True)
                cash += amount
                entries.append(
                    DividendEntry(
                        event.identity,
                        day,
                        "cash_payment",
                        amount,
                        right.quantity,
                        right.acquired.isoformat(),
                    )
                )
            rights.append(right)
        return replace(
            self,
            rights=tuple(rights),
            entries=tuple(entries),
            tax_payable=0.0,
            settled_day=day,
        ), cash

    def close(self, day: str, holdings: Mapping[InstrumentId, int]) -> DividendBook:
        """Track net daily changes, then freeze record-date rights after trading."""
        if not self.events or day == self.closed_day:
            return self
        if day < self.closed_day or day < self.settled_day:
            raise ValueError("dividend clock cannot move backwards")
        current = date.fromisoformat(day)
        lots, rights, entries = list(self.lots), list(self.rights), list(self.entries)
        payable = self.tax_payable
        for iid in sorted({e.instrument_id for e in self.events}):
            previous = sum(lot.quantity for lot in lots if lot.instrument_id == iid)
            change = holdings.get(iid, 0) - previous
            if change > 0:
                lots.append(DividendLot(iid, current, change))
            elif change < 0:
                payable += _dispose_lots(lots, rights, entries, iid, -change, current)
        lots = [lot for lot in lots if lot.quantity]
        for event in self.events:
            if event.record_date == current:
                rights.extend(
                    DividendRight(event, lot.acquired, lot.quantity, lot.quantity)
                    for lot in lots
                    if lot.instrument_id == event.instrument_id
                )
            elif (
                event.record_date < current
                and (
                    not self.closed_day
                    or event.record_date.isoformat() > self.closed_day
                )
                and any(
                    lot.instrument_id == event.instrument_id
                    and lot.acquired < event.record_date
                    for lot in lots
                )
            ):
                raise ValueError(
                    f"missing dividend record-day holdings: {event.identity}"
                )
        return replace(
            self,
            lots=tuple(lots),
            rights=tuple(rights),
            entries=tuple(entries),
            tax_payable=payable,
            closed_day=day,
        )


def _dispose_lots(
    lots: list[DividendLot],
    rights: list[DividendRight],
    entries: list[DividendEntry],
    iid: InstrumentId,
    remaining: int,
    current: date,
) -> float:
    """Apply daily net disposals to the oldest lots and their retained rights."""
    payable = 0.0
    day = current.isoformat()
    for index, lot in enumerate(lots):
        if lot.instrument_id != iid or not remaining:
            continue
        sold = min(lot.quantity, remaining)
        remaining -= sold
        lots[index] = replace(lot, quantity=lot.quantity - sold)
        for rindex, right in enumerate(rights):
            if right.event.instrument_id != iid or right.acquired != lot.acquired:
                continue
            entitled = min(sold, right.remaining)
            rate = dividend_tax_rate(lot.acquired, current, right.event.record_date)
            tax = (
                entitled
                * right.event.gross_per_share
                * (rate - right.event.withholding_rate)
            )
            payable += tax
            rights[rindex] = replace(right, remaining=right.remaining - entitled)
            if tax:
                entries.append(
                    DividendEntry(
                        right.event.identity,
                        day,
                        "tax_reserved",
                        -tax,
                        entitled,
                        lot.acquired.isoformat(),
                    )
                )
    return payable
