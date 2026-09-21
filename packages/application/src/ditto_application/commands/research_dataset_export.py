"""Explicit research dataset export (safe publication follows in #254)."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import polars as pl
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.research.specs import DatasetSnapshot

from ditto_application.exceptions import AppQueryError

_VALID_TABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _sanitize_table_name(dataset_id: str) -> str:
    """
    Convert dataset_id to a safe SQLite table name.

    Replaces ``-`` with ``_`` and validates the result matches
    a legal SQL identifier pattern.  Raises ``ValueError`` for
    identifiers that could enable SQL injection.
    """
    table_name = dataset_id.replace("-", "_")
    if not _VALID_TABLE_NAME.match(table_name):
        raise AppQueryError(f"Invalid dataset_id for table name: {dataset_id!r}")
    return table_name


class ResearchDatasetExport:
    """Export an existing research snapshot without rebuilding it."""

    def __init__(self, *, research_artifact_service: ResearchArtifactService) -> None:
        self._artifact_service = research_artifact_service

    def export(
        self,
        snapshot: DatasetSnapshot,
        fmt: str,
        path: Path,
    ) -> None:
        """
        导出研究数据集快照到指定格式.

        Args:
            snapshot: 数据集快照.
            fmt: 导出格式 ("csv", "sqlite").
            path: 输出文件路径.

        Raises:
            ValueError: 不支持的格式.

        """
        df = self._artifact_service.read_parquet(snapshot.data_path)
        if fmt == "csv":
            df.write_csv(str(path))
        elif fmt == "sqlite":
            self._export_sqlite(df, snapshot.dataset_id, path)
        else:
            raise AppQueryError(f"不支持的导出格式: {fmt}")

    @staticmethod
    def _export_sqlite(
        df: pl.DataFrame,
        dataset_id: str,
        path: Path,
    ) -> None:
        """将 DataFrame 导出为 SQLite 表."""
        table_name = _sanitize_table_name(dataset_id)
        conn = sqlite3.connect(str(path))
        records = df.to_dicts()
        if records:
            columns = list(records[0].keys())
            col_str = ",".join(columns)
            placeholders = ",".join(["?"] * len(columns))
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {table_name} ({col_str})",
            )
            conn.executemany(
                f"INSERT INTO {table_name} VALUES ({placeholders})",
                [tuple(r.values()) for r in records],
            )
            conn.commit()
        conn.close()
