"""BalanceSheet writer for CQRS pattern."""

from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec
from ditto_data.storage.base.sqlite_table_writer import SqliteTableWriter
from ditto_data.storage.sqlite_client import SQLiteClient


class BalanceSheetWriter(SqliteTableWriter):
    """Writer for balance sheet data."""

    def __init__(self, spec: SqliteTableSpec, client: SQLiteClient) -> None:
        super().__init__(spec, client)
