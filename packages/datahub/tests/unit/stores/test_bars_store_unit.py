"""Tests for BarsStore."""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
import pytest
from ditto_datahub.models import OnDuplicate
from ditto_datahub.stores.bars_store import BarsStore


class TestBarsStore:
    """Test cases for BarsStore."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.store = BarsStore(Path(self.temp_dir.name))

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_read_returns_empty_dataframe_for_nonexistent_dataset(self) -> None:
        """Test read returns empty DataFrame when dataset doesn't exist."""
        result = self.store.read(
            "nonexistent", start_date="2020-01-01", end_date="2020-12-31"
        )
        assert isinstance(result, pl.DataFrame)
        assert result.is_empty()

    def test_write_and_read_bars(self) -> None:
        """Test write and read operations."""
        # Create test data
        test_df = pl.DataFrame(
            {
                "sid": [100000001, 100000002],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )

        # Write data
        write_result = self.store.write("stock_daily", test_df, 2024)

        assert write_result.file_path is not None
        assert write_result.checksum is not None
        assert Path(write_result.file_path).exists()

        # Read data back
        result = self.store.read(
            "stock_daily", start_date="2024-01-01", end_date="2024-01-31"
        )

        assert len(result) == 2
        assert set(result["sid"].to_list()) == {100000001, 100000002}

    def test_write_merge_with_existing_data(self) -> None:
        """Test write merges with existing data (using KEEP_LAST)."""
        # Initial data
        df1 = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )

        self.store.write("stock_daily", df1, 2024)

        # Additional data with overlap
        df2 = pl.DataFrame(
            {
                "sid": [100000001, 100000002],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "open": [10.5, 11.0],
                "high": [12.5, 13.0],
                "low": [9.5, 10.0],
                "close": [11.5, 12.0],
                "volume": [1500, 2000],
            }
        )

        # Explicitly use KEEP_LAST to test the old Last-Write-Wins behavior
        self.store.write("stock_daily", df2, 2024, on_duplicate=OnDuplicate.KEEP_LAST)

        # Read back - should have unique sid/date pairs
        result = self.store.read(
            "stock_daily", start_date="2024-01-01", end_date="2024-01-31"
        )

        assert len(result) == 2
        # The overlapped record should be updated with new data
        record_100000001 = result.filter(pl.col("sid") == 100000001)
        assert len(record_100000001) == 1
        assert record_100000001["close"][0] == 11.5  # Updated value

    def test_get_years_returns_empty_list_for_nonexistent_dataset(self) -> None:
        """Test get_years returns empty list when dataset doesn't exist."""
        years = self.store.get_years("nonexistent")
        assert years == []

    def test_get_years_returns_available_years(self) -> None:
        """Test get_years returns list of available years."""
        test_df = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )

        self.store.write("stock_daily", test_df, 2024)
        self.store.write("stock_daily", test_df, 2023)

        years = self.store.get_years("stock_daily")
        assert years == [2023, 2024]

    def test_count_returns_zero_for_nonexistent_dataset(self) -> None:
        """Test count returns zero when dataset doesn't exist."""
        count = self.store.count("nonexistent")
        assert count == 0

    def test_count_returns_record_count(self) -> None:
        """Test count returns correct record count."""
        test_df = pl.DataFrame(
            {
                "sid": [100000001, 100000002, 100000003],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
                "open": [10.0, 11.0, 12.0],
                "high": [12.0, 13.0, 14.0],
                "low": [9.0, 10.0, 11.0],
                "close": [11.0, 12.0, 13.0],
                "volume": [1000, 2000, 3000],
            }
        )

        self.store.write("stock_daily", test_df, 2024)

        count = self.store.count("stock_daily")
        assert count == 3

    def test_read_filters_by_sids(self) -> None:
        """Test read filters by security IDs."""
        test_df = pl.DataFrame(
            {
                "sid": [100000001, 100000002, 100000003],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 1), date(2024, 1, 1)],
                "open": [10.0, 11.0, 12.0],
                "high": [12.0, 13.0, 14.0],
                "low": [9.0, 10.0, 11.0],
                "close": [11.0, 12.0, 13.0],
                "volume": [1000, 2000, 3000],
            }
        )

        self.store.write("stock_daily", test_df, 2024)

        result = self.store.read("stock_daily", sids=[100000001, 100000002])
        assert len(result) == 2
        assert set(result["sid"].to_list()) == {100000001, 100000002}

    def test_delete_removes_year_partition(self) -> None:
        """Test delete removes year partition file."""
        test_df = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )

        self.store.write("stock_daily", test_df, 2024)

        # Delete existing partition
        result = self.store.delete("stock_daily", 2024)
        assert result is True

        # Try to delete non-existent partition
        result = self.store.delete("stock_daily", 2024)
        assert result is False


class TestBarsStoreRefactoredHelpers:
    """Tests for refactored helper methods in BarsStore."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.store = BarsStore(Path(self.temp_dir.name))

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_merge_with_existing_returns_new_data_when_no_file(self) -> None:
        """Test _merge_with_existing returns new data when file doesn't exist."""
        new_df = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        non_existent_path = Path(self.temp_dir.name) / "nonexistent.parquet"

        result = self.store._merge_with_existing(
            new_df, non_existent_path, OnDuplicate.KEEP_LAST
        )

        # Should return MergeResult with new data
        assert len(result.df) == 1
        assert result.added == 1
        assert result.updated == 0
        assert result.df["sid"][0] == 100000001

    def test_merge_with_existing_merges_when_file_exists(self) -> None:
        """Test _merge_with_existing merges data when file exists."""
        # First write initial data
        initial_df = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        self.store.write("stock_daily", initial_df, 2024)

        # Create new data with overlap
        new_df = pl.DataFrame(
            {
                "sid": [100000001, 100000002],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "open": [10.5, 11.0],
                "high": [12.5, 13.0],
                "low": [9.5, 10.0],
                "close": [11.5, 12.0],
                "volume": [1500, 2000],
            }
        )

        file_path = self.store._get_path("stock_daily", 2024)
        result = self.store._merge_with_existing(
            new_df, file_path, OnDuplicate.KEEP_LAST
        )

        # Should have 2 unique records
        assert len(result.df) == 2
        # 1 new record added, 1 updated
        assert result.added == 1
        assert result.updated == 1
        # The overlapped record should be updated
        record = result.df.filter(pl.col("sid") == 100000001)
        assert record["close"][0] == 11.5

    def test_prepare_for_write_normalizes_dates(self) -> None:
        """Test _prepare_for_write normalizes date types."""
        # Create DataFrame with string dates
        df = pl.DataFrame(
            {
                "sid": [100000001, 100000002],
                "trade_date": ["2024-01-01", "2024-01-02"],
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )

        result = self.store._prepare_for_write(df)

        # Dates should be Date type
        assert result["trade_date"].dtype == pl.Date
        # Data should be sorted by trade_date, sid
        # Use row() or proper indexing for single row access
        first_row = result.row(0)
        assert first_row[1] == date(2024, 1, 1)

    def test_prepare_for_write_sorts_data(self) -> None:
        """Test _prepare_for_write sorts data correctly."""
        # Create intentionally unsorted data
        df = pl.DataFrame(
            {
                "sid": [100000002, 100000001, 100000002],
                "trade_date": [date(2024, 1, 2), date(2024, 1, 1), date(2024, 1, 1)],
                "open": [11.0, 10.0, 11.0],
                "high": [13.0, 12.0, 13.0],
                "low": [10.0, 9.0, 10.0],
                "close": [12.0, 11.0, 12.0],
                "volume": [2000, 1000, 2000],
            }
        )

        result = self.store._prepare_for_write(df)

        # Should be sorted by trade_date, then sid
        # First row should be 2024-01-01, sid=100000001
        first_row = result.row(0)
        assert first_row[1] == date(2024, 1, 1)
        assert first_row[0] == 100000001
        # Last row should be 2024-01-02, sid=100000002
        last_row = result.row(2)
        assert last_row[1] == date(2024, 1, 2)
        assert last_row[0] == 100000002


class TestOnDuplicate:
    """Tests for on_duplicate parameter to prevent data overwriting."""

    def setup_method(self) -> None:
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.store = BarsStore(Path(self.temp_dir.name))

    def teardown_method(self) -> None:
        """Clean up test environment."""
        self.temp_dir.cleanup()

    def test_on_duplicate_error_raises_on_duplicates(self) -> None:
        """Test OnDuplicate.ERROR raises exception on duplicate data."""
        # Initial data (high quality, e.g., from paid API)
        df1 = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        self.store.write("stock_daily", df1, 2024)

        # Try to write duplicate data (low quality, e.g., from web scraper)
        df2 = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.5],  # Different values
                "high": [12.5],
                "low": [9.5],
                "close": [11.5],
                "volume": [1500],
            }
        )

        # Should raise ValueError due to duplicate
        with pytest.raises(ValueError, match="Duplicate data"):
            self.store.write("stock_daily", df2, 2024, on_duplicate=OnDuplicate.ERROR)

    def test_on_duplicate_keep_first_preserves_original(self) -> None:
        """Test OnDuplicate.KEEP_FIRST preserves original data."""
        # Initial data
        df1 = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        self.store.write("stock_daily", df1, 2024)

        # Try to write duplicate with different values
        df2 = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.5],
                "high": [12.5],
                "low": [9.5],
                "close": [11.5],
                "volume": [1500],
            }
        )
        self.store.write("stock_daily", df2, 2024, on_duplicate=OnDuplicate.KEEP_FIRST)

        # Should keep original data
        result = self.store.read(
            "stock_daily", start_date="2024-01-01", end_date="2024-01-31"
        )
        assert len(result) == 1
        assert result["close"][0] == 11.0  # Original value
        assert result["volume"][0] == 1000

    def test_on_duplicate_keep_last_overwrites(self) -> None:
        """Test OnDuplicate.KEEP_LAST overwrites with new data (Last-Write-Wins)."""
        # Initial data
        df1 = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        self.store.write("stock_daily", df1, 2024)

        # Write duplicate with new values
        df2 = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.5],
                "high": [12.5],
                "low": [9.5],
                "close": [11.5],
                "volume": [1500],
            }
        )
        self.store.write("stock_daily", df2, 2024, on_duplicate=OnDuplicate.KEEP_LAST)

        # Should use new data
        result = self.store.read(
            "stock_daily", start_date="2024-01-01", end_date="2024-01-31"
        )
        assert len(result) == 1
        assert result["close"][0] == 11.5  # New value
        assert result["volume"][0] == 1500

    def test_on_duplicate_with_non_overlapping_data(self) -> None:
        """Test on_duplicate allows non-overlapping data regardless of strategy."""
        # New data with different sid/date (no overlap)
        df1 = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        df2 = pl.DataFrame(
            {
                "sid": [100000002],
                "trade_date": [date(2024, 1, 2)],
                "open": [11.0],
                "high": [13.0],
                "low": [10.0],
                "close": [12.0],
                "volume": [2000],
            }
        )

        # All strategies should work when there's no duplicate
        # Each strategy uses a separate temp directory
        for strategy in [
            OnDuplicate.ERROR,
            OnDuplicate.KEEP_FIRST,
            OnDuplicate.KEEP_LAST,
        ]:
            with TemporaryDirectory() as temp_dir:
                store = BarsStore(Path(temp_dir))
                store.write("stock_daily", df1, 2024)
                store.write("stock_daily", df2, 2024, on_duplicate=strategy)

                result = store.read(
                    "stock_daily", start_date="2024-01-01", end_date="2024-01-31"
                )
                assert len(result) == 2
                sids = set(result["sid"].to_list())
                assert sids == {100000001, 100000002}


class TestBarsStoreEdgeCases:
    """测试 BarsStore 边缘情况和异常处理."""

    def setup_method(self) -> None:
        """设置测试环境."""
        self.temp_dir = TemporaryDirectory()
        self.store = BarsStore(Path(self.temp_dir.name))

    def teardown_method(self) -> None:
        """清理测试环境."""
        self.temp_dir.cleanup()

    def test_ensure_date_column_with_object_type_date_objects(self) -> None:
        """测试 _ensure_date_column 处理 Object 类型包含 date 对象."""
        # 创建包含 date 对象的 DataFrame（Object 类型）
        df = pl.DataFrame(
            {
                "sid": [100000001, 100000002],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 2),
                ],  # date 对象会变成 Object 类型
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            },
            schema={
                "sid": pl.Int64,
                "trade_date": pl.Object,  # 强制设置为 Object 类型
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Int64,
            },
        )

        result = self.store._ensure_date_column(df)

        # 应该返回 DataFrame（可能转换失败但不应崩溃）
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 2

    def test_ensure_date_column_with_string_dates(self) -> None:
        """测试 _ensure_date_column 处理 String 类型的日期."""
        df = pl.DataFrame(
            {
                "sid": [100000001, 100000002],
                "trade_date": ["2024-01-01", "2024-01-02"],
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )

        result = self.store._ensure_date_column(df)

        # 日期应该被转换为 Date 类型
        assert result["trade_date"].dtype == pl.Date
        assert len(result) == 2

    def test_ensure_date_column_with_date_type(self) -> None:
        """测试 _ensure_date_column 处理已经是 Date 类型的列."""
        df = pl.DataFrame(
            {
                "sid": [100000001, 100000002],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 2)],
                "open": [10.0, 11.0],
                "high": [12.0, 13.0],
                "low": [9.0, 10.0],
                "close": [11.0, 12.0],
                "volume": [1000, 2000],
            }
        )

        result = self.store._ensure_date_column(df)

        # 应该直接返回，不做任何转换
        assert result["trade_date"].dtype == pl.Date
        assert len(result) == 2

    def test_merge_with_invalid_on_duplicate_strategy(self) -> None:
        """测试 _merge_with_existing 使用无效的 OnDuplicate 策略."""
        # 先写入一些数据
        df1 = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        self.store.write("stock_daily", df1, 2024)

        # 尝试写入重复数据
        df2 = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.5],
                "high": [12.5],
                "low": [9.5],
                "close": [11.5],
                "volume": [1500],
            }
        )

        file_path = self.store._get_path("stock_daily", 2024)

        # 使用一个无效的 OnDuplicate 值（创建一个假的枚举值）
        class InvalidOnDuplicate:
            """无效的 OnDuplicate 策略."""

            pass

        invalid_strategy = InvalidOnDuplicate()  # type: ignore

        # 应该抛出 ValueError
        with pytest.raises(ValueError, match="Unknown OnDuplicate strategy"):
            self.store._merge_with_existing(df2, file_path, invalid_strategy)  # type: ignore

    def test_write_with_batch_internal_duplicates(self) -> None:
        """测试写入时检测并处理批量内部重复数据."""
        # 创建包含重复 (sid, trade_date) 对的数据
        df = pl.DataFrame(
            {
                "sid": [100000001, 100000001, 100000002],
                "trade_date": [date(2024, 1, 1), date(2024, 1, 1), date(2024, 1, 2)],
                "open": [10.0, 10.5, 11.0],
                "high": [12.0, 12.5, 13.0],
                "low": [9.0, 9.5, 10.0],
                "close": [11.0, 11.5, 12.0],
                "volume": [1000, 1500, 2000],
            }
        )

        # 写入应该自动去重（保留第一条）
        write_result = self.store.write("stock_daily", df, 2024)

        assert write_result.file_path is not None
        assert write_result.checksum is not None
        assert Path(write_result.file_path).exists()

        # 读取验证：应该只有 2 条记录（自动去重）
        result = self.store.read(
            "stock_daily", start_date="2024-01-01", end_date="2024-01-31"
        )

        assert len(result) == 2
        # 验证保留了第一条记录（close=11.0 而不是 11.5）
        record_100000001 = result.filter(pl.col("sid") == 100000001)
        assert len(record_100000001) == 1
        assert record_100000001["close"][0] == 11.0

    def test_read_with_default_year_range(self) -> None:
        """测试读取时不指定日期范围时的默认年份范围."""
        # 写入 2024 年的数据
        df = pl.DataFrame(
            {
                "sid": [100000001],
                "trade_date": [date(2024, 1, 1)],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [1000],
            }
        )
        self.store.write("stock_daily", df, 2024)

        # 不指定日期范围读取（使用默认的 1990-2099）
        result = self.store.read("stock_daily")

        assert len(result) == 1
        assert result["sid"][0] == 100000001

    def test_read_filters_by_date_range(self) -> None:
        """测试读取时按日期范围过滤."""
        # 写入多日期的数据
        df = pl.DataFrame(
            {
                "sid": [100000001, 100000001, 100000001],
                "trade_date": [
                    date(2024, 1, 1),
                    date(2024, 1, 15),
                    date(2024, 2, 1),
                ],
                "open": [10.0, 11.0, 12.0],
                "high": [12.0, 13.0, 14.0],
                "low": [9.0, 10.0, 11.0],
                "close": [11.0, 12.0, 13.0],
                "volume": [1000, 2000, 3000],
            }
        )
        self.store.write("stock_daily", df, 2024)

        # 读取 1 月份的数据
        result = self.store.read(
            "stock_daily", start_date="2024-01-01", end_date="2024-01-31"
        )

        assert len(result) == 2
        # 验证日期范围
        assert result["trade_date"].min() == date(2024, 1, 1)
        assert result["trade_date"].max() == date(2024, 1, 15)
