"""Checksum 计算工具单元测试."""

import polars as pl
import xxhash
from ditto_infra.foundation.util.checksum import ChecksumCompute

STOCK_DAILY_KEYS = ("trade_date", "instrument_id")
CALENDAR_KEYS = ("trade_date",)


class TestChecksumCompute:
    """ChecksumCompute 单元测试."""

    def test_empty_dataframe_returns_xxh3_128_of_empty_bytes(self) -> None:
        """空 DataFrame 应返回 XXH3_128 of empty bytes."""
        df = pl.DataFrame()
        checksum = ChecksumCompute.from_dataframe(df)
        expected = xxhash.xxh3_128_hexdigest(b"")
        assert checksum == expected

    def test_deterministic_irrespective_of_row_order(self) -> None:
        """验证行顺序不影响 checksum(核心测试)."""
        df1 = pl.DataFrame(
            {
                "trade_date": ["2024-01-02", "2024-01-01"],
                "instrument_id": [2, 1],
                "close": [10.0, 11.0],
                "source": ["tushare", "tushare"],
            }
        )

        df2 = pl.DataFrame(
            {
                "trade_date": ["2024-01-01", "2024-01-02"],
                "instrument_id": [1, 2],
                "close": [11.0, 10.0],
                "source": ["tushare", "tushare"],
            }
        )

        checksum1 = ChecksumCompute.from_dataframe(df1, sort_keys=STOCK_DAILY_KEYS)
        checksum2 = ChecksumCompute.from_dataframe(df2, sort_keys=STOCK_DAILY_KEYS)

        assert checksum1 == checksum2, "相同数据不同行顺序应产生相同 checksum"

    def test_checksum_includes_all_fields_including_sid_and_source(self) -> None:
        """验证 checksum 包含所有字段(包括 instrument_id、source)."""
        df_with_sid = pl.DataFrame(
            {
                "trade_date": ["2024-01-01"],
                "instrument_id": [1],
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

        checksum1 = ChecksumCompute.from_dataframe(
            df_with_sid, sort_keys=STOCK_DAILY_KEYS
        )
        checksum2 = ChecksumCompute.from_dataframe(
            df_without_sid, sort_keys=STOCK_DAILY_KEYS
        )

        assert checksum1 != checksum2, "instrument_id/source 字段应影响 checksum"

    def test_different_source_produces_different_checksum(self) -> None:
        """验证不同 source 产生不同 checksum."""
        base_data = {
            "trade_date": ["2024-01-01"],
            "instrument_id": [1],
            "close": [10.0],
        }

        df_tushare = pl.DataFrame({**base_data, "source": ["tushare"]})
        df_akshare = pl.DataFrame({**base_data, "source": ["akshare"]})

        checksum1 = ChecksumCompute.from_dataframe(
            df_tushare, sort_keys=STOCK_DAILY_KEYS
        )
        checksum2 = ChecksumCompute.from_dataframe(
            df_akshare, sort_keys=STOCK_DAILY_KEYS
        )

        assert checksum1 != checksum2, "不同 source 应产生不同 checksum"

    def test_uses_xxh3_128_algorithm_32_char_hex(self) -> None:
        """验证使用 XXH3_128 算法(32 字符 hex)."""
        df = pl.DataFrame(
            {
                "trade_date": ["2024-01-01"],
                "instrument_id": [1],
            }
        )

        checksum = ChecksumCompute.from_dataframe(df, sort_keys=STOCK_DAILY_KEYS)

        assert len(checksum) == 32
        assert all(c in "0123456789abcdef" for c in checksum)

    def test_sort_keys_produce_deterministic_results(self) -> None:
        """验证通过 sort_keys 参数控制排序产生确定性结果."""
        df_stock = pl.DataFrame(
            {
                "trade_date": ["2024-01-02", "2024-01-01"],
                "instrument_id": [2, 1],
                "close": [10.0, 11.0],
            }
        )

        df_calendar = pl.DataFrame(
            {
                "trade_date": ["2024-01-02", "2024-01-01"],
                "is_trading": [True, False],
            }
        )

        checksum1a = ChecksumCompute.from_dataframe(
            df_stock, sort_keys=STOCK_DAILY_KEYS
        )
        checksum1b = ChecksumCompute.from_dataframe(
            df_stock.reverse(), sort_keys=STOCK_DAILY_KEYS
        )
        assert checksum1a == checksum1b

        checksum2a = ChecksumCompute.from_dataframe(
            df_calendar, sort_keys=CALENDAR_KEYS
        )
        checksum2b = ChecksumCompute.from_dataframe(
            df_calendar.reverse(), sort_keys=CALENDAR_KEYS
        )
        assert checksum2a == checksum2b

    def test_fallback_sort_keys(self) -> None:
        """验证自定义排序键产生确定性结果."""
        df = pl.DataFrame(
            {
                "id": [2, 1],
                "value": [10.0, 11.0],
            }
        )

        checksum = ChecksumCompute.from_dataframe(df, sort_keys=["id"])
        checksum_reversed = ChecksumCompute.from_dataframe(
            df.reverse(), sort_keys=["id"]
        )

        assert checksum == checksum_reversed

    def test_no_sort_keys_preserves_row_order(self) -> None:
        """验证不提供 sort_keys 时保留原始行顺序."""
        df = pl.DataFrame(
            {
                "value": [1, 2],
            }
        )

        checksum1 = ChecksumCompute.from_dataframe(df)
        checksum2 = ChecksumCompute.from_dataframe(df.reverse())

        assert checksum1 != checksum2

    def test_handles_missing_sort_keys_gracefully(self) -> None:
        """验证缺失排序键时能优雅处理（不排序，记录警告）."""
        df = pl.DataFrame(
            {
                "unknown_col": [1, 2],
                "value": [10.0, 11.0],
            }
        )

        checksum1 = ChecksumCompute.from_dataframe(df, sort_keys=["nonexistent"])
        checksum2 = ChecksumCompute.from_dataframe(
            df.reverse(), sort_keys=["nonexistent"]
        )

        assert checksum1 != checksum2

    def test_different_data_types_affect_checksum(self) -> None:
        """验证不同数据类型产生不同 checksum."""
        df_int = pl.DataFrame({"value": [1]})
        df_float = pl.DataFrame({"value": [1.0]})
        df_str = pl.DataFrame({"value": ["1"]})
        df_bool = pl.DataFrame({"value": [True]})

        checksums = [
            ChecksumCompute.from_dataframe(df_int),
            ChecksumCompute.from_dataframe(df_float),
            ChecksumCompute.from_dataframe(df_str),
            ChecksumCompute.from_dataframe(df_bool),
        ]

        assert len(set(checksums)) == 4

    def test_handles_null_values(self) -> None:
        """验证处理 None/null 值."""
        df_with_null = pl.DataFrame(
            {
                "trade_date": ["2024-01-01"],
                "value": [None],
            }
        )

        df_with_zero = pl.DataFrame(
            {
                "trade_date": ["2024-01-01"],
                "value": [0],
            }
        )

        checksum1 = ChecksumCompute.from_dataframe(df_with_null)
        checksum2 = ChecksumCompute.from_dataframe(df_with_zero)

        assert checksum1 != checksum2

    def test_multi_row_dataframe_checksum(self) -> None:
        """验证多行 DataFrame 的 checksum 计算."""
        df = pl.DataFrame(
            {
                "trade_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "instrument_id": [1, 2, 3],
                "close": [10.0, 11.0, 12.0],
            }
        )

        checksum = ChecksumCompute.from_dataframe(df, sort_keys=STOCK_DAILY_KEYS)

        assert len(checksum) == 32
        assert all(c in "0123456789abcdef" for c in checksum)

    def test_adj_factor_sorting(self) -> None:
        """验证 adj_factor 排序键产生确定性结果."""
        df = pl.DataFrame(
            {
                "trade_date": ["2024-01-02", "2024-01-01"],
                "instrument_id": [2, 1],
                "adj_factor": [1.0, 0.95],
            }
        )

        checksum1 = ChecksumCompute.from_dataframe(df, sort_keys=STOCK_DAILY_KEYS)
        checksum2 = ChecksumCompute.from_dataframe(
            df.reverse(), sort_keys=STOCK_DAILY_KEYS
        )

        assert checksum1 == checksum2

    def test_empty_string_vs_none(self) -> None:
        """验证空字符串与 None 产生不同 checksum."""
        df_empty_str = pl.DataFrame({"value": [""]})
        df_none = pl.DataFrame({"value": [None]})

        checksum1 = ChecksumCompute.from_dataframe(df_empty_str)
        checksum2 = ChecksumCompute.from_dataframe(df_none)

        assert checksum1 != checksum2
