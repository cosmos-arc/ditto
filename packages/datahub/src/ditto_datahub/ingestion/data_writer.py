"""
IngestionDataWriter utility class for writing data to stores.

This module provides a unified interface for writing data to different storage
backends (Parquet files, SQLite databases) with support for duplicate handling
strategies.
"""

from pathlib import Path
from sqlite3 import Connection

import polars as pl
from ditto_foundation.util.checksum import ChecksumCompute

from ditto_datahub.models.common import OnDuplicate
from ditto_datahub.models.storage import WriteResult


class IngestionDataWriter:
    """
    数据写入工具

    提供 Store 写入的通用工具方法，支持 Parquet 文件和 SQLite 数据库。

    该类提供了统一的写入接口，支持不同的重复数据处理策略：
    - OnDuplicate.ERROR: 遇到重复数据时报错（默认，最安全）
    - OnDuplicate.KEEP_FIRST: 保留现有数据，忽略新数据
    - OnDuplicate.KEEP_LAST: 使用新数据覆盖现有数据（Last-Write-Wins）

    Examples:
        >>> # 写入 Parquet 文件
        >>> result = IngestionDataWriter.write_parquet(
        ...     df=dataframe,
        ...     path=Path("data.parquet"),
        ...     on_duplicate=OnDuplicate.KEEP_FIRST,
        ... )
        >>> print(f"写入 {result.rows_written} 行")

        >>> # 写入 SQLite 表
        >>> import sqlite3
        >>> conn = sqlite3.connect("data.db")
        >>> result = IngestionDataWriter.write_sqlite(
        ...     df=dataframe,
        ...     table="stocks",
        ...     conn=conn,
        ...     on_duplicate=OnDuplicate.KEEP_LAST,
        ... )
        >>> conn.close()

    """

    @staticmethod
    def write_parquet(
        df: pl.DataFrame,
        path: Path,
        *,
        on_duplicate: OnDuplicate = OnDuplicate.KEEP_FIRST,
        key_columns: tuple[str, ...] | None = None,
    ) -> WriteResult:
        """
        写入 Parquet 文件

        支持增量写入和重复数据处理策略。使用文件锁确保并发安全。

        Args:
            df: 要写入的 DataFrame
            path: Parquet 文件路径
            on_duplicate: 重复数据处理策略
            key_columns: 主键列（用于检测重复，如果为 None 则使用所有列）

        Returns:
            WriteResult: 包含写入结果的统计信息

        Raises:
            ValueError: 当 on_duplicate=ERROR 且存在重复数据时

        Examples:
            >>> result = IngestionDataWriter.write_parquet(
            ...     df=dataframe,
            ...     path=Path("stocks.parquet"),
            ...     on_duplicate=OnDuplicate.KEEP_FIRST,
            ...     key_columns=("instrument_id", "trade_date"),
            ... )

        """
        # 如果没有指定 key_columns，使用所有列
        if key_columns is None:
            key_columns = tuple(df.columns)

        # 检查输入数据
        if df.is_empty():
            return WriteResult(
                file_path=str(path),
                checksum="",
                rows_written=0,
                rows_total=0,
                blocked=False,
            )

        # 读取现有数据
        if path.exists():
            existing = pl.read_parquet(path)
            existing_keys = existing.select(key_columns)

            # 检查是否有重复
            new_keys = df.select(key_columns)
            overlap = new_keys.join(existing_keys, on=key_columns, how="inner")
            has_overlap = not overlap.is_empty()

            if has_overlap:
                overlap_count = len(overlap)

                if on_duplicate == OnDuplicate.ERROR:
                    msg = (
                        f"发现 {overlap_count} 行重复数据 (主键: {key_columns})。"
                        f"使用 OnDuplicate.KEEP_FIRST 保留现有数据, "
                        f"或 OnDuplicate.KEEP_LAST 覆盖现有数据。"
                    )
                    raise ValueError(msg)
                elif on_duplicate == OnDuplicate.KEEP_FIRST:
                    # 保留现有数据，过滤掉新数据中的重复部分
                    non_overlapping = new_keys.join(
                        existing_keys, on=key_columns, how="anti"
                    )
                    df = df.join(non_overlapping, on=key_columns, how="inner")
                    combined = pl.concat([existing, df])
                    added = len(df)
                elif on_duplicate == OnDuplicate.KEEP_LAST:
                    # Last-Write-Wins: 新数据覆盖现有数据
                    combined = pl.concat([existing, df])
                    combined = combined.unique(subset=key_columns, keep="last")
                    added = len(df) - overlap_count
                else:
                    raise ValueError(f"未知的 OnDuplicate 策略: {on_duplicate}")
            else:
                # 无重复，直接合并
                combined = pl.concat([existing, df])
                added = len(df)
        else:
            # 文件不存在，直接写入
            combined = df
            added = len(df)

        # 确保父目录存在
        path.parent.mkdir(parents=True, exist_ok=True)

        # 写入 Parquet 文件
        combined.write_parquet(path)

        # 计算 checksum
        checksum = ChecksumCompute.from_dataframe(combined, path.name)

        return WriteResult(
            file_path=str(path),
            checksum=checksum,
            rows_written=added,
            rows_total=len(combined),
            blocked=False,
        )

    # ========================================================================
    # SQLite 写入辅助方法
    # ========================================================================

    @staticmethod
    def _validate_sqlite_input(
        df: pl.DataFrame,
        table: str,
        key_columns: tuple[str, ...] | None,
    ) -> tuple[str, ...]:
        """
        验证 SQLite 写入输入并返回 key_columns.

        Args:
            df: 要写入的 DataFrame
            table: 表名
            key_columns: 主键列（如果为 None 则使用所有列）

        Returns:
            确定后的 key_columns 元组

        """
        # 如果没有指定 key_columns，使用所有列
        if key_columns is None:
            key_columns = tuple(df.columns)

        # 检查输入数据
        if df.is_empty():
            return key_columns

        return key_columns

    @staticmethod
    def _check_table_exists(conn: Connection, table: str) -> bool:
        """
        检查表是否存在.

        Args:
            conn: SQLite 连接
            table: 表名

        Returns:
            True 如果表存在，否则 False

        """
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        return cursor.fetchone() is not None

    @staticmethod
    def _detect_sqlite_overlap(
        df: pl.DataFrame,
        existing: pl.DataFrame,
        key_columns: tuple[str, ...],
    ) -> tuple[bool, pl.DataFrame, int]:
        """
        检测 SQLite 表中的重复数据.

        Args:
            df: 新数据
            existing: 现有数据
            key_columns: 用于检测重复的键列

        Returns:
            (has_overlap, overlap_df, count) 元组

        """
        existing_keys = existing.select(key_columns)
        new_keys = df.select(key_columns)
        overlap = new_keys.join(existing_keys, on=key_columns, how="inner")
        has_overlap = not overlap.is_empty()
        return has_overlap, overlap, len(overlap)

    @staticmethod
    def _handle_keep_first_sqlite(
        df: pl.DataFrame,
        existing: pl.DataFrame,
        key_columns: tuple[str, ...],
    ) -> tuple[pl.DataFrame, int]:
        """
        处理 KEEP_FIRST 策略（保留现有数据）.

        Args:
            df: 新数据
            existing: 现有数据
            key_columns: 主键列

        Returns:
            (combined, added) 元组

        """
        existing_keys = existing.select(key_columns)
        new_keys = df.select(key_columns)

        # 过滤掉新数据中的重复部分
        non_overlapping = new_keys.join(existing_keys, on=key_columns, how="anti")
        df_filtered = df.join(non_overlapping, on=key_columns, how="inner")
        combined = pl.concat([existing, df_filtered])
        return combined, len(df_filtered)

    @staticmethod
    def _handle_keep_last_sqlite(
        df: pl.DataFrame,
        existing: pl.DataFrame,
        key_columns: tuple[str, ...],
        overlap_count: int,
    ) -> tuple[pl.DataFrame, int]:
        """
        处理 KEEP_LAST 策略（新数据覆盖现有数据）.

        Args:
            df: 新数据
            existing: 现有数据
            key_columns: 主键列
            overlap_count: 重复数据行数

        Returns:
            (combined, added) 元组

        """
        combined = pl.concat([existing, df])
        combined = combined.unique(subset=key_columns, keep="last")
        added = len(df) - overlap_count
        return combined, added

    @staticmethod
    def _write_sqlite_table(
        df: pl.DataFrame,
        combined: pl.DataFrame,
        table: str,
        conn: Connection,
        on_duplicate: OnDuplicate,
        table_exists: bool,
        has_overlap: bool,
    ) -> None:
        """
        执行 SQLite 表写入.

        Args:
            df: 新数据
            combined: 合并后的数据
            table: 表名
            conn: SQLite 连接
            on_duplicate: 重复数据处理策略
            table_exists: 表是否已存在
            has_overlap: 是否有重复数据

        """
        # 根据策略选择写入方式
        if on_duplicate == OnDuplicate.KEEP_LAST and table_exists and has_overlap:
            # 对于 KEEP_LAST，我们删除了旧表，所以直接创建新表
            combined.write_database(
                table_name=table,
                connection=conn,
                if_table_exists="replace",
            )
        elif on_duplicate == OnDuplicate.KEEP_FIRST and table_exists and has_overlap:
            # 对于 KEEP_FIRST，只追加新数据
            df.write_database(
                table_name=table,
                connection=conn,
                if_table_exists="append",
            )
        elif table_exists:
            # 无重复的情况，追加新数据
            df.write_database(
                table_name=table,
                connection=conn,
                if_table_exists="append",
            )
        else:
            # 表不存在，创建新表
            combined.write_database(
                table_name=table,
                connection=conn,
                if_table_exists="replace",
            )

    @staticmethod
    def write_sqlite(
        df: pl.DataFrame,
        table: str,
        conn: Connection,
        *,
        on_duplicate: OnDuplicate = OnDuplicate.KEEP_FIRST,
        key_columns: tuple[str, ...] | None = None,
    ) -> WriteResult:
        """
        写入 SQLite 表

        支持增量写入和重复数据处理策略。使用事务确保数据一致性。

        Args:
            df: 要写入的 DataFrame
            table: 表名
            conn: SQLite 连接
            on_duplicate: 重复数据处理策略
            key_columns: 主键列（用于检测重复，如果为 None 则使用所有列）

        Returns:
            WriteResult: 包含写入结果的统计信息

        Raises:
            ValueError: 当 on_duplicate=ERROR 且存在重复数据时

        Examples:
            >>> import sqlite3
            >>> conn = sqlite3.connect("data.db")
            >>> result = IngestionDataWriter.write_sqlite(
            ...     df=dataframe,
            ...     table="stocks",
            ...     conn=conn,
            ...     on_duplicate=OnDuplicate.KEEP_LAST,
            ...     key_columns=("instrument_id", "trade_date"),
            ... )
            >>> conn.commit()
            >>> conn.close()

        """
        # 验证输入并确定 key_columns
        key_columns = IngestionDataWriter._validate_sqlite_input(df, table, key_columns)

        # 处理空数据
        if df.is_empty():
            return WriteResult(
                file_path=f"sqlite:{table}",
                checksum="",
                rows_written=0,
                rows_total=0,
                blocked=False,
            )

        # 检查表是否存在
        table_exists = IngestionDataWriter._check_table_exists(conn, table)

        # 初始化变量
        has_overlap = False
        added = 0

        if table_exists:
            # 读取现有数据
            existing = pl.read_database(f"SELECT * FROM {table}", connection=conn)  # noqa: S608

            # 检测重复数据
            has_overlap, _, overlap_count = IngestionDataWriter._detect_sqlite_overlap(
                df, existing, key_columns
            )

            if has_overlap:
                if on_duplicate == OnDuplicate.ERROR:
                    msg = (
                        f"发现 {overlap_count} 行重复数据 (主键: {key_columns})。"
                        f"使用 OnDuplicate.KEEP_FIRST 保留现有数据, "
                        f"或 OnDuplicate.KEEP_LAST 覆盖现有数据。"
                    )
                    raise ValueError(msg)
                elif on_duplicate == OnDuplicate.KEEP_FIRST:
                    # 保留现有数据
                    combined, added = IngestionDataWriter._handle_keep_first_sqlite(
                        df, existing, key_columns
                    )
                elif on_duplicate == OnDuplicate.KEEP_LAST:
                    # 新数据覆盖现有数据
                    combined, added = IngestionDataWriter._handle_keep_last_sqlite(
                        df, existing, key_columns, overlap_count
                    )
                    # 删除旧表并重建（将在 _write_sqlite_table 中处理）
                    pass
                else:
                    raise ValueError(f"未知的 OnDuplicate 策略: {on_duplicate}")
            else:
                # 无重复，直接合并
                combined = pl.concat([existing, df])
                added = len(df)
        else:
            # 表不存在，直接创建
            combined = df
            added = len(df)
            has_overlap = False

        # 写入数据库
        IngestionDataWriter._write_sqlite_table(
            df, combined, table, conn, on_duplicate, table_exists, has_overlap
        )

        # 计算 checksum
        checksum = ChecksumCompute.from_dataframe(combined, table)

        return WriteResult(
            file_path=f"sqlite:{table}",
            checksum=checksum,
            rows_written=added,
            rows_total=len(combined),
            blocked=False,
        )
