"""Dividend reader for CQRS pattern."""

from datetime import date

import polars as pl
from ditto_platform.foundation import SQLiteClient

from ditto_data.storage.base.sqlite_table_reader import SqliteTableReader
from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec


class DividendReader(SqliteTableReader):
    """Reader for dividend data."""

    def __init__(self, spec: SqliteTableSpec, client: SQLiteClient) -> None:
        super().__init__(spec, client)

    def get(self, id_value: int | str, as_of_date: date) -> pl.DataFrame:
        """Keep supplementary issuer facts behind their own publication cutoff."""
        return _visible_tax_evidence(super().get(id_value, as_of_date), as_of_date)

    def get_range(
        self,
        id_value: int | str,
        start_date: date | None = None,
        end_date: date | None = None,
        as_of_date: date | None = None,
    ) -> pl.DataFrame:
        """Apply the same issuer cutoff to public range queries."""
        return _visible_tax_evidence(
            super().get_range(id_value, start_date, end_date, as_of_date), as_of_date
        )


def _visible_tax_evidence(frame: pl.DataFrame, cutoff: date | None) -> pl.DataFrame:
    if cutoff is None or frame.is_empty():
        return frame
    return frame.filter(
        pl.col("share_tax_basis").is_null()
        | (pl.col("share_tax_knowledge_date").cast(pl.Date) <= cutoff)
    )
