"""Effective-dated index composition writer for CQRS pattern."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_platform.foundation import SQLiteClient

from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec
from ditto_data.storage.base.sqlite_table_writer import SqliteTableWriter


class IndexCompositionWriter(SqliteTableWriter):
    """Write complete index snapshots while maintaining non-overlapping intervals."""

    def __init__(self, spec: SqliteTableSpec, client: SQLiteClient) -> None:
        super().__init__(spec, client)

    def write(self, df: pl.DataFrame) -> int:
        """Close adjacent snapshots and persist the incoming effective intervals."""
        if df.is_empty():
            return super().write(df)

        prepared, snapshot_dates = self._prepare_intervals(df)
        try:
            for index_id, effective_from in snapshot_dates:
                self._client.execute(
                    """UPDATE index_weight
                    SET effective_to = ?
                    WHERE index_id = ?
                      AND effective_from < ?
                      AND (effective_to IS NULL OR effective_to > ?)""",
                    [effective_from, index_id, effective_from, effective_from],
                )
        except Exception:
            self._client.rollback()
            raise
        return super().write(prepared)

    def _prepare_intervals(
        self,
        df: pl.DataFrame,
    ) -> tuple[pl.DataFrame, tuple[tuple[str, date], ...]]:
        required = {"index_id", "instrument_id", "effective_from", "weight"}
        missing = required - set(df.columns)
        if missing:
            msg = f"index_weight missing required columns: {sorted(missing)}"
            raise ValueError(msg)

        normalized = df.with_columns(
            pl.col("effective_from").cast(pl.Date),
            (
                pl.col("effective_to").cast(pl.Date)
                if "effective_to" in df.columns
                else pl.lit(None, dtype=pl.Date).alias("effective_to")
            ),
        )
        snapshot_dates = tuple(
            sorted(
                {
                    (str(row["index_id"]), _as_date(row["effective_from"]))
                    for row in normalized.select(
                        "index_id", "effective_from"
                    ).to_dicts()
                }
            )
        )
        incoming_by_index: dict[str, tuple[date, ...]] = {}
        for index_id, _ in snapshot_dates:
            incoming_by_index[index_id] = tuple(
                snapshot_date
                for candidate_id, snapshot_date in snapshot_dates
                if candidate_id == index_id
            )

        next_dates: dict[tuple[str, date], date | None] = {}
        for index_id, effective_from in snapshot_dates:
            candidates = [
                candidate
                for candidate in incoming_by_index[index_id]
                if candidate > effective_from
            ]
            persisted = self._client.fetchone(
                """SELECT MIN(effective_from) AS next_effective_from
                FROM index_weight
                WHERE index_id = ? AND effective_from > ?""",
                [index_id, effective_from],
            )
            if persisted is not None and persisted["next_effective_from"] is not None:
                candidates.append(_as_date(persisted["next_effective_from"]))
            next_dates[(index_id, effective_from)] = min(candidates, default=None)

        records = normalized.to_dicts()
        for record in records:
            key = (str(record["index_id"]), _as_date(record["effective_from"]))
            next_date = next_dates[key]
            current_end = record["effective_to"]
            if next_date is not None and (
                current_end is None or next_date < _as_date(current_end)
            ):
                record["effective_to"] = next_date
        return pl.from_dicts(records, schema=normalized.schema), snapshot_dates


def _as_date(value: object) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise ValueError(f"Expected ISO date, got {value!r}")
