"""Tests for bond yield adapter error handling."""

from datetime import date

from ditto_datahub.sources.tushare.adapters.bond_yield import (
    CN_BOND_YIELD_INDICATORS,
    BondYieldTushareAdapter,
)


class TestBondYieldErrorHandling:
    """Tests for handling invalid data in bond yield responses."""

    def test_parse_row_skips_invalid_curve_term(self) -> None:
        """Rows with non-numeric curve_term should be skipped, not defaulted to 0.0."""
        adapter = BondYieldTushareAdapter.__new__(BondYieldTushareAdapter)

        row = {
            "curve_term": "--",  # Invalid
            "trade_date": "20240101",
            "yield": 2.5,
        }

        term_to_indicator = {
            1.0: ("CN_BOND_YIELD_1Y", CN_BOND_YIELD_INDICATORS["CN_BOND_YIELD_1Y"]),
        }

        result = adapter._parse_row(row, term_to_indicator)
        # Should return None, NOT a tuple with value=0.0
        assert result is None

    def test_parse_row_skips_invalid_yield(self) -> None:
        """Rows with non-numeric yield should be skipped, not defaulted to 0.0."""
        adapter = BondYieldTushareAdapter.__new__(BondYieldTushareAdapter)

        row = {
            "curve_term": 1.0,
            "trade_date": "20240101",
            "yield": "--",  # Invalid
        }

        term_to_indicator = {
            1.0: ("CN_BOND_YIELD_1Y", CN_BOND_YIELD_INDICATORS["CN_BOND_YIELD_1Y"]),
        }

        result = adapter._parse_row(row, term_to_indicator)
        assert result is None

    def test_parse_row_accepts_valid_data(self) -> None:
        """Valid data should be parsed correctly."""
        adapter = BondYieldTushareAdapter.__new__(BondYieldTushareAdapter)

        row = {
            "curve_term": 1.0,
            "trade_date": "20240101",
            "yield": 2.5,
        }

        term_to_indicator = {
            1.0: ("CN_BOND_YIELD_1Y", CN_BOND_YIELD_INDICATORS["CN_BOND_YIELD_1Y"]),
        }

        result = adapter._parse_row(row, term_to_indicator)
        assert result is not None
        code, _indicator, date_obj, value = result
        assert value == 2.5
        assert code == "CN_BOND_YIELD_1Y"
        assert date_obj == date(2024, 1, 1)

    def test_parse_row_skips_none_curve_term(self) -> None:
        """Rows with None curve_term should be skipped."""
        adapter = BondYieldTushareAdapter.__new__(BondYieldTushareAdapter)

        row = {
            "curve_term": None,
            "trade_date": "20240101",
            "yield": 2.5,
        }

        term_to_indicator = {
            1.0: ("CN_BOND_YIELD_1Y", CN_BOND_YIELD_INDICATORS["CN_BOND_YIELD_1Y"]),
        }

        result = adapter._parse_row(row, term_to_indicator)
        assert result is None

    def test_parse_row_skips_none_yield(self) -> None:
        """Rows with None yield should be skipped."""
        adapter = BondYieldTushareAdapter.__new__(BondYieldTushareAdapter)

        row = {
            "curve_term": 1.0,
            "trade_date": "20240101",
            "yield": None,
        }

        term_to_indicator = {
            1.0: ("CN_BOND_YIELD_1Y", CN_BOND_YIELD_INDICATORS["CN_BOND_YIELD_1Y"]),
        }

        result = adapter._parse_row(row, term_to_indicator)
        assert result is None

    def test_parse_row_skips_invalid_trade_date(self) -> None:
        """Rows with invalid trade_date should be skipped."""
        adapter = BondYieldTushareAdapter.__new__(BondYieldTushareAdapter)

        row = {
            "curve_term": 1.0,
            "trade_date": "invalid",
            "yield": 2.5,
        }

        term_to_indicator = {
            1.0: ("CN_BOND_YIELD_1Y", CN_BOND_YIELD_INDICATORS["CN_BOND_YIELD_1Y"]),
        }

        result = adapter._parse_row(row, term_to_indicator)
        assert result is None

    def test_parse_row_skips_unmatched_curve_term(self) -> None:
        """Rows with curve_term not in mapping should be skipped."""
        adapter = BondYieldTushareAdapter.__new__(BondYieldTushareAdapter)

        row = {
            "curve_term": 99.0,  # Not in mapping
            "trade_date": "20240101",
            "yield": 2.5,
        }

        term_to_indicator = {
            1.0: ("CN_BOND_YIELD_1Y", CN_BOND_YIELD_INDICATORS["CN_BOND_YIELD_1Y"]),
        }

        result = adapter._parse_row(row, term_to_indicator)
        assert result is None
