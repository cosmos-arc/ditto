"""
Universe Accessor for security universe management.

This module provides the domain-level interface for universe operations,
coordinating UniverseStore and SidAllocator.
"""

from __future__ import annotations

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.domains.metadata.instrument import InstrumentStore
from ditto_datahub.runtime.sid_allocator import SidAllocator
from ditto_datahub.stores.universe_store import UniverseStore


class UniverseAccessor:
    """
    Security universe accessor.

    Provides domain-level interface for universe data operations,
    coordinating UniverseStore and SidAllocator.

    Core functionality:
    - create: Create a new universe
    - get_constituents: Query constituents with optional symbol join
    - add_constituents: Batch add constituents with weights
    - list_universes: List all universes
    - get_csi300/get_csi500: Predefined universe shortcuts
    """

    def __init__(
        self,
        universe_store: UniverseStore,
        instrument_store: InstrumentStore,
        sid_allocator: SidAllocator,
    ) -> None:
        """
        Initialize UniverseAccessor.

        Args:
            universe_store: Universe store for data access.
            instrument_store: Instrument store for symbol enrichment.
            sid_allocator: SID allocator (not currently used but kept for future).

        """
        self._universe_store = universe_store
        self._instrument_store = instrument_store
        self._sid_allocator = sid_allocator

    @traced("accessor.universe.create")
    def create(
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

        self._universe_store.create_universe(
            universe_id=universe_id,
            name=name,
            description=description,
            universe_type=universe_type,
            source_ref=source_ref,
        )

        logger.info(
            "Universe created successfully",
            event="universe_create_complete",
            universe_id=universe_id,
        )

        # Record metrics
        M.data_records.add(1, {"dataset": "universe", "operation": "create"})

    @traced("accessor.universe.get_constituents")
    def get_constituents(
        self,
        universe_id: str,
        asof: str | None = None,
        with_symbol: bool = False,
    ) -> pl.DataFrame:
        """
        Get constituents for a universe.

        Args:
            universe_id: Universe identifier.
            asof: Point-in-time date. If None, returns current constituents.
            with_symbol: If True, join with security table to get symbols.

        Returns:
            DataFrame with constituent data.

        """
        logger.debug(
            "Fetching universe constituents",
            event="universe_get_constituents_start",
            universe_id=universe_id,
            asof=asof,
            with_symbol=with_symbol,
        )

        # Get constituents from store
        constituents = self._universe_store.get_constituents(
            universe_id=universe_id,
            asof=asof,
        )

        # Add symbol if requested
        if with_symbol and not constituents.is_empty():
            constituents = self._instrument_store.enrich_with_symbol(constituents)

        logger.debug(
            "Constituents fetched",
            event="universe_get_constituents_complete",
            universe_id=universe_id,
            row_count=len(constituents),
        )

        # Record metrics
        M.data_records.add(
            len(constituents), {"dataset": "universe_constituent", "operation": "get"}
        )

        return constituents

    @traced("accessor.universe.add_constituents")
    def add_constituents(
        self,
        universe_id: str,
        sids: list[int],
        effective_date: str,
        weights: list[float] | None = None,
    ) -> int:
        """
        Add constituents to a universe.

        Args:
            universe_id: Universe identifier.
            sids: List of security IDs to add.
            effective_date: Effective start date (YYYY-MM-DD).
            weights: Optional list of weights. If None, defaults to 1.0 for all.

        Returns:
            Number of constituents added.

        """
        logger.info(
            "Adding constituents to universe",
            event="universe_add_constituents_start",
            universe_id=universe_id,
            sid_count=len(sids),
            effective_date=effective_date,
        )

        # Prepare records with weights
        if weights is None:
            weights = [1.0] * len(sids)

        if len(weights) != len(sids):
            raise ValueError(
                f"Length mismatch: {len(sids)} SIDs but {len(weights)} weights"
            )

        records = [
            {
                "sid": sid,
                "effective_from": effective_date,
                "weight": weight,
            }
            for sid, weight in zip(sids, weights, strict=False)
        ]

        count = self._universe_store.add_constituents(universe_id, records)

        logger.info(
            "Constituents added successfully",
            event="universe_add_constituents_complete",
            universe_id=universe_id,
            count=count,
        )

        # Record metrics
        M.data_records.add(
            count, {"dataset": "universe_constituent", "operation": "add"}
        )

        return count

    @traced("accessor.universe.list")
    def list_universes(
        self,
        universe_type: str | None = None,
    ) -> pl.DataFrame:
        """
        List all universes.

        Args:
            universe_type: Optional filter by universe type.

        Returns:
            DataFrame with universe data.

        """
        logger.debug(
            "Listing universes",
            event="universe_list_start",
            universe_type=universe_type,
        )

        result = self._universe_store.list_universes(universe_type=universe_type)

        logger.debug(
            "Universes listed",
            event="universe_list_complete",
            count=len(result),
        )

        return result

    @traced("accessor.universe.get_csi300")
    def get_csi300(self, asof: str | None = None) -> list[int]:
        """
        Get CSI 300 universe constituents (predefined shortcut).

        Args:
            asof: Point-in-time date. If None, returns current constituents.

        Returns:
            List of security IDs.

        """
        logger.debug(
            "Fetching CSI 300 universe",
            event="universe_get_csi300_start",
            asof=asof,
        )

        sids = self._universe_store.get_constituents_sids("csi300", asof=asof)

        logger.debug(
            "CSI 300 universe fetched",
            event="universe_get_csi300_complete",
            sid_count=len(sids),
        )

        return sids

    @traced("accessor.universe.get_csi500")
    def get_csi500(self, asof: str | None = None) -> list[int]:
        """
        Get CSI 500 universe constituents (predefined shortcut).

        Args:
            asof: Point-in-time date. If None, returns current constituents.

        Returns:
            List of security IDs.

        """
        logger.debug(
            "Fetching CSI 500 universe",
            event="universe_get_csi500_start",
            asof=asof,
        )

        sids = self._universe_store.get_constituents_sids("csi500", asof=asof)

        logger.debug(
            "CSI 500 universe fetched",
            event="universe_get_csi500_complete",
            sid_count=len(sids),
        )

        return sids
