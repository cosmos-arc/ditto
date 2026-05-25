"""Tests for CapitalStore."""

from datetime import date

import polars as pl
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.deps import CapitalReaders, CapitalWriters
from pytest_mock import MockerFixture


class TestCapitalStoreGetMethods:
    """Tests for CapitalStore get_* methods."""

    def test_get_margin_trading_delegates_to_reader(
        self, mocker: MockerFixture
    ) -> None:
        """Test get_margin_trading() delegates to MarginTradingReader."""
        # Arrange
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame({"instrument_id": [1], "date": ["2024-01-01"]})
        mock_reader.get = mocker.Mock(return_value=expected_df)

        read_ports = CapitalReaders(
            margin_trading=mock_reader,
            pledge_ratio=mocker.Mock(),
            valuation_metrics=mocker.Mock(),
            index_composition=mocker.Mock(),
        )
        write_ports = CapitalWriters(
            margin_trading=mocker.Mock(),
            pledge_ratio=mocker.Mock(),
            valuation_metrics=mocker.Mock(),
            index_composition=mocker.Mock(),
        )
        service = CapitalStore(read_ports=read_ports, write_ports=write_ports)

        # Act
        result = service.get_margin_trading(
            instrument_id=1, as_of_date=date(2024, 1, 1)
        )

        # Assert
        assert isinstance(result, pl.DataFrame)
        mock_reader.get.assert_called_once_with(1, date(2024, 1, 1))

    def test_get_pledge_ratio_delegates_to_reader(self, mocker: MockerFixture) -> None:
        """Test get_pledge_ratio() delegates to PledgeRatioReader."""
        # Arrange
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame({"instrument_id": [1], "ratio": [0.5]})
        mock_reader.get = mocker.Mock(return_value=expected_df)

        read_ports = CapitalReaders(
            margin_trading=mocker.Mock(),
            pledge_ratio=mock_reader,
            valuation_metrics=mocker.Mock(),
            index_composition=mocker.Mock(),
        )
        write_ports = CapitalWriters(
            margin_trading=mocker.Mock(),
            pledge_ratio=mocker.Mock(),
            valuation_metrics=mocker.Mock(),
            index_composition=mocker.Mock(),
        )
        service = CapitalStore(read_ports=read_ports, write_ports=write_ports)

        # Act
        result = service.get_pledge_ratio(instrument_id=1, as_of_date=date(2024, 1, 1))

        # Assert
        assert isinstance(result, pl.DataFrame)
        mock_reader.get.assert_called_once_with(1, date(2024, 1, 1))

    def test_get_valuation_metrics_delegates_to_reader(
        self, mocker: MockerFixture
    ) -> None:
        """Test get_valuation_metrics() delegates to ValuationMetricsReader."""
        # Arrange
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame({"instrument_id": [1], "pe": [10.5]})
        mock_reader.get = mocker.Mock(return_value=expected_df)

        read_ports = CapitalReaders(
            margin_trading=mocker.Mock(),
            pledge_ratio=mocker.Mock(),
            valuation_metrics=mock_reader,
            index_composition=mocker.Mock(),
        )
        write_ports = CapitalWriters(
            margin_trading=mocker.Mock(),
            pledge_ratio=mocker.Mock(),
            valuation_metrics=mocker.Mock(),
            index_composition=mocker.Mock(),
        )
        service = CapitalStore(read_ports=read_ports, write_ports=write_ports)

        # Act
        result = service.get_valuation_metrics(
            instrument_id=1, as_of_date=date(2024, 1, 1)
        )

        # Assert
        assert isinstance(result, pl.DataFrame)
        mock_reader.get.assert_called_once_with(1, date(2024, 1, 1))

    def test_get_index_composition_delegates_to_reader(
        self, mocker: MockerFixture
    ) -> None:
        """Test get_index_composition() delegates to IndexCompositionReader."""
        # Arrange
        mock_reader = mocker.Mock()
        expected_df = pl.DataFrame({"index_id": ["399300.XSHE"], "constituent_id": [2]})
        mock_reader.get = mocker.Mock(return_value=expected_df)

        read_ports = CapitalReaders(
            margin_trading=mocker.Mock(),
            pledge_ratio=mocker.Mock(),
            valuation_metrics=mocker.Mock(),
            index_composition=mock_reader,
        )
        write_ports = CapitalWriters(
            margin_trading=mocker.Mock(),
            pledge_ratio=mocker.Mock(),
            valuation_metrics=mocker.Mock(),
            index_composition=mocker.Mock(),
        )
        service = CapitalStore(read_ports=read_ports, write_ports=write_ports)

        # Act
        result = service.get_index_composition(
            index_id="399300.XSHE", as_of_date=date(2024, 1, 1)
        )

        # Assert
        assert isinstance(result, pl.DataFrame)
        mock_reader.get.assert_called_once_with("399300.XSHE", date(2024, 1, 1))


class TestCapitalStoreSaveMethods:
    """Tests for CapitalStore save_* methods."""

    def test_save_margin_trading_delegates_to_writer(
        self, mocker: MockerFixture
    ) -> None:
        """Test save_margin_trading() delegates to MarginTradingWriter."""
        # Arrange
        mock_writer = mocker.Mock()
        mock_writer.write = mocker.Mock(return_value=5)
        test_df = pl.DataFrame({"col1": [1, 2]})

        read_ports = CapitalReaders(
            margin_trading=mocker.Mock(),
            pledge_ratio=mocker.Mock(),
            valuation_metrics=mocker.Mock(),
            index_composition=mocker.Mock(),
        )
        write_ports = CapitalWriters(
            margin_trading=mock_writer,
            pledge_ratio=mocker.Mock(),
            valuation_metrics=mocker.Mock(),
            index_composition=mocker.Mock(),
        )
        service = CapitalStore(read_ports=read_ports, write_ports=write_ports)

        # Act
        result = service.save_margin_trading(test_df)

        # Assert
        assert result == 5
        mock_writer.write.assert_called_once_with(test_df)

    def test_save_pledge_ratio_delegates_to_writer(self, mocker: MockerFixture) -> None:
        """Test save_pledge_ratio() delegates to PledgeRatioWriter."""
        # Arrange
        mock_writer = mocker.Mock()
        mock_writer.write = mocker.Mock(return_value=3)
        test_df = pl.DataFrame({"col1": [1, 2]})

        read_ports = CapitalReaders(
            margin_trading=mocker.Mock(),
            pledge_ratio=mocker.Mock(),
            valuation_metrics=mocker.Mock(),
            index_composition=mocker.Mock(),
        )
        write_ports = CapitalWriters(
            margin_trading=mocker.Mock(),
            pledge_ratio=mock_writer,
            valuation_metrics=mocker.Mock(),
            index_composition=mocker.Mock(),
        )
        service = CapitalStore(read_ports=read_ports, write_ports=write_ports)

        # Act
        result = service.save_pledge_ratio(test_df)

        # Assert
        assert result == 3
        mock_writer.write.assert_called_once_with(test_df)

    def test_save_valuation_metrics_delegates_to_writer(
        self, mocker: MockerFixture
    ) -> None:
        """Test save_valuation_metrics() delegates to ValuationMetricsWriter."""
        # Arrange
        mock_writer = mocker.Mock()
        mock_writer.write = mocker.Mock(return_value=7)
        test_df = pl.DataFrame({"col1": [1, 2]})

        read_ports = CapitalReaders(
            margin_trading=mocker.Mock(),
            pledge_ratio=mocker.Mock(),
            valuation_metrics=mocker.Mock(),
            index_composition=mocker.Mock(),
        )
        write_ports = CapitalWriters(
            margin_trading=mocker.Mock(),
            pledge_ratio=mocker.Mock(),
            valuation_metrics=mock_writer,
            index_composition=mocker.Mock(),
        )
        service = CapitalStore(read_ports=read_ports, write_ports=write_ports)

        # Act
        result = service.save_valuation_metrics(test_df)

        # Assert
        assert result == 7
        mock_writer.write.assert_called_once_with(test_df)

    def test_save_index_composition_delegates_to_writer(
        self, mocker: MockerFixture
    ) -> None:
        """Test save_index_composition() delegates to IndexCompositionWriter."""
        # Arrange
        mock_writer = mocker.Mock()
        mock_writer.write = mocker.Mock(return_value=6)
        test_df = pl.DataFrame({"col1": [1, 2]})

        read_ports = CapitalReaders(
            margin_trading=mocker.Mock(),
            pledge_ratio=mocker.Mock(),
            valuation_metrics=mocker.Mock(),
            index_composition=mocker.Mock(),
        )
        write_ports = CapitalWriters(
            margin_trading=mocker.Mock(),
            pledge_ratio=mocker.Mock(),
            valuation_metrics=mocker.Mock(),
            index_composition=mock_writer,
        )
        service = CapitalStore(read_ports=read_ports, write_ports=write_ports)

        # Act
        result = service.save_index_composition(test_df)

        # Assert
        assert result == 6
        mock_writer.write.assert_called_once_with(test_df)
