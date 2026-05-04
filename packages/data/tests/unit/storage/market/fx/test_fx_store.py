"""FX store tests."""

from datetime import date
from pathlib import Path

import polars as pl
from ditto_data.storage.market.fx.bars import FxBarsReader, FxBarsWriter
from ditto_platform.foundation.storage import ParquetStore, YearlyPartition


class TestFxStore:
    """汇率存储测试."""

    def test_write_and_read_fx_bars(self, tmp_path: Path) -> None:
        """测试写入和读取汇率数据."""
        store = ParquetStore(tmp_path, YearlyPartition())
        writer = FxBarsWriter(store)
        reader = FxBarsReader(store)

        # 准备测试数据
        df = pl.DataFrame(
            {
                "instrument_id": [4_000_001],
                "trade_date": [date(2024, 1, 15)],
                "open": [7.1800],
                "high": [7.1900],
                "low": [7.1750],
                "close": [7.1850],
            }
        )

        # 写入
        result = writer.write(df, year=2024)
        assert result.added == 1

        # 读取
        read_df = reader.read(start_date="2024-01-01", end_date="2024-01-31")
        assert read_df.height == 1
        assert read_df["instrument_id"][0] == 4_000_001
        assert abs(read_df["close"][0] - 7.1850) < 0.0001

    def test_read_by_instrument_id(self, tmp_path: Path) -> None:
        """测试按 instrument_id 过滤读取."""
        store = ParquetStore(tmp_path, YearlyPartition())
        writer = FxBarsWriter(store)
        reader = FxBarsReader(store)

        # 写入多个货币对的数据
        df = pl.DataFrame(
            {
                "instrument_id": [4_000_001, 4_000_002],
                "trade_date": [date(2024, 1, 15), date(2024, 1, 15)],
                "open": [7.18, 1.08],
                "high": [7.19, 1.09],
                "low": [7.17, 1.07],
                "close": [7.185, 1.085],
            }
        )

        writer.write(df, year=2024)

        # 只读取 USDCNH
        usdcnh_df = reader.read(instrument_ids=[4_000_001])
        assert usdcnh_df.height == 1
        assert usdcnh_df["instrument_id"][0] == 4_000_001
