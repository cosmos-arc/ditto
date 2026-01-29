"""Tests for Capital SourceSchema definitions."""

from datetime import date

import polars as pl
from ditto_datahub.sources.source_schema import SourceSchema


class TestBalanceSheetSourceSchema:
    """Tests for BALANCE_SHEET_SOURCE_SCHEMA."""

    def test_schema_is_source_schema_instance(self) -> None:
        """Schema should be a SourceSchema instance."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            BALANCE_SHEET_SOURCE_SCHEMA,
        )

        assert isinstance(BALANCE_SHEET_SOURCE_SCHEMA, SourceSchema)

    def test_dataset_name(self) -> None:
        """Dataset name should be 'balance_sheet'."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            BALANCE_SHEET_SOURCE_SCHEMA,
        )

        assert BALANCE_SHEET_SOURCE_SCHEMA.dataset == "balance_sheet"

    def test_key_columns(self) -> None:
        """Key columns should include PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            BALANCE_SHEET_SOURCE_SCHEMA,
        )

        assert BALANCE_SHEET_SOURCE_SCHEMA.key_columns == (
            "instrument_id",
            "report_date",
            "effective_from",
        )

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            BALANCE_SHEET_SOURCE_SCHEMA,
        )

        required_fields = {
            "instrument_id",
            "report_date",
            "knowledge_date",
            "effective_from",
            "effective_to",
            "total_assets",
            "total_liabilities",
            "net_assets",
            "current_assets",
            "current_liabilities",
        }
        assert set(BALANCE_SHEET_SOURCE_SCHEMA.schema.keys()) == required_fields

    def test_schema_types_are_polars_types(self) -> None:
        """Schema values should be Polars data types."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            BALANCE_SHEET_SOURCE_SCHEMA,
        )

        valid_types = (pl.String, pl.Float64, pl.Date)
        for dtype in BALANCE_SHEET_SOURCE_SCHEMA.schema.values():
            assert dtype in valid_types

    def test_instrument_id_is_string(self) -> None:
        """instrument_id field should be String."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            BALANCE_SHEET_SOURCE_SCHEMA,
        )

        assert BALANCE_SHEET_SOURCE_SCHEMA.schema["instrument_id"] == pl.String

    def test_report_date_is_date(self) -> None:
        """report_date field should be Date."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            BALANCE_SHEET_SOURCE_SCHEMA,
        )

        assert BALANCE_SHEET_SOURCE_SCHEMA.schema["report_date"] == pl.Date

    def test_knowledge_date_is_date(self) -> None:
        """knowledge_date field should be Date."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            BALANCE_SHEET_SOURCE_SCHEMA,
        )

        assert BALANCE_SHEET_SOURCE_SCHEMA.schema["knowledge_date"] == pl.Date

    def test_effective_from_is_date(self) -> None:
        """effective_from field should be Date."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            BALANCE_SHEET_SOURCE_SCHEMA,
        )

        assert BALANCE_SHEET_SOURCE_SCHEMA.schema["effective_from"] == pl.Date

    def test_effective_to_is_date(self) -> None:
        """effective_to field should be Date."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            BALANCE_SHEET_SOURCE_SCHEMA,
        )

        assert BALANCE_SHEET_SOURCE_SCHEMA.schema["effective_to"] == pl.Date

    def test_financial_fields_are_float64(self) -> None:
        """Financial fields should be Float64."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            BALANCE_SHEET_SOURCE_SCHEMA,
        )

        financial_fields = [
            "total_assets",
            "total_liabilities",
            "net_assets",
            "current_assets",
            "current_liabilities",
        ]
        for field in financial_fields:
            assert BALANCE_SHEET_SOURCE_SCHEMA.schema[field] == pl.Float64

    def test_has_pit_columns(self) -> None:
        """Schema should have PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            BALANCE_SHEET_SOURCE_SCHEMA,
        )

        expected = ("effective_from", "effective_to")
        assert BALANCE_SHEET_SOURCE_SCHEMA.pit_columns == expected

    def test_validate_valid_dataframe(self) -> None:
        """Should validate a valid DataFrame."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            BALANCE_SHEET_SOURCE_SCHEMA,
        )

        df = pl.DataFrame(
            {
                "instrument_id": ["inst_001"],
                "report_date": [date(2024, 3, 31)],
                "knowledge_date": [date(2024, 4, 30)],
                "effective_from": [date(2024, 4, 30)],
                "effective_to": [None],
                "total_assets": [1000000.0],
                "total_liabilities": [500000.0],
                "net_assets": [500000.0],
                "current_assets": [600000.0],
                "current_liabilities": [300000.0],
            }
        )
        # Should not raise
        BALANCE_SHEET_SOURCE_SCHEMA.validate(df)


class TestIncomeStatementSourceSchema:
    """Tests for INCOME_STATEMENT_SOURCE_SCHEMA."""

    def test_schema_is_source_schema_instance(self) -> None:
        """Schema should be a SourceSchema instance."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            INCOME_STATEMENT_SOURCE_SCHEMA,
        )

        assert isinstance(INCOME_STATEMENT_SOURCE_SCHEMA, SourceSchema)

    def test_dataset_name(self) -> None:
        """Dataset name should be 'income_statement'."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            INCOME_STATEMENT_SOURCE_SCHEMA,
        )

        assert INCOME_STATEMENT_SOURCE_SCHEMA.dataset == "income_statement"

    def test_key_columns(self) -> None:
        """Key columns should include PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            INCOME_STATEMENT_SOURCE_SCHEMA,
        )

        assert INCOME_STATEMENT_SOURCE_SCHEMA.key_columns == (
            "instrument_id",
            "report_date",
            "effective_from",
        )

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            INCOME_STATEMENT_SOURCE_SCHEMA,
        )

        required_fields = {
            "instrument_id",
            "report_date",
            "knowledge_date",
            "effective_from",
            "effective_to",
            "revenue",
            "operating_profit",
            "net_profit",
            "eps",
        }
        assert set(INCOME_STATEMENT_SOURCE_SCHEMA.schema.keys()) == required_fields

    def test_has_pit_columns(self) -> None:
        """Schema should have PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            INCOME_STATEMENT_SOURCE_SCHEMA,
        )

        expected = ("effective_from", "effective_to")
        assert INCOME_STATEMENT_SOURCE_SCHEMA.pit_columns == expected


class TestCashFlowSourceSchema:
    """Tests for CASH_FLOW_SOURCE_SCHEMA."""

    def test_schema_is_source_schema_instance(self) -> None:
        """Schema should be a SourceSchema instance."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            CASH_FLOW_SOURCE_SCHEMA,
        )

        assert isinstance(CASH_FLOW_SOURCE_SCHEMA, SourceSchema)

    def test_dataset_name(self) -> None:
        """Dataset name should be 'cash_flow'."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            CASH_FLOW_SOURCE_SCHEMA,
        )

        assert CASH_FLOW_SOURCE_SCHEMA.dataset == "cash_flow"

    def test_key_columns(self) -> None:
        """Key columns should include PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            CASH_FLOW_SOURCE_SCHEMA,
        )

        assert CASH_FLOW_SOURCE_SCHEMA.key_columns == (
            "instrument_id",
            "report_date",
            "effective_from",
        )

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            CASH_FLOW_SOURCE_SCHEMA,
        )

        required_fields = {
            "instrument_id",
            "report_date",
            "knowledge_date",
            "effective_from",
            "effective_to",
            "operating_cash_flow",
            "investing_cash_flow",
            "financing_cash_flow",
            "net_cash_flow",
        }
        assert set(CASH_FLOW_SOURCE_SCHEMA.schema.keys()) == required_fields

    def test_has_pit_columns(self) -> None:
        """Schema should have PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            CASH_FLOW_SOURCE_SCHEMA,
        )

        expected = ("effective_from", "effective_to")
        assert CASH_FLOW_SOURCE_SCHEMA.pit_columns == expected


class TestValuationMetricsSourceSchema:
    """Tests for VALUATION_METRICS_SOURCE_SCHEMA."""

    def test_schema_is_source_schema_instance(self) -> None:
        """Schema should be a SourceSchema instance."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            VALUATION_METRICS_SOURCE_SCHEMA,
        )

        assert isinstance(VALUATION_METRICS_SOURCE_SCHEMA, SourceSchema)

    def test_dataset_name(self) -> None:
        """Dataset name should be 'valuation_metrics'."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            VALUATION_METRICS_SOURCE_SCHEMA,
        )

        assert VALUATION_METRICS_SOURCE_SCHEMA.dataset == "valuation_metrics"

    def test_key_columns(self) -> None:
        """Key columns should include PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            VALUATION_METRICS_SOURCE_SCHEMA,
        )

        assert VALUATION_METRICS_SOURCE_SCHEMA.key_columns == (
            "instrument_id",
            "trade_date",
            "effective_from",
        )

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            VALUATION_METRICS_SOURCE_SCHEMA,
        )

        required_fields = {
            "instrument_id",
            "trade_date",
            "knowledge_date",
            "effective_from",
            "effective_to",
            "pe_ratio",
            "pb_ratio",
            "ps_ratio",
            "dividend_yield",
            "market_cap",
        }
        assert set(VALUATION_METRICS_SOURCE_SCHEMA.schema.keys()) == required_fields

    def test_has_pit_columns(self) -> None:
        """Schema should have PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            VALUATION_METRICS_SOURCE_SCHEMA,
        )

        expected = ("effective_from", "effective_to")
        assert VALUATION_METRICS_SOURCE_SCHEMA.pit_columns == expected


class TestFuturesSourceSchema:
    """Tests for FUTURES_SOURCE_SCHEMA."""

    def test_schema_is_source_schema_instance(self) -> None:
        """Schema should be a SourceSchema instance."""
        from ditto_datahub.sources.schemas.capital_schemas import FUTURES_SOURCE_SCHEMA

        assert isinstance(FUTURES_SOURCE_SCHEMA, SourceSchema)

    def test_dataset_name(self) -> None:
        """Dataset name should be 'futures'."""
        from ditto_datahub.sources.schemas.capital_schemas import FUTURES_SOURCE_SCHEMA

        assert FUTURES_SOURCE_SCHEMA.dataset == "futures"

    def test_key_columns(self) -> None:
        """Key columns should include PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import FUTURES_SOURCE_SCHEMA

        assert FUTURES_SOURCE_SCHEMA.key_columns == (
            "instrument_id",
            "trade_date",
            "effective_from",
        )

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        from ditto_datahub.sources.schemas.capital_schemas import FUTURES_SOURCE_SCHEMA

        required_fields = {
            "instrument_id",
            "trade_date",
            "knowledge_date",
            "effective_from",
            "effective_to",
            "open_interest",
            "settlement_price",
            "volume",
            "turnover",
        }
        assert set(FUTURES_SOURCE_SCHEMA.schema.keys()) == required_fields

    def test_has_pit_columns(self) -> None:
        """Schema should have PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import FUTURES_SOURCE_SCHEMA

        expected = ("effective_from", "effective_to")
        assert FUTURES_SOURCE_SCHEMA.pit_columns == expected


class TestIndexCompositionSourceSchema:
    """Tests for INDEX_COMPOSITION_SOURCE_SCHEMA."""

    def test_schema_is_source_schema_instance(self) -> None:
        """Schema should be a SourceSchema instance."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            INDEX_COMPOSITION_SOURCE_SCHEMA,
        )

        assert isinstance(INDEX_COMPOSITION_SOURCE_SCHEMA, SourceSchema)

    def test_dataset_name(self) -> None:
        """Dataset name should be 'index_composition'."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            INDEX_COMPOSITION_SOURCE_SCHEMA,
        )

        assert INDEX_COMPOSITION_SOURCE_SCHEMA.dataset == "index_composition"

    def test_key_columns(self) -> None:
        """Key columns should include PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            INDEX_COMPOSITION_SOURCE_SCHEMA,
        )

        assert INDEX_COMPOSITION_SOURCE_SCHEMA.key_columns == (
            "index_id",
            "instrument_id",
            "effective_from",
        )

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            INDEX_COMPOSITION_SOURCE_SCHEMA,
        )

        required_fields = {
            "index_id",
            "instrument_id",
            "weight",
            "effective_from",
            "effective_to",
        }
        assert set(INDEX_COMPOSITION_SOURCE_SCHEMA.schema.keys()) == required_fields

    def test_has_pit_columns(self) -> None:
        """Schema should have PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            INDEX_COMPOSITION_SOURCE_SCHEMA,
        )

        expected = ("effective_from", "effective_to")
        assert INDEX_COMPOSITION_SOURCE_SCHEMA.pit_columns == expected


class TestCorporateActionsSourceSchema:
    """Tests for CORPORATE_ACTIONS_SOURCE_SCHEMA."""

    def test_schema_is_source_schema_instance(self) -> None:
        """Schema should be a SourceSchema instance."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            CORPORATE_ACTIONS_SOURCE_SCHEMA,
        )

        assert isinstance(CORPORATE_ACTIONS_SOURCE_SCHEMA, SourceSchema)

    def test_dataset_name(self) -> None:
        """Dataset name should be 'corporate_actions'."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            CORPORATE_ACTIONS_SOURCE_SCHEMA,
        )

        assert CORPORATE_ACTIONS_SOURCE_SCHEMA.dataset == "corporate_actions"

    def test_key_columns(self) -> None:
        """Key columns should not include PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            CORPORATE_ACTIONS_SOURCE_SCHEMA,
        )

        assert CORPORATE_ACTIONS_SOURCE_SCHEMA.key_columns == (
            "instrument_id",
            "action_type",
            "announcement_date",
        )

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            CORPORATE_ACTIONS_SOURCE_SCHEMA,
        )

        required_fields = {
            "instrument_id",
            "action_type",
            "announcement_date",
            "effective_date",
            "description",
        }
        assert set(CORPORATE_ACTIONS_SOURCE_SCHEMA.schema.keys()) == required_fields

    def test_no_pit_columns(self) -> None:
        """Schema should not have PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            CORPORATE_ACTIONS_SOURCE_SCHEMA,
        )

        assert CORPORATE_ACTIONS_SOURCE_SCHEMA.pit_columns == ()


class TestDividendSourceSchema:
    """Tests for DIVIDEND_SOURCE_SCHEMA."""

    def test_schema_is_source_schema_instance(self) -> None:
        """Schema should be a SourceSchema instance."""
        from ditto_datahub.sources.schemas.capital_schemas import DIVIDEND_SOURCE_SCHEMA

        assert isinstance(DIVIDEND_SOURCE_SCHEMA, SourceSchema)

    def test_dataset_name(self) -> None:
        """Dataset name should be 'dividend'."""
        from ditto_datahub.sources.schemas.capital_schemas import DIVIDEND_SOURCE_SCHEMA

        assert DIVIDEND_SOURCE_SCHEMA.dataset == "dividend"

    def test_key_columns(self) -> None:
        """Key columns should include PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import DIVIDEND_SOURCE_SCHEMA

        assert DIVIDEND_SOURCE_SCHEMA.key_columns == (
            "instrument_id",
            "ex_dividend_date",
            "effective_from",
        )

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        from ditto_datahub.sources.schemas.capital_schemas import DIVIDEND_SOURCE_SCHEMA

        required_fields = {
            "instrument_id",
            "ex_dividend_date",
            "knowledge_date",
            "effective_from",
            "effective_to",
            "dividend_per_share",
            "dividend_yield",
        }
        assert set(DIVIDEND_SOURCE_SCHEMA.schema.keys()) == required_fields

    def test_has_pit_columns(self) -> None:
        """Schema should have PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import DIVIDEND_SOURCE_SCHEMA

        expected = ("effective_from", "effective_to")
        assert DIVIDEND_SOURCE_SCHEMA.pit_columns == expected


class TestMarginTradingSourceSchema:
    """Tests for MARGIN_TRADING_SOURCE_SCHEMA."""

    def test_schema_is_source_schema_instance(self) -> None:
        """Schema should be a SourceSchema instance."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            MARGIN_TRADING_SOURCE_SCHEMA,
        )

        assert isinstance(MARGIN_TRADING_SOURCE_SCHEMA, SourceSchema)

    def test_dataset_name(self) -> None:
        """Dataset name should be 'margin_trading'."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            MARGIN_TRADING_SOURCE_SCHEMA,
        )

        assert MARGIN_TRADING_SOURCE_SCHEMA.dataset == "margin_trading"

    def test_key_columns(self) -> None:
        """Key columns should include PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            MARGIN_TRADING_SOURCE_SCHEMA,
        )

        assert MARGIN_TRADING_SOURCE_SCHEMA.key_columns == (
            "instrument_id",
            "trade_date",
            "effective_from",
        )

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            MARGIN_TRADING_SOURCE_SCHEMA,
        )

        required_fields = {
            "instrument_id",
            "trade_date",
            "knowledge_date",
            "effective_from",
            "effective_to",
            "margin_buy_balance",
            "short_sell_balance",
            "margin_buy_volume",
            "short_sell_volume",
        }
        assert set(MARGIN_TRADING_SOURCE_SCHEMA.schema.keys()) == required_fields

    def test_has_pit_columns(self) -> None:
        """Schema should have PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            MARGIN_TRADING_SOURCE_SCHEMA,
        )

        expected = ("effective_from", "effective_to")
        assert MARGIN_TRADING_SOURCE_SCHEMA.pit_columns == expected


class TestPledgeRatioSourceSchema:
    """Tests for PLEDGE_RATIO_SOURCE_SCHEMA."""

    def test_schema_is_source_schema_instance(self) -> None:
        """Schema should be a SourceSchema instance."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            PLEDGE_RATIO_SOURCE_SCHEMA,
        )

        assert isinstance(PLEDGE_RATIO_SOURCE_SCHEMA, SourceSchema)

    def test_dataset_name(self) -> None:
        """Dataset name should be 'pledge_ratio'."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            PLEDGE_RATIO_SOURCE_SCHEMA,
        )

        assert PLEDGE_RATIO_SOURCE_SCHEMA.dataset == "pledge_ratio"

    def test_key_columns(self) -> None:
        """Key columns should include PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            PLEDGE_RATIO_SOURCE_SCHEMA,
        )

        assert PLEDGE_RATIO_SOURCE_SCHEMA.key_columns == (
            "instrument_id",
            "report_date",
            "effective_from",
        )

    def test_schema_has_all_required_fields(self) -> None:
        """Schema should have all required fields."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            PLEDGE_RATIO_SOURCE_SCHEMA,
        )

        required_fields = {
            "instrument_id",
            "report_date",
            "knowledge_date",
            "effective_from",
            "effective_to",
            "pledge_ratio",
            "pledge_shares",
            "total_shares",
        }
        assert set(PLEDGE_RATIO_SOURCE_SCHEMA.schema.keys()) == required_fields

    def test_has_pit_columns(self) -> None:
        """Schema should have PIT columns."""
        from ditto_datahub.sources.schemas.capital_schemas import (
            PLEDGE_RATIO_SOURCE_SCHEMA,
        )

        expected = ("effective_from", "effective_to")
        assert PLEDGE_RATIO_SOURCE_SCHEMA.pit_columns == expected
