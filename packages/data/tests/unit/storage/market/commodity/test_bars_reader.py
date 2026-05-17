"""Commodity bars store tests."""

from datetime import date
from pathlib import Path

import polars as pl
from ditto_data.storage.market.commodity.bars import (
    CommodityBarsReader,
    CommodityBarsWriter,
)
from ditto_platform.foundation import ParquetStore, YearlyPartition

MARKET_KEY_COLUMNS = ("instrument_id", "trade_date")
MARKET_DATE_COLUMN = "trade_date"
MARKET_INSTRUMENT_COLUMN = "instrument_id"


def _market_store(root: Path) -> ParquetStore:
    return ParquetStore(
        root,
        YearlyPartition(),
        key_columns=MARKET_KEY_COLUMNS,
        date_column=MARKET_DATE_COLUMN,
        instrument_column=MARKET_INSTRUMENT_COLUMN,
    )


class TestCommodityBarsStore:
    """商品行情存储测试."""

    def test_write_and_read_commodity_bars(self, tmp_path: Path) -> None:
        """测试写入和读取商品行情数据."""
        store = _market_store(tmp_path)
        writer = CommodityBarsWriter(store)
        reader = CommodityBarsReader(store)

        # 准备测试数据 - 使用 instrument_id 5_000_001 (大宗商品范围)
        df = pl.DataFrame(
            {
                "instrument_id": [5_000_001],
                "trade_date": [date(2024, 1, 15)],
                "open": [1850.50],
                "high": [1865.00],
                "low": [1848.00],
                "close": [1860.25],
            }
        )

        # 写入
        result = writer.write(df, year=2024)
        assert result.added == 1

        # 读取
        read_df = reader.read(start_date="2024-01-01", end_date="2024-01-31")
        assert read_df.height == 1
        assert read_df["instrument_id"][0] == 5_000_001
        assert abs(read_df["close"][0] - 1860.25) < 0.01

    def test_read_by_instrument_id(self, tmp_path: Path) -> None:
        """测试按 instrument_id 过滤读取."""
        store = _market_store(tmp_path)
        writer = CommodityBarsWriter(store)
        reader = CommodityBarsReader(store)

        # 写入多个商品的数据
        df = pl.DataFrame(
            {
                "instrument_id": [5_000_001, 5_000_002],
                "trade_date": [date(2024, 1, 15), date(2024, 1, 15)],
                "open": [1850.50, 75.20],
                "high": [1865.00, 76.00],
                "low": [1848.00, 74.80],
                "close": [1860.25, 75.50],
            }
        )

        writer.write(df, year=2024)

        # 只读取第一个商品
        filtered_df = reader.read(instrument_ids=[5_000_001])
        assert filtered_df.height == 1
        assert filtered_df["instrument_id"][0] == 5_000_001

    def test_count_records(self, tmp_path: Path) -> None:
        """测试计数功能."""
        store = _market_store(tmp_path)
        writer = CommodityBarsWriter(store)
        reader = CommodityBarsReader(store)

        df = pl.DataFrame(
            {
                "instrument_id": [5_000_001, 5_000_001, 5_000_002],
                "trade_date": [
                    date(2024, 1, 15),
                    date(2024, 1, 16),
                    date(2024, 1, 15),
                ],
                "open": [1850.50, 1860.00, 75.20],
                "high": [1865.00, 1870.00, 76.00],
                "low": [1848.00, 1855.00, 74.80],
                "close": [1860.25, 1865.50, 75.50],
            }
        )

        writer.write(df, year=2024)

        # 计数
        assert reader.count() == 3
        assert reader.count(instrument_ids=[5_000_001]) == 2
        assert reader.count(start_date="2024-01-16", end_date="2024-01-16") == 1

    def test_get_years(self, tmp_path: Path) -> None:
        """测试获取可用年份."""
        store = _market_store(tmp_path)
        writer = CommodityBarsWriter(store)
        reader = CommodityBarsReader(store)

        # 写入 2023 年数据
        df_2023 = pl.DataFrame(
            {
                "instrument_id": [5_000_001],
                "trade_date": [date(2023, 6, 1)],
                "open": [1800.00],
                "high": [1810.00],
                "low": [1795.00],
                "close": [1805.00],
            }
        )
        writer.write(df_2023, year=2023)

        # 写入 2024 年数据
        df_2024 = pl.DataFrame(
            {
                "instrument_id": [5_000_001],
                "trade_date": [date(2024, 1, 15)],
                "open": [1850.50],
                "high": [1865.00],
                "low": [1848.00],
                "close": [1860.25],
            }
        )
        writer.write(df_2024, year=2024)

        years = reader.get_years()
        assert years == [2023, 2024]

    def test_delete_records(self, tmp_path: Path) -> None:
        """测试删除记录."""
        store = _market_store(tmp_path)
        writer = CommodityBarsWriter(store)
        reader = CommodityBarsReader(store)

        df = pl.DataFrame(
            {
                "instrument_id": [5_000_001, 5_000_002],
                "trade_date": [date(2024, 1, 15), date(2024, 1, 15)],
                "open": [1850.50, 75.20],
                "high": [1865.00, 76.00],
                "low": [1848.00, 74.80],
                "close": [1860.25, 75.50],
            }
        )

        writer.write(df, year=2024)

        # 删除一个商品的数据
        deleted = writer.delete(instrument_ids=[5_000_001])
        assert deleted == 1

        # 验证删除后的数据
        remaining_df = reader.read()
        assert remaining_df.height == 1
        assert remaining_df["instrument_id"][0] == 5_000_002

    def test_list_instrument_ids(self, tmp_path: Path) -> None:
        """测试列出所有 instrument_id."""
        store = _market_store(tmp_path)
        writer = CommodityBarsWriter(store)
        reader = CommodityBarsReader(store)

        df = pl.DataFrame(
            {
                "instrument_id": [5_000_001, 5_000_002, 5_000_001],
                "trade_date": [date(2024, 1, 15), date(2024, 1, 15), date(2024, 1, 16)],
                "open": [1850.50, 75.20, 1860.00],
                "high": [1865.00, 76.00, 1870.00],
                "low": [1848.00, 74.80, 1855.00],
                "close": [1860.25, 75.50, 1865.00],
            }
        )

        writer.write(df, year=2024)

        instrument_ids = reader.list_instrument_ids()
        assert instrument_ids == [5_000_001, 5_000_002]

    def test_get_date_range(self, tmp_path: Path) -> None:
        """测试获取日期范围."""
        store = _market_store(tmp_path)
        writer = CommodityBarsWriter(store)
        reader = CommodityBarsReader(store)

        df = pl.DataFrame(
            {
                "instrument_id": [5_000_001, 5_000_001],
                "trade_date": [date(2024, 1, 10), date(2024, 1, 20)],
                "open": [1850.00, 1860.00],
                "high": [1860.00, 1870.00],
                "low": [1845.00, 1855.00],
                "close": [1855.00, 1865.00],
            }
        )

        writer.write(df, year=2024)

        start_date, end_date = reader.get_date_range()
        assert start_date == "2024-01-10"
        assert end_date == "2024-01-20"
