"""Unit tests for SQLiteClient identifier validation."""

import tempfile
from pathlib import Path

import pytest
from ditto_platform.foundation.db import SQLitePool
from ditto_platform.foundation.storage.sqlite_client import (
    SQLiteClient,
    validate_identifier,
)


@pytest.fixture
def client() -> SQLiteClient:
    """Create a SQLiteClient with a temporary database."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.db"
        pool = SQLitePool(str(db_path))
        pool.execute("CREATE TABLE valid_table (id INTEGER PRIMARY KEY, name TEXT)")
        pool.execute("INSERT INTO valid_table VALUES (1, 'Alice')")
        pool.commit()
        yield SQLiteClient(pool)
        pool.close()


# --- validate_identifier ---


class TestValidateIdentifier:
    """Tests for the validate_identifier function."""

    def test_accepts_simple_table_name(self) -> None:
        validate_identifier("my_table")

    def test_accepts_underscore_prefix(self) -> None:
        validate_identifier("_private")

    def test_accepts_letters_digits_underscores(self) -> None:
        validate_identifier("table_123")

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            validate_identifier("")

    def test_rejects_leading_digit(self) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            validate_identifier("1table")

    def test_rejects_semicolon(self) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            validate_identifier("tbl; DROP TABLE")

    def test_rejects_quotes(self) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            validate_identifier("tbl'; DROP TABLE--")

    def test_rejects_spaces(self) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            validate_identifier("my table")

    def test_rejects_hyphens(self) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            validate_identifier("my-table")

    def test_rejects_sql_comment(self) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            validate_identifier("tbl--")

    def test_rejects_block_comment(self) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            validate_identifier("tbl/*")


# --- SQLiteClient.count with validation ---


class TestCountIdentifierValidation:
    """Tests proving SQLiteClient.count rejects malicious identifiers."""

    def test_count_with_valid_table(self, client: SQLiteClient) -> None:
        assert client.count("valid_table") == 1

    def test_count_with_where_and_params(self, client: SQLiteClient) -> None:
        result = client.count("valid_table", "id = ?", [1])
        assert result == 1

    def test_count_rejects_semicolon_in_table(self, client: SQLiteClient) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            client.count("valid_table; DROP TABLE valid_table--")

    def test_count_rejects_quote_in_table(self, client: SQLiteClient) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            client.count("'; DROP TABLE valid_table--")

    def test_count_rejects_union_in_table(self, client: SQLiteClient) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            client.count("valid_table UNION SELECT * FROM secrets")

    def test_count_rejects_comment_in_table(self, client: SQLiteClient) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            client.count("valid_table--")

    def test_count_empty_table_name(self, client: SQLiteClient) -> None:
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            client.count("")

    def test_count_rejects_where_without_params(self, client: SQLiteClient) -> None:
        with pytest.raises(ValueError, match="'params' required"):
            client.count("valid_table", "id = 1")

    def test_count_accepts_where_with_params(self, client: SQLiteClient) -> None:
        assert client.count("valid_table", "id = ?", [1]) == 1

    def test_count_accepts_and_joined_parameterized_filters(
        self, client: SQLiteClient
    ) -> None:
        assert client.count("valid_table", "id >= ? AND id <= ?", [1, 2]) == 1

    def test_count_rejects_where_literal_even_with_params(
        self, client: SQLiteClient
    ) -> None:
        with pytest.raises(ValueError, match="Invalid SQL WHERE clause"):
            client.count("valid_table", "id = 1", [])

    def test_count_rejects_where_or_tautology_with_params(
        self, client: SQLiteClient
    ) -> None:
        with pytest.raises(ValueError, match="Invalid SQL WHERE clause"):
            client.count("valid_table", "id = ? OR 1 = 1", [1])

    def test_count_rejects_statement_separator_in_where(
        self, client: SQLiteClient
    ) -> None:
        with pytest.raises(ValueError, match="Invalid SQL WHERE clause"):
            client.count("valid_table", "id = ?; DROP TABLE valid_table", [1])

    def test_count_rejects_where_placeholder_count_mismatch(
        self, client: SQLiteClient
    ) -> None:
        with pytest.raises(ValueError, match="placeholder"):
            client.count("valid_table", "id = ? AND name = ?", [1])
