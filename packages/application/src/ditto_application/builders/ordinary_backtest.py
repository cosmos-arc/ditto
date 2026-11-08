"""Assemble observed ordinary research rules and market inputs (#723)."""

from collections.abc import Callable
from decimal import Decimal

import polars as pl
from ditto_data.services.metadata_service import MetadataService
from ditto_execution.reality.ordinary_equity import (
    CashEquityListing,
    ordinary_equity_rules,
)
from ditto_execution.reality.price import round_to_tick
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
) -> InMemoryRuleProvider:
    """Bind every frozen member to an explicitly covered listing."""
    rules: dict[InstrumentId, InstrumentRules] = {}
    for iid in instrument_ids:
        record = metadata.instrument.get_instrument(iid)
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
        rules[InstrumentId(iid)] = ordinary_equity_rules(
            listing,
            commission_rate=commission_rate,
            start=start,
            end=end,
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
) -> Callable[[pl.DataFrame], pl.DataFrame]:
    """Use real status/limits for stocks and the verified ETF limit formula."""

    def transform(frame: pl.DataFrame) -> pl.DataFrame:
        if frame.is_empty():
            return frame
        ordered = frame.sort(["instrument_id", "trade_date"]).with_columns(
            pl.col("adj_factor").shift(1).over("instrument_id").alias("_previous_adj"),
        )
        actions = ordered.filter(
            (pl.col("trade_date").cast(pl.String) >= start_date)
            & (pl.col("adj_factor") != pl.col("_previous_adj"))
        )
        if not actions.is_empty():
            raise ValueError(
                "corporate action requires cash/share accounting: "
                + f"{actions.select('instrument_id', 'trade_date').to_dicts()}"
            )
        rows = ordered.drop("_previous_adj").to_dicts()
        for row in rows:
            iid = InstrumentId(int(row["instrument_id"]))
            day = str(row["trade_date"])
            definition, rule, _ = provider.get_rules(day, [iid])[iid]
            if definition.asset_class == "stock":
                if row.get("is_st") is not False:
                    raise ValueError(
                        f"unverified risk-warning rule/status: {iid} {day}"
                    )
            else:
                # Positive recorded turnover proves trading occurred. A zero/missing
                # quote is not evidence of suspension: refuse an invented status.
                if row.get("volume") is None or row["volume"] <= 0:
                    raise ValueError(f"unknown ETF suspension/valuation: {iid} {day}")
                previous = row.get("pre_close")
                if previous is None or previous <= 0 or rule.price_limit_pct is None:
                    raise ValueError(f"missing ETF limit inputs: {iid} {day}")
                previous_decimal = Decimal(str(previous))
                band = Decimal(str(rule.price_limit_pct))
                row["limit_up"] = round_to_tick(
                    previous_decimal * (1 + band), definition.tick_size
                )
                row["limit_down"] = round_to_tick(
                    previous_decimal * (1 - band), definition.tick_size
                )
                row["is_suspended"] = False
            if row.get("source") != "tushare":
                raise ValueError(f"unknown execution volume/amount units: {iid} {day}")
            # Tushare daily/fund_daily: volume is lots, amount is CNY thousands.
            row["volume"] *= 100
            row["amount"] *= 1000
        return pl.DataFrame(rows)

    return transform
