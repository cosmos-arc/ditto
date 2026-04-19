"""Fundamental domain SqliteTableSpec definitions."""

from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec

BALANCE_SHEET_SPEC = SqliteTableSpec(
    table="balance_sheet",
    columns=(
        "total_assets",
        "total_liabilities",
        "net_assets",
        "current_assets",
        "current_liabilities",
    ),
    id_column="instrument_id",
    date_column="report_date",
    nullable_columns=frozenset({"effective_to"}),
)

INCOME_STATEMENT_SPEC = SqliteTableSpec(
    table="income_statement",
    columns=("revenue", "operating_profit", "net_profit", "eps"),
    id_column="instrument_id",
    date_column="report_date",
    nullable_columns=frozenset({"effective_to"}),
)

CASH_FLOW_SPEC = SqliteTableSpec(
    table="cash_flow",
    columns=(
        "operating_cash_flow",
        "investing_cash_flow",
        "financing_cash_flow",
        "net_cash_flow",
    ),
    id_column="instrument_id",
    date_column="report_date",
    nullable_columns=frozenset({"effective_to"}),
)

DIVIDEND_SPEC = SqliteTableSpec(
    table="dividend",
    columns=("dividend_per_share", "dividend_yield", "div_proc"),
    id_column="instrument_id",
    date_column="ex_dividend_date",
    nullable_columns=frozenset(
        {
            "effective_to",
            "ex_dividend_date",
            "dividend_per_share",
            "dividend_yield",
            "div_proc",
        }
    ),
)

CORPORATE_ACTIONS_SPEC = SqliteTableSpec(
    table="corporate_actions",
    columns=("action_type", "action_date", "description"),
    id_column="instrument_id",
    date_column="action_date",
    nullable_columns=frozenset({"effective_to"}),
)

FORECAST_SPEC = SqliteTableSpec(
    table="forecast",
    columns=("type", "profit_range_min", "profit_range_max"),
    id_column="instrument_id",
    date_column="report_date",
    nullable_columns=frozenset(
        {"effective_to", "profit_range_min", "profit_range_max"}
    ),
)

EXPRESS_SPEC = SqliteTableSpec(
    table="express",
    columns=("type", "profit_range_min", "profit_range_max"),
    id_column="instrument_id",
    date_column="report_date",
    nullable_columns=frozenset(
        {"effective_to", "profit_range_min", "profit_range_max"}
    ),
)
