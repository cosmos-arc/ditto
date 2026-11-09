"""Validated checkpoint representation for cash dividend accounting."""

from dataclasses import asdict
from datetime import date
from typing import cast

import orjson
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.accounting.dividends import (
    CashDividend,
    DividendBook,
    DividendEntry,
    DividendLot,
    DividendRight,
)

from ditto_backtest._checkpoint_codec import (
    payload_float,
    payload_int,
    payload_mapping,
    payload_sequence,
    payload_str,
)


def dividend_payload(book: DividendBook) -> dict[str, object]:
    """Use the same JSON primitive representation before and after persistence."""
    return cast(dict[str, object], orjson.loads(orjson.dumps(asdict(book))))


def _event(payload: object) -> CashDividend:
    row = payload_mapping(payload)
    return CashDividend(
        instrument_id=InstrumentId(payload_int(row, "instrument_id")),
        record_date=date.fromisoformat(payload_str(row, "record_date")),
        ex_date=date.fromisoformat(payload_str(row, "ex_date")),
        pay_date=date.fromisoformat(payload_str(row, "pay_date")),
        gross_per_share=payload_float(row, "gross_per_share"),
        announcement_date=date.fromisoformat(payload_str(row, "announcement_date")),
        source_snapshot_id=payload_str(row, "source_snapshot_id"),
        source_ticker=payload_str(row, "source_ticker"),
    )


def dividend_from_payload(payload: object) -> DividendBook:
    """Reject malformed amounts, holdings and flags at the persistence boundary."""
    data = payload_mapping(payload)
    lots: list[DividendLot] = []
    for item in payload_sequence(data, "lots"):
        row = payload_mapping(item)
        lots.append(
            DividendLot(
                InstrumentId(payload_int(row, "instrument_id")),
                date.fromisoformat(payload_str(row, "acquired")),
                payload_int(row, "quantity"),
            )
        )
    rights: list[DividendRight] = []
    for item in payload_sequence(data, "rights"):
        row = payload_mapping(item)
        accrued, paid = row["accrued"], row["paid"]
        if type(accrued) is not bool or type(paid) is not bool:
            raise ValueError("invalid dividend state flags")
        rights.append(
            DividendRight(
                _event(row["event"]),
                date.fromisoformat(payload_str(row, "acquired")),
                payload_int(row, "quantity"),
                payload_int(row, "remaining"),
                accrued,
                paid,
            )
        )
    entries: list[DividendEntry] = []
    for item in payload_sequence(data, "entries"):
        row = payload_mapping(item)
        entries.append(
            DividendEntry(
                payload_str(row, "event_id"),
                payload_str(row, "day"),
                payload_str(row, "kind"),
                payload_float(row, "amount"),
                payload_int(row, "quantity"),
                payload_str(row, "acquired"),
            )
        )
    book = DividendBook(
        events=tuple(_event(item) for item in payload_sequence(data, "events")),
        lots=tuple(lots),
        rights=tuple(rights),
        entries=tuple(entries),
        tax_payable=payload_float(data, "tax_payable"),
        closed_day=payload_str(data, "closed_day"),
        settled_day=payload_str(data, "settled_day"),
    )
    if (
        book.tax_payable < 0
        or any(lot.quantity <= 0 or lot.instrument_id <= 0 for lot in lots)
        or any(
            r.quantity <= 0
            or not 0 <= r.remaining <= r.quantity
            or (r.paid and not r.accrued)
            or r.acquired > r.event.record_date
            for r in rights
        )
    ):
        raise ValueError("invalid dividend checkpoint holdings or tax")
    for day in (book.closed_day, book.settled_day):
        if day and date.fromisoformat(day).isoformat() != day:
            raise ValueError("invalid dividend checkpoint date")
    DividendBook.start(book.events)
    return book
