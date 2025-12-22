"""Tests for DQ Checker."""

import polars as pl
from ditto_datahub.runtime.dq_checker import DQChecker


class TestDQChecker:
    """Test cases for DQChecker."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.dq_checker = DQChecker()

    def test_check_valid_market_daily(self) -> None:
        """Test checking valid market daily data."""
        # Create valid OHLC data
        df = pl.DataFrame(
            {
                "sid": [100001, 100001, 100002],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-01"],
                "open": [10.0, 10.5, 20.0],
                "high": [10.2, 10.8, 20.5],
                "low": [9.8, 10.2, 19.5],
                "close": [10.1, 10.6, 20.2],
                "volume": [1000, 1200, 800],
                "amount": [10100, 12720, 16160],
            }
        )

        result = self.dq_checker.check(df, "market_daily")

        assert result.passed
        assert result.fail_count == 0
        assert all(r.passed for r in result.results)

    def test_check_duplicate_primary_key(self) -> None:
        """Test duplicate primary key detection."""
        # Create data with duplicate (sid, trade_date)
        df = pl.DataFrame(
            {
                "sid": [100001, 100001, 100001],
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-01"],  # Duplicate
                "open": [10.0, 10.5, 10.2],
                "high": [10.2, 10.8, 10.4],
                "low": [9.8, 10.2, 9.9],
                "close": [10.1, 10.6, 10.3],
                "volume": [1000, 1200, 1100],
                "amount": [10100, 12720, 11130],
            }
        )

        result = self.dq_checker.check(df, "market_daily")

        assert not result.passed
        assert result.fail_count > 0

        # Find primary key error
        pk_errors = [r for r in result.results if r.rule_name == "primary_key_unique"]
        assert len(pk_errors) == 1
        assert not pk_errors[0].passed
        assert "duplicate" in pk_errors[0].message.lower()

    def test_check_null_sid(self) -> None:
        """Test null SID detection."""
        # Create data with null sid
        df = pl.DataFrame(
            {
                "sid": [100001, None, 100002],  # One null SID
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-01"],
                "open": [10.0, 10.5, 20.0],
                "high": [10.2, 10.8, 20.5],
                "low": [9.8, 10.2, 19.5],
                "close": [10.1, 10.6, 20.2],
            }
        )

        result = self.dq_checker.check(df, "market_daily")

        assert not result.passed
        assert result.fail_count > 0

        # Find null SID error
        null_errors = [r for r in result.results if r.rule_name == "sid_not_null"]
        assert len(null_errors) == 1
        assert not null_errors[0].passed
        assert null_errors[0].affected_rows == 1

    def test_check_negative_prices(self) -> None:
        """Test negative price detection."""
        # Create data with negative prices
        df = pl.DataFrame(
            {
                "sid": [100001, 100002, 100003],
                "trade_date": ["2024-01-01", "2024-01-01", "2024-01-01"],
                "open": [10.0, -5.0, 20.0],  # Negative open
                "high": [10.2, 10.8, -10.0],  # Negative high
                "low": [9.8, 10.2, 19.5],
                "close": [10.1, 10.6, 20.2],
            }
        )

        result = self.dq_checker.check(df, "market_daily")

        assert not result.passed
        assert result.fail_count > 0

        # Find negative price error
        price_errors = [r for r in result.results if r.rule_name == "ohlc_positive"]
        assert len(price_errors) == 1
        assert not price_errors[0].passed
        assert price_errors[0].affected_rows == 2

    def test_check_ohlc_relationship_violation(self) -> None:
        """Test OHLC relationship violation detection."""
        # Create data with OHLC violations
        df = pl.DataFrame(
            {
                "sid": [100001, 100002],
                "trade_date": ["2024-01-01", "2024-01-01"],
                "open": [10.5, 15.0],
                "high": [10.2, 14.0],  # High lower than open
                "low": [10.8, 16.0],  # Low higher than open
                "close": [10.1, 15.5],
            }
        )

        result = self.dq_checker.check(df, "market_daily")

        assert not result.passed
        assert result.fail_count > 0

        # Find OHLC relationship error
        ohlc_errors = [r for r in result.results if r.rule_name == "ohlc_relationship"]
        assert len(ohlc_errors) == 1
        assert not ohlc_errors[0].passed
        assert ohlc_errors[0].affected_rows == 2

    def test_check_etf_daily_subset(self) -> None:
        """Test ETF daily data with subset of rules."""
        df = pl.DataFrame(
            {
                "sid": [200001, 200001],  # ETF SIDs
                "trade_date": ["2024-01-01", "2024-01-02"],
                "open": [10.0, 10.5],
                "high": [10.2, 10.8],
                "low": [9.8, 10.2],
                "close": [10.1, 10.6],
            }
        )

        result = self.dq_checker.check(df, "etf_daily")

        assert result.passed
        # ETF daily should have fewer rules than market_daily
        assert len(result.results) == 3  # pk_unique, sid_not_null, ohlc_positive

    def test_check_unknown_dataset(self) -> None:
        """Test checking unknown dataset ID."""
        df = pl.DataFrame({"test": [1, 2, 3]})

        result = self.dq_checker.check(df, "unknown_dataset")

        # Should pass with no rules
        assert result.passed
        assert len(result.results) == 0

    def test_check_index_weight(self) -> None:
        """Test index weight validation."""
        # Create valid index weight data
        df = pl.DataFrame(
            {
                "index_sid": [300001, 300001, 300001],
                "con_sid": [100001, 100002, 100003],
                "trade_date": ["2024-01-01", "2024-01-01", "2024-01-01"],
                "weight": [0.3, 0.4, 0.3],
            }
        )

        result = self.dq_checker.check(df, "index_weight")

        assert result.passed

        # Test with negative weight
        df_bad = df.with_columns(
            pl.when(pl.col("con_sid") == 100002)
            .then(pl.lit(-0.1))
            .otherwise(pl.col("weight"))
            .alias("weight")
        )

        result_bad = self.dq_checker.check(df_bad, "index_weight")

        # Weight violations are warnings, not failures, so overall should pass
        assert result_bad.passed
        assert result_bad.warn_count == 1  # Weight is a warning, not failure

        weight_errors = [
            r for r in result_bad.results if r.rule_name == "weight_positive"
        ]
        assert len(weight_errors) == 1
        assert not weight_errors[0].passed
