"""Tests for CapitalStore."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.deps import CapitalReaders, CapitalWriters
from ditto_data.storage.capital.moneyflow import MoneyflowReader, MoneyflowWriter
from ditto_platform.foundation import ParquetStore
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

    def test_get_moneyflow_converges_knowledge_date_versions(self) -> None:
        """#667:同 (instrument_id, trade_date) 多 knowledge_date 版本收敛到最新."""
        # Arrange:多版本形态(10-26 两行 kd 10-27/10-28,值不同)。当前生产
        # 通路 kd=映射层 T+1(确定性,同键原位替换)不会产生此形态;此测试
        # 锁定 kd 策略改为摄取日锚(index_valuation 形)时读取语义不变。
        mock_reader = MagicMock()
        mock_reader.read.return_value = pl.DataFrame(
            {
                "instrument_id": [1, 1, 1],
                "trade_date": [
                    date(2026, 10, 26),
                    date(2026, 10, 26),
                    date(2026, 10, 27),
                ],
                "knowledge_date": [
                    date(2026, 10, 27),
                    date(2026, 10, 28),
                    date(2026, 10, 28),
                ],
                "net_mf_amount": [123.4, 130.0, 131.0],
                "net_mf_vol": [500.0, 520.0, 530.0],
                "source": ["tushare"] * 3,
            }
        )
        service = CapitalStore(
            read_ports=CapitalReaders(
                margin_trading=MagicMock(),
                pledge_ratio=MagicMock(),
                valuation_metrics=MagicMock(),
                index_composition=MagicMock(),
                moneyflow=mock_reader,
            ),
            write_ports=CapitalWriters(
                margin_trading=MagicMock(),
                pledge_ratio=MagicMock(),
                valuation_metrics=MagicMock(),
                index_composition=MagicMock(),
            ),
        )

        # Act
        result = service.get_moneyflow(1, "2026-10-26", "2026-10-27")

        # Assert:每交易日单行,10-26 取最新 kd(10-28)的修订值,按 trade_date 排序。
        assert result.height == 2
        first = result.row(0, named=True)
        assert first["trade_date"] == date(2026, 10, 26)
        assert first["net_mf_amount"] == 130.0
        assert result["net_mf_amount"].to_list() == [130.0, 131.0]

    def test_get_moneyflow_empty_frame_passthrough(self) -> None:
        """#667:空帧原样返回,不走收敛/排序."""
        mock_reader = MagicMock()
        mock_reader.read.return_value = pl.DataFrame(
            schema={
                "instrument_id": pl.Int64,
                "trade_date": pl.Date,
                "knowledge_date": pl.Date,
                "net_mf_amount": pl.Float64,
                "net_mf_vol": pl.Float64,
                "source": pl.String,
            }
        )
        service = CapitalStore(
            read_ports=CapitalReaders(
                margin_trading=MagicMock(),
                pledge_ratio=MagicMock(),
                valuation_metrics=MagicMock(),
                index_composition=MagicMock(),
                moneyflow=mock_reader,
            ),
            write_ports=CapitalWriters(
                margin_trading=MagicMock(),
                pledge_ratio=MagicMock(),
                valuation_metrics=MagicMock(),
                index_composition=MagicMock(),
            ),
        )

        result = service.get_moneyflow(1, "2026-10-26", "2026-10-27")

        assert result.is_empty()

    def test_get_moneyflow_real_store_double_version_converges(
        self, tmp_path: Path
    ) -> None:
        """#667:真实 ParquetStore(生产键形)双版本落库→读取收敛单行最新值."""
        # 生产键形见 di/capital.py _moneyflow_parquet_store:
        # key=(instrument_id, trade_date, knowledge_date),date_column=trade_date。
        store = ParquetStore(
            tmp_path,
            key_columns=("instrument_id", "trade_date", "knowledge_date"),
            date_column="trade_date",
            instrument_column="instrument_id",
        )
        base = {
            "instrument_id": [1],
            "trade_date": [date(2026, 10, 26)],
            "buy_elg_amount": [10.0],
            "buy_elg_vol": [1.0],
            "buy_lg_amount": [20.0],
            "buy_lg_vol": [2.0],
            "buy_md_amount": [30.0],
            "buy_md_vol": [3.0],
            "buy_sm_amount": [40.0],
            "buy_sm_vol": [4.0],
            "sell_elg_amount": [11.0],
            "sell_elg_vol": [1.1],
            "sell_lg_amount": [21.0],
            "sell_lg_vol": [2.1],
            "sell_md_amount": [31.0],
            "sell_md_vol": [3.1],
            "sell_sm_amount": [41.0],
            "sell_sm_vol": [4.1],
            "net_mf_amount": [123.4],
            "net_mf_vol": [500.0],
            "source": ["tushare"],
        }
        # 双版本:同 (instrument_id, trade_date),kd 10-27 旧值/10-28 修订值。
        MoneyflowWriter(store).write(
            pl.DataFrame(base | {"knowledge_date": [date(2026, 10, 27)]}), 2026
        )
        MoneyflowWriter(store).write(
            pl.DataFrame(
                base
                | {"knowledge_date": [date(2026, 10, 28)], "net_mf_amount": [130.0]}
            ),
            2026,
        )
        service = CapitalStore(
            read_ports=CapitalReaders(
                margin_trading=MagicMock(),
                pledge_ratio=MagicMock(),
                valuation_metrics=MagicMock(),
                index_composition=MagicMock(),
                moneyflow=MoneyflowReader(store),
            ),
            write_ports=CapitalWriters(
                margin_trading=MagicMock(),
                pledge_ratio=MagicMock(),
                valuation_metrics=MagicMock(),
                index_composition=MagicMock(),
            ),
        )

        result = service.get_moneyflow(1, "2026-10-26", "2026-10-27")

        # 收敛:该交易日单行,取最新 kd(10-28)的修订值。
        day_26 = result.filter(pl.col("trade_date") == date(2026, 10, 26))
        assert day_26.height == 1
        assert day_26["net_mf_amount"].to_list() == [130.0]


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


class TestTop10DisclosureWrite:
    """#627 correctness F1：披露锚帧跨年分片已下沉 ParquetDatasetWriter
    （审计 #684 批B #14，writer 层真存储测试覆盖分区归属）；服务层只保留
    空帧契约."""

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
