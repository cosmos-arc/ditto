"""Tests for CapitalStore."""

from datetime import date

import polars as pl
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.deps import CapitalReaders, CapitalWriters
from ditto_platform.foundation.storage.types import OnDuplicate
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
        mock_writer.write.assert_called_once_with(
            test_df, on_duplicate=OnDuplicate.KEEP_FIRST
        )

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
        """Test save_index_composition() delegates to the index_weight writer."""
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


class TestTop10DisclosureSharding:
    """#627 correctness F1：披露锚帧按 report_date 年分片写（跨年报告期行
    落报告期年分区，按报告期年的范围读不漏行——fina_indicator #3 同因）."""

    def _top10_frame(self) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "report_date": [date(2025, 12, 31), date(2026, 3, 31)],
                "knowledge_date": [date(2026, 4, 30), date(2026, 4, 30)],
                "holder_name": ["a", "b"],
                "hold_amount": [1.0, 2.0],
            }
        )

    def test_save_top10_holders_shards_by_report_year(
        self, mocker: MockerFixture
    ) -> None:
        calls: list[tuple[int, int]] = []
        writer = mocker.Mock()

        def fake_write(part: pl.DataFrame, year: int, on_duplicate: object = None):
            calls.append((year, part.height))
            return mocker.Mock(added=part.height, updated=0)

        writer.write = fake_write
        service = CapitalStore(
            read_ports=mocker.Mock(),
            write_ports=mocker.Mock(top10_holders=writer),
        )

        written = service.save_top10_holders(self._top10_frame(), year=2026)

        # 报告期 2025-12-31 的行落 2025 分区（公告年 2026 不承载它）
        assert sorted(calls) == [(2025, 1), (2026, 1)]
        assert written == 2

    def test_save_top10_floatholders_shards_by_report_year(
        self, mocker: MockerFixture
    ) -> None:
        writer = mocker.Mock()
        writer.write = mocker.Mock(
            side_effect=lambda part, year, on_duplicate=None: mocker.Mock(
                added=part.height, updated=0
            )
        )
        service = CapitalStore(
            read_ports=mocker.Mock(),
            write_ports=mocker.Mock(top10_floatholders=writer),
        )

        written = service.save_top10_floatholders(self._top10_frame(), year=2026)

        years = sorted(call.args[1] for call in writer.write.call_args_list)
        assert years == [2025, 2026]
        assert written == 2

    def test_save_top10_holders_empty_frame_writes_nothing(
        self, mocker: MockerFixture
    ) -> None:
        writer = mocker.Mock()
        service = CapitalStore(
            read_ports=mocker.Mock(),
            write_ports=mocker.Mock(top10_holders=writer),
        )
        assert (
            service.save_top10_holders(
                pl.DataFrame(schema={"report_date": pl.Date}), 2026
            )
            == 0
        )
        writer.write.assert_not_called()
