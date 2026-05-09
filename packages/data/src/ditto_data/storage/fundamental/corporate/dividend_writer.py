"""Dividend writer for CQRS pattern."""

from ditto_platform.foundation import SQLiteClient

from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec
from ditto_data.storage.base.sqlite_table_writer import SqliteTableWriter


class DividendWriter(SqliteTableWriter):
    """Writer for dividend data."""

    def __init__(self, spec: SqliteTableSpec, client: SQLiteClient) -> None:
        super().__init__(spec, client)
