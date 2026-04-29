"""Tests for manifest_builder helpers."""

import pytest
from ditto_app.process.materialization.dependency_refs import dependency_refs


class TestDependencyRefs:
    """Tests for dependency_refs() classification logic."""

    def test_market_stock_daily_classified_as_dataset(self) -> None:
        result = dependency_refs(("market.close", "market.volume"))
        assert result == (("dataset", "market.stock_daily"),)

    def test_market_adj_factor_classified_as_dataset(self) -> None:
        result = dependency_refs(("market.adj_factor",))
        assert result == (("dataset", "market.adj_factor"),)

    def test_market_stock_status_classified_as_dataset(self) -> None:
        result = dependency_refs(("market.is_st", "market.list_status"))
        assert result == (("dataset", "market.stock_status"),)

    def test_etf_daily_classified_as_dataset(self) -> None:
        result = dependency_refs(("etf.close", "etf.volume"))
        assert result == (("dataset", "etf.daily"),)

    def test_etf_daily_mixed_with_market(self) -> None:
        result = dependency_refs(("market.close", "etf.close"))
        assert set(result) == {
            ("dataset", "market.stock_daily"),
            ("dataset", "etf.daily"),
        }

    def test_etf_daily_deduped(self) -> None:
        result = dependency_refs(("etf.open", "etf.close", "etf.open"))
        assert result == (("dataset", "etf.daily"),)

    def test_unsupported_etf_column_raises(self) -> None:
        with pytest.raises(NotImplementedError, match="Unsupported ETF dependency"):
            dependency_refs(("etf.unknown_column",))

    def test_derived_dependency_classified_as_derived(self) -> None:
        result = dependency_refs(("upstream.alpha_v2",))
        assert result == (("derived", "upstream.alpha_v2"),)

    def test_dependency_without_dot_skipped(self) -> None:
        result = dependency_refs(("plain_column",))
        assert result == ()

    def test_mixed_dependencies(self) -> None:
        result = dependency_refs(
            ("market.close", "etf.amount", "upstream.alpha", "bare_col")
        )
        assert set(result) == {
            ("dataset", "market.stock_daily"),
            ("dataset", "etf.daily"),
            ("derived", "upstream.alpha"),
        }

    def test_empty_input(self) -> None:
        result = dependency_refs(())
        assert result == ()
