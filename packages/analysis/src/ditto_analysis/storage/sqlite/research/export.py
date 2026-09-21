"""Single-snapshot SQLite export with explicit schema and transaction."""

import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl

from ditto_analysis.errors import ResearchDatasetError


def _identifier(value: str) -> str:
    if not value or "\x00" in value:
        raise ResearchDatasetError("SQLite export requires nonempty identifiers")
    return '"' + value.replace('"', '""') + '"'


def _column_type(dtype: pl.DataType) -> str:
    if dtype.is_integer() or dtype == pl.Boolean:
        return "INTEGER"
    if dtype.is_float():
        return "REAL"
    if dtype == pl.Binary:
        return "BLOB"
    if (
        isinstance(dtype, (pl.String, pl.Null, pl.Categorical, pl.Enum))
        or dtype.is_temporal()
        or dtype.is_decimal()
    ):
        return "TEXT"
    raise ResearchDatasetError(f"Unsupported SQLite export type: {dtype}")


def sqlite_dataset_bytes(frame: pl.DataFrame, table_name: str) -> bytes:
    """Commit a standalone temporary database before returning publishable bytes."""
    table = _identifier(table_name)
    columns = ", ".join(
        f"{_identifier(name)} {_column_type(dtype)}"
        for name, dtype in frame.schema.items()
    )
    if not columns:
        raise ResearchDatasetError("SQLite export requires at least one column")
    for name, dtype in frame.schema.items():
        if dtype.is_float() and frame[name].is_nan().any():
            raise ResearchDatasetError(
                "SQLite export cannot represent NaN without data loss"
            )
    frame = frame.with_columns(
        pl.col(name).cast(pl.String)
        for name, dtype in frame.schema.items()
        if dtype.is_temporal() or dtype.is_decimal()
    )
    placeholders = ", ".join("?" for _ in frame.columns)
    with TemporaryDirectory(prefix="ditto-research-export-") as directory:
        path = Path(directory) / "dataset.sqlite"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("BEGIN")
            connection.execute(f"CREATE TABLE {table} ({columns})")
            connection.executemany(
                f"INSERT INTO {table} VALUES ({placeholders})",
                frame.iter_rows(),
            )
        return path.read_bytes()
