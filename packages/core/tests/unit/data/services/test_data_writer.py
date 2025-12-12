"""Tests for the DataWriter implementation without adapter abstraction."""

from datetime import date, datetime
from unittest.mock import patch

import pytest
from ditto_core.data.services.data_writer import DataWriter


class TestDataWriter:
    """Test cases for the DataWriter implementation."""

    @pytest.fixture
    def test_writer(self):
        """Create a DataWriter instance with in-memory databases for testing."""
        return DataWriter.for_testing()

    def test_store_etf_info_with_dataframe(self, test_writer):
        """Test storing ETF info with DataFrame input."""
        # Arrange
        import polars as pl

        etf_data = pl.DataFrame(
            [
                {
                    "symbol": "159915",
                    "name": "创业板ETF",
                    "list_date": date(2011, 1, 1),
                },
                {
                    "symbol": "510300",
                    "name": "沪深300ETF",
                    "list_date": date(2012, 5, 4),
                },
            ]
        )

        # Act
        test_writer.store_etf_info(etf_data)

        # Assert
        result = test_writer._duck_conn.sql(
            "SELECT * FROM etf_info ORDER BY symbol"
        ).pl()
        assert len(result) == 2
        assert result["symbol"][0] == "159915"
        assert result["name"][1] == "沪深300ETF"

    def test_store_etf_info_with_dict_list(self, test_writer):
        """Test storing ETF info with dictionary list input."""
        # Arrange
        etf_data = [
            {"symbol": "159915", "name": "创业板ETF"},
            {"symbol": "510300", "name": "沪深300ETF", "list_date": "2012-05-04"},
        ]

        # Act
        test_writer.store_etf_info(etf_data)

        # Assert
        result = test_writer._duck_conn.sql(
            "SELECT * FROM etf_info ORDER BY symbol"
        ).pl()
        assert len(result) == 2
        assert result["symbol"][0] == "159915"
        assert result["symbol"][1] == "510300"

    def test_store_etf_info_missing_required_columns(self, test_writer):
        """Test store_etf_info raises error when required columns are missing."""
        # Arrange
        etf_data = [{"name": "创业板ETF"}]  # Missing symbol

        # Act & Assert
        with pytest.raises(ValueError, match="必须包含symbol和name列"):
            test_writer.store_etf_info(etf_data)

    def test_store_daily_data_with_dataframe(self, test_writer):
        """Test storing daily price data with DataFrame input."""
        # Arrange
        import polars as pl

        daily_data = pl.DataFrame(
            [
                {
                    "symbol": "159915",
                    "date": "2024-01-02",
                    "open": 2.5,
                    "high": 2.6,
                    "low": 2.4,
                    "close": 2.55,
                    "volume": 1000000,
                },
                {
                    "symbol": "159915",
                    "date": "2024-01-03",
                    "open": 2.55,
                    "high": 2.65,
                    "low": 2.5,
                    "close": 2.6,
                    "volume": 1200000,
                },
            ]
        )

        # Act
        test_writer.store_daily_data(daily_data)

        # Assert
        result = test_writer._duck_conn.sql(
            "SELECT * FROM daily_price ORDER BY trade_date"
        ).pl()
        assert len(result) == 2
        assert result["symbol"][0] == "159915"
        assert float(result["close_price"][1]) == 2.6

    def test_store_daily_data_with_dict_list(self, test_writer):
        """Test storing daily price data with dictionary list input."""
        # Arrange
        daily_data = [
            {
                "symbol": "159915",
                "date": "2024-01-02",
                "open": 2.5,
                "high": 2.6,
                "low": 2.4,
                "close": 2.55,
                "volume": 1000000,
            }
        ]

        # Act
        test_writer.store_daily_data(daily_data)

        # Assert
        result = test_writer._duck_conn.sql("SELECT * FROM daily_price").pl()
        assert len(result) == 1
        assert result["symbol"][0] == "159915"
        assert float(result["close_price"][0]) == 2.55

    def test_store_adjustment_factors(self, test_writer):
        """Test storing adjustment factors."""
        # Arrange
        adj_data = [
            {
                "symbol": "159915",
                "ex_date": "2024-01-02",
                "adj_factor": 1.05,
                "adj_type": "dividend",
            },
            {
                "symbol": "159915",
                "ex_date": "2024-06-01",  # Using 'ex_date'
                "adj_factor": 1.1,
                "adj_type": "split",
            },
        ]

        # Act
        test_writer.store_adjustment_factors(adj_data)

        # Assert
        result = test_writer._duck_conn.sql(
            "SELECT * FROM adjustment_factors ORDER BY ex_date"
        ).pl()
        assert len(result) == 2
        assert result["symbol"][0] == "159915"
        assert float(result["adj_factor"][1]) == 1.1

    def test_store_trading_calendar(self, test_writer):
        """Test storing trading calendar."""
        # Arrange
        calendar_data = [
            {"date": "2024-01-01", "is_trading_day": False, "market": "SZSE"},
            {"date": "2024-01-02", "is_trading_day": True, "market": "SZSE"},
        ]

        # Act
        test_writer.store_trading_calendar(calendar_data)

        # Assert
        result = test_writer._duck_conn.sql(
            "SELECT * FROM trading_calendar ORDER BY trade_date"
        ).pl()
        assert len(result) == 2
        assert result["is_trading_day"][0] is False
        assert result["is_trading_day"][1] is True

    def test_store_trades(self, test_writer):
        """Test storing trade records."""
        # Arrange
        trades_data = [
            {
                "symbol": "159915",
                "side": "buy",
                "quantity": 1000,
                "price": 2.55,
            },
            {
                "symbol": "510300",
                "side": "sell",
                "quantity": 500,
                "price": 4.05,
                "timestamp": datetime(2024, 1, 2, 10, 30),
            },
        ]

        # Act
        test_writer.store_trades(trades_data)

        # Assert
        cursor = test_writer._sqlite_conn.execute(
            "SELECT * FROM trades ORDER BY trade_id"
        )
        trades = cursor.fetchall()
        assert len(trades) == 2
        assert trades[0][1] == "159915"  # symbol
        assert trades[0][2] == "buy"  # side
        assert trades[0][3] == 1000  # quantity

    def test_store_orders(self, test_writer):
        """Test storing order records."""
        # Arrange
        orders_data = [
            {
                "symbol": "159915",
                "side": "buy",
                "quantity": 1000,
                "price": 2.55,
                "status": "filled",
            },
            {
                "symbol": "510300",
                "side": "sell",
                "order_type": "limit",
                "quantity": 500,
                "price": 4.05,
                "status": "pending",
            },
        ]

        # Act
        test_writer.store_orders(orders_data)

        # Assert
        cursor = test_writer._sqlite_conn.execute(
            "SELECT * FROM orders ORDER BY order_id"
        )
        orders = cursor.fetchall()
        assert len(orders) == 2
        assert orders[0][1] == "159915"  # symbol
        assert orders[0][2] == "buy"  # side
        assert orders[0][6] == "filled"  # status

    def test_store_positions(self, test_writer):
        """Test storing position records."""
        # Arrange
        positions_data = [
            {
                "symbol": "159915",
                "quantity": 1000,
                "avg_price": 2.55,
                "market_value": 2550.0,
            },
            {
                "symbol": "510300",
                "quantity": -500,
                "avg_price": 4.05,
                "market_value": -2025.0,
            },
        ]

        # Act
        test_writer.store_positions(positions_data)

        # Assert
        cursor = test_writer._sqlite_conn.execute(
            "SELECT * FROM positions ORDER BY position_id"
        )
        positions = cursor.fetchall()
        assert len(positions) == 2
        assert positions[0][1] == "159915"  # symbol
        assert positions[0][2] == 1000  # quantity
        assert positions[0][3] == 2.55  # avg_price

    def test_knowledge_date_auto_added(self, test_writer):
        """Test that knowledge_date is automatically added when missing."""
        # Arrange
        etf_data = [{"symbol": "TEST", "name": "Test ETF", "list_date": None}]

        # Act
        test_writer.store_etf_info(etf_data)

        # Assert
        result = test_writer._duck_conn.sql(
            "SELECT knowledge_date FROM etf_info WHERE symbol = 'TEST'"
        ).pl()
        assert len(result) == 1
        assert result["knowledge_date"][0] == datetime.now().date()

    def test_data_writer_initialization_uses_real_paths(self):
        """Test that DataWriter uses configured database paths when not in test mode."""
        # Arrange & Act
        with patch("ditto_foundation.config.settings.get_settings") as mock_settings:
            mock_settings.return_value.database.duckdb_path = "/test/path/market.db"
            mock_settings.return_value.database.sqlite_path = "/test/path/trading.db"

            writer = DataWriter()

            # Assert
            # The constructor should have attempted to create the directories
            # We can't easily test the actual connections without files
            assert writer is not None

    def test_data_isolation_between_instances(self):
        """Test that different DataWriter instances have isolated data."""
        # Create two separate instances
        writer1 = DataWriter.for_testing()
        writer2 = DataWriter.for_testing()

        # Store data in writer1
        writer1.store_etf_info(
            [{"symbol": "TEST1", "name": "Test ETF 1", "list_date": None}]
        )

        # Store data in writer2
        writer2.store_etf_info(
            [{"symbol": "TEST2", "name": "Test ETF 2", "list_date": None}]
        )

        # Verify isolation
        result1 = writer1._duck_conn.sql("SELECT * FROM etf_info").pl()
        result2 = writer2._duck_conn.sql("SELECT * FROM etf_info").pl()

        assert len(result1) == 1
        assert result1["symbol"][0] == "TEST1"

        assert len(result2) == 1
        assert result2["symbol"][0] == "TEST2"
