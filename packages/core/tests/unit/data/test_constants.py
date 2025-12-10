"""Unit tests for data constants."""

from ditto_core.data.constants import DatabaseType, DataSourceType


class TestDataSourceType:
    """Test cases for DataSourceType constants."""

    def test_tushare_constant_value_is_correct(self) -> None:
        """Test that TUSHARE constant has the correct value."""
        # Arrange
        expected_value = "tushare"

        # Act
        actual_value = DataSourceType.TUSHARE

        # Assert
        assert actual_value == expected_value

    def test_akshare_constant_value_is_correct(self) -> None:
        """Test that AKSHARE constant has the correct value."""
        # Arrange
        expected_value = "akshare"

        # Act
        actual_value = DataSourceType.AKSHARE

        # Assert
        assert actual_value == expected_value

    def test_datasource_type_has_all_expected_members(self) -> None:
        """Test that DataSourceType has all expected members."""
        # Arrange & Act
        members = {
            "TUSHARE": DataSourceType.TUSHARE,
            "AKSHARE": DataSourceType.AKSHARE,
        }

        # Assert
        assert len(members) == 2
        assert "TUSHARE" in members
        assert "AKSHARE" in members
        assert all(members.values())  # Ensure no None or empty values


class TestDatabaseType:
    """Test cases for DatabaseType constants."""

    def test_analytical_constant_value_is_correct(self) -> None:
        """Test that ANALYTICAL constant has the correct value."""
        # Arrange
        expected_value = "duckdb"

        # Act
        actual_value = DatabaseType.ANALYTICAL

        # Assert
        assert actual_value == expected_value

    def test_transactional_constant_value_is_correct(self) -> None:
        """Test that TRANSACTIONAL constant has the correct value."""
        # Arrange
        expected_value = "sqlite"

        # Act
        actual_value = DatabaseType.TRANSACTIONAL

        # Assert
        assert actual_value == expected_value

    def test_database_type_has_all_expected_members(self) -> None:
        """Test that DatabaseType has all expected members."""
        # Arrange & Act
        members = {
            "ANALYTICAL": DatabaseType.ANALYTICAL,
            "TRANSACTIONAL": DatabaseType.TRANSACTIONAL,
        }

        # Assert
        assert len(members) == 2
        assert "ANALYTICAL" in members
        assert "TRANSACTIONAL" in members
        assert all(members.values())  # Ensure no None or empty values
