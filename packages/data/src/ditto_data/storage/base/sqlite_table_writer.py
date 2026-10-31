"""SqliteTableWriter — generic SQLite table writer parameterized by SqliteTableSpec."""

from __future__ import annotations

from typing import cast

import polars as pl
from ditto_platform.foundation import Metrics, SQLiteClient, logger
from ditto_platform.foundation.storage.types import OnDuplicate

from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec


class SqliteTableWriter:
    """通用 SQLite 表写入器，通过 spec 参数化表结构和写入逻辑。"""

    def __init__(self, spec: SqliteTableSpec, client: SQLiteClient) -> None:
        self._spec = spec
        self._client = client

    def write(
        self, df: pl.DataFrame, on_duplicate: OnDuplicate = OnDuplicate.KEEP_FIRST
    ) -> int:
        """
        写入数据，失败时自动回滚。

        KEEP_FIRST（默认）= 冲突行忽略；KEEP_LAST = 同主键后写覆盖
        （#625：force 重取的值修正在 SQLite 通路同样收敛，与 parquet
        族写入语义一致）。其余策略（ERROR/VERIFY_IDENTICAL/FLAGGED）
        在 SQLite 通路未实现，响亮失败而非静默降级。
        """
        all_cols = self._spec.all_columns
        col_names = ", ".join(all_cols)
        placeholders = ", ".join("?" for _ in all_cols)
        if on_duplicate in (OnDuplicate.KEEP_FIRST, OnDuplicate.VERIFY_IDENTICAL):
            # VERIFY_IDENTICAL 在 SQLite 通路退化为冲突忽略（#625 留档）：
            # 同内容重写为天然幂等；值变更重写仅经 force→KEEP_LAST 通道
            # 覆盖，非 force 重写在 skip 决策层已被拦截。
            conflict_clause = "ON CONFLICT DO NOTHING"
        elif on_duplicate is OnDuplicate.KEEP_LAST:
            if not self._spec.conflict_columns:
                raise ValueError(
                    f"KEEP_LAST upsert requires spec.conflict_columns on table "
                    f"'{self._spec.table}'"
                )
            update_cols = [
                col for col in all_cols if col not in self._spec.conflict_columns
            ]
            assignments = ", ".join(f"{col} = excluded.{col}" for col in update_cols)
            conflict_clause = (
                f"ON CONFLICT({', '.join(self._spec.conflict_columns)}) "
                f"DO UPDATE SET {assignments}"
            )
        else:
            raise ValueError(
                f"OnDuplicate.{on_duplicate.value} not supported by "
                f"SqliteTableWriter ('{self._spec.table}')"
            )
        sql = (
            f"INSERT INTO {self._spec.table} ({col_names}) "  # noqa: S608
            f"VALUES ({placeholders}) "
            f"{conflict_clause}"
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
