"""Tests for domain-level Fetcher Protocols and SourceRegistry."""

from datetime import UTC, date, datetime

import polars as pl
import pytest
from ditto_data.sources.protocols import (
    CapitalFetcher,
    FundamentalFetcher,
    MacroFetcher,
    MarketFetcher,
    MetadataFetcher,
)
from ditto_data.sources.registry import SourceRegistry

# ---------------------------------------------------------------------------
# Helpers: concrete implementations for Protocol structural typing tests
# ---------------------------------------------------------------------------


class _StubMetadataFetcher:
    """Stub implementing MetadataFetcher Protocol."""

    def fetch_stock_basic(self, source_ticker: str | None = None) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_etf_basic(self) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_index_basic(self) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_sw_industry(self, level: int = 1) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_sw_industry_concepts(
        self,
        asof_date: str | None = None,
        level: int = 1,
        *,
        knowledge_date: date | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()


class _StubMarketFetcher:
    """Stub implementing MarketFetcher Protocol."""

    def fetch_stock_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_etf_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_index_daily(
        self,
        trade_date: str | None = None,
        ts_codes: list[str] | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_global_index_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        *,
        observed_at: datetime | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_adj_factor_by_ticker(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_fund_adj(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
        return pl.DataFrame()


class _StubFundamentalFetcher:
    """Stub implementing FundamentalFetcher Protocol."""

    def fetch_balance_sheet(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_income_statement(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_cash_flow(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_dividend(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_corporate_actions(self, trade_date: str) -> pl.DataFrame:
        return pl.DataFrame()


class _StubCapitalFetcher:
    """Stub implementing CapitalFetcher Protocol."""

    def fetch_valuation_metrics(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_margin_trading(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_pledge_ratio(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()


class _StubMacroFetcher:
    """Stub implementing MacroFetcher Protocol."""

    def fetch_macro_indicators(self, trade_date: str) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_macro_indicators_by_codes(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        *,
        observed_on: date | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_fx_daily(
        self,
        ts_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_commodities(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def fetch_metal_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        return pl.DataFrame()


class _StubFullSource(
    _StubMetadataFetcher,
    _StubMarketFetcher,
    _StubFundamentalFetcher,
    _StubCapitalFetcher,
    _StubMacroFetcher,
):
    """Stub implementing all 5 Fetcher Protocols."""

    pass


# ---------------------------------------------------------------------------
# Protocol structural typing tests
# ---------------------------------------------------------------------------


class TestMetadataFetcherProtocol:
    def test_structural_subtyping(self) -> None:
        stub = _StubMetadataFetcher()
        source: MetadataFetcher = stub
        assert source.fetch_stock_basic().shape == (0, 0)

    def test_all_methods_callable(self) -> None:
        stub = _StubMetadataFetcher()
        stub.fetch_stock_basic()
        stub.fetch_etf_basic()
        stub.fetch_index_basic()
        stub.fetch_calendar("2024-01-01", "2024-12-31")
        stub.fetch_sw_industry(level=2)
        stub.fetch_sw_industry_concepts(level=1, knowledge_date=date(2026, 9, 1))


class TestMarketFetcherProtocol:
    def test_structural_subtyping(self) -> None:
        stub = _StubMarketFetcher()
        source: MarketFetcher = stub
        assert source.fetch_stock_daily("2024-01-02").shape == (0, 0)

    def test_all_methods_callable(self) -> None:
        stub = _StubMarketFetcher()
        stub.fetch_stock_daily("2024-01-02")
        stub.fetch_etf_daily("2024-01-02")
        stub.fetch_index_daily("2024-01-02")
        stub.fetch_global_index_daily(
            ["SPX"],
            "2024-03-25",
            "2024-04-02",
            observed_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
        stub.fetch_adj_factor("2024-01-02")
        stub.fetch_adj_factor_by_ticker("000001.SZ", "20240101", "20240131")
        stub.fetch_fund_adj("2024-01-02")
        stub.fetch_stock_status("2024-01-02")


class TestFundamentalFetcherProtocol:
    def test_structural_subtyping(self) -> None:
        stub = _StubFundamentalFetcher()
        source: FundamentalFetcher = stub
        assert source.fetch_balance_sheet("2024-01-02").shape == (0, 0)

    def test_all_methods_callable(self) -> None:
        stub = _StubFundamentalFetcher()
        stub.fetch_balance_sheet("2024-01-02")
        stub.fetch_income_statement("2024-01-02")
        stub.fetch_cash_flow("2024-01-02")
        stub.fetch_dividend("2024-01-02")
        stub.fetch_corporate_actions("2024-01-02")


class TestCapitalFetcherProtocol:
    def test_structural_subtyping(self) -> None:
        stub = _StubCapitalFetcher()
        source: CapitalFetcher = stub
        assert source.fetch_valuation_metrics("2024-01-02").shape == (0, 0)

    def test_all_methods_callable(self) -> None:
        stub = _StubCapitalFetcher()
        stub.fetch_valuation_metrics("2024-01-02")
        stub.fetch_margin_trading("2024-01-02")
        stub.fetch_pledge_ratio("2024-01-02")


class TestMacroFetcherProtocol:
    def test_structural_subtyping(self) -> None:
        stub = _StubMacroFetcher()
        source: MacroFetcher = stub
        assert source.fetch_macro_indicators("2024-01-02").shape == (0, 0)

    def test_all_methods_callable(self) -> None:
        stub = _StubMacroFetcher()
        stub.fetch_macro_indicators("2024-01-02")
        stub.fetch_fx_daily(["USDCNH.FXCM"], "2024-01-01", "2024-01-31")
        stub.fetch_commodities(["COMMOD_WTI"], "2024-01-01", "2024-01-31")
        stub.fetch_metal_daily(["COMMOD_GOLD"], "2024-01-01", "2024-01-31")


class TestFullSource:
    def test_satisfies_all_protocols(self) -> None:
        stub = _StubFullSource()
        metadata: MetadataFetcher = stub
        market: MarketFetcher = stub
        fundamental: FundamentalFetcher = stub
        capital: CapitalFetcher = stub
        macro: MacroFetcher = stub
        assert metadata.fetch_etf_basic().shape == (0, 0)
        assert market.fetch_stock_daily("2024-01-02").shape == (0, 0)
        assert fundamental.fetch_balance_sheet("2024-01-02").shape == (0, 0)
        assert capital.fetch_valuation_metrics("2024-01-02").shape == (0, 0)
        assert macro.fetch_macro_indicators("2024-01-02").shape == (0, 0)


# ---------------------------------------------------------------------------
# SourceRegistry tests
# ---------------------------------------------------------------------------


class TestSourceRegistry:
    def test_register_and_get(self) -> None:
        registry = SourceRegistry()
        stub = _StubMetadataFetcher()
        registry.register("tushare", MetadataFetcher, stub)

        result = registry.get("tushare", MetadataFetcher)
        assert result is stub

    def test_get_unknown_name_raises(self) -> None:
        registry = SourceRegistry()
        with pytest.raises(ValueError, match="No source registered"):
            registry.get("unknown", MetadataFetcher)

    def test_get_unknown_protocol_raises(self) -> None:
        registry = SourceRegistry()
        stub = _StubMetadataFetcher()
        registry.register("tushare", MetadataFetcher, stub)

        with pytest.raises(ValueError, match="No source registered"):
            registry.get("tushare", MarketFetcher)

    def test_get_all(self) -> None:
        registry = SourceRegistry()
        stub1 = _StubMetadataFetcher()
        stub2 = _StubMetadataFetcher()
        registry.register("tushare", MetadataFetcher, stub1)
        registry.register("fred", MetadataFetcher, stub2)

        all_sources = registry.get_all(MetadataFetcher)
        assert len(all_sources) == 2
        assert stub1 in all_sources
        assert stub2 in all_sources

    def test_get_all_empty(self) -> None:
        registry = SourceRegistry()
        assert registry.get_all(MetadataFetcher) == []

    def test_multiple_protocols(self) -> None:
        registry = SourceRegistry()
        full = _StubFullSource()
        registry.register("tushare", MetadataFetcher, full)
        registry.register("tushare", MarketFetcher, full)
        registry.register("tushare", FundamentalFetcher, full)

        assert registry.get("tushare", MetadataFetcher) is full
        assert registry.get("tushare", MarketFetcher) is full
        assert registry.get("tushare", FundamentalFetcher) is full

    def test_replace_registration(self) -> None:
        registry = SourceRegistry()
        old = _StubMetadataFetcher()
        new = _StubMetadataFetcher()
        registry.register("tushare", MetadataFetcher, old)
        registry.register("tushare", MetadataFetcher, new)

        assert registry.get("tushare", MetadataFetcher) is new
        assert registry.get_all(MetadataFetcher) == [new]

    def test_type_safety(self) -> None:
        registry = SourceRegistry()
        registry.register("tushare", MetadataFetcher, _StubMetadataFetcher())

        result: MetadataFetcher = registry.get("tushare", MetadataFetcher)
        assert result.fetch_etf_basic().shape == (0, 0)
