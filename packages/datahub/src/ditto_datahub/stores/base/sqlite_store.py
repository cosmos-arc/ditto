"""SQLiteStore implementation for SQLite database storage."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import polars as pl
from ditto_foundation import M, SQLitePool, logger, traced
from ditto_foundation.util.io import file_md5

from ditto_datahub.models import OnDuplicate
from ditto_datahub.models.storage import WriteResultStore
from ditto_datahub.stores.base.base_store import BaseStore


class SQLiteStore(BaseStore):
    """
    SQLite 数据库存储实现.

    支持特性：
    - SQL 查询和执行
    - DataFrame 读写
    - 重复数据处理（error/keep_first/keep_last）
    - 日期范围查询
    - 自动提交事务

    Attributes:
        db_path: SQLite 数据库文件路径.
        data_root: 数据根目录路径（数据库文件的父目录）.

    """

    def __init__(self, db_path: Path) -> None:
        """
        初始化 SQLiteStore.

        Args:
            db_path: SQLite 数据库文件路径.

        """
        # 调用父类初始化，data_root 是数据库的父目录
        super().__init__(db_path.parent)
        self._db_path = Path(db_path)
        self._pool = SQLitePool(str(db_path))
        logger.debug(
            "SQLite store initialized",
            event="store_init_complete",
            db_path=str(db_path),
        )

    @property
    def db_path(self) -> Path:
        """获取数据库文件路径."""
        return self._db_path

    # ============ Connection operations ============

    def _get_connection(self) -> sqlite3.Connection:
        """
        获取当前线程的数据库连接.

        Returns:
            SQLite 连接对象.

        """
        return self._pool.get_connection()

    # ============ Read operation ============

    @traced("data.read")
    def read(
        self,
        dataset: str,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: object,
    ) -> pl.DataFrame:
        """
        读取数据.

        Args:
            dataset: 数据集名称（表名）.
            instrument_ids: 证券 ID 列表（可选）.
            start_date: 起始日期 (YYYY-MM-DD)（可选）.
            end_date: 结束日期 (YYYY-MM-DD)（可选）.
            **kwargs: 其他参数（忽略）.

        Returns:
            DataFrame 包含匹配的记录.

        """
        # 构建 SQL 查询
        conditions: list[str] = []
        params: list[Any] = []

        if instrument_ids:
            placeholders = ",".join("?" * len(instrument_ids))
            conditions.append(f"instrument_id IN ({placeholders})")
            params.extend(instrument_ids)

        if start_date:
            conditions.append("trade_date >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("trade_date <= ?")
            params.append(end_date)

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

        sql = f"SELECT * FROM {dataset}{where_clause}"  # noqa: S608 - dataset 是受控的表名

        # 执行查询
        rows = self.fetchall(sql, params)

        # 转换为 DataFrame
        if not rows:
            return pl.DataFrame()

        df = pl.DataFrame(rows)

        # 归一化日期列：将字符串转换为 Date
        if "trade_date" in df.columns and df["trade_date"].dtype == pl.String:
            df = df.with_columns(pl.col("trade_date").str.strptime(pl.Date, "%Y-%m-%d"))

        # 记录指标
        M.data_records.add(len(df))

        return df

    # ============ Write operation ============

    @traced("data.write")
    def write(
        self,
        dataset: str,
        data: object,
        on_duplicate: str = "error",
        **kwargs: object,
    ) -> WriteResultStore:
        """
        写入数据.

        Args:
            dataset: 数据集名称（表名）.
            data: 要写入的数据（pl.DataFrame）.
            on_duplicate: 重复数据处理策略 ("error"|"keep_first"|"keep_last").
            **kwargs: 其他参数（忽略）.

        Returns:
            写入结果统计.

        Raises:
            ValueError: 如果 data 不是 DataFrame.

        """
        if not isinstance(data, pl.DataFrame):
            msg = "data must be a polars DataFrame"
            raise ValueError(msg)

        df: pl.DataFrame = data

        # 空数据直接返回
        if len(df) == 0:
            return WriteResultStore(
                file_path=str(self._db_path),
                checksum="",
                added=0,
                updated=0,
                skipped=0,
                is_merge=False,
            )

        # 调用 write_dataframe
        return self.write_dataframe(dataset, df, on_duplicate)

    def write_dataframe(
        self,
        table: str,
        df: pl.DataFrame,
        on_duplicate: str = "error",
    ) -> WriteResultStore:
        """
        写入 DataFrame 到表.

        Args:
            table: 表名.
            df: 要写入的 DataFrame.
            on_duplicate: 重复数据处理策略 ("error"|"keep_first"|"keep_last").

        Returns:
            写入结果统计.

        Raises:
            ValueError: 如果 on_duplicate 策略无效.

        """
        # 空数据直接返回
        if len(df) == 0:
            return WriteResultStore(
                file_path=str(self._db_path),
                checksum="",
                added=0,
                updated=0,
                skipped=0,
                is_merge=False,
            )

        # 归一化日期列
        df = self._prepare_for_write(df)

        # 解析去重策略
        strategy = OnDuplicate(on_duplicate)

        # 统计信息
        added = 0
        updated = 0

        # 检查表是否存在记录
        existing_count = self._count_rows(table)
        is_merge = existing_count > 0

        if is_merge:
            # 读取现有数据
            existing_df = self._read_table(table)

            # 合并数据并获取统计信息
            df, added, updated = self._merge_data(df, existing_df, strategy)
        else:
            # 新表，只需去重 batch 内部重复
            df = df.unique(subset=["instrument_id", "trade_date"], keep="first")
            added = len(df)
            updated = 0

        # 写入数据库
        self._insert_dataframe(table, df, strategy)

        # 计算 checksum
        checksum = ""
        if self._db_path.exists():
            checksum = file_md5(self._db_path)

        logger.info(
            "Data write completed",
            event="data_write_complete",
            table=table,
            row_count=len(df),
            is_merge=is_merge,
            db_path=str(self._db_path),
            checksum=checksum,
        )

        return WriteResultStore(
            file_path=str(self._db_path),
            checksum=checksum,
            added=added,
            updated=updated,
            skipped=0,
            is_merge=is_merge,
        )

    def _read_table(self, table: str) -> pl.DataFrame:
        """
        读取整个表.

        Args:
            table: 表名.

        Returns:
            DataFrame 包含表的所有记录.

        """
        rows = self.fetchall(f"SELECT * FROM {table}")  # noqa: S608 - table 是受控的表名
        if not rows:
            return pl.DataFrame()
        return pl.DataFrame(rows)

    def _insert_dataframe(
        self,
        table: str,
        df: pl.DataFrame,
        on_duplicate: OnDuplicate,
    ) -> None:
        """
        插入 DataFrame 到表.

        Args:
            table: 表名.
            df: 要插入的 DataFrame.
            on_duplicate: 重复数据处理策略.

        Raises:
            ValueError: 如果 on_duplicate 策略无效.

        """
        # 获取列名
        columns = df.columns
        placeholders = ",".join(["?"] * len(columns))
        col_names = ",".join(f'"{col}"' for col in columns)

        # 根据策略选择 SQL 语句
        # table 是受控的表名，不需要参数化
        if on_duplicate == OnDuplicate.KEEP_LAST:
            # INSERT OR REPLACE：删除旧记录，插入新记录
            sql = (
                f'INSERT OR REPLACE INTO "{table}" ({col_names}) '  # noqa: S608
                f"VALUES ({placeholders})"
            )
        elif on_duplicate == OnDuplicate.KEEP_FIRST:
            # INSERT OR IGNORE：忽略重复记录
            sql = (
                f'INSERT OR IGNORE INTO "{table}" ({col_names}) '  # noqa: S608
                f"VALUES ({placeholders})"
            )
        elif on_duplicate == OnDuplicate.ERROR:
            # 直接 INSERT：遇到重复会报错
            sql = (
                f'INSERT INTO "{table}" ({col_names}) '  # noqa: S608
                f"VALUES ({placeholders})"
            )
        else:
            msg = f"Unknown OnDuplicate strategy: {on_duplicate}"
            raise ValueError(msg)

        # 转换 DataFrame 为元组列表
        rows = df.rows()

        # 批量插入
        self.executemany(sql, rows)

        # 提交事务
        self.commit()

    def _merge_data(
        self,
        new_df: pl.DataFrame,
        existing_df: pl.DataFrame,
        on_duplicate: OnDuplicate,
    ) -> tuple[pl.DataFrame, int, int]:
        """
        合并新数据与现有数据.

        Args:
            new_df: 新数据.
            existing_df: 现有数据.
            on_duplicate: 重复数据处理策略.

        Returns:
            (合并后的 DataFrame, 新增行数, 更新行数).

        Raises:
            ValueError: 如果 on_duplicate=ERROR 且存在重复数据.

        """
        key_columns = ["instrument_id", "trade_date"]

        # 检测重复数据
        existing_keys = existing_df.select(key_columns)
        new_keys = new_df.select(key_columns)

        # 找出重叠的键
        merged_keys = existing_keys.join(new_keys, on=key_columns, how="inner")
        overlap_count = len(merged_keys)

        added = 0
        updated = 0

        if not merged_keys.is_empty():
            # 存在重复数据
            if on_duplicate == OnDuplicate.ERROR:
                msg = (
                    f"Duplicate data: {overlap_count} overlapping key pairs. "
                    "Use on_duplicate='keep_first' to preserve, or "
                    "on_duplicate='keep_last' to overwrite."
                )
                raise ValueError(msg)
            elif on_duplicate == OnDuplicate.KEEP_FIRST:
                # 保留现有数据，过滤掉新数据中的重复部分
                non_overlapping = new_keys.join(
                    existing_keys, on=key_columns, how="anti"
                )
                new_df = new_df.join(non_overlapping, on=key_columns, how="inner")
                combined = pl.concat([existing_df, new_df])
                added = len(new_df)
                updated = 0
            elif on_duplicate == OnDuplicate.KEEP_LAST:
                # Last-Write-Wins: 新数据覆盖现有数据
                combined = pl.concat([existing_df, new_df])
                combined = combined.unique(subset=key_columns, keep="last")
                # 新增 = 新数据中去重后的行数
                # 更新 = 重叠的行数
                added = len(new_df) - overlap_count
                updated = overlap_count
            else:
                msg = f"Unknown OnDuplicate strategy: {on_duplicate}"
                raise ValueError(msg)
        else:
            # 无重复，直接合并
            combined = pl.concat([existing_df, new_df])
            added = len(new_df)
            updated = 0

        return combined, added, updated

    def _prepare_for_write(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        准备写入：归一化日期列并排序.

        Args:
            df: 输入 DataFrame.

        Returns:
            准备好的 DataFrame.

        """
        # 归一化日期列
        if "trade_date" in df.columns:
            if df["trade_date"].dtype == pl.Date:
                # 转换为字符串
                df = df.with_columns(
                    pl.col("trade_date").dt.strftime("%Y-%m-%d").alias("trade_date")
                )
            elif df["trade_date"].dtype != pl.String:
                df = df.with_columns(pl.col("trade_date").cast(pl.String))

        # 排序
        return df.sort(["instrument_id", "trade_date"])

    # ============ Delete operation ============

    @traced("data.delete")
    def delete(
        self,
        dataset: str,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: object,
    ) -> int:
        """
        删除数据.

        Args:
            dataset: 数据集名称（表名）.
            instrument_ids: 证券 ID 列表（可选）.
            start_date: 起始日期 (YYYY-MM-DD)（可选）.
            end_date: 结束日期 (YYYY-MM-DD)（可选）.
            **kwargs: 其他参数（忽略）.

        Returns:
            删除的记录数.

        """
        # 构建删除条件
        conditions: list[str] = []
        params: list[Any] = []

        if instrument_ids:
            placeholders = ",".join("?" * len(instrument_ids))
            conditions.append(f"instrument_id IN ({placeholders})")
            params.extend(instrument_ids)

        if start_date and end_date:
            conditions.append("trade_date >= ? AND trade_date <= ?")
            params.append(start_date)
            params.append(end_date)
        elif start_date:
            conditions.append("trade_date >= ?")
            params.append(start_date)
        elif end_date:
            conditions.append("trade_date <= ?")
            params.append(end_date)

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

        # 先统计删除前的行数
        before_count = self._count_rows(dataset)

        # 执行删除
        sql = f"DELETE FROM {dataset}{where_clause}"  # noqa: S608 - dataset 是受控的表名
        self.execute(sql, params)
        self.commit()

        # 统计删除后的行数
        after_count = self._count_rows(dataset)

        deleted_count = before_count - after_count

        logger.info(
            "Data delete completed",
            event="data_delete_complete",
            table=dataset,
            deleted_count=deleted_count,
        )

        return deleted_count

    # ============ SQL operations ============

    def execute(
        self,
        sql: str,
        params: Sequence[Any] | tuple[Any, ...] | None = None,
    ) -> sqlite3.Cursor:
        """
        执行 SQL 语句.

        Args:
            sql: SQL 语句.
            params: 参数列表（可选）.

        Returns:
            Cursor 对象.

        """
        conn = self._get_connection()
        if params:
            return conn.execute(sql, params)
        return conn.execute(sql)

    def executemany(
        self,
        sql: str,
        params_list: Sequence[Sequence[Any] | tuple[Any, ...]],
    ) -> sqlite3.Cursor:
        """
        批量执行 SQL 语句.

        Args:
            sql: SQL 语句.
            params_list: 参数列表.

        Returns:
            Cursor 对象.

        """
        conn = self._get_connection()
        return conn.executemany(sql, params_list)

    def fetchone(
        self,
        sql: str,
        params: Sequence[Any] | tuple[Any, ...] | None = None,
    ) -> dict[str, Any] | None:
        """
        查询单行记录.

        Args:
            sql: SQL 语句.
            params: 参数列表（可选）.

        Returns:
            记录字典，如果不存在则返回 None.

        """
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        if row:
            # 获取列名
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row, strict=True))
        return None

    def fetchall(
        self,
        sql: str,
        params: Sequence[Any] | tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        """
        查询所有记录.

        Args:
            sql: SQL 语句.
            params: 参数列表（可选）.

        Returns:
            记录字典列表.

        """
        cursor = self.execute(sql, params)
        rows = cursor.fetchall()
        if not rows:
            return []

        # 获取列名
        columns = [desc[0] for desc in cursor.description]

        # 转换为字典列表
        result = [dict(zip(columns, row, strict=True)) for row in rows]

        logger.debug(
            "Query completed",
            event="sql_query_complete",
            row_count=len(result),
        )

        return result

    def commit(self) -> None:
        """提交事务."""
        conn = self._get_connection()
        conn.commit()

    def _count_rows(self, table: str) -> int:
        """
        统计表的行数.

        Args:
            table: 表名.

        Returns:
            行数.

        """
        result = self.fetchone(f"SELECT COUNT(*) as count FROM {table}")  # noqa: S608 - table 是受控的表名
        if result is None:
            return 0
        return cast(int, result["count"])
