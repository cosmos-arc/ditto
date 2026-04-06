"""Tests for QualityRecordService."""

import polars as pl
from ditto_data.ingestion.quality_record_service import QualityRecordService
from pytest_mock import MockerFixture


class TestQualityRecordService:
    """Tests for QualityRecordService."""

    def test_list_quarantined_data_returns_dataframe(
        self, mocker: MockerFixture
    ) -> None:
        """Test list_quarantined_data() returns DataFrame from reader."""
        # Arrange
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame(
            {"id": [1, 2], "dataset": ["stock_daily", "stock_daily"]}
        )
        mock_reader.get_quarantined_data = mocker.Mock(return_value=expected_df)

        mock_writer = mocker.Mock()
        service = QualityRecordService(
            comparison_reader=mocker.Mock(),
            comparison_writer=mocker.Mock(),
            quarantine_reader=mock_reader,
            quarantine_writer=mock_writer,
        )

        # Act
        result = service.list_quarantined_data(
            dataset="stock_daily", rule_id="dq_001", limit=100
        )

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 2
        mock_reader.get_quarantined_data.assert_called_once_with(
            "stock_daily", "dq_001", 100
        )

    def test_list_quarantined_data_with_default_params(
        self, mocker: MockerFixture
    ) -> None:
        """Test list_quarantined_data() uses default parameters."""
        # Arrange
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame()
        mock_reader.get_quarantined_data = mocker.Mock(return_value=expected_df)

        service = QualityRecordService(
            comparison_reader=mocker.Mock(),
            comparison_writer=mocker.Mock(),
            quarantine_reader=mock_reader,
            quarantine_writer=mocker.Mock(),
        )

        # Act
        service.list_quarantined_data()

        # Assert
        mock_reader.get_quarantined_data.assert_called_once_with(None, None, 1000)

    def test_get_failed_data_returns_dataframe(self, mocker: MockerFixture) -> None:
        """Test get_failed_data() returns DataFrame from reader."""
        # Arrange
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame({"code": ["000001"], "close": [10.5]})
        mock_reader.get_failed_data_df = mocker.Mock(return_value=expected_df)

        service = QualityRecordService(
            comparison_reader=mocker.Mock(),
            comparison_writer=mocker.Mock(),
            quarantine_reader=mock_reader,
            quarantine_writer=mocker.Mock(),
        )

        # Act
        result = service.get_failed_data(row_id=123)

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 1
        mock_reader.get_failed_data_df.assert_called_once_with(123)

    def test_get_failed_data_returns_empty_on_not_found(
        self, mocker: MockerFixture
    ) -> None:
        """Test get_failed_data() returns empty DataFrame when not found."""
        # Arrange
        mock_reader = mocker.Mock()
        empty_df = pl.DataFrame()
        mock_reader.get_failed_data_df = mocker.Mock(return_value=empty_df)

        service = QualityRecordService(
            comparison_reader=mocker.Mock(),
            comparison_writer=mocker.Mock(),
            quarantine_reader=mock_reader,
            quarantine_writer=mocker.Mock(),
        )

        # Act
        result = service.get_failed_data(row_id=999)

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0
        mock_reader.get_failed_data_df.assert_called_once_with(999)

    def test_save_comparison_delegates_to_writer(self, mocker: MockerFixture) -> None:
        """Test save_comparison() delegates to ComparisonWriter."""
        # Arrange
        mock_writer = mocker.Mock()
        test_df = pl.DataFrame({"col1": [1, 2]})

        service = QualityRecordService(
            comparison_reader=mocker.Mock(),
            comparison_writer=mock_writer,
            quarantine_reader=mocker.Mock(),
            quarantine_writer=mocker.Mock(),
        )

        # Act
        service.save_comparison(
            trade_date="20240101", df=test_df, dataset="stock_daily"
        )

        # Assert
        mock_writer.write_comparison.assert_called_once_with(
            "20240101", test_df, "stock_daily"
        )

    def test_get_comparison_delegates_to_reader(self, mocker: MockerFixture) -> None:
        """Test get_comparison() delegates to ComparisonReader."""
        # Arrange
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame({"status": ["pass"]})
        mock_reader.read_comparison = mocker.Mock(return_value=expected_df)

        service = QualityRecordService(
            comparison_reader=mock_reader,
            comparison_writer=mocker.Mock(),
            quarantine_reader=mocker.Mock(),
            quarantine_writer=mocker.Mock(),
        )

        # Act
        result = service.get_comparison(trade_date="20240101", dataset="stock_daily")

        # Assert
        assert result is not None
        mock_reader.read_comparison.assert_called_once_with("20240101", "stock_daily")

    def test_save_failed_data_delegates_to_writer(self, mocker: MockerFixture) -> None:
        """Test save_failed_data() delegates to QuarantineWriter."""
        # Arrange
        mock_writer = mocker.Mock()
        mock_writer.save_failed_data = mocker.Mock(return_value=123)
        failed_df = pl.DataFrame({"code": ["000001"]})

        service = QualityRecordService(
            comparison_reader=mocker.Mock(),
            comparison_writer=mocker.Mock(),
            quarantine_reader=mocker.Mock(),
            quarantine_writer=mock_writer,
        )

        # Act
        row_id = service.save_failed_data(
            dataset="stock_daily",
            rule_id="dq_001",
            severity="error",
            failed_data=failed_df,
            trade_date="20240101",
        )

        # Assert
        assert row_id == 123
        mock_writer.save_failed_data.assert_called_once_with(
            "stock_daily", "dq_001", "error", failed_df, "20240101"
        )

    def test_get_comparison_stats_delegates_to_reader(
        self, mocker: MockerFixture
    ) -> None:
        """Test get_comparison_stats() delegates to ComparisonReader."""
        # Arrange
        mock_reader = mocker.Mock()
        expected_stats = [{"trade_date": "20240101", "row_count": 100}]
        mock_reader.get_stats = mocker.Mock(return_value=expected_stats)

        service = QualityRecordService(
            comparison_reader=mock_reader,
            comparison_writer=mocker.Mock(),
            quarantine_reader=mocker.Mock(),
            quarantine_writer=mocker.Mock(),
        )

        # Act
        result = service.get_comparison_stats()

        # Assert
        assert result == expected_stats
        mock_reader.get_stats.assert_called_once()

    def test_get_quarantine_stats_delegates_to_reader(
        self, mocker: MockerFixture
    ) -> None:
        """Test get_quarantine_stats() delegates to QuarantineReader."""
        # Arrange
        mock_reader = mocker.Mock()
        expected_stats = [{"dataset": "stock_daily", "count": 5}]
        mock_reader.get_stats = mocker.Mock(return_value=expected_stats)

        service = QualityRecordService(
            comparison_reader=mocker.Mock(),
            comparison_writer=mocker.Mock(),
            quarantine_reader=mock_reader,
            quarantine_writer=mocker.Mock(),
        )

        # Act
        result = service.get_quarantine_stats()

        # Assert
        assert result == expected_stats
        mock_reader.get_stats.assert_called_once()

    def test_get_all_stats_combines_stats(self, mocker: MockerFixture) -> None:
        """Test get_all_stats() combines comparison and quarantine stats."""
        # Arrange
        mock_comp_reader = mocker.Mock()
        mock_comp_reader.get_stats = mocker.Mock(return_value=[{"comp": "stat"}])

        mock_quar_reader = mocker.Mock()
        mock_quar_reader.get_stats = mocker.Mock(return_value=[{"quar": "stat"}])

        service = QualityRecordService(
            comparison_reader=mock_comp_reader,
            comparison_writer=mocker.Mock(),
            quarantine_reader=mock_quar_reader,
            quarantine_writer=mocker.Mock(),
        )

        # Act
        result = service.get_all_stats()

        # Assert
        assert "comparison" in result
        assert "quarantine" in result
        assert result["comparison"] == [{"comp": "stat"}]
        assert result["quarantine"] == [{"quar": "stat"}]

    def test_clear_old_quarantine_records_delegates_to_writer(
        self, mocker: MockerFixture
    ) -> None:
        """Test clear_old_quarantine_records() delegates to QuarantineWriter."""
        # Arrange
        mock_writer = mocker.Mock()
        mock_writer.clear_old_records = mocker.Mock(return_value=42)

        service = QualityRecordService(
            comparison_reader=mocker.Mock(),
            comparison_writer=mocker.Mock(),
            quarantine_reader=mocker.Mock(),
            quarantine_writer=mock_writer,
        )

        # Act
        result = service.clear_old_quarantine_records(days=30)

        # Assert
        assert result == 42
        mock_writer.clear_old_records.assert_called_once_with(30)
