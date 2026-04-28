"""Capital domain SqliteTableSpec definitions."""

from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec

VALUATION_METRICS_SPEC = SqliteTableSpec(
    table="valuation_metrics",
    columns=("pe_ratio", "pb_ratio", "ps_ratio", "dividend_yield", "market_cap"),
    id_column="instrument_id",
    date_column="trade_date",
    nullable_columns=frozenset(
        {
            "effective_to",
            "pe_ratio",
            "pb_ratio",
            "ps_ratio",
            "dividend_yield",
            "market_cap",
        }
    ),
)

MARGIN_TRADING_SPEC = SqliteTableSpec(
    table="margin_trading",
    columns=(
        "margin_buy_balance",
        "short_sell_balance",
        "margin_buy_volume",
        "short_sell_volume",
    ),
    id_column="instrument_id",
    date_column="trade_date",
    nullable_columns=frozenset(
        {
            "effective_to",
            "margin_buy_balance",
            "short_sell_balance",
            "margin_buy_volume",
            "short_sell_volume",
        }
    ),
)

PLEDGE_RATIO_SPEC = SqliteTableSpec(
    table="pledge_ratio",
    columns=("pledge_ratio", "pledge_shares", "total_shares"),
    id_column="instrument_id",
    date_column="report_date",
    nullable_columns=frozenset(
        {"effective_to", "pledge_ratio", "pledge_shares", "total_shares"}
    ),
)

INDEX_COMPOSITION_SPEC = SqliteTableSpec(
    table="index_composition",
    columns=("instrument_id", "weight"),
    id_column="index_id",
    date_column=None,
    pit_columns=("effective_from", "effective_to"),
    order_by_column="instrument_id",
    nullable_columns=frozenset({"effective_to", "weight"}),
)
