"""Tests for FactorService."""

import polars as pl
from ditto_datahub.services.factor_service import FactorQuery, FactorService
from pytest_mock import MockerFixture


class TestFactorService:
    """Tests for FactorService."""

    def test_find_factors_returns_dataframe(self, mocker: MockerFixture) -> None:
        """Test find_factors() returns DataFrame from reader."""
        # Arrange
        mock_factor_reader = mocker.Mock()
        data_df = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": ["2024-01-02", "2024-01-02"],
                "factor_id": ["factor_momentum_12m", "factor_momentum_12m"],
                "factor_class": ["technical", "technical"],
                "factor_family": ["momentum", "momentum"],
                "exposure": [0.5, 0.6],
                "raw_value": [0.05, 0.06],
                "effective_from": ["2024-01-02", "2024-01-02"],
            }
        )
        mock_factor_reader.read = mocker.Mock(return_value=data_df)

        mock_metadata_reader = mocker.Mock()
        metadata_df = pl.DataFrame(
            {
                "code": ["factor_momentum_12m"],
                "name": ["12-Month Momentum"],
                "class": ["technical"],
                "family": ["momentum"],
                "description": ["12-month price momentum"],
            }
        )
        mock_metadata_reader.batch_get_by_codes = mocker.Mock(return_value=metadata_df)

        service = FactorService(
            factor_reader=mock_factor_reader,
            factor_writer=mocker.Mock(),
            metadata_reader=mock_metadata_reader,
            metadata_writer=mocker.Mock(),
        )

        query = FactorQuery(
            factors=["factor_momentum_12m"],
            start="2024-01-01",
            end="2024-01-31",
        )

        # Act
        result = service.find_factors(query)

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 2
        mock_factor_reader.read.assert_called_once()
        mock_metadata_reader.batch_get_by_codes.assert_called_once()

    def test_find_factors_with_empty_result(self, mocker: MockerFixture) -> None:
        """Test find_factors() returns empty DataFrame when no data."""
        # Arrange
        mock_factor_reader = mocker.Mock()
        mock_factor_reader.read = mocker.Mock(return_value=pl.DataFrame())

        mock_metadata_reader = mocker.Mock()
        mock_metadata_reader.batch_get_by_codes = mocker.Mock(
            return_value=pl.DataFrame()
        )

        service = FactorService(
            factor_reader=mock_factor_reader,
            factor_writer=mocker.Mock(),
            metadata_reader=mock_metadata_reader,
            metadata_writer=mocker.Mock(),
        )

        query = FactorQuery(factors=["factor_nonexistent"], start="2024-01-01")

        # Act
        result = service.find_factors(query)

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0

    def test_list_factors_convenience_method(self, mocker: MockerFixture) -> None:
        """Test list_factors() is a convenience wrapper that calls find_factors()."""
        # Arrange
        mock_factor_reader = mocker.Mock()
        data_df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-02"],
                "factor_id": ["factor_momentum_12m"],
                "factor_class": ["technical"],
                "factor_family": ["momentum"],
                "exposure": [0.5],
                "raw_value": [0.05],
                "effective_from": ["2024-01-02"],
            }
        )
        mock_factor_reader.read = mocker.Mock(return_value=data_df)

        mock_metadata_reader = mocker.Mock()
        metadata_df = pl.DataFrame(
            {
                "code": ["factor_momentum_12m"],
                "name": ["12-Month Momentum"],
                "class": ["technical"],
                "family": ["momentum"],
                "description": ["12-month price momentum"],
            }
        )
        mock_metadata_reader.batch_get_by_codes = mocker.Mock(return_value=metadata_df)

        service = FactorService(
            factor_reader=mock_factor_reader,
            factor_writer=mocker.Mock(),
            metadata_reader=mock_metadata_reader,
            metadata_writer=mocker.Mock(),
        )

        # Act
        result = service.list_factors(
            start="2024-01-01", end="2024-01-31", factor_ids=["factor_momentum_12m"]
        )

        # Assert
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 1
        # Verify the underlying reader was called with correct parameters
        mock_factor_reader.read.assert_called_once_with(
            start_date="2024-01-01",
            end_date="2024-01-31",
            as_of_date=None,
            factor_ids=["factor_momentum_12m"],
        )

    def test_list_factors_with_none_factor_ids(self, mocker: MockerFixture) -> None:
        """Test list_factors() with None factor_ids returns all factors."""
        # Arrange
        mock_factor_reader = mocker.Mock()
        data_df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-02"],
                "factor_id": ["factor_momentum_12m"],
                "factor_class": ["technical"],
                "factor_family": ["momentum"],
                "exposure": [0.5],
                "raw_value": [0.05],
                "effective_from": ["2024-01-02"],
            }
        )
        mock_factor_reader.read = mocker.Mock(return_value=data_df)

        mock_metadata_reader = mocker.Mock()
        mock_metadata_reader.batch_get_by_codes = mocker.Mock(
            return_value=pl.DataFrame()
        )

        service = FactorService(
            factor_reader=mock_factor_reader,
            factor_writer=mocker.Mock(),
            metadata_reader=mock_metadata_reader,
            metadata_writer=mocker.Mock(),
        )

        # Act
        result = service.list_factors(
            start="2024-01-01", end="2024-01-31", factor_ids=None
        )

        # Assert
        assert isinstance(result, pl.DataFrame)
        mock_factor_reader.read.assert_called_once_with(
            start_date="2024-01-01",
            end_date="2024-01-31",
            as_of_date=None,
            factor_ids=None,
        )

    def test_find_factors_filters_by_class_and_family(
        self, mocker: MockerFixture
    ) -> None:
        """Test find_factors() applies class and family filters."""
        # Arrange
        mock_factor_reader = mocker.Mock()
        data_df = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": ["2024-01-02", "2024-01-02"],
                "factor_id": ["factor_momentum_12m", "factor_pe_ratio"],
                "factor_class": ["technical", "fundamental"],
                "factor_family": ["momentum", "value"],
                "exposure": [0.5, 0.6],
                "raw_value": [0.05, 0.06],
                "effective_from": ["2024-01-02", "2024-01-02"],
            }
        )
        mock_factor_reader.read = mocker.Mock(return_value=data_df)

        mock_metadata_reader = mocker.Mock()
        mock_metadata_reader.batch_get_by_codes = mocker.Mock(
            return_value=pl.DataFrame()
        )

        service = FactorService(
            factor_reader=mock_factor_reader,
            factor_writer=mocker.Mock(),
            metadata_reader=mock_metadata_reader,
            metadata_writer=mocker.Mock(),
        )

        # Act - filter by class only
        query = FactorQuery(
            start="2024-01-01",
            end="2024-01-31",
            factor_classes=["technical"],
        )
        result = service.find_factors(query)

        # Assert
        assert len(result) == 1
        assert result["factor_class"][0] == "technical"

    def test_find_factors_with_int_factor_ids(self, mocker: MockerFixture) -> None:
        """Test find_factors() handles both int and str factor IDs."""
        # Arrange
        mock_factor_reader = mocker.Mock()
        data_df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": ["2024-01-02"],
                "factor_id": ["factor_momentum_12m"],
                "factor_class": ["technical"],
                "factor_family": ["momentum"],
                "exposure": [0.5],
                "raw_value": [0.05],
                "effective_from": ["2024-01-02"],
            }
        )
        mock_factor_reader.read = mocker.Mock(return_value=data_df)

        mock_metadata_reader = mocker.Mock()
        mock_metadata_reader.batch_get_by_codes = mocker.Mock(
            return_value=pl.DataFrame()
        )

        service = FactorService(
            factor_reader=mock_factor_reader,
            factor_writer=mocker.Mock(),
            metadata_reader=mock_metadata_reader,
            metadata_writer=mocker.Mock(),
        )

        # Act - pass int factor IDs
        query = FactorQuery(factors=[1, 2, 3], start="2024-01-01")
        service.find_factors(query)

        # Assert - verify reader was called with string IDs
        call_args = mock_factor_reader.read.call_args
        assert call_args[1]["factor_ids"] == ["1", "2", "3"]

    def test_close_does_nothing(self, mocker: MockerFixture) -> None:
        """Test close() does nothing (Readers/Writers don't own resources)."""
        # Arrange
        service = FactorService(
            factor_reader=mocker.Mock(),
            factor_writer=mocker.Mock(),
            metadata_reader=mocker.Mock(),
            metadata_writer=mocker.Mock(),
        )

        # Act & Assert - should not raise
        service.close()
