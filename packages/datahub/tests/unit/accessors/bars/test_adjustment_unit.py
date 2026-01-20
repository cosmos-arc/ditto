"""Tests for adjustment module (pure functions)."""

from datetime import date

import polars as pl
import pytest
from ditto_datahub.accessors.bars.adjustment import (
    apply_hfq_adj,
    apply_qfq_adj,
    filter_baseline_by_asof,
    parse_asof_date,
)


class TestParseAsofDate:
    """Tests for parse_asof_date function."""

    def test_parse_iso_string(self) -> None:
        """Test parsing ISO format string to date."""
        result = parse_asof_date("2024-01-15")
        assert result == date(2024, 1, 15)

    def test_return_date_object(self) -> None:
        """Test returning date object as-is."""
        input_date = date(2024, 1, 15)
        result = parse_asof_date(input_date)
        assert result == input_date
        assert result is input_date  # Same object


class TestFilterBaselineByAsof:
    """Tests for filter_baseline_by_asof function."""

    def test_filter_with_knowledge_date(self) -> None:
        """Test filtering with knowledge_date column."""
        adj_df = pl.DataFrame(
            {
                "sid": [1, 1, 1, 2, 2],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                ],
                "knowledge_date": [
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 4),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                ],
                "adj_factor": [1.0, 1.1, 1.2, 1.0, 1.05],
            }
        )

        result = filter_baseline_by_asof(adj_df, date(2024, 1, 3))

        # Should include rows with knowledge_date <= 2024-01-03
        assert len(result) == 4
        assert result["sid"].to_list() == [1, 1, 2, 2]
        assert result["trade_date"].to_list() == [
            date(2024, 1, 1),
            date(2024, 1, 2),
            date(2024, 1, 1),
            date(2024, 1, 2),
        ]
        assert result["knowledge_date"].to_list() == [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 2),
            date(2024, 1, 3),
        ]
        assert result["adj_factor"].to_list() == [1.0, 1.1, 1.0, 1.05]

    def test_filter_without_knowledge_date(self) -> None:
        """Test filtering without knowledge_date column (fallback to trade_date)."""
        adj_df = pl.DataFrame(
            {
                "sid": [1, 1, 1, 2, 2],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                ],
                "adj_factor": [1.0, 1.1, 1.2, 1.0, 1.05],
            }
        )

        result = filter_baseline_by_asof(adj_df, date(2024, 1, 2))

        # Should include rows with trade_date <= 2024-01-02
        assert len(result) == 4
        assert result["sid"].to_list() == [1, 1, 2, 2]
        assert result["trade_date"].to_list() == [
            date(2024, 1, 1),
            date(2024, 1, 2),
            date(2024, 1, 1),
            date(2024, 1, 2),
        ]
        assert result["adj_factor"].to_list() == [1.0, 1.1, 1.0, 1.05]

        # Note: Warning is logged but we don't test it here to avoid
        # caplog complexity. The warning functionality is tested in the
        # existing test_bars_qfq_helpers_unit.py


class TestApplyQfqAdj:
    """Tests for apply_qfq_adj function."""

    def test_basic_qfq_adjustment(self) -> None:
        """Test basic QFQ adjustment without asof."""
        # K线数据
        df = pl.DataFrame(
            {
                "sid": [1, 1, 1],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                ],
                "open": [10.0, 11.0, 12.0],
                "high": [10.5, 11.5, 12.5],
                "low": [9.5, 10.5, 11.5],
                "close": [10.0, 11.0, 12.0],
                "adj_factor": [1.0, 1.1, 1.2],
            }
        )

        # [REVIEW]
        adj_df = pl.DataFrame(
            {
                "sid": [1, 1, 1],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                ],
                "adj_factor": [1.0, 1.1, 1.2],
            }
        )

        result = apply_qfq_adj(df, adj_df)

        # QFQ: adj_price = orig_price * cur_factor / latest_factor
        # latest_factor = 1.2
        # Day 1: 10.0 * 1.0 / 1.2 = 8.333...
        # Day 2: 11.0 * 1.1 / 1.2 = 10.083...
        # Day 3: 12.0 * 1.2 / 1.2 = 12.0
        assert len(result) == 3
        assert result["open"].to_list() == [
            10.0 * 1.0 / 1.2,
            11.0 * 1.1 / 1.2,
            12.0 * 1.2 / 1.2,
        ]
        assert result["close"].to_list() == [
            10.0 * 1.0 / 1.2,
            11.0 * 1.1 / 1.2,
            12.0 * 1.2 / 1.2,
        ]
        # adj_factor and latest_factor should be dropped
        assert "adj_factor" not in result.columns
        assert "latest_factor" not in result.columns

    def test_qfq_with_asof(self) -> None:
        """Test QFQ adjustment with asof parameter."""
        df = pl.DataFrame(
            {
                "sid": [1, 1, 1, 1],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 4),
                ],
                "open": [10.0, 11.0, 12.0, 13.0],
                "high": [10.5, 11.5, 12.5, 13.5],
                "low": [9.5, 10.5, 11.5, 12.5],
                "close": [10.0, 11.0, 12.0, 13.0],
                "adj_factor": [1.0, 1.1, 1.2, 1.3],
            }
        )

        # [REVIEW] with knowledge_date
        adj_df = pl.DataFrame(
            {
                "sid": [1, 1, 1, 1],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 4),
                ],
                "knowledge_date": [
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                    date(2024, 1, 4),
                    date(2024, 1, 5),
                ],
                "adj_factor": [1.0, 1.1, 1.2, 1.3],
            }
        )

        # asof = 2024-01-03, baseline should only use factors with
        # knowledge_date <= 2024-01-03
        # latest_factor = 1.1 (from 2024-01-02)
        result = apply_qfq_adj(df, adj_df, asof=date(2024, 1, 3))

        # All prices adjusted using latest_factor = 1.1
        expected_latest = 1.1
        assert result["open"].to_list() == [
            10.0 * 1.0 / expected_latest,
            11.0 * 1.1 / expected_latest,
            12.0 * 1.2 / expected_latest,
            13.0 * 1.3 / expected_latest,
        ]
        assert result["close"].to_list() == [
            10.0 * 1.0 / expected_latest,
            11.0 * 1.1 / expected_latest,
            12.0 * 1.2 / expected_latest,
            13.0 * 1.3 / expected_latest,
        ]

    def test_qfq_missing_factor(self) -> None:
        """Test QFQ adjustment with missing adj_factor."""
        df = pl.DataFrame(
            {
                "sid": [1, 1, 2],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 1),
                ],
                "open": [10.0, 11.0, 20.0],
                "high": [10.5, 11.5, 20.5],
                "low": [9.5, 10.5, 19.5],
                "close": [10.0, 11.0, 20.0],
                "adj_factor": [1.0, 1.1, None],
            }
        )

        adj_df = pl.DataFrame(
            {
                "sid": [1, 1],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                ],
                "adj_factor": [1.0, 1.1],
            }
        )

        result = apply_qfq_adj(df, adj_df)

        # SID 2 should have unchanged prices (coalesce to 1.0)
        assert result["open"].to_list() == [
            10.0 * 1.0 / 1.1,
            11.0 * 1.1 / 1.1,
            20.0,  # No factor, unchanged
        ]
        assert result["close"].to_list() == [
            10.0 * 1.0 / 1.1,
            11.0 * 1.1 / 1.1,
            20.0,  # No factor, unchanged
        ]

    def test_qfq_with_asof_string(self) -> None:
        """Test QFQ adjustment with asof as string."""
        df = pl.DataFrame(
            {
                "sid": [1, 1],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                ],
                "open": [10.0, 11.0],
                "high": [10.5, 11.5],
                "low": [9.5, 10.5],
                "close": [10.0, 11.0],
                "adj_factor": [1.0, 1.1],
            }
        )

        adj_df = pl.DataFrame(
            {
                "sid": [1, 1],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                ],
                "knowledge_date": [
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                ],
                "adj_factor": [1.0, 1.1],
            }
        )

        # asof as string
        result = apply_qfq_adj(df, adj_df, asof="2024-01-02")

        # baseline = factors with knowledge_date <= 2024-01-02
        # latest_factor = 1.0
        assert len(result) == 2
        # First row should be adjusted with 1.0/1.0 = 1.0
        assert result["close"][0] == 10.0 * 1.0 / 1.0


class TestApplyHfqAdj:
    """Tests for apply_hfq_adj function."""

    def test_basic_hfq_adjustment(self) -> None:
        """Test basic HFQ adjustment."""
        df = pl.DataFrame(
            {
                "sid": [1, 1, 1],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                ],
                "open": [10.0, 11.0, 12.0],
                "high": [10.5, 11.5, 12.5],
                "low": [9.5, 10.5, 11.5],
                "close": [10.0, 11.0, 12.0],
                "adj_factor": [1.0, 1.1, 1.2],
            }
        )

        adj_df = pl.DataFrame(
            {
                "sid": [1, 1, 1],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 3),
                ],
                "adj_factor": [1.0, 1.1, 1.2],
            }
        )

        result = apply_hfq_adj(df, adj_df)

        # HFQ: adj_price = orig_price * cur_factor
        assert result["open"].to_list() == pytest.approx([10.0, 12.1, 14.4])
        assert result["close"].to_list() == pytest.approx([10.0, 12.1, 14.4])
        # adj_factor should be dropped
        assert "adj_factor" not in result.columns

    def test_hfq_missing_factor(self) -> None:
        """Test HFQ adjustment with missing adj_factor."""
        df = pl.DataFrame(
            {
                "sid": [1, 1, 2],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                    date(2024, 1, 1),
                ],
                "open": [10.0, 11.0, 20.0],
                "high": [10.5, 11.5, 20.5],
                "low": [9.5, 10.5, 19.5],
                "close": [10.0, 11.0, 20.0],
                "adj_factor": [1.0, 1.1, None],
            }
        )

        adj_df = pl.DataFrame(
            {
                "sid": [1, 1],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                ],
                "adj_factor": [1.0, 1.1],
            }
        )

        result = apply_hfq_adj(df, adj_df)

        # SID 2 should have unchanged prices (coalesce to 1.0)
        assert result["open"].to_list() == pytest.approx([10.0, 12.1, 20.0])
        assert result["close"].to_list() == pytest.approx([10.0, 12.1, 20.0])
