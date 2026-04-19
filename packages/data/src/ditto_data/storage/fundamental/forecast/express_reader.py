"""Express reader for CQRS pattern."""

from ditto_data.storage.base.sqlite_table_reader import SqliteTableReader
from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec
from ditto_data.storage.sqlite_client import SQLiteClient


class ExpressReader(SqliteTableReader):
    """Reader for express forecast data."""

    def __init__(self, spec: SqliteTableSpec, client: SQLiteClient) -> None:
        super().__init__(spec, client)
