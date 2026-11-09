"""Assemble observed ordinary research rules and market inputs (#723)."""

from collections.abc import Callable
from datetime import date, timedelta

import polars as pl
from ditto_data.services.metadata_service import MetadataService
from ditto_execution.reality.ordinary_equity import (
    MIN_ORDINARY_LISTED_DAYS,
    CashEquityListing,
    ordinary_equity_rules,
    ordinary_execution_fields,
)
from ditto_execution.rules import InMemoryRuleProvider
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import InstrumentRules

from ditto_application.exceptions import AppBuilderError


def build_ordinary_rules(
    metadata: MetadataService,
    instrument_ids: list[int],
    *,
    asset_class: str,
    commission_rate: float,
    start: str,
    end: str,
    historical_roster: list[dict[str, object]] | None = None,
) -> InMemoryRuleProvider:
    """Bind every frozen member to an explicitly covered listing."""
    rules: dict[InstrumentId, InstrumentRules] = {}
    frozen = (
        {int(str(row["instrument_id"])): row for row in historical_roster}
        if historical_roster is not None
        else None
    )
    for iid in instrument_ids:
        record = (
            frozen.get(iid)
            if frozen is not None
            else metadata.instrument.get_instrument(iid)
        )
        if record is None or record.get("asset_class") != asset_class:
            raise AppBuilderError(f"missing or mismatched asset definition: {iid}")
        listing = CashEquityListing(
            instrument_id=InstrumentId(iid),
            ticker=str(record["ticker"]),
            asset_class=asset_class,
            exchange=str(record["exchange"]),
            list_date=str(record["list_date"]),
            delist_date=str(record["delist_date"])
            if record.get("delist_date")
            else None,
        )
        rule_start = start
        if historical_roster is not None:
            rule_start = max(
                start,
                (
                    date.fromisoformat(listing.list_date)
                    + timedelta(days=MIN_ORDINARY_LISTED_DAYS)
                ).isoformat(),
            )
            if rule_start > end:
                continue
        rules[InstrumentId(iid)] = ordinary_equity_rules(
            listing,
            commission_rate=commission_rate,
            start=rule_start,
            end=end,
            historical_reconstruction=historical_roster is not None,
        )
    return InMemoryRuleProvider(
        definitions={iid: rule[0] for iid, rule in rules.items()},
        trading_rules={iid: [rule[1]] for iid, rule in rules.items()},
        fee_schedules={iid: [rule[2]] for iid, rule in rules.items()},
    )


def ordinary_market_transform(
    provider: InMemoryRuleProvider,
    *,
    start_date: str,
    participation: pl.DataFrame | None = None,
) -> Callable[[pl.DataFrame], pl.DataFrame]:
    """Use real status/limits for stocks and the verified ETF limit formula."""
    execution_dates = (
        set(
            participation.filter(pl.col("execution_available"))
            .select("instrument_id", "trade_date")
            .iter_rows()
        )
        if participation is not None
        else None
    )

    def transform(frame: pl.DataFrame) -> pl.DataFrame:
        if frame.is_empty():
            return frame
        ordered = frame.sort(["instrument_id", "trade_date"]).with_columns(
            pl.col("adj_factor").shift(1).over("instrument_id").alias("_previous_adj"),
        )
        rows = ordered.to_dicts()
        for row in rows:
            iid = InstrumentId(int(row["instrument_id"]))
            day = str(row["trade_date"])
            try:
                available = (
                    execution_dates is None or (int(iid), day) in execution_dates
                )
                if day >= start_date and available:
                    row.update(
                        ordinary_execution_fields(
                            row,
                            provider.get_rules(day, [iid])[iid],
                            start_date=start_date,
                        )
                    )
            except ValueError as exc:
                raise AppBuilderError(str(exc)) from exc
            row.pop("_previous_adj")
            if row.get("source") != "tushare":
                raise AppBuilderError(
                    f"unknown execution volume/amount units: {iid} {day}"
                )
            # Tushare daily/fund_daily: volume is lots, amount is CNY thousands.
            row["volume"] *= 100
            row["amount"] *= 1000
        return pl.DataFrame(rows)

    return transform
