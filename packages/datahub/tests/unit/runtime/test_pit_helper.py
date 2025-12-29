"""Tests for PitHelper."""

from ditto_datahub.runtime.pit_helper import PitHelper


class TestPitHelper:
    """Test cases for PitHelper."""

    def test_add_pit_filter_no_where(self) -> None:
        """Test add_pit_filter adds WHERE clause when none exists."""
        query = "SELECT * FROM stock_daily"
        result = PitHelper.add_pit_filter(query, "2024-01-15")

        expected = (
            "SELECT * FROM stock_daily WHERE knowledge_date <= '2024-01-15'"
        )
        assert result == expected

    def test_add_pit_filter_with_where(self) -> None:
        """Test add_pit_filter adds AND clause when WHERE exists."""
        query = "SELECT * FROM stock_daily WHERE sid = 1"
        result = PitHelper.add_pit_filter(query, "2024-01-15")

        expected = (
            "SELECT * FROM stock_daily WHERE sid = 1 "
            "AND knowledge_date <= '2024-01-15'"
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
        query = "SELECT * FROM stock_daily WHERE sid = 1 AND volume > 1000"
        result = PitHelper.add_pit_filter(query, "2024-01-15")

        expected = (
            "SELECT * FROM stock_daily WHERE sid = 1 AND volume > 1000 "
            "AND knowledge_date <= '2024-01-15'"
        )
        assert result == expected

    def test_add_pit_join_basic(self) -> None:
        """Test add_pit_join generates correct JOIN syntax."""
        result = PitHelper.add_pit_join(
            "stock_daily s",
            "adj_factor a",
            ["s.sid = a.sid"],
            "2024-01-15",
        )

        expected = (
            "stock_daily s LEFT JOIN adj_factor a "
            "ON s.sid = a.sid AND a.trade_date <= '2024-01-15'"
        )
        assert result == expected

    def test_add_pit_join_multiple_keys(self) -> None:
        """Test add_pit_join with multiple join keys."""
        result = PitHelper.add_pit_join(
            "stock_daily s",
            "adj_factor a",
            ["s.sid = a.sid", "s.source = a.source"],
            "2024-01-15",
        )

        expected = (
            "stock_daily s LEFT JOIN adj_factor a "
            "ON s.sid = a.sid AND s.source = a.source "
            "AND a.trade_date <= '2024-01-15'"
        )
        assert result == expected

    def test_wrap_pit_cte_basic(self) -> None:
        """Test wrap_pit_cte wraps query in CTE."""
        query = "SELECT sid, close FROM stock_daily"
        result = PitHelper.wrap_pit_cte(query, "pit_data")

        expected = (
            "WITH pit_data AS (SELECT sid, close FROM stock_daily) "
            "SELECT * FROM pit_data"
        )
        assert result == expected

    def test_wrap_pit_cte_with_asof_date(self) -> None:
        """Test wrap_pit_cte adds WHERE clause when asof_date provided."""
        query = "SELECT sid, close FROM stock_daily"
        result = PitHelper.wrap_pit_cte(query, "pit_data", asof_date="2024-01-15")

        expected = (
            "WITH pit_data AS (SELECT sid, close FROM stock_daily) "
            "SELECT * FROM pit_data WHERE trade_date <= '2024-01-15'"
        )
        assert result == expected

    def test_wrap_pit_cte_custom_name(self) -> None:
        """Test wrap_pit_cte with custom CTE name."""
        query = "SELECT sid, close FROM stock_daily"
        result = PitHelper.wrap_pit_cte(query, "my_cte")

        expected = (
            "WITH my_cte AS (SELECT sid, close FROM stock_daily) SELECT * FROM my_cte"
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
        query = "SELECT * FROM stock_daily where sid = 1"
        result = PitHelper.add_pit_filter(query, "2024-01-15")

        assert (
            result
            == "SELECT * FROM stock_daily where sid = 1 AND knowledge_date <= '2024-01-15'"
        )

    def test_wrap_pit_cte_no_asof_date(self) -> None:
        """Test wrap_pit_cte without asof_date doesn't add WHERE."""
        query = "SELECT sid, close FROM stock_daily WHERE sid = 1"
        result = PitHelper.wrap_pit_cte(query, "pit_data", asof_date=None)

        # 不应该添加额外的 WHERE
        expected = "WITH pit_data AS (SELECT sid, close FROM stock_daily WHERE sid = 1) SELECT * FROM pit_data"
        assert result == expected

    def test_combined_pit_query_workflow(self) -> None:
        """Test combined workflow of using multiple PitHelper methods."""
        # 原始查询
        query = "SELECT sid, close FROM stock_daily WHERE sid = 1"

        # 先包装成 CTE
        cte_query = PitHelper.wrap_pit_cte(query, "filtered_data")
        # 添加 PIT 过滤
        pit_query = PitHelper.add_pit_filter(cte_query, "2024-01-15")

        # 结果应该同时包含 CTE 和 PIT 过滤
        assert "WITH filtered_data AS" in pit_query
        assert "knowledge_date <= '2024-01-15'" in pit_query
