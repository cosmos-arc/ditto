"""Assemble observed ordinary research rules and market inputs (#723)."""

from collections.abc import Callable
from dataclasses import dataclass

import polars as pl
from ditto_data.services.metadata_service import MetadataService
from ditto_execution.reality.ordinary_equity import (
    CashEquityListing,
    cash_stock_board,
    ordinary_equity_rules,
    ordinary_execution_fields,
    stock_rule_history,
)
from ditto_execution.reality.ordinary_etf import etf_rule_history
from ditto_execution.rules import InMemoryRuleProvider
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import InstrumentRules
from ditto_portfolio.accounting.dividends import Distribution

from ditto_application.exceptions import AppBuilderError


@dataclass(frozen=True)
class HistoricalRuleInputs:
    """The frozen listing, calendar and status evidence of one ordinary request."""

    roster: list[dict[str, object]]
    trading_days: list[str]
    stock_status: pl.DataFrame | None
    etf_reference: pl.DataFrame | None = None


def build_ordinary_rules(
    metadata: MetadataService,
    instrument_ids: list[int],
    *,
    asset_class: str,
    commission_rate: float,
    period: tuple[str, str],
    historical_inputs: HistoricalRuleInputs | None = None,
) -> InMemoryRuleProvider:
    """Bind every frozen member to an explicitly covered listing."""
    start, end = period
    historical_roster = historical_inputs.roster if historical_inputs else None
    stock_status = historical_inputs.stock_status if historical_inputs else None
    trading_days = historical_inputs.trading_days if historical_inputs else []
    rules: dict[InstrumentId, tuple[InstrumentRules, ...]] = {}
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
        if historical_inputs is not None and asset_class == "etf":
            if listing.list_date > end:
                continue
            if historical_inputs.etf_reference is None:
                raise AppBuilderError(f"missing frozen etf_reference: {iid} {start}")
            rules[InstrumentId(iid)] = etf_rule_history(
                listing,
                facts=historical_inputs.etf_reference.filter(
                    pl.col("instrument_id") == iid
                ).to_dicts(),
                commission_rate=commission_rate,
                start=max(start, listing.list_date),
                end=end,
                trading_days=trading_days,
            )
            continue
        if historical_roster is not None and cash_stock_board(
            listing.asset_class, listing.exchange, listing.ticker
        ):
            if listing.list_date > end:
                continue
            rules[InstrumentId(iid)] = stock_rule_history(
                listing,
                commission_rate=commission_rate,
                start=max(start, listing.list_date),
                end=end,
                trading_days=trading_days or [],
                risk_warning=dict(
                    stock_status.filter(pl.col("instrument_id") == iid)
                    .select(pl.col("trade_date").cast(pl.String), "is_st")
                    .iter_rows()
                )
                if stock_status is not None
                else None,
            )
            continue
        rules[InstrumentId(iid)] = (
            ordinary_equity_rules(
                listing,
                commission_rate=commission_rate,
                start=start,
                end=end,
                historical_reconstruction=historical_roster is not None,
            ),
        )
    return InMemoryRuleProvider(
        definitions={iid: history[0][0] for iid, history in rules.items()},
        trading_rules={
            iid: [rule[1] for rule in history] for iid, history in rules.items()
        },
        fee_schedules={
            iid: [rule[2] for rule in history] for iid, history in rules.items()
        },
    )


def ordinary_rule_description(
    provider: InMemoryRuleProvider, instrument_id: int, day: str
) -> str | None:
    """Saved report wording comes from the exact rule used by execution."""
    rule = provider.get_rules(day, [InstrumentId(instrument_id)]).get(
        InstrumentId(instrument_id)
    )
    if rule is None:
        return None
    definition, trading, _ = rule
    if definition.ipo_date is not None and day < definition.ipo_date:
        return None
    band = (
        "无日涨跌幅限制"
        if trading.price_limit_pct is None
        else f"涨跌幅 {trading.price_limit_pct:.0%}"
    )
    registration = (
        "2020-08-24" if definition.board_segment == "chinext" else "2023-04-10"
    )
    if (
        trading.price_limit_pct is None
        and definition.board_segment != "star"
        and (definition.ipo_date or "") < registration
    ):
        band = "上市首日申报价格范围"
    if "market" not in trading.order_types_supported:
        band += " · 不接受市价申报"
    if (
        definition.asset_class == "etf"
        and "market_on_close" not in trading.order_types_supported
    ):
        band += " · 无收盘集合竞价"
    if trading.max_daily_buy_quantity is not None:
        band += f" · 当日已买入及未撤销买单合计 ≤{trading.max_daily_buy_quantity} 股"
    unit = "股" if definition.asset_class == "stock" else "份"
    if trading.max_limit_order_quantity is not None:
        band += f" · 限价/收盘单笔 ≤{trading.max_limit_order_quantity} {unit}"
    if trading.max_market_order_quantity is not None:
        band += f" · 市价单笔 ≤{trading.max_market_order_quantity} {unit}"
    quantity = f"买入 {definition.lot_size} {unit}"
    if trading.min_order_quantity > definition.lot_size:
        quantity = (
            f"买卖 {trading.min_order_quantity} {unit}起"
            + f", 递增 {definition.lot_size} {unit}"
            + f"; 不足 {trading.min_order_quantity} {unit}仅可全部卖出"
        )
    category = {
        "equity_etf": "股票 ETF",
        "bond_etf": "债券 ETF",
        "gold_etf": "黄金 ETF",
        "cross_border_etf": "跨境 ETF",
        "money_etf": "货币 ETF",
        "commodity_futures_etf": "商品期货 ETF",
    }.get(definition.board_segment, definition.board_segment)
    return (
        f"{definition.exchange}/{category}/{trading.as_of_date}"
        + f" · {band} · {quantity}"
        + f" · 报价 {definition.tick_size:g} 元 · T+{trading.settlement_cycle}"
        + (
            " · 规则依据 docs/evidence/star-rules-755.md"
            if definition.board_segment == "star"
            else " · ETF 历史品类与规则声明已冻结"
            if definition.asset_class == "etf"
            else ""
        )
    )


def ordinary_market_transform(
    provider: InMemoryRuleProvider,
    *,
    start_date: str,
    participation: pl.DataFrame | None = None,
    cash_dividends: tuple[Distribution, ...] = (),
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
            pl.col("close").shift(1).over("instrument_id").alias("_previous_close"),
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
                            share_ratio=next(
                                (
                                    e.share_ratio
                                    for e in cash_dividends
                                    if e.instrument_id == iid
                                    and e.ex_date.isoformat() == day
                                ),
                                0.0,
                            ),
                            cash_dividend=next(
                                (
                                    e.gross_per_share
                                    for e in cash_dividends
                                    if e.instrument_id == iid
                                    and e.ex_date.isoformat() == day
                                ),
                                None,
                            ),
                        )
                    )
            except ValueError as exc:
                raise AppBuilderError(str(exc)) from exc
            row.pop("_previous_adj")
            row.pop("_previous_close")
            if row.get("source") != "tushare":
                raise AppBuilderError(
                    f"unknown execution volume/amount units: {iid} {day}"
                )
            # Tushare daily/fund_daily: volume is lots, amount is CNY thousands.
            row["volume"] *= 100
            row["amount"] *= 1000
        return pl.DataFrame(rows)

    return transform
