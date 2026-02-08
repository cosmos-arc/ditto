"""
IndexWeightStore for index constituent weight tracking with PIT support.

This module provides storage and retrieval for index constituent weights
with Point-in-Time support for tracking changes over time.

Migrated from stores/index_weight_store.py to domains/market/index/weight/
"""

from __future__ import annotations

from typing import Any

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class IndexWeightStore:
    """
    Index constituent weight storage with PIT support.

    Core functionality:
    - upsert_weights: Insert/update weight records for an index
    - get_constituents: Query constituents with PIT support
    - get_constituents_sids: Get constituent SIDs as list
    - remove_constituent: Remove constituent (sets effective_to)
    """

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """
        Initialize IndexWeightStore.

        Args:
            sqlite_client: SQLite client for database operations.

        """
        self._client = sqlite_client
        logger.debug(
            "IndexWeightStore initialized",
            event="index_weight_store_init_complete",
        )

    @traced("store.index_weight.upsert")
    def upsert_weights(
        self,
        index_id: str,
        records: list[dict[str, Any]],
    ) -> int:
        """
        Batch insert/update index constituent weights.

        Args:
            index_id: Index identifier (e.g., '000300.SH')
            records: List of constituent records. Each record should contain:
                - instrument_id: Security ID (required)
                - effective_from: Effective start date (required)
                - effective_to: Effective end date (optional)
                - weight: Constituent weight (optional)

        Returns:
            Number of records upserted.

        """
        logger.info(
            "Upserting index weights",
            event="index_weight_upsert_start",
            index_id=index_id,
            record_count=len(records),
        )

        # Prepare records for batch upsert
        params_list: list[list[Any] | tuple[Any, ...]] = []
        for record in records:
            params = (
                index_id,
                record.get("instrument_id"),
                record.get("effective_from"),
                record.get("effective_to"),
                record.get("weight"),
            )
            params_list.append(params)

        self._client.executemany(
            """INSERT INTO index_weight
            (index_id, instrument_id, effective_from, effective_to, weight)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(index_id, instrument_id, effective_from) DO UPDATE SET
                weight = excluded.weight,
                effective_to = excluded.effective_to
            """,
            params_list,
        )
        self._client.commit()

        logger.info(
            "Index weights upserted successfully",
            event="index_weight_upsert_complete",
            index_id=index_id,
            count=len(records),
        )
        M.data_records.add(len(records), {"dataset": "index_weight"})

        return len(records)

    def get_constituents(
        self,
        index_id: str,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        Get constituents for an index (PIT-safe).

        Args:
            index_id: Index identifier.
            asof: Point-in-time date. If None, returns current constituents.

        Returns:
            DataFrame with constituent data.

        """
        if asof:
            # PIT query: get constituents effective as of the given date
            rows = self._client.fetchall(
                """SELECT * FROM index_weight
                WHERE index_id = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY instrument_id
                """,
                [index_id, asof, asof],
            )
        else:
            # Current query: only active constituents
            rows = self._client.fetchall(
                """SELECT * FROM index_weight
                WHERE index_id = ? AND effective_to IS NULL
                ORDER BY instrument_id
                """,
                [index_id],
            )

        if not rows:
            return pl.DataFrame()

        return pl.DataFrame([dict(r) for r in rows])

    def get_constituents_sids(
        self,
        index_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        Get constituent SIDs as a list.

        Args:
            index_id: Index identifier.
            asof: Point-in-time date. If None, returns current SIDs.

        Returns:
            List of security IDs.

        """
        if asof:
            rows = self._client.fetchall(
                """SELECT instrument_id FROM index_weight
                WHERE index_id = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY instrument_id
                """,
                [index_id, asof, asof],
            )
        else:
            rows = self._client.fetchall(
                """SELECT instrument_id FROM index_weight
                WHERE index_id = ? AND effective_to IS NULL
                ORDER BY instrument_id
                """,
                [index_id],
            )

        return [int(r["instrument_id"]) for r in rows]

    @traced("store.index_weight.remove_constituent")
    def remove_constituent(
        self,
        index_id: str,
        instrument_id: int,
        effective_date: str,
    ) -> None:
        """
        Remove a constituent by setting effective_to date.

        Args:
            index_id: Index identifier.
            instrument_id: Security ID to remove.
            effective_date: Date when constituent becomes ineffective.

        """
        logger.info(
            "Removing constituent from index",
            event="index_weight_remove_constituent_start",
            index_id=index_id,
            instrument_id=instrument_id,
            effective_date=effective_date,
        )

        # Update effective_to for active records
        self._client.execute(
            """UPDATE index_weight
            SET effective_to = ?
            WHERE index_id = ? AND instrument_id = ? AND effective_to IS NULL
            """,
            [effective_date, index_id, instrument_id],
        )
        self._client.commit()

        logger.info(
            "Constituent removed successfully",
            event="index_weight_remove_constituent_complete",
            index_id=index_id,
            instrument_id=instrument_id,
        )

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
