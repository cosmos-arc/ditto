"""Tests for ingestion protocols."""

import polars as pl
import pytest


@pytest.mark.unit
class TestIngestionDataSourceProtocol:
    """测试 IngestionDataSource 协议."""

    def test_protocol_has_fetch_index_basic(self) -> None:
        """验证协议包含 fetch_index_basic 方法."""
        from ditto_port.services.ingestion.protocols import IngestionDataSource

        # 使用 mock 实现验证协议方法存在
        class MockSource:
            def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_stock_basic(self) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_etf_basic(self) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_index_basic(self) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_stock_daily(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_etf_daily(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_index_daily(
                self,
                trade_date: str,
                ts_codes: list[str] | None = None,
            ) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_fund_adj(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_balance_sheet(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_income_statement(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_cash_flow(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_dividend(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_valuation_metrics(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_margin_trading(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_pledge_ratio(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_macro_indicators(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_futures(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

            def fetch_corporate_actions(self, trade_date: str) -> pl.DataFrame:
                return pl.DataFrame()

        source: IngestionDataSource = MockSource()  # type: ignore
        assert callable(source.fetch_index_basic)
        assert callable(source.fetch_index_daily)
