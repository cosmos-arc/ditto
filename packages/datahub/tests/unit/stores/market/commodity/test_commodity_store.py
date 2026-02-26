"""Commodity store tests."""

from datetime import date
from pathlib import Path

import polars as pl
from ditto_datahub.stores.market.commodity import (
    CommodityBarsReader,
    CommodityBarsWriter,
)


class TestCommodityStore:
    """商品存储测试."""

    def test_write_and_read_commodity_bars(self, tmp_path: Path) -> None:
        """测试写入和读取商品数据."""
        writer = CommodityBarsWriter(tmp_path)
        reader = CommodityBarsReader(tmp_path)

        # 准备测试数据 (WTI 原油, instrument_id = 5_000_001)
        df = pl.DataFrame(
            {
                "instrument_id": [5_000_001],
                "trade_date": [date(2024, 1, 15)],
                "open": [72.50],
                "high": [73.00],
                "low": [72.00],
                "close": [72.80],
            }
        )

        # 写入
        result = writer.write(df, year=2024)
        assert result.added == 1

        # 读取
        read_df = reader.read(start_date="2024-01-01", end_date="2024-01-31")
        assert read_df.height == 1
        assert read_df["instrument_id"][0] == 5_000_001
        assert abs(read_df["close"][0] - 72.80) < 0.0001

    def test_read_by_instrument_id(self, tmp_path: Path) -> None:
        """测试按 instrument_id 过滤读取."""
        writer = CommodityBarsWriter(tmp_path)
        reader = CommodityBarsReader(tmp_path)

        # 写入多个商品的数据
        df = pl.DataFrame(
            {
                "instrument_id": [5_000_001, 5_000_002],
                "trade_date": [date(2024, 1, 15), date(2024, 1, 15)],
                "open": [72.50, 85.00],
                "high": [73.00, 86.00],
                "low": [72.00, 84.00],
                "close": [72.80, 85.50],
            }
        )

        writer.write(df, year=2024)

        # 只读取 WTI 原油
        wti_df = reader.read(instrument_ids=[5_000_001])
        assert wti_df.height == 1
        assert wti_df["instrument_id"][0] == 5_000_001
