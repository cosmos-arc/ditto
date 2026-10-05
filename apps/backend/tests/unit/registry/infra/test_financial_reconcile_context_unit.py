"""#473：FundamentalFinancialReconcileContext — 财务对账主源上下文单测."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_apps.registry.infra.protocol_adapters import (
    FundamentalFinancialReconcileContext,
)


def _readers(income_frame: pl.DataFrame) -> SimpleNamespace:
    income = MagicMock()

    def get_range(instrument_id: int, **_: object) -> pl.DataFrame:
        if instrument_id == 1:
            return income_frame
        return pl.DataFrame()

    income.get_range.side_effect = get_range
    return SimpleNamespace(
        income_statement=income,
        balance_sheet=MagicMock(),
        cash_flow=MagicMock(),
    )


def _instrument_reader() -> MagicMock:
    reader = MagicMock()
    reader.map_bare_tickers_to_instrument_ids.return_value = {"600519": [1]}
    return reader


def _income_rows() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1, 1],
            "report_date": [date(2026, 6, 30), date(2026, 3, 31)],
            "knowledge_date": [date(2026, 8, 14), date(2026, 4, 23)],
            "effective_from": [date(2026, 8, 14), date(2026, 4, 23)],
            "effective_to": [None, None],
            "revenue": [1.0e10, 5.0e9],
            "operating_profit": [1.0e9, 5.0e8],
            "net_profit": [1.0e9, 5.0e8],
            "eps": [10.0, 5.0],
        }
    )


@pytest.mark.unit
class TestFundamentalFinancialReconcileContext:
    def test_golden_scoped_latest_statements_with_ticker(self) -> None:
        golden = MagicMock()
        golden.is_enabled = True
        golden.get_tickers.return_value = ["600519", "510300"]
        instrument_reader = _instrument_reader()
        # 510300（ETF）反查无股票 instrument → 无财务行，不进入主源帧
        instrument_reader.map_bare_tickers_to_instrument_ids.return_value = {
            "600519": [1],
            "510300": [7],
        }
        context = FundamentalFinancialReconcileContext(
            _readers(_income_rows()), instrument_reader, golden
        )

        frame = context.latest_statements("income_statement", "2026-10-05")

        assert frame.height == 2
        assert frame["ticker"].unique().to_list() == ["600519"]
        assert "knowledge_date" in frame.columns

    def test_golden_unset_rejects_full_market_expansion(self) -> None:
        context = FundamentalFinancialReconcileContext(
            _readers(_income_rows()), _instrument_reader(), None
        )

        with pytest.raises(RuntimeError, match="golden"):
            context.latest_statements("income_statement", "2026-10-05")

    def test_empty_store_returns_empty_frame(self) -> None:
        golden = MagicMock()
        golden.is_enabled = True
        golden.get_tickers.return_value = ["600519"]
        empty_reader = MagicMock()
        empty_reader.get_range.return_value = pl.DataFrame()
        context = FundamentalFinancialReconcileContext(
            _readers(pl.DataFrame()), _instrument_reader(), golden
        )
        context._readers = SimpleNamespace(
            income_statement=empty_reader,
            balance_sheet=MagicMock(),
            cash_flow=MagicMock(),
        )

        assert context.latest_statements("income_statement", "2026-10-05").is_empty()

    def test_unsupported_dataset_rejected(self) -> None:
        golden = MagicMock()
        golden.is_enabled = True
        golden.get_tickers.return_value = ["600519"]
        context = FundamentalFinancialReconcileContext(
            _readers(_income_rows()), _instrument_reader(), golden
        )

        with pytest.raises(RuntimeError, match="unsupported financial dataset"):
            context.latest_statements("dividend", "2026-10-05")
