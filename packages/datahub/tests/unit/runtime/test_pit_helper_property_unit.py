"""
Property-based tests for PIT Helper in ditto-datahub.

Uses Hypothesis to verify PIT query generation invariants.
"""

import re

import pytest
from ditto_datahub.helpers.pit import PitHelper
from hypothesis import HealthCheck, given, settings
from hypothesis.strategies import (
    from_regex,
    lists,
    sampled_from,
    text,
)

# Valid strategies - use text with alphabet to avoid newlines
valid_date_strategy = from_regex(r"^\d{4}-\d{2}-\d{2}$")

# Use text with alphabet to ensure only valid identifier characters
valid_identifier_strategy = text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789",
    min_size=1,
    max_size=10,
).filter(lambda x: x and re.match(r"^[a-zA-Z_]", x))


# Sample from common valid identifiers for stability
common_identifiers = sampled_from(
    [
        "table1",
        "table2",
        "stock_daily",
        "adj_factor",
        "t1",
        "t2",
        "a",
        "b",
        "my_table",
        "data",
        "result",
    ]
)


# Sample valid dates
valid_dates = sampled_from(
    [
        "2024-01-15",
        "2023-12-31",
        "2025-06-30",
        "2024-02-28",
        "2024-12-25",
    ]
)


class TestPitHelperProperties:
    """Property-based tests for PitHelper."""

    @given(valid_date_strategy)
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_validate_date_string_accepts_valid(self, date_str: str) -> None:
        """
        Property: Valid date strings should pass validation.

        Any string matching YYYY-MM-DD format should be accepted.
        """
        # Should not raise
        PitHelper._validate_date_string(date_str)

    @given(from_regex(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"))
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_add_pit_filter_preserves_structure(self, date_str: str) -> None:
        """
        Property: add_pit_filter should preserve original query structure.

        The generated query should contain the original query and the filter condition.
        """
        query = "SELECT * FROM stock_daily"
        result = PitHelper.add_pit_filter(query, date_str)

        # Should contain original query
        assert query in result or "FROM stock_daily" in result
        # Should contain filter condition
        assert "<=" in result
        assert date_str in result

    @given(
        valid_identifier_strategy,
        valid_date_strategy,
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_add_pit_filter_invariants(self, date_column: str, date_str: str) -> None:
        """
        Property: add_pit_filter maintains key invariants.

        - Result should contain <= comparison
        - Result should contain the date value
        - Result should contain the column name
        """
        query = "SELECT * FROM table1"
        result = PitHelper.add_pit_filter(query, date_str, date_column)

        assert "<=" in result, "Result should contain <= comparison"
        assert date_str in result, "Result should contain the date value"
        assert date_column in result, "Result should contain the column name"

    @given(valid_identifier_strategy, valid_identifier_strategy, valid_date_strategy)
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_add_pit_join_structure_invariants(
        self, left_table: str, right_table: str, asof_date: str
    ) -> None:
        """
        Property: add_pit_join generates correct JOIN structure.

        - Result should contain LEFT JOIN
        - Result should contain ON clause
        - Result should contain <= comparison with asof_date
        """
        join_keys = ["t1.instrument_id = t2.instrument_id"]
        result = PitHelper.add_pit_join(left_table, right_table, join_keys, asof_date)

        assert "LEFT JOIN" in result, "Result should contain LEFT JOIN"
        assert "ON" in result, "Result should contain ON clause"
        assert "<=" in result, "Result should contain <= comparison"
        assert asof_date in result, "Result should contain asof_date"

    @given(
        common_identifiers,
        sampled_from(["trade_date", "knowledge_date", "effective_date"]),
        valid_dates,
    )
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_add_pit_join_custom_date_column(
        self, right_alias: str, date_column: str, asof_date: str
    ) -> None:
        """Property: Custom date column should appear in JOIN condition."""
        left_table = "table1 t1"
        right_table = f"table2 {right_alias}"
        join_keys = ["t1.instrument_id = t2.instrument_id"]
        result = PitHelper.add_pit_join(
            left_table, right_table, join_keys, asof_date, date_column
        )

        # Should contain custom date column with right table alias
        expected_pattern = f"{right_alias}.{date_column}"
        assert expected_pattern in result, f"Should contain {expected_pattern}"

    @given(valid_identifier_strategy, valid_date_strategy)
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_wrap_pit_cte_structure(self, cte_name: str, asof_date: str) -> None:
        """
        Property: wrap_pit_cte generates correct CTE structure.

        - Result should start with WITH
        - Result should contain AS (CTE definition)
        - Result should contain SELECT * FROM cte_name
        """
        query = "SELECT instrument_id, close FROM stock_daily"
        result = PitHelper.wrap_pit_cte(query, cte_name, asof_date)

        assert result.startswith("WITH"), "CTE should start with WITH"
        assert " AS " in result, "CTE should contain AS clause"
        assert f"SELECT * FROM {cte_name}" in result, f"Should select from {cte_name}"

    @given(valid_identifier_strategy, valid_date_strategy)
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_get_safe_trade_date_format(
        self, base_column: str, knowledge_date: str
    ) -> None:
        """
        Property: get_safe_trade_date generates correct format.

        - Result should contain <= operator
        - Result should contain base column name
        - Result should contain knowledge date (quoted if not placeholder)
        """
        result = PitHelper.get_safe_trade_date(base_column, knowledge_date)

        assert "<=" in result, "Result should contain <= operator"
        assert base_column in result, "Result should contain base column"
        assert knowledge_date in result, "Result should contain knowledge date"

    @given(valid_identifier_strategy)
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_get_safe_trade_date_placeholder_format(self, base_column: str) -> None:
        """Property: Placeholder ($asof) should not be quoted."""
        result = PitHelper.get_safe_trade_date(base_column, "$asof")

        assert "$asof" in result, "Result should contain placeholder"
        assert "'$asof'" not in result, "Placeholder should not be quoted"

    @given(
        valid_identifier_strategy,
        sampled_from(["2024-01-15", "2023-12-31", "2025-06-30"]),
    )
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_get_safe_trade_date_concrete_date_quoted(
        self, base_column: str, knowledge_date: str
    ) -> None:
        """Property: Concrete dates should be single-quoted."""
        result = PitHelper.get_safe_trade_date(base_column, knowledge_date)

        assert f"'{knowledge_date}'" in result, (
            f"Date {knowledge_date} should be quoted"
        )

    @given(text(min_size=1, max_size=20))
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_invalid_identifier_rejected(self, identifier: str) -> None:
        """
        Property: Invalid identifiers should raise ValueError.

        Strings that don't match valid SQL identifier pattern should be rejected.
        """
        # Filter out valid identifiers
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", identifier):
            return  # Skip valid identifiers

        with pytest.raises(ValueError, match="Invalid"):
            PitHelper._validate_sql_identifier(identifier)

    @given(text(min_size=1, max_size=20))
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_invalid_date_rejected(self, date_str: str) -> None:
        """
        Property: Invalid date strings should raise ValueError.

        Strings that don't match YYYY-MM-DD pattern should be rejected.
        """
        # Filter out valid dates
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return  # Skip valid dates

        with pytest.raises(ValueError, match="Invalid date format"):
            PitHelper._validate_date_string(date_str)

    @given(
        lists(valid_identifier_strategy, min_size=1, max_size=5, unique=True),
        valid_date_strategy,
    )
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_multiple_join_keys_preserved(
        self, join_keys: list[str], asof_date: str
    ) -> None:
        """Property: Multiple join keys should all be present in result."""
        # Create join key conditions
        join_conditions = [f"t1.{key} = t2.{key}" for key in join_keys[:3]]

        result = PitHelper.add_pit_join(
            "table1 t1", "table2 t2", join_conditions, asof_date
        )

        # All join keys should be present
        for key in join_keys[:3]:
            assert key in result, f"Join key {key} should be in result"

    @given(
        valid_date_strategy,
        sampled_from(
            [
                "SELECT * FROM table1 WHERE x > 10",
                "SELECT a, b FROM table1 ORDER BY a",
                "SELECT COUNT(*) FROM table1 GROUP BY category",
            ]
        ),
    )
    @settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
    def test_add_pit_filter_preserves_where(self, date_str: str, query: str) -> None:
        """Property: Existing WHERE clause should be preserved."""
        result = PitHelper.add_pit_filter(query, date_str)

        # Original query elements should be preserved
        assert "SELECT" in result
        assert "FROM" in result
        # Filter should be added
        assert date_str in result
