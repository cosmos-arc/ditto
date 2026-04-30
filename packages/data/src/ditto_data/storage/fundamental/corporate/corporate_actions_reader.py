"""CorporateActions reader for CQRS pattern."""

from datetime import date

import polars as pl
from ditto_platform.foundation import logger, traced

from ditto_data.storage.base.sqlite_table_reader import SqliteTableReader
from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec
from ditto_data.storage.sqlite_client import SQLiteClient


class CorporateActionsReader(SqliteTableReader):
    """Reader for corporate actions data."""

    def __init__(self, spec: SqliteTableSpec, client: SQLiteClient) -> None:
        super().__init__(spec, client)

    @traced("data.corporate_actions_query")
    def query(
        self,
        id_value: int | str,
        start_date: date | None = None,
        end_date: date | None = None,
        as_of_date: date | None = None,
    ) -> pl.DataFrame:
        """Query corporate actions with optional filters."""
        logger.debug(
            "Querying corporate actions",
            instrument_id=id_value,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
        )
        return self.get_range(id_value, start_date, end_date, as_of_date)
