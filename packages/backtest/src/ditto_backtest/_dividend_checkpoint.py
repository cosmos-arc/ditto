"""Validated checkpoint representation for cash dividend accounting."""

from dataclasses import asdict
from datetime import date
from typing import cast

import orjson
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.accounting.conversions import (
    ShareConversion,
    validate_share_conversions,
)
from ditto_portfolio.accounting.dividends import (
    Distribution,
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


def _event(payload: object) -> Distribution:
    row = payload_mapping(payload)
    # shortcut: 含分红事件的升级前 checkpoint 无法 resume——state_hash 按重序列化
    # 载荷重算，回填默认值必致哈希漂移；缺字段在此响亮失败等价且更诚实，
    # 需要真兼容时引入 payload 版本标记而不是默认值。
    asset_class = payload_str(row, "asset_class")
    if asset_class not in ("stock", "etf"):
        raise ValueError("invalid distribution asset class")
    return Distribution(
        instrument_id=InstrumentId(payload_int(row, "instrument_id")),
        record_date=date.fromisoformat(payload_str(row, "record_date")),
        ex_date=date.fromisoformat(payload_str(row, "ex_date")),
        pay_date=date.fromisoformat(payload_str(row, "pay_date"))
        if row["pay_date"] is not None
        else None,
        gross_per_share=payload_float(row, "gross_per_share"),
        announcement_date=date.fromisoformat(payload_str(row, "announcement_date")),
        source_snapshot_id=payload_str(row, "source_snapshot_id"),
        source_ticker=payload_str(row, "source_ticker"),
        share_ratio=payload_float(row, "share_ratio"),
        listing_date=date.fromisoformat(payload_str(row, "listing_date"))
        if row["listing_date"] is not None
        else None,
        taxable_share_income=payload_float(row, "taxable_share_income"),
        share_tax_basis=payload_str(row, "share_tax_basis"),
        asset_class=asset_class,
    )


def _conversion(payload: object) -> ShareConversion:
    row = payload_mapping(payload)
    return ShareConversion(
        instrument_id=InstrumentId(payload_int(row, "instrument_id")),
        effective_date=date.fromisoformat(payload_str(row, "effective_date")),
        ratio=payload_float(row, "ratio"),
        announcement_date=date.fromisoformat(payload_str(row, "announcement_date")),
        source_snapshot_id=payload_str(row, "source_snapshot_id"),
        source_ticker=payload_str(row, "source_ticker"),
        rounding_note=payload_str(row, "rounding_note"),
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
                date.fromisoformat(payload_str(row, "available_from"))
                if row["available_from"] is not None
                else None,
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
        conversions=tuple(
            _conversion(item) for item in payload_sequence(data, "conversions")
        ),
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
    validate_share_conversions(book.conversions)
    return book
