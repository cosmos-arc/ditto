"""Margin trading reader for CQRS pattern."""

from ditto_platform.foundation.storage.sqlite_client import SQLiteClient

from ditto_data.storage.base.sqlite_table_reader import SqliteTableReader
from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec


class MarginTradingReader(SqliteTableReader):
    """Reader for margin trading data."""

    def __init__(self, spec: SqliteTableSpec, client: SQLiteClient) -> None:
        super().__init__(spec, client)
