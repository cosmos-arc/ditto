"""PledgeRatio reader for CQRS pattern."""

from ditto_platform.foundation import SQLiteClient

from ditto_data.storage.base.sqlite_table_reader import SqliteTableReader
from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec


class PledgeRatioReader(SqliteTableReader):
    """Reader for pledge ratio data."""

    def __init__(self, spec: SqliteTableSpec, client: SQLiteClient) -> None:
        super().__init__(spec, client)
