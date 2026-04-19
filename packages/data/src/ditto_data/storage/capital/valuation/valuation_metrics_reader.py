"""ValuationMetrics reader for CQRS pattern."""

from ditto_data.storage.base.sqlite_table_reader import SqliteTableReader
from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec
from ditto_data.storage.sqlite_client import SQLiteClient


class ValuationMetricsReader(SqliteTableReader):
    """Reader for valuation metrics data."""

    def __init__(self, spec: SqliteTableSpec, client: SQLiteClient) -> None:
        super().__init__(spec, client)
