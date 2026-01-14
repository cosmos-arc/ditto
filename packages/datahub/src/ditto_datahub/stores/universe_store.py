"""
UniverseStore for security universe management with PIT support.

This module provides storage and retrieval for security universes
with Point-in-Time support for constituent tracking.

Following design document at docs/design/02_data_design.md
"""

from __future__ import annotations

from typing import Any

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.sqlite_client import SQLiteClient


class UniverseStore:
    """
    Security universe storage with PIT support.

    Core functionality:
    - create_universe: Create a new universe definition
    - add_constituents: Add constituents to a universe
    - get_constituents: Query constituents with PIT support
    - remove_constituent: Remove constituent (sets effective_to)
    """

    def __init__(self, sqlite_client: SQLiteClient) -> None:
        """
        Initialize UniverseStore.

        Args:
            sqlite_client: SQLite client for database operations.

        """
        self._client = sqlite_client
        logger.debug(
            "UniverseStore initialized",
            event="universe_store_init_complete",
        )

    @property
    def client(self) -> SQLiteClient:
        """Get the SQLite client."""
        return self._client

    @traced("data.universe_create")
    def create_universe(
        self,
        universe_id: str,
        name: str,
        description: str | None = None,
        universe_type: str = "custom",
        source_ref: str | None = None,
    ) -> None:
        """
        Create a new universe.

        Args:
            universe_id: Unique identifier for the universe.
            name: Universe display name.
            description: Optional description.
            universe_type: Type of universe (custom, index, sector, etc.).
            source_ref: Optional external reference (e.g., index code).

        Raises:
            sqlite3.IntegrityError: If universe_id already exists.

        """
        logger.info(
            "Creating universe",
            event="universe_create_start",
            universe_id=universe_id,
            name=name,
            universe_type=universe_type,
            source_ref=source_ref,
        )

        self._client.execute(
            """INSERT INTO universe
            (universe_id, name, description, universe_type, source_ref)
            VALUES (?, ?, ?, ?, ?)""",
            [universe_id, name, description, universe_type, source_ref],
        )
        self._client.commit()

        logger.info(
            "Universe created successfully",
            event="universe_create_complete",
            universe_id=universe_id,
        )
        M.data_records.add(1, {"dataset": "universe", "status": "created"})

    def get_universe(self, universe_id: str) -> dict[str, Any] | None:
        """
        Get universe by ID.

        Args:
            universe_id: Universe identifier.

        Returns:
            Dictionary with universe data or None if not found.

        """
        row = self._client.fetchone(
            "SELECT * FROM universe WHERE universe_id = ?",
            [universe_id],
        )
        return row

    def list_universes(self, universe_type: str | None = None) -> pl.DataFrame:
        """
        List all universes.

        Args:
            universe_type: Optional filter by universe type.

        Returns:
            DataFrame with universe data.

        """
        sql = "SELECT * FROM universe"
        params: list[Any] = []

        if universe_type:
            sql += " WHERE universe_type = ?"
            params.append(universe_type)

        rows = self._client.fetchall(sql, params)

        if not rows:
            return pl.DataFrame()

        return pl.DataFrame([dict(r) for r in rows])

    @traced("data.universe_add_constituents")
    def add_constituents(
        self,
        universe_id: str,
        records: list[dict[str, Any]],
    ) -> int:
        """
        Add constituents to a universe.

        Args:
            universe_id: Universe identifier.
            records: List of constituent records. Each record should contain:
                - sid: Security ID (required)
                - effective_from: Effective start date (required)
                - effective_to: Effective end date (optional)
                - weight: Constituent weight (optional, default 1.0)
                - source: Data source (optional)
                - src_code: Source code (optional)

        Returns:
            Number of records added.

        """
        logger.info(
            "Adding constituents to universe",
            event="universe_add_constituents_start",
            universe_id=universe_id,
            record_count=len(records),
        )

        # Prepare records for batch insert
        params_list: list[list[Any] | tuple[Any, ...]] = []
        for record in records:
            params = (
                universe_id,
                record.get("sid"),
                record.get("effective_from"),
                record.get("effective_to"),
                record.get("weight", 1.0),
                record.get("source"),
                record.get("src_code"),
            )
            params_list.append(params)

        self._client.executemany(
            """INSERT INTO universe_constituent
            (universe_id, sid, effective_from, effective_to, weight, source, src_code)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            params_list,
        )
        self._client.commit()

        logger.info(
            "Constituents added successfully",
            event="universe_add_constituents_complete",
            universe_id=universe_id,
            count=len(records),
        )
        M.data_records.add(len(records), {"dataset": "universe_constituent"})

        return len(records)

    def get_constituents(
        self,
        universe_id: str,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        Get constituents for a universe (PIT-safe).

        Args:
            universe_id: Universe identifier.
            asof: Point-in-time date. If None, returns current constituents.

        Returns:
            DataFrame with constituent data.

        """
        if asof:
            # PIT query: get constituents effective as of the given date
            rows = self._client.fetchall(
                """SELECT * FROM universe_constituent
                WHERE universe_id = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY sid""",
                [universe_id, asof, asof],
            )
        else:
            # Current query: only active constituents
            rows = self._client.fetchall(
                """SELECT * FROM universe_constituent
                WHERE universe_id = ? AND effective_to IS NULL
                ORDER BY sid""",
                [universe_id],
            )

        if not rows:
            return pl.DataFrame()

        return pl.DataFrame([dict(r) for r in rows])

    def get_constituents_sids(
        self,
        universe_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        Get constituent SIDs as a list.

        Args:
            universe_id: Universe identifier.
            asof: Point-in-time date. If None, returns current SIDs.

        Returns:
            List of security IDs.

        """
        if asof:
            rows = self._client.fetchall(
                """SELECT sid FROM universe_constituent
                WHERE universe_id = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY sid""",
                [universe_id, asof, asof],
            )
        else:
            rows = self._client.fetchall(
                """SELECT sid FROM universe_constituent
                WHERE universe_id = ? AND effective_to IS NULL
                ORDER BY sid""",
                [universe_id],
            )

        return [int(r["sid"]) for r in rows]

    @traced("data.universe_remove_constituent")
    def remove_constituent(
        self,
        universe_id: str,
        sid: int,
        effective_date: str,
    ) -> None:
        """
        Remove a constituent by setting effective_to date.

        Args:
            universe_id: Universe identifier.
            sid: Security ID to remove.
            effective_date: Date when constituent becomes ineffective.

        """
        logger.info(
            "Removing constituent from universe",
            event="universe_remove_constituent_start",
            universe_id=universe_id,
            sid=sid,
            effective_date=effective_date,
        )

        # Update effective_to for active records
        self._client.execute(
            """UPDATE universe_constituent
            SET effective_to = ?
            WHERE universe_id = ? AND sid = ? AND effective_to IS NULL""",
            [effective_date, universe_id, sid],
        )
        self._client.commit()

        logger.info(
            "Constituent removed successfully",
            event="universe_remove_constituent_complete",
            universe_id=universe_id,
            sid=sid,
        )

    def close(self) -> None:
        """Close the underlying SQLite client."""
        self._client.close()
