"""Checksum 计算工具单元测试."""

import hashlib

import polars as pl
from ditto_foundation.util.checksum import ChecksumCompute


class TestChecksumCompute:
    """ChecksumCompute 单元测试."""

    def test_empty_dataframe_returns_md5_of_empty_bytes(self) -> None:
        """空 DataFrame 应返回 MD5 of empty bytes."""
        df = pl.DataFrame()
        checksum = ChecksumCompute.from_dataframe(df, "stock_daily")
        expected = hashlib.md5(b"", usedforsecurity=False).hexdigest()
        assert checksum == expected

    def test_deterministic_irrespective_of_row_order(self) -> None:
        """验证行顺序不影响 checksum（核心测试）."""
        # 相同数据，不同行顺序
        df1 = pl.DataFrame(
            {
                "trade_date": ["2024-01-02", "2024-01-01"],
                "sid": [2, 1],
                "close": [10.0, 11.0],
                "source": ["tushare", "tushare"],
            }
        )

        df2 = pl.DataFrame(
            {
                "trade_date": ["2024-01-01", "2024-01-02"],
                "sid": [1, 2],
                "close": [11.0, 10.0],
                "source": ["tushare", "tushare"],
            }
        )

        checksum1 = ChecksumCompute.from_dataframe(df1, "stock_daily")
        checksum2 = ChecksumCompute.from_dataframe(df2, "stock_daily")

        assert checksum1 == checksum2, "相同数据不同行顺序应产生相同 checksum"

    def test_checksum_includes_all_fields_including_sid_and_source(self) -> None:
        """验证 checksum 包含所有字段（包括 sid、source）."""
        df_with_sid = pl.DataFrame(
            {
                "trade_date": ["2024-01-01"],
                "sid": [1],
                "close": [10.0],
                "source": ["tushare"],
            }
        )

        df_without_sid = pl.DataFrame(
            {
                "trade_date": ["2024-01-01"],
                "close": [10.0],
            }
        )

        checksum1 = ChecksumCompute.from_dataframe(df_with_sid, "stock_daily")
        checksum2 = ChecksumCompute.from_dataframe(df_without_sid, "stock_daily")

        assert checksum1 != checksum2, "sid/source 字段应影响 checksum"

    def test_different_source_produces_different_checksum(self) -> None:
        """验证不同 source 产生不同 checksum."""
        base_data = {
            "trade_date": ["2024-01-01"],
            "sid": [1],
            "close": [10.0],
        }

        df_tushare = pl.DataFrame({**base_data, "source": ["tushare"]})
        df_akshare = pl.DataFrame({**base_data, "source": ["akshare"]})

        checksum1 = ChecksumCompute.from_dataframe(df_tushare, "stock_daily")
        checksum2 = ChecksumCompute.from_dataframe(df_akshare, "stock_daily")

        assert checksum1 != checksum2, "不同 source 应产生不同 checksum"

    def test_uses_md5_algorithm_32_char_hex(self) -> None:
        """验证使用 MD5 算法（32 字符 hex）."""
        df = pl.DataFrame(
            {
                "trade_date": ["2024-01-01"],
                "sid": [1],
            }
        )

        checksum = ChecksumCompute.from_dataframe(df, "stock_daily")

        # MD5 应该是 32 字符 hex string
        assert len(checksum) == 32
        assert all(c in "0123456789abcdef" for c in checksum)

    def test_dataset_specific_sort_keys(self) -> None:
        """验证不同数据集使用不同的排序键."""
        # stock_daily: 按 trade_date, sid 排序
        df_stock = pl.DataFrame(
            {
                "trade_date": ["2024-01-02", "2024-01-01"],
                "sid": [2, 1],
                "close": [10.0, 11.0],
            }
        )

        # calendar: 按 trade_date 排序
        df_calendar = pl.DataFrame(
            {
                "trade_date": ["2024-01-02", "2024-01-01"],
                "is_trading": [True, False],
            }
        )

        # stock_daily: 两行不同顺序应相同
        checksum1a = ChecksumCompute.from_dataframe(df_stock, "stock_daily")
        checksum1b = ChecksumCompute.from_dataframe(df_stock.reverse(), "stock_daily")
        assert checksum1a == checksum1b

        # calendar: 两行不同顺序应相同
        checksum2a = ChecksumCompute.from_dataframe(df_calendar, "calendar")
        checksum2b = ChecksumCompute.from_dataframe(df_calendar.reverse(), "calendar")
        assert checksum2a == checksum2b

    def test_unknown_dataset_with_fallback_sort_keys(self) -> None:
        """验证未知数据集可以使用备用排序键."""
        df = pl.DataFrame(
            {
                "id": [2, 1],
                "value": [10.0, 11.0],
            }
        )

        # 使用备用排序键
        checksum = ChecksumCompute.from_dataframe(
            df,
            "unknown_dataset",
            fallback_sort_keys=["id"],
        )

        # 相同数据不同顺序应产生相同 checksum
        checksum_reversed = ChecksumCompute.from_dataframe(
            df.reverse(),
            "unknown_dataset",
            fallback_sort_keys=["id"],
        )

        assert checksum == checksum_reversed

    def test_get_sort_keys_returns_sequence(self) -> None:
        """验证 get_sort_keys 返回正确的排序键."""
        keys = ChecksumCompute.get_sort_keys("stock_daily")
        assert list(keys) == ["trade_date", "sid"]

        keys_calendar = ChecksumCompute.get_sort_keys("calendar")
        assert list(keys_calendar) == ["trade_date"]

        keys_unknown = ChecksumCompute.get_sort_keys("unknown")
        assert list(keys_unknown) == []
