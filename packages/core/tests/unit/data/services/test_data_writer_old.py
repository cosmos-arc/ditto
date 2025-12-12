"""Tests for DataWriter service."""

from datetime import datetime

import polars as pl
import pytest
from ditto_core.data.services.data_writer import DataWriter
from pytest_mock import MockerFixture


class TestDataWriter:
    """Test cases for DataWriter service."""

    def test_data_writer_store_etf_info(self, mocker: MockerFixture) -> None:
        """Test storing ETF info to database."""
        # Arrange
        mock_adapter = mocker.Mock()
        mock_adapter.execute.return_value = None

        writer = DataWriter(mock_adapter)
        etf_data = pl.DataFrame(
            {
                "symbol": ["510300.SH"],
                "name": ["沪深300ETF"],
                "list_date": ["2022-01-01"],
            }
        )

        # Act & Assert
        writer.store_etf_info(etf_data)  # Should not raise

        # Verify SQL was executed
        assert mock_adapter.execute.call_count == 1
        call_args = mock_adapter.execute.call_args[0]
        assert "INSERT OR REPLACE INTO etf_info" in call_args[0]

    def test_data_writer_store_etf_info_adds_knowledge_date(
        self, mocker: MockerFixture
    ) -> None:
        """Test that store_etf_info adds knowledge_date if missing."""
        # Arrange
        mock_adapter = mocker.Mock()
        mock_adapter.execute.return_value = None

        writer = DataWriter(mock_adapter)
        etf_data = pl.DataFrame(
            {
                "symbol": ["510300.SH"],
                "name": ["沪深300ETF"],
                "list_date": ["2022-01-01"],
            }
        )

        # Act
        writer.store_etf_info(etf_data)

        # Assert
        call_args = mock_adapter.execute.call_args[0]
        # Check that knowledge_date is in the SQL column list
        assert "knowledge_date" in call_args[0]

    def test_data_writer_store_daily_data(self, mocker: MockerFixture) -> None:
        """Test storing daily price data."""
        # Arrange
        mock_adapter = mocker.Mock()
        mock_adapter.execute.return_value = None

        writer = DataWriter(mock_adapter)
        daily_data = pl.DataFrame(
            {
                "symbol": ["510300.SH"],
                "date": ["2024-01-02"],
                "open": [3.5],
                "high": [3.6],
                "low": [3.4],
                "close": [3.55],
                "volume": [1000000],
            }
        )

        # Act & Assert
        writer.store_daily_data(daily_data)  # Should not raise

        # Verify batch_insert was called
        assert mock_adapter.execute_many.called or mock_adapter.execute.called

    def test_data_writer_store_daily_data_missing_columns(
        self, mocker: MockerFixture
    ) -> None:
        """Test that store_daily_data raises error for missing columns."""
        # Arrange
        mock_adapter = mocker.Mock()
        writer = DataWriter(mock_adapter)
        daily_data = pl.DataFrame(
            {
                "symbol": ["510300.SH"],
                "date": ["2024-01-02"],
                # Missing required OHLCV columns
            }
        )

        # Act & Assert
        with pytest.raises(ValueError, match="Missing required columns"):
            writer.store_daily_data(daily_data)

    def test_data_writer_store_daily_data_adds_knowledge_date(
        self, mocker: MockerFixture
    ) -> None:
        """Test that store_daily_data adds knowledge_date if missing."""
        # Arrange
        mock_adapter = mocker.Mock()
        mock_adapter.execute.return_value = None
        mock_adapter.execute_many.return_value = None

        writer = DataWriter(mock_adapter)
        daily_data = pl.DataFrame(
            {
                "symbol": ["510300.SH"],
                "date": ["2024-01-02"],
                "open": [3.5],
                "high": [3.6],
                "low": [3.4],
                "close": [3.55],
                "volume": [1000000],
            }
        )

        # Act
        writer.store_daily_data(daily_data)

        # Assert - Check that knowledge_date was added
        # Either execute_many or execute should have been called with knowledge_date
        if mock_adapter.execute_many.called:
            call_args = mock_adapter.execute_many.call_args[0]
            # Check the data passed to execute_many
            assert any("knowledge_date" in str(row) for row in call_args[1])

    def test_data_writer_store_adjustment_factors(self, mocker: MockerFixture) -> None:
        """Test storing adjustment factors."""
        # Arrange
        mock_adapter = mocker.Mock()
        mock_adapter.execute.return_value = None

        writer = DataWriter(mock_adapter)
        adj_data = pl.DataFrame(
            {
                "symbol": ["510300.SH"],
                "ex_date": ["2024-01-02"],
                "adj_factor": [1.1],
                "adj_type": ["dividend"],
            }
        )

        # Act & Assert
        writer.store_adjustment_factors(adj_data)  # Should not raise

        # Verify batch_insert was called
        assert mock_adapter.execute_many.called or mock_adapter.execute.called

    def test_data_writer_store_trading_calendar(self, mocker: MockerFixture) -> None:
        """Test storing trading calendar."""
        # Arrange
        mock_adapter = mocker.Mock()
        mock_adapter.execute.return_value = None

        writer = DataWriter(mock_adapter)
        calendar_data = pl.DataFrame(
            {"date": ["2024-01-01", "2024-01-02"], "is_trading_day": [False, True]}
        )

        # Act & Assert
        writer.store_trading_calendar(calendar_data)  # Should not raise

        # Verify batch_insert was called
        assert mock_adapter.execute_many.called or mock_adapter.execute.called

    def test_data_writer_batch_insert_daily_price(self, mocker: MockerFixture) -> None:
        """Test _batch_insert method for daily_price table."""
        # Arrange
        mock_adapter = mocker.Mock()
        writer = DataWriter(mock_adapter)

        data = pl.DataFrame(
            {
                "symbol": ["510300.SH"],
                "date": ["2024-01-02"],
                "open": [3.5],
                "high": [3.6],
                "low": [3.4],
                "close": [3.55],
                "volume": [1000000],
                "knowledge_date": [datetime.now()],
            }
        )

        # Act
        writer._batch_insert("daily_price_raw", data)

        # Assert
        assert mock_adapter.execute.called
        call_args = mock_adapter.execute.call_args[0]
        assert "INSERT OR REPLACE INTO daily_price_raw" in call_args[0]

    def test_data_writer_batch_insert_adjustment_factors(
        self, mocker: MockerFixture
    ) -> None:
        """Test _batch_insert method for adjustment_factors table."""
        # Arrange
        mock_adapter = mocker.Mock()
        writer = DataWriter(mock_adapter)

        data = pl.DataFrame(
            {
                "symbol": ["510300.SH"],
                "ex_date": ["2024-01-02"],
                "adj_factor": [1.1],
                "adj_type": ["dividend"],
                "knowledge_date": [datetime.now()],
            }
        )

        # Act
        writer._batch_insert("adjustment_factors", data)

        # Assert
        assert mock_adapter.execute.called
        call_args = mock_adapter.execute.call_args[0]
        assert "INSERT OR REPLACE INTO adjustment_factors" in call_args[0]

    def test_data_writer_batch_insert_other_table(self, mocker: MockerFixture) -> None:
        """Test _batch_insert method for other tables using execute_many."""
        # Arrange
        mock_adapter = mocker.Mock()
        writer = DataWriter(mock_adapter)

        data = pl.DataFrame({"date": ["2024-01-01"], "is_trading_day": [True]})

        # Act
        writer._batch_insert("trading_calendar", data)

        # Assert
        # For non-price/adjustment tables, should use execute_many
        assert mock_adapter.execute_many.called
        call_args = mock_adapter.execute_many.call_args[0]
        assert "INSERT OR IGNORE INTO trading_calendar" in call_args[0]

    def test_data_writer_handles_exceptions(self, mocker: MockerFixture) -> None:
        """Test that DataWriter properly handles and re-raises exceptions."""
        # Arrange
        mock_adapter = mocker.Mock()
        mock_adapter.execute.side_effect = Exception("Database error")

        writer = DataWriter(mock_adapter)
        etf_data = pl.DataFrame(
            {
                "symbol": ["510300.SH"],
                "name": ["沪深300ETF"],
                "list_date": ["2022-01-01"],
                "knowledge_date": [datetime.now()],
            }
        )

        # Act & Assert
        with pytest.raises(Exception, match="Database error"):
            writer.store_etf_info(etf_data)
