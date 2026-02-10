"""Fundamental domain service with unified query/write contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import polars as pl
from ditto_foundation import logger

from ditto_datahub.stores.fundamental.corporate.corporate_actions_reader import (
    CorporateActionsReader,
)
from ditto_datahub.stores.fundamental.corporate.corporate_actions_writer import (
    CorporateActionsWriter,
)
from ditto_datahub.stores.fundamental.corporate.dividend_reader import (
    DividendReader,
)
from ditto_datahub.stores.fundamental.corporate.dividend_writer import (
    DividendWriter,
)
from ditto_datahub.stores.fundamental.financial.balance_sheet_reader import (
    BalanceSheetReader,
)
from ditto_datahub.stores.fundamental.financial.balance_sheet_writer import (
    BalanceSheetWriter,
)
from ditto_datahub.stores.fundamental.financial.cash_flow_reader import (
    CashFlowReader,
)
from ditto_datahub.stores.fundamental.financial.cash_flow_writer import (
    CashFlowWriter,
)
from ditto_datahub.stores.fundamental.financial.income_statement_reader import (
    IncomeStatementReader,
)
from ditto_datahub.stores.fundamental.financial.income_statement_writer import (
    IncomeStatementWriter,
)
from ditto_datahub.stores.fundamental.forecast.express_reader import (
    ExpressReader,
)
from ditto_datahub.stores.fundamental.forecast.express_writer import (
    ExpressWriter,
)
from ditto_datahub.stores.fundamental.forecast.forecast_reader import (
    ForecastReader,
)
from ditto_datahub.stores.fundamental.forecast.forecast_writer import (
    ForecastWriter,
)

FundamentalDataset = Literal[
    "balance_sheet",
    "income_statement",
    "cash_flow",
    "dividend",
    "corporate_actions",
    "forecast",
    "express",
]


@dataclass(frozen=True)
class FundamentalQuery:
    """Unified query contract for Fundamental domain."""

    dataset: FundamentalDataset
    instrument_id: str
    as_of_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None


@dataclass(frozen=True)
class FundamentalWriteResult:
    """Write result for Fundamental domain service."""

    dataset: FundamentalDataset
    records_written: int


class FundamentalService:
    """
    Fundamental domain unified service.

    Thin wrapper with dependency injection using CQRS pattern.
    Delegates read operations to Readers and write operations to Writers.
    """

    def __init__(  # noqa: PLR0913
        self,
        balance_sheet_reader: BalanceSheetReader,
        balance_sheet_writer: BalanceSheetWriter,
        income_statement_reader: IncomeStatementReader,
        income_statement_writer: IncomeStatementWriter,
        cash_flow_reader: CashFlowReader,
        cash_flow_writer: CashFlowWriter,
        dividend_reader: DividendReader,
        dividend_writer: DividendWriter,
        corporate_actions_reader: CorporateActionsReader,
        corporate_actions_writer: CorporateActionsWriter,
        forecast_reader: ForecastReader,
        forecast_writer: ForecastWriter,
        express_reader: ExpressReader,
        express_writer: ExpressWriter,
    ) -> None:
        """
        Initialize FundamentalService with CQRS Readers and Writers.

        Args:
            balance_sheet_reader: BalanceSheet data reader.
            balance_sheet_writer: BalanceSheet data writer.
            income_statement_reader: IncomeStatement data reader.
            income_statement_writer: IncomeStatement data writer.
            cash_flow_reader: CashFlow data reader.
            cash_flow_writer: CashFlow data writer.
            dividend_reader: Dividend data reader.
            dividend_writer: Dividend data writer.
            corporate_actions_reader: CorporateActions data reader.
            corporate_actions_writer: CorporateActions data writer.
            forecast_reader: Forecast data reader.
            forecast_writer: Forecast data writer.
            express_reader: Express data reader.
            express_writer: Express data writer.

        """
        self._balance_sheet_reader = balance_sheet_reader
        self._balance_sheet_writer = balance_sheet_writer
        self._income_statement_reader = income_statement_reader
        self._income_statement_writer = income_statement_writer
        self._cash_flow_reader = cash_flow_reader
        self._cash_flow_writer = cash_flow_writer
        self._dividend_reader = dividend_reader
        self._dividend_writer = dividend_writer
        self._corporate_actions_reader = corporate_actions_reader
        self._corporate_actions_writer = corporate_actions_writer
        self._forecast_reader = forecast_reader
        self._forecast_writer = forecast_writer
        self._express_reader = express_reader
        self._express_writer = express_writer

        logger.debug(
            "FundamentalService initialized with CQRS Readers and Writers",
            event="fundamental_service_init_complete",
        )

    @staticmethod
    def _require_as_of_date(query: FundamentalQuery) -> date:
        if query.as_of_date is None:
            msg = f"{query.dataset} 查询必须提供 as_of_date"
            raise ValueError(msg)
        return query.as_of_date

    def write(
        self,
        dataset: FundamentalDataset,
        df: pl.DataFrame,
    ) -> FundamentalWriteResult:
        """Write dataset via unified contract."""
        writers = {
            "balance_sheet": self._balance_sheet_writer.write,
            "income_statement": self._income_statement_writer.write,
            "cash_flow": self._cash_flow_writer.write,
            "dividend": self._dividend_writer.write,
            "corporate_actions": self._corporate_actions_writer.write,
            "forecast": self._forecast_writer.write,
            "express": self._express_writer.write,
        }
        records_written = writers[dataset](df)
        return FundamentalWriteResult(dataset=dataset, records_written=records_written)

    def query(self, query: FundamentalQuery) -> pl.DataFrame:
        """Query dataset via unified contract."""
        if query.dataset == "corporate_actions":
            return self._corporate_actions_reader.get(
                query.instrument_id,
                query.start_date,
                query.end_date,
            )

        readers = {
            "balance_sheet": self._balance_sheet_reader.get,
            "income_statement": self._income_statement_reader.get,
            "cash_flow": self._cash_flow_reader.get,
            "dividend": self._dividend_reader.get,
            "forecast": self._forecast_reader.get,
            "express": self._express_reader.get,
        }
        as_of_date = self._require_as_of_date(query)
        return readers[query.dataset](query.instrument_id, as_of_date)
