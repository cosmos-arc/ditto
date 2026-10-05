"""Data 层 - Fundamental Domain Provider。"""

from __future__ import annotations

from dishka import Provider, Scope, provide
from ditto_platform.foundation import ParquetStore, SQLiteClient

from ditto_data.config.data_store import DataStoreSettings
from ditto_data.services.deps import FundamentalReaders, FundamentalWriters
from ditto_data.services.fundamental_store import FundamentalStore
from ditto_data.storage.fundamental.corporate.corporate_actions_reader import (
    CorporateActionsReader,
)
from ditto_data.storage.fundamental.corporate.corporate_actions_writer import (
    CorporateActionsWriter,
)
from ditto_data.storage.fundamental.corporate.dividend_reader import (
    DividendReader,
)
from ditto_data.storage.fundamental.corporate.dividend_writer import (
    DividendWriter,
)
from ditto_data.storage.fundamental.earnings.express import (
    EarningsExpressReader,
    EarningsExpressWriter,
)
from ditto_data.storage.fundamental.earnings.forecast import (
    EarningsForecastReader,
    EarningsForecastWriter,
)
from ditto_data.storage.fundamental.financial.balance_sheet_reader import (
    BalanceSheetReader,
)
from ditto_data.storage.fundamental.financial.balance_sheet_writer import (
    BalanceSheetWriter,
)
from ditto_data.storage.fundamental.financial.cash_flow_reader import (
    CashFlowReader,
)
from ditto_data.storage.fundamental.financial.cash_flow_writer import (
    CashFlowWriter,
)
from ditto_data.storage.fundamental.financial.income_statement_reader import (
    IncomeStatementReader,
)
from ditto_data.storage.fundamental.financial.income_statement_writer import (
    IncomeStatementWriter,
)
from ditto_data.storage.fundamental.specs import (
    BALANCE_SHEET_SPEC,
    CASH_FLOW_SPEC,
    CORPORATE_ACTIONS_SPEC,
    DIVIDEND_SPEC,
    INCOME_STATEMENT_SPEC,
)

__all__ = ["FundamentalProvider"]


class FundamentalProvider(Provider):
    """Fundamental Domain Provider - 财务报表、股息、公司行动."""

    scope = Scope.APP

    @provide
    def fundamental_readers(
        self,
        sqlite_client: SQLiteClient,
        settings: DataStoreSettings,
    ) -> FundamentalReaders:
        """Fundamental 域读取依赖聚合。"""
        return FundamentalReaders(
            balance_sheet=BalanceSheetReader(BALANCE_SHEET_SPEC, sqlite_client),
            income_statement=IncomeStatementReader(
                INCOME_STATEMENT_SPEC,
                sqlite_client,
            ),
            cash_flow=CashFlowReader(CASH_FLOW_SPEC, sqlite_client),
            dividend=DividendReader(DIVIDEND_SPEC, sqlite_client),
            corporate_actions=CorporateActionsReader(
                CORPORATE_ACTIONS_SPEC,
                sqlite_client,
            ),
            earnings_forecast=EarningsForecastReader(
                _earnings_forecast_parquet_store(settings)
            ),
            earnings_express=EarningsExpressReader(
                _earnings_express_parquet_store(settings)
            ),
        )

    @provide
    def fundamental_writers(
        self,
        sqlite_client: SQLiteClient,
        settings: DataStoreSettings,
    ) -> FundamentalWriters:
        """Fundamental 域写入依赖聚合。"""
        return FundamentalWriters(
            balance_sheet=BalanceSheetWriter(BALANCE_SHEET_SPEC, sqlite_client),
            income_statement=IncomeStatementWriter(
                INCOME_STATEMENT_SPEC,
                sqlite_client,
            ),
            cash_flow=CashFlowWriter(CASH_FLOW_SPEC, sqlite_client),
            dividend=DividendWriter(DIVIDEND_SPEC, sqlite_client),
            corporate_actions=CorporateActionsWriter(
                CORPORATE_ACTIONS_SPEC,
                sqlite_client,
            ),
            earnings_forecast=EarningsForecastWriter(
                _earnings_forecast_parquet_store(settings)
            ),
            earnings_express=EarningsExpressWriter(
                _earnings_express_parquet_store(settings)
            ),
        )

    @provide
    def fundamental_store(
        self,
        read_ports: FundamentalReaders,
        write_ports: FundamentalWriters,
    ) -> FundamentalStore:
        """Fundamental domain unified service."""
        return FundamentalStore(
            read_ports=read_ports,
            write_ports=write_ports,
        )


def _earnings_forecast_parquet_store(settings: DataStoreSettings) -> ParquetStore:
    """预告行以 (标的, 公告日, 报告期, 类型, 修订标志, 采集日) 为自然键."""
    return ParquetStore(
        settings.data_root,
        key_columns=(
            "source_ticker",
            "ann_date",
            "report_date",
            "forecast_type",
            "update_flag",
            "knowledge_date",
        ),
        date_column="ann_date",
        instrument_column="source_ticker",
    )


def _earnings_express_parquet_store(settings: DataStoreSettings) -> ParquetStore:
    """快报行以 (标的, 公告日, 报告期, 采集日) 为自然键."""
    return ParquetStore(
        settings.data_root,
        key_columns=("source_ticker", "ann_date", "report_date", "knowledge_date"),
        date_column="ann_date",
        instrument_column="source_ticker",
    )
