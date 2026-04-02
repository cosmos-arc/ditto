"""Tests for PitHelper."""

import pytest
from ditto_data.helpers.pit import PitHelper


class TestPitHelper:
    """Test cases for PitHelper."""

    def test_add_pit_filter_no_where(self) -> None:
        """Test add_pit_filter adds WHERE clause when none exists."""
        query = "SELECT * FROM stock_daily"
        result = PitHelper.add_pit_filter(query, "2024-01-15")

        expected = "SELECT * FROM stock_daily WHERE knowledge_date <= '2024-01-15'"
        assert result == expected

    def test_add_pit_filter_with_where(self) -> None:
        """Test add_pit_filter adds AND clause when WHERE exists."""
        query = "SELECT * FROM stock_daily WHERE instrument_id = 1"
        result = PitHelper.add_pit_filter(query, "2024-01-15")

        expected = (
            "SELECT * FROM stock_daily "
            "WHERE instrument_id = 1 AND knowledge_date <= '2024-01-15'"
        )
        assert result == expected

    def test_add_pit_filter_custom_date_column(self) -> None:
        """Test add_pit_filter with custom date column."""
        query = "SELECT * FROM stock_daily"
        result = PitHelper.add_pit_filter(query, "2024-01-15", date_column="trade_date")

        expected = "SELECT * FROM stock_daily WHERE trade_date <= '2024-01-15'"
        assert result == expected

    def test_add_pit_filter_preserves_existing_conditions(self) -> None:
        """Test add_pit_filter preserves existing WHERE conditions."""
        query = "SELECT * FROM stock_daily WHERE instrument_id = 1 AND volume > 1000"
        result = PitHelper.add_pit_filter(query, "2024-01-15")

        expected = (
            "SELECT * FROM stock_daily WHERE instrument_id = 1 AND volume > 1000 "
            "AND knowledge_date <= '2024-01-15'"
        )
        assert result == expected

    def test_add_pit_join_basic(self) -> None:
        """Test add_pit_join generates correct JOIN syntax."""
        result = PitHelper.add_pit_join(
            "stock_daily s",
            "adj_factor a",
            ["s.instrument_id = a.instrument_id"],
            "2024-01-15",
        )

        expected = (
            "stock_daily s LEFT JOIN adj_factor a "
            "ON s.instrument_id = a.instrument_id AND a.trade_date <= '2024-01-15'"
        )
        assert result == expected

    def test_add_pit_join_multiple_keys(self) -> None:
        """Test add_pit_join with multiple join keys."""
        result = PitHelper.add_pit_join(
            "stock_daily s",
            "adj_factor a",
            ["s.instrument_id = a.instrument_id", "s.source = a.source"],
            "2024-01-15",
        )

        expected = (
            "stock_daily s LEFT JOIN adj_factor a "
            "ON s.instrument_id = a.instrument_id AND s.source = a.source "
            "AND a.trade_date <= '2024-01-15'"
        )
        assert result == expected

    def test_add_pit_join_custom_date_column(self) -> None:
        """Test add_pit_join with custom date column parameter."""
        result = PitHelper.add_pit_join(
            "stock_daily s",
            "adj_factor a",
            ["s.instrument_id = a.instrument_id"],
            "2024-01-15",
            date_column="effective_from",
        )

        expected = (
            "stock_daily s LEFT JOIN adj_factor a "
            "ON s.instrument_id = a.instrument_id AND a.effective_from <= '2024-01-15'"
        )
        assert result == expected

    def test_add_pit_join_custom_date_column_knowledge_date(self) -> None:
        """Test add_pit_join with knowledge_date column."""
        result = PitHelper.add_pit_join(
            "stock_daily s",
            "instrument_mapping m",
            ["s.instrument_id = m.instrument_id"],
            "2024-01-15",
            date_column="knowledge_date",
        )

        expected = (
            "stock_daily s LEFT JOIN instrument_mapping m "
            "ON s.instrument_id = m.instrument_id AND m.knowledge_date <= '2024-01-15'"
        )
        assert result == expected

    def test_add_pit_join_default_date_column(self) -> None:
        """Test add_pit_join with default date_column parameter."""
        # When date_column is not specified, should use "trade_date" (default)
        result = PitHelper.add_pit_join(
            "stock_daily s",
            "adj_factor a",
            ["s.instrument_id = a.instrument_id"],
            "2024-01-15",
        )

        expected = (
            "stock_daily s LEFT JOIN adj_factor a "
            "ON s.instrument_id = a.instrument_id AND a.trade_date <= '2024-01-15'"
        )
        assert result == expected

    def test_wrap_pit_cte_basic(self) -> None:
        """Test wrap_pit_cte wraps query in CTE."""
        query = "SELECT instrument_id, close FROM stock_daily"
        result = PitHelper.wrap_pit_cte(query, "pit_data")

        expected = (
            "WITH pit_data AS (SELECT instrument_id, close FROM stock_daily) "
            "SELECT * FROM pit_data"
        )
        assert result == expected

    def test_wrap_pit_cte_with_asof_date(self) -> None:
        """Test wrap_pit_cte adds WHERE clause when asof_date provided."""
        query = "SELECT instrument_id, close FROM stock_daily"
        result = PitHelper.wrap_pit_cte(query, "pit_data", asof_date="2024-01-15")

        expected = (
            "WITH pit_data AS (SELECT instrument_id, close FROM stock_daily) "
            "SELECT * FROM pit_data WHERE trade_date <= '2024-01-15'"
        )
        assert result == expected

    def test_wrap_pit_cte_custom_name(self) -> None:
        """Test wrap_pit_cte with custom CTE name."""
        query = "SELECT instrument_id, close FROM stock_daily"
        result = PitHelper.wrap_pit_cte(query, "my_cte")

        expected = (
            "WITH my_cte AS (SELECT instrument_id, close FROM stock_daily) "
            "SELECT * FROM my_cte"
        )
        assert result == expected

    def test_get_safe_trade_date_default(self) -> None:
        """Test get_safe_trade_date with default parameters."""
        result = PitHelper.get_safe_trade_date()

        assert result == "trade_date <= $asof"

    def test_get_safe_trade_date_custom_column(self) -> None:
        """Test get_safe_trade_date with custom column name."""
        result = PitHelper.get_safe_trade_date(base_column="knowledge_date")

        assert result == "knowledge_date <= $asof"

    def test_get_safe_trade_date_specific_date(self) -> None:
        """Test get_safe_trade_date with specific date."""
        result = PitHelper.get_safe_trade_date(knowledge_date="2024-01-15")

        assert result == "trade_date <= '2024-01-15'"

    def test_get_safe_trade_date_custom_column_and_date(self) -> None:
        """Test get_safe_trade_date with custom column and date."""
        result = PitHelper.get_safe_trade_date(
            base_column="knowledge_date", knowledge_date="2024-01-15"
        )

        assert result == "knowledge_date <= '2024-01-15'"

    def test_add_pit_filter_case_insensitive(self) -> None:
        """Test add_pit_filter handles WHERE case insensitively."""
        query = "SELECT * FROM stock_daily where instrument_id = 1"
        result = PitHelper.add_pit_filter(query, "2024-01-15")

        assert result == (
            "SELECT * FROM stock_daily "
            "where instrument_id = 1 AND knowledge_date <= '2024-01-15'"
        )

    def test_wrap_pit_cte_no_asof_date(self) -> None:
        """Test wrap_pit_cte without asof_date doesn't add WHERE."""
        query = "SELECT instrument_id, close FROM stock_daily WHERE instrument_id = 1"
        result = PitHelper.wrap_pit_cte(query, "pit_data", asof_date=None)

        # [REVIEW] WHERE
        expected = (
            "WITH pit_data AS ("
            "SELECT instrument_id, close FROM stock_daily WHERE instrument_id = 1"
            ") "
            "SELECT * FROM pit_data"
        )
        assert result == expected

    def test_combined_pit_query_workflow(self) -> None:
        """Test combined workflow of using multiple PitHelper methods."""
        # [REVIEW]
        query = "SELECT instrument_id, close FROM stock_daily WHERE instrument_id = 1"

        # [REVIEW] CTE
        cte_query = PitHelper.wrap_pit_cte(query, "filtered_data")
        # [REVIEW] PIT 过滤
        pit_query = PitHelper.add_pit_filter(cte_query, "2024-01-15")

        # [REVIEW] CTE 和 PIT 过滤
        assert "WITH filtered_data AS" in pit_query
        assert "knowledge_date <= '2024-01-15'" in pit_query


class TestSQLSyntaxHandling:
    """Tests for handling complex SQL syntax (ORDER BY, LIMIT, etc.)."""

    def test_add_pit_filter_with_order_by(self) -> None:
        """Test add_pit_filter handles ORDER BY clause correctly."""
        query = "SELECT * FROM stock_daily ORDER BY trade_date DESC"
        result = PitHelper.add_pit_filter(query, "2024-01-15")

        # Should use CTE wrapper to avoid breaking ORDER BY
        assert "WITH _pit_original AS" in result
        assert "knowledge_date <= '2024-01-15'" in result
        assert "ORDER BY trade_date DESC" in result

    def test_add_pit_filter_with_limit(self) -> None:
        """Test add_pit_filter handles LIMIT clause correctly."""
        query = "SELECT * FROM stock_daily LIMIT 100"
        result = PitHelper.add_pit_filter(query, "2024-01-15")

        # Should use CTE wrapper to avoid breaking LIMIT
        assert "WITH _pit_original AS" in result
        assert "knowledge_date <= '2024-01-15'" in result
        assert "LIMIT 100" in result

    def test_add_pit_filter_with_group_by(self) -> None:
        """Test add_pit_filter handles GROUP BY clause correctly."""
        query = (
            "SELECT instrument_id, AVG(close) FROM stock_daily GROUP BY instrument_id"
        )
        result = PitHelper.add_pit_filter(query, "2024-01-15")

        # Should use CTE wrapper to avoid breaking GROUP BY
        assert "WITH _pit_original AS" in result
        assert "knowledge_date <= '2024-01-15'" in result
        assert "GROUP BY instrument_id" in result

    def test_add_pit_filter_with_having(self) -> None:
        """Test add_pit_filter handles HAVING clause correctly."""
        query = (
            "SELECT instrument_id, AVG(close) as avg_close FROM stock_daily "
            "GROUP BY instrument_id HAVING avg_close > 10"
        )
        result = PitHelper.add_pit_filter(query, "2024-01-15")

        # Should use CTE wrapper to avoid breaking HAVING
        assert "WITH _pit_original AS" in result
        assert "knowledge_date <= '2024-01-15'" in result
        assert "HAVING avg_close > 10" in result

    def test_add_pit_filter_with_where_and_order_by(self) -> None:
        """Test add_pit_filter handles WHERE + ORDER BY correctly."""
        query = (
            "SELECT * FROM stock_daily WHERE instrument_id = 1 ORDER BY trade_date DESC"
        )
        result = PitHelper.add_pit_filter(query, "2024-01-15")

        # Should use CTE wrapper because ORDER BY is present
        assert "WITH _pit_original AS" in result
        assert "knowledge_date <= '2024-01-15'" in result

    def test_add_pit_filter_with_order_by_and_limit(self) -> None:
        """Test add_pit_filter handles ORDER BY + LIMIT correctly."""
        query = "SELECT * FROM stock_daily ORDER BY trade_date DESC LIMIT 10"
        result = PitHelper.add_pit_filter(query, "2024-01-15")

        # Should use CTE wrapper
        assert "WITH _pit_original AS" in result
        assert "knowledge_date <= '2024-01-15'" in result
        assert "ORDER BY trade_date DESC" in result
        assert "LIMIT 10" in result


class TestSQLInjectionProtection:
    """Tests for SQL injection protection in PitHelper."""

    def test_add_pit_filter_rejects_invalid_date_format(self) -> None:
        """Test that add_pit_filter rejects invalid date format."""
        with pytest.raises(ValueError, match="Invalid date format"):
            PitHelper.add_pit_filter("SELECT * FROM stock_daily", "2024/01/15")

    def test_add_pit_filter_rejects_sql_injection_single_quote(self) -> None:
        """Test that add_pit_filter rejects SQL injection with single quote."""
        with pytest.raises(ValueError, match="Invalid date format"):
            PitHelper.add_pit_filter(
                "SELECT * FROM stock_daily", "2024-01-15' OR '1'='1"
            )

    def test_add_pit_filter_rejects_sql_injection_comment(self) -> None:
        """Test that add_pit_filter rejects SQL injection with comment."""
        with pytest.raises(ValueError, match="Invalid date format"):
            PitHelper.add_pit_filter("SELECT * FROM stock_daily", "2024-01-15--")

    def test_add_pit_filter_rejects_sql_injection_semicolon(self) -> None:
        """Test that add_pit_filter rejects SQL injection with semicolon."""
        with pytest.raises(ValueError, match="Invalid date format"):
            PitHelper.add_pit_filter(
                "SELECT * FROM stock_daily", "2024-01-15; DROP TABLE users--"
            )

    def test_add_pit_join_rejects_invalid_date_format(self) -> None:
        """Test that add_pit_join rejects invalid date format."""
        with pytest.raises(ValueError, match="Invalid date format"):
            PitHelper.add_pit_join(
                "stock_daily s",
                "adj_factor a",
                ["s.instrument_id = a.instrument_id"],
                "2024/01/15",
            )

    def test_add_pit_join_rejects_sql_injection(self) -> None:
        """Test that add_pit_join rejects SQL injection."""
        with pytest.raises(ValueError, match="Invalid date format"):
            PitHelper.add_pit_join(
                "stock_daily s",
                "adj_factor a",
                ["s.instrument_id = a.instrument_id"],
                "2024-01-15' OR '1'='1",
            )

    def test_wrap_pit_cte_rejects_invalid_date_format(self) -> None:
        """Test that wrap_pit_cte rejects invalid date format."""
        with pytest.raises(ValueError, match="Invalid date format"):
            PitHelper.wrap_pit_cte(
                "SELECT instrument_id, close FROM stock_daily", "pit_data", "2024/01/15"
            )

    def test_wrap_pit_cte_rejects_sql_injection(self) -> None:
        """Test that wrap_pit_cte rejects SQL injection."""
        with pytest.raises(ValueError, match="Invalid date format"):
            PitHelper.wrap_pit_cte(
                "SELECT instrument_id, close FROM stock_daily",
                "pit_data",
                "2024-01-15'; DROP TABLE users--",
            )

    def test_get_safe_trade_date_rejects_invalid_date_format(self) -> None:
        """Test that get_safe_trade_date rejects invalid date format."""
        with pytest.raises(ValueError, match="Invalid date format"):
            PitHelper.get_safe_trade_date(knowledge_date="2024/01/15")

    def test_get_safe_trade_date_rejects_sql_injection(self) -> None:
        """Test that get_safe_trade_date rejects SQL injection."""
        with pytest.raises(ValueError, match="Invalid date format"):
            PitHelper.get_safe_trade_date(knowledge_date="2024-01-15' OR '1'='1")

    def test_add_pit_filter_accepts_valid_date(self) -> None:
        """Test that add_pit_filter accepts valid date format."""
        # Should not raise
        result = PitHelper.add_pit_filter("SELECT * FROM stock_daily", "2024-01-15")
        assert "knowledge_date <= '2024-01-15'" in result

    def test_validate_sql_identifier_rejects_empty_string(self) -> None:
        """Test that _validate_sql_identifier rejects empty string."""
        with pytest.raises(ValueError, match="Invalid identifier"):
            PitHelper._validate_sql_identifier("")

    def test_validate_sql_identifier_rejects_starting_with_number(self) -> None:
        """Test that _validate_sql_identifier rejects identifiers starting with
        number."""
        with pytest.raises(ValueError, match="Invalid identifier"):
            PitHelper._validate_sql_identifier("123table")

    def test_validate_sql_identifier_rejects_special_characters(self) -> None:
        """Test that _validate_sql_identifier rejects special characters."""
        with pytest.raises(ValueError, match="Invalid identifier"):
            PitHelper._validate_sql_identifier("table-name")

    def test_validate_sql_identifier_rejects_sql_injection(self) -> None:
        """Test that _validate_sql_identifier rejects SQL injection attempts."""
        with pytest.raises(ValueError, match="Invalid identifier"):
            PitHelper._validate_sql_identifier("table; DROP TABLE users--")

    def test_validate_sql_identifier_rejects_hyphen(self) -> None:
        """Test that _validate_sql_identifier rejects hyphens."""
        with pytest.raises(ValueError, match="Invalid identifier"):
            PitHelper._validate_sql_identifier("my-table")

    def test_validate_sql_identifier_rejects_space(self) -> None:
        """Test that _validate_sql_identifier rejects spaces."""
        with pytest.raises(ValueError, match="Invalid identifier"):
            PitHelper._validate_sql_identifier("my table")

    def test_validate_sql_identifier_accepts_valid_identifier(self) -> None:
        """Test that _validate_sql_identifier accepts valid identifiers."""
        # Should not raise
        PitHelper._validate_sql_identifier("table_name")
        PitHelper._validate_sql_identifier("_private")
        PitHelper._validate_sql_identifier("Table123")
        PitHelper._validate_sql_identifier("a")

    def test_validate_sql_identifier_custom_name(self) -> None:
        """Test that _validate_sql_identifier uses custom name in error message."""
        with pytest.raises(ValueError, match="Invalid cte_name"):
            PitHelper._validate_sql_identifier("123invalid", "cte_name")

    def test_add_pit_join_single_word_right_table(self) -> None:
        """Test add_pit_join with single word right table (no alias)."""
        result = PitHelper.add_pit_join(
            "stock_daily s",
            "adj_factor",
            ["s.instrument_id = adj_factor.instrument_id"],
            "2024-01-15",
        )

        # When right_table has no space, entire string is used as alias
        expected = (
            "stock_daily s LEFT JOIN adj_factor "
            "ON s.instrument_id = adj_factor.instrument_id "
            "AND adj_factor.trade_date <= '2024-01-15'"
        )
        assert result == expected

    def test_add_pit_join_right_table_multiple_spaces(self) -> None:
        """Test add_pit_join with multiple spaces in right table."""
        result = PitHelper.add_pit_join(
            "stock_daily s",
            "adj_factor   a",
            ["s.instrument_id = a.instrument_id"],
            "2024-01-15",
        )

        # Should handle multiple spaces correctly
        expected = (
            "stock_daily s LEFT JOIN adj_factor   a "
            "ON s.instrument_id = a.instrument_id AND a.trade_date <= '2024-01-15'"
        )
        assert result == expected

    def test_get_safe_trade_date_with_custom_placeholder(self) -> None:
        """Test get_safe_trade_date with custom placeholder."""
        result = PitHelper.get_safe_trade_date(
            base_column="knowledge_date", knowledge_date="$latest_date"
        )

        # Should not add quotes around custom placeholder
        assert result == "knowledge_date <= $latest_date"

    def test_get_safe_trade_date_placeholder_with_custom_column(self) -> None:
        """Test get_safe_trade_date with placeholder and custom column."""
        result = PitHelper.get_safe_trade_date(
            base_column="effective_date", knowledge_date="$asof"
        )

        # Should use custom column without quotes on placeholder
        assert result == "effective_date <= $asof"
