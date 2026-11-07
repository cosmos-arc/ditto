"""Margin trading reader for CQRS pattern."""

from pathlib import Path

import polars as pl
from ditto_platform.foundation import SQLiteClient

from ditto_data.storage.base.sqlite_table_reader import SqliteTableReader
from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec
from ditto_data.storage.capital.version_eligibility import eligible_versions


class MarginTradingReader(SqliteTableReader):
    """Reader for margin trading data."""

    def __init__(
        self, spec: SqliteTableSpec, client: SQLiteClient, data_root: Path
    ) -> None:
        super().__init__(spec, client)
        self._data_root = data_root

    def _finalize(self, df: pl.DataFrame, *, pit: bool) -> pl.DataFrame:
        return super()._finalize(
            eligible_versions(df, self._data_root, "margin_trading"), pit=True
        )
