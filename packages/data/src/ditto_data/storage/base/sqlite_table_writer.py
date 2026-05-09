"""SqliteTableWriter — generic SQLite table writer parameterized by SqliteTableSpec."""

from __future__ import annotations

from typing import cast

import polars as pl
from ditto_platform.foundation import Metrics, SQLiteClient, logger

from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec


class SqliteTableWriter:
    """通用 SQLite 表写入器，通过 spec 参数化表结构和写入逻辑。"""

    def __init__(self, spec: SqliteTableSpec, client: SQLiteClient) -> None:
        self._spec = spec
        self._client = client

    def write(self, df: pl.DataFrame) -> int:
        """写入数据，失败时自动回滚。"""
        all_cols = self._spec.all_columns
        col_names = ", ".join(all_cols)
        placeholders = ", ".join("?" for _ in all_cols)
        sql = (
            f"INSERT INTO {self._spec.table} ({col_names}) "  # noqa: S608
            f"VALUES ({placeholders}) "
            f"ON CONFLICT DO NOTHING"
        )

        logger.info(
            "Starting SQLite table write", table=self._spec.table, record_count=len(df)
        )

        try:
            missing_cols = [
                col
                for col in self._spec.columns
                if col not in self._spec.nullable_columns and col not in df.columns
            ]
            if missing_cols:
                msg = (
                    f"Missing required columns for table '{self._spec.table}': "
                    + f"{missing_cols}. Columns: {list(df.columns)}"
                )
                raise ValueError(msg)
            records = df.to_dicts()
            rows = [
                tuple(
                    r.get(col) if col in self._spec.nullable_columns else r[col]
                    for col in all_cols
                )
                for r in records
            ]
            self._client.executemany(
                sql, cast(list[list[object] | tuple[object, ...]], rows)
            )
            self._client.commit()

            logger.info(
                "SQLite table write completed",
                table=self._spec.table,
                record_count=len(records),
            )
            Metrics.data_records.add(
                len(records), {"dataset": self._spec.table, "status": "success"}
            )
            return len(records)

        except Exception as e:
            self._client.rollback()
            logger.error(
                "SQLite table write failed", table=self._spec.table, error=str(e)
            )
            Metrics.data_records.add(
                len(df), {"dataset": self._spec.table, "status": "failed"}
            )
            raise
