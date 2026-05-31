"""SQLiteStore implementation for SQLite database storage."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import polars as pl
from ditto_platform.foundation import (
    Metrics,
    OnDuplicate,
    SQLitePool,
    WriteStoreResult,
    file_md5,
    logger,
    traced,
)

from ditto_data.storage.base.sqlite_helpers import prepare_for_write
from ditto_data.storage.base.sqlite_merge import insert_dataframe, merge_data


class SQLiteStore:
    """SQLite 数据库存储实现，支持 SQL 查询/执行、DataFrame 读写、去重策略."""

    def __init__(self, db_path: Path) -> None:
        self._data_root = db_path.parent
        self._db_path = db_path
        self._pool = SQLitePool(str(db_path))
        logger.debug(
            "SQLite store initialized",
            event="store_init_complete",
            db_path=str(db_path),
        )

    @property
    def data_root(self) -> Path:
        """获取数据根目录路径."""
        return self._data_root

    @property
    def db_path(self) -> Path:
        """获取数据库文件路径."""
        return self._db_path

    # ============ Connection operations ============

    def _get_connection(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接."""
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
        """读取数据，支持按 instrument_ids / start_date / end_date 过滤."""
        conditions: list[str] = []
        params: list[Any] = []

        if instrument_ids:
            placeholders = ",".join("?" * len(instrument_ids))
            conditions.append(f"instrument_id IN ({placeholders})")
            params.extend(instrument_ids)

        if start_date is not None:
            conditions.append("trade_date >= ?")
            params.append(start_date)

        if end_date is not None:
            conditions.append("trade_date <= ?")
            params.append(end_date)

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"SELECT * FROM {dataset}{where_clause}"  # noqa: S608 - dataset 是受控的表名

        rows = self.fetchall(sql, params)
        if not rows:
            return pl.DataFrame()

        df = pl.DataFrame(rows)
        if "trade_date" in df.columns and df["trade_date"].dtype == pl.String:
            df = df.with_columns(pl.col("trade_date").str.strptime(pl.Date, "%Y-%m-%d"))

        Metrics.data_records.add(len(df))
        return df

    # ============ Write operation ============

    @traced("data.write")
    def write(
        self,
        dataset: str,
        data: object,
        on_duplicate: str = "error",
        **kwargs: object,
    ) -> WriteStoreResult:
        """写入数据（pl.DataFrame），委托给 write_dataframe."""
        if not isinstance(data, pl.DataFrame):
            msg = "data must be a polars DataFrame"
            raise ValueError(msg)

        if len(data) == 0:
            return self._empty_result()

        return self.write_dataframe(dataset, data, on_duplicate)

    def write_dataframe(
        self,
        table: str,
        df: pl.DataFrame,
        on_duplicate: str = "error",
    ) -> WriteStoreResult:
        """写入 DataFrame 到表，支持 error/keep_first/keep_last 去重策略."""
        if len(df) == 0:
            return self._empty_result()

        df = prepare_for_write(df)
        strategy = OnDuplicate(on_duplicate)

        added = 0
        updated = 0
        existing_count = self._count_rows(table)
        is_merge = existing_count > 0

        if is_merge:
            existing_df = self._read_table(table)
            df, added, updated = merge_data(df, existing_df, strategy)
        else:
            df = df.unique(subset=["instrument_id", "trade_date"], keep="first")
            added = len(df)
            updated = 0

        insert_dataframe(table, df, strategy, self.executemany, self.commit)

        checksum = file_md5(self._db_path) if self._db_path.exists() else ""

        logger.info(
            "Data write completed",
            event="data_write_complete",
            table=table,
            row_count=len(df),
            is_merge=is_merge,
            db_path=str(self._db_path),
            checksum=checksum,
        )

        return WriteStoreResult(
            file_path=str(self._db_path),
            checksum=checksum,
            added=added,
            updated=updated,
            skipped=0,
            is_merge=is_merge,
        )

    def _read_table(self, table: str) -> pl.DataFrame:
        """读取整个表."""
        rows = self.fetchall(f"SELECT * FROM {table}")  # noqa: S608 - table 是受控的表名
        if not rows:
            return pl.DataFrame()
        return pl.DataFrame(rows)

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
        """删除数据，支持按 instrument_ids / 日期范围过滤，返回删除行数."""
        conditions: list[str] = []
        params: list[Any] = []

        if instrument_ids:
            placeholders = ",".join("?" * len(instrument_ids))
            conditions.append(f"instrument_id IN ({placeholders})")
            params.extend(instrument_ids)

        if start_date is not None and end_date is not None:
            conditions.append("trade_date >= ? AND trade_date <= ?")
            params.extend([start_date, end_date])
        elif start_date is not None:
            conditions.append("trade_date >= ?")
            params.append(start_date)
        elif end_date is not None:
            conditions.append("trade_date <= ?")
            params.append(end_date)

        where_clause = f" WHERE {' AND '.join(conditions)}" if conditions else ""

        before_count = self._count_rows(dataset)
        self.execute(f"DELETE FROM {dataset}{where_clause}", params)  # noqa: S608 - dataset 是受控的表名
        self.commit()
        deleted_count = before_count - self._count_rows(dataset)

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
        """执行 SQL 语句."""
        conn = self._get_connection()
        if params:
            return conn.execute(sql, params)
        return conn.execute(sql)

    def executemany(
        self,
        sql: str,
        params_list: Sequence[Sequence[Any] | tuple[Any, ...]],
    ) -> sqlite3.Cursor:
        """批量执行 SQL 语句."""
        conn = self._get_connection()
        return conn.executemany(sql, params_list)

    def fetchone(
        self,
        sql: str,
        params: Sequence[Any] | tuple[Any, ...] | None = None,
    ) -> dict[str, Any] | None:
        """查询单行记录，返回 dict 或 None."""
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row, strict=True))
        return None

    def fetchall(
        self,
        sql: str,
        params: Sequence[Any] | tuple[Any, ...] | None = None,
    ) -> list[dict[str, Any]]:
        """查询所有记录，返回 dict 列表."""
        cursor = self.execute(sql, params)
        rows = cursor.fetchall()
        if not rows:
            return []
        columns = [desc[0] for desc in cursor.description]
        result = [dict(zip(columns, row, strict=True)) for row in rows]
        logger.debug(
            "Query completed", event="sql_query_complete", row_count=len(result)
        )
        return result

    def commit(self) -> None:
        """提交事务."""
        conn = self._get_connection()
        conn.commit()

    def _count_rows(self, table: str) -> int:
        """统计表的行数."""
        result = self.fetchone(f"SELECT COUNT(*) as count FROM {table}")  # noqa: S608 - table 是受控的表名
        if result is None:
            return 0
        return cast(int, result["count"])

    def _empty_result(self) -> WriteStoreResult:
        """构造空写入结果（携带当前 db_path）."""
        return WriteStoreResult(
            file_path=str(self._db_path),
            checksum="",
            added=0,
            updated=0,
            skipped=0,
            is_merge=False,
        )
