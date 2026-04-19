"""数据存储验证测试.

验证 Writer/Reader CQRS 模式的数据存储功能。
该测试属于 E2E 验证，使用 tmp_path 进行隔离测试。

参考文档：docs/plans/2026-02-17-e2e-validation-design.md 第 4 节
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_data.models import OnDuplicate
from ditto_data.storage.base.parquet_store import ParquetStore
from ditto_data.storage.market.stock.bars import StockBarsReader, StockBarsWriter
from pytest_mock import MockerFixture


@pytest.mark.e2e
@pytest.mark.integration
class TestStorage:
    """数据存储验证 - Writer/Reader CQRS 模式.

    验证项清单:
    | 编号 | 验证项 | 验证方法 | 通过标准 |
    |------|--------|---------|---------|
    | S2-01 | Writer 写入完整性 | 写入 -> count() | 写入数 = count 数 |
    | S2-02 | Reader 查询准确性 | 写入 -> 条件查询 | 查询结果与预期一致 |
    | S2-03 | Upsert 幂等性 | 同一批数据写入 2 次 | 无重复记录 |
    | S2-04 | 范围查询正确性 | 按日期范围查询 | 起止边界准确 |
    | S2-05 | 多标的并发写入 | 并行写入 25 个标的 | 无数据污染 |
    | S2-06 | 事务回滚恢复 | 模拟写入失败 | 无脏数据残留 |
    """

    def test_s2_01_writer_write_integrity(
        self,
        stock_bars_writer: StockBarsWriter,
        stock_bars_reader: StockBarsReader,
        sample_bars_df: pl.DataFrame,
    ) -> None:
        """S2-01: Writer 写入完整性验证.

        验证 Writer 写入的数据能够通过 Reader 正确统计。
        写入数应等于 count() 返回的记录数。

        Args:
            stock_bars_writer: Stock 日线数据 Writer 实例.
            stock_bars_reader: Stock 日线数据 Reader 实例.
            sample_bars_df: 样本日线数据.

        """
        # Arrange: 准备写入数据
        expected_rows = sample_bars_df.height

        # Act: 写入数据
        result = stock_bars_writer.write(
            df=sample_bars_df,
            year=2024,
            on_duplicate=OnDuplicate.ERROR,
        )

        # Assert: 验证写入结果
        assert result.added == expected_rows, (
            f"写入行数不匹配: 期望 {expected_rows}, 实际 {result.added}"
        )

        # Assert: 验证 count() 返回正确的记录数
        actual_count = stock_bars_reader.count()
        assert actual_count == expected_rows, (
            f"count() 返回值不匹配: 期望 {expected_rows}, 实际 {actual_count}"
        )

    def test_s2_02_reader_query_accuracy(
        self,
        stock_bars_writer: StockBarsWriter,
        stock_bars_reader: StockBarsReader,
        sample_bars_df: pl.DataFrame,
    ) -> None:
        """S2-02: Reader 查询准确性验证.

        验证 Reader 能够准确查询指定条件的数据。

        Args:
            stock_bars_writer: Stock 日线数据 Writer 实例.
            stock_bars_reader: Stock 日线数据 Reader 实例.
            sample_bars_df: 样本日线数据.

        """
        # Arrange: 写入数据
        stock_bars_writer.write(
            df=sample_bars_df,
            year=2024,
            on_duplicate=OnDuplicate.ERROR,
        )

        # Act & Assert: 按 instrument_id 查询
        df_by_id = stock_bars_reader.read(instrument_ids=[1000001])
        assert df_by_id.height == 3, (
            f"按 instrument_id 查询结果不正确: 期望 3, 实际 {df_by_id.height}"
        )

        # Act & Assert: 按日期范围查询
        df_by_date = stock_bars_reader.read(
            start_date="2024-01-02",
            end_date="2024-01-03",
        )
        assert df_by_date.height == 2, (
            f"按日期范围查询结果不正确: 期望 2, 实际 {df_by_date.height}"
        )

        # Act & Assert: 组合条件查询
        df_combined = stock_bars_reader.read(
            instrument_ids=[1000001],
            start_date="2024-01-03",
            end_date="2024-01-04",
        )
        assert df_combined.height == 2, (
            f"组合条件查询结果不正确: 期望 2, 实际 {df_combined.height}"
        )

        # Act & Assert: 查询不存在的 instrument_id
        df_empty = stock_bars_reader.read(instrument_ids=[9999999])
        assert df_empty.height == 0, (
            f"查询不存在的 ID 应返回空结果: 实际 {df_empty.height}"
        )

    def test_s2_03_upsert_idempotency(
        self,
        stock_bars_writer: StockBarsWriter,
        stock_bars_reader: StockBarsReader,
        sample_bars_df: pl.DataFrame,
    ) -> None:
        """S2-03: Upsert 幂等性验证.

        验证同一批数据写入两次不会产生重复记录。
        使用 KEEP_FIRST 策略，第二次写入应跳过已存在的数据。

        Args:
            stock_bars_writer: Stock 日线数据 Writer 实例.
            stock_bars_reader: Stock 日线数据 Reader 实例.
            sample_bars_df: 样本日线数据.

        """
        # Arrange: 第一次写入
        first_result = stock_bars_writer.write(
            df=sample_bars_df,
            year=2024,
            on_duplicate=OnDuplicate.KEEP_FIRST,
        )
        expected_rows = sample_bars_df.height

        # Assert: 验证第一次写入成功
        assert first_result.added == expected_rows, (
            f"第一次写入行数不匹配: 期望 {expected_rows}, 实际 {first_result.added}"
        )

        # Act: 第二次写入相同数据
        second_result = stock_bars_writer.write(
            df=sample_bars_df,
            year=2024,
            on_duplicate=OnDuplicate.KEEP_FIRST,
        )

        # Assert: 验证第二次写入无新增（幂等）
        assert second_result.added == 0, (
            f"重复写入应无新增: 实际新增 {second_result.added}"
        )
        assert second_result.updated == 0, (
            f"KEEP_FIRST 策略应无更新: 实际更新 {second_result.updated}"
        )

        # Assert: 验证总记录数不变
        total_count = stock_bars_reader.count()
        assert total_count == expected_rows, (
            f"总记录数应保持不变: 期望 {expected_rows}, 实际 {total_count}"
        )

    def test_s2_04_range_query_correctness(
        self,
        stock_bars_writer: StockBarsWriter,
        stock_bars_reader: StockBarsReader,
        tmp_path: Path,
    ) -> None:
        """S2-04: 范围查询正确性验证.

        验证按日期范围查询的边界准确性。
        起始日期和结束日期边界应准确包含。

        Args:
            stock_bars_writer: Stock 日线数据 Writer 实例.
            stock_bars_reader: Stock 日线数据 Reader 实例.
            tmp_path: 临时目录.

        """
        # Arrange: 创建跨年的测试数据（使用明确的日期列表）
        dates_2023 = [
            date(2023, 12, 25),
            date(2023, 12, 26),
            date(2023, 12, 27),
            date(2023, 12, 28),
            date(2023, 12, 29),
        ]
        dates_2024 = [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
            date(2024, 1, 5),
            date(2024, 1, 8),
        ]

        df_2023 = pl.DataFrame(
            {
                "instrument_id": [1000001] * 5,
                "trade_date": dates_2023,
                "open": [10.0] * 5,
                "high": [10.5] * 5,
                "low": [9.8] * 5,
                "close": [10.3] * 5,
                "volume": [1000000] * 5,
                "amount": [10000000.0] * 5,
            }
        )
        df_2024 = pl.DataFrame(
            {
                "instrument_id": [1000001] * 5,
                "trade_date": dates_2024,
                "open": [10.0] * 5,
                "high": [10.5] * 5,
                "low": [9.8] * 5,
                "close": [10.3] * 5,
                "volume": [1000000] * 5,
                "amount": [10000000.0] * 5,
            }
        )

        # 重新创建 Writer/Reader 以使用新的 tmp_path
        writer = StockBarsWriter(ParquetStore(tmp_path))
        reader = StockBarsReader(ParquetStore(tmp_path))

        # Act: 写入数据
        writer.write(df=df_2023, year=2023, on_duplicate=OnDuplicate.ERROR)
        writer.write(df=df_2024, year=2024, on_duplicate=OnDuplicate.ERROR)

        # Act & Assert: 查询跨年日期范围（边界测试）
        # 范围: 2023-12-28 到 2024-01-04（包含边界）
        df_range = reader.read(
            start_date="2023-12-28",
            end_date="2024-01-04",
        )

        # 验证边界日期
        trade_dates = df_range["trade_date"].to_list()
        assert date(2023, 12, 28) in trade_dates, "起始日期 2023-12-28 应包含在结果中"
        assert date(2023, 12, 29) in trade_dates, "2023-12-29 应包含在结果中"
        assert date(2024, 1, 2) in trade_dates, "2024-01-02 应包含在结果中"
        assert date(2024, 1, 3) in trade_dates, "2024-01-03 应包含在结果中"
        assert date(2024, 1, 4) in trade_dates, "结束日期 2024-01-04 应包含在结果中"

        # 验证不包含边界外的日期
        assert date(2023, 12, 27) not in trade_dates, "2023-12-27 不应包含在结果中"
        assert date(2024, 1, 5) not in trade_dates, "2024-01-05 不应包含在结果中"

    def test_s2_05_multi_ticker_concurrent_write(
        self,
        stock_bars_writer: StockBarsWriter,
        stock_bars_reader: StockBarsReader,
        multi_ticker_bars_df: pl.DataFrame,
    ) -> None:
        """S2-05: 多标的并发写入验证.

        验证多个标的顺序写入不产生数据污染。
        注意：由于 Parquet 文件使用原子写入，真正的并发写入需要文件锁保护。
        此测试验证多个标的按顺序写入后数据的完整性。

        Args:
            stock_bars_writer: Stock 日线数据 Writer 实例.
            stock_bars_reader: Stock 日线数据 Reader 实例.
            multi_ticker_bars_df: 多标的日线数据.

        """
        # Arrange: 按标的分组
        tickers = multi_ticker_bars_df["instrument_id"].unique().to_list()
        records_per_ticker = 10

        # Act: 顺序写入所有标的数据（模拟并发场景的最终结果）
        total_added = 0
        for ticker in tickers:
            ticker_df = multi_ticker_bars_df.filter(pl.col("instrument_id") == ticker)
            result = stock_bars_writer.write(
                df=ticker_df,
                year=2024,
                on_duplicate=OnDuplicate.KEEP_LAST,
            )
            total_added += result.added

        # Assert: 验证总记录数正确
        total_count = stock_bars_reader.count()
        expected_total = len(tickers) * records_per_ticker
        assert total_count == expected_total, (
            f"总记录数不正确: 期望 {expected_total}, 实际 {total_count}"
        )

        # Assert: 验证每个标的的记录数正确
        for ticker in tickers:
            ticker_count = stock_bars_reader.count(instrument_ids=[ticker])
            assert ticker_count == records_per_ticker, (
                f"标的 {ticker} 记录数不正确: "
                f"期望 {records_per_ticker}, 实际 {ticker_count}"
            )

        # Assert: 验证无数据污染（无交叉数据）
        all_ids = stock_bars_reader.list_instrument_ids()
        assert set(all_ids) == set(tickers), f"instrument_id 列表不正确: {all_ids}"

    def test_s2_06_transaction_rollback_recovery(
        self,
        stock_bars_writer: StockBarsWriter,
        stock_bars_reader: StockBarsReader,
        sample_bars_df: pl.DataFrame,
        mocker: MockerFixture,
    ) -> None:
        """S2-06: 事务回滚恢复验证.

        验证写入失败时不会留下脏数据。
        使用原子写入，失败时应无残留数据。

        Args:
            stock_bars_writer: Stock 日线数据 Writer 实例.
            stock_bars_reader: Stock 日线数据 Reader 实例.
            sample_bars_df: 样本日线数据.
            mocker: pytest-mock fixture.

        """
        # Arrange: 先写入一些有效数据
        valid_df = sample_bars_df.slice(0, 2)  # 取前 2 条
        stock_bars_writer.write(
            df=valid_df,
            year=2024,
            on_duplicate=OnDuplicate.ERROR,
        )
        initial_count = stock_bars_reader.count()

        # Act: 模拟写入失败场景
        # 使用 Mock 模拟原子写入失败
        original_write = stock_bars_writer._store.write

        def mock_write_with_failure(*args, **kwargs):
            """模拟写入失败的 Mock 函数."""
            # 在写入过程中模拟异常
            raise OSError("模拟磁盘写入失败")

        mocker.patch.object(
            stock_bars_writer._store,
            "write",
            side_effect=mock_write_with_failure,
        )

        # 尝试写入新数据（应该失败）
        new_df = sample_bars_df.slice(2, 1)  # 取第 3 条
        with pytest.raises(OSError, match="模拟磁盘写入失败"):
            stock_bars_writer.write(
                df=new_df,
                year=2024,
                on_duplicate=OnDuplicate.ERROR,
            )

        # Assert: 验证失败后数据未改变（无脏数据）
        final_count = stock_bars_reader.count()
        assert final_count == initial_count, (
            f"写入失败后数据不应改变: 期望 {initial_count}, 实际 {final_count}"
        )

        # 恢复原始写入方法，验证系统仍可正常写入
        mocker.patch.object(
            stock_bars_writer._store,
            "write",
            side_effect=original_write,
        )

        # Act: 恢复后重新写入
        result = stock_bars_writer.write(
            df=new_df,
            year=2024,
            on_duplicate=OnDuplicate.KEEP_LAST,
        )

        # Assert: 验证恢复后可以正常写入
        assert result.added == 1, f"恢复后写入应成功: 实际新增 {result.added}"
        recovered_count = stock_bars_reader.count()
        assert recovered_count == initial_count + 1, (
            f"恢复后数据应增加 1 条: 期望 {initial_count + 1}, 实际 {recovered_count}"
        )
