"""Index Repository for index data and constituents access."""

from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.index_weight_store import IndexWeightStore
from ditto_datahub.stores.security_store import SecurityStore

if TYPE_CHECKING:
    from ditto_datahub.runtime.sid_allocator import SidAllocator


class IndexRepository:
    """
    Index data repository.

    Provides domain-level interface for index data operations,
    coordinating BarsStore, IndexWeightStore, and SecurityStore.

    Core functionality:
    - get_bars: Query index daily bars (delegates to BarsStore)
    - get_constituents: Query index constituents (PIT support)
    - get_index_constituents_sids: Convenience method returning SIDs list
    - get_csi300_bars/get_csi300_constituents: Predefined CSI300 shortcuts
    - get_csi500_constituents: Predefined CSI500 shortcut
    """

    def __init__(
        self,
        bars_store: BarsStore,
        index_weight_store: IndexWeightStore,
        security_store: SecurityStore,
    ) -> None:
        """
        Initialize IndexRepository.

        Args:
            bars_store: Bars store for index daily data.
            index_weight_store: Index weight store for constituents.
            security_store: Security store for symbol resolution.

        """
        self._bars_store = bars_store
        self._index_weight_store = index_weight_store
        self._security_store = security_store

    @traced("repository.index.get_bars")
    def get_bars(
        self,
        sids: list[int] | None = None,
        symbols: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        Query index daily bars.

        Args:
            sids: Filter by SIDs.
            symbols: Filter by symbols (requires SID resolution).
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD).
            asof: Point-in-time query date for symbol resolution.

        Returns:
            Index bars DataFrame.

        Raises:
            ValueError: If both sids and symbols are None.

        """
        logger.debug(
            "Fetching index bars",
            event="index_get_bars_start",
            sids_count=len(sids) if sids else None,
            symbols_count=len(symbols) if symbols else None,
            start=start,
            end=end,
            asof=asof,
        )

        # Resolve symbols to SIDs if provided
        if symbols:
            resolved_sids: list[int] = []
            for symbol in symbols:
                sid = self._security_store.resolve_sid(symbol, "tushare", asof)
                if sid:
                    resolved_sids.append(sid)

            # If sids also provided, combine them
            query_sids = list(set(sids + resolved_sids)) if sids else resolved_sids
        elif sids:
            query_sids = sids
        else:
            raise ValueError("Either sids or symbols must be provided")

        # Query bars from store
        result: pl.DataFrame = self._bars_store.read(
            dataset="index_daily",
            sids=query_sids,
            start_date=start,
            end_date=end,
        )

        logger.debug(
            "Index bars fetched",
            event="index_get_bars_complete",
            row_count=len(result),
        )

        # Record metrics
        M.data_records.add(
            len(result), {"dataset": "index_daily", "operation": "get_bars"}
        )

        return result

    @traced("repository.index.get_constituents")
    def get_constituents(
        self,
        index_id: str,
        asof: str | None = None,
        with_symbol: bool = False,
        min_weight: float | None = None,
    ) -> pl.DataFrame:
        """
        Query index constituents.

        Args:
            index_id: Index identifier (e.g., '000300.SH').
            asof: Point-in-time date. If None, returns current constituents.
            with_symbol: If True, join with security table to get symbols.
            min_weight: Minimum weight threshold. If None, no filtering.

        Returns:
            Constituents DataFrame.

        """
        logger.debug(
            "Fetching index constituents",
            event="index_get_constituents_start",
            index_id=index_id,
            asof=asof,
            with_symbol=with_symbol,
            min_weight=min_weight,
        )

        # Get constituents from store
        constituents = self._index_weight_store.get_constituents(
            index_id=index_id,
            asof=asof,
        )

        # Filter by minimum weight if specified
        if (
            min_weight is not None
            and not constituents.is_empty()
            and "weight" in constituents.columns
        ):
            constituents = constituents.filter(pl.col("weight") >= min_weight)

        # Add symbol if requested
        if with_symbol and not constituents.is_empty():
            constituents = self._enrich_with_symbol(constituents)

        logger.debug(
            "Constituents fetched",
            event="index_get_constituents_complete",
            index_id=index_id,
            row_count=len(constituents),
        )

        # Record metrics
        M.data_records.add(
            len(constituents),
            {"dataset": "index_weight", "operation": "get_constituents"},
        )

        return constituents

    @traced("repository.index.get_constituents_sids")
    def get_index_constituents_sids(
        self,
        index_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        Get index constituent SIDs as a list.

        Args:
            index_id: Index identifier.
            asof: Point-in-time date. If None, returns current SIDs.

        Returns:
            List of security IDs.

        """
        logger.debug(
            "Fetching index constituent SIDs",
            event="index_get_constituents_sids_start",
            index_id=index_id,
            asof=asof,
        )

        sids = self._index_weight_store.get_constituents_sids(
            index_id=index_id,
            asof=asof,
        )

        logger.debug(
            "Constituent SIDs fetched",
            event="index_get_constituents_sids_complete",
            index_id=index_id,
            sid_count=len(sids),
        )

        return sids

    @traced("repository.index.get_csi300_bars")
    def get_csi300_bars(
        self,
        start: str | None = None,
        end: str | None = None,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        Get CSI 300 index daily bars (predefined shortcut).

        Args:
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD).
            asof: Point-in-time query date for symbol resolution.

        Returns:
            Index bars DataFrame.

        """
        logger.debug(
            "Fetching CSI 300 bars",
            event="index_get_csi300_bars_start",
            start=start,
            end=end,
            asof=asof,
        )

        # Resolve CSI 300 SID
        sid = self._security_store.resolve_sid("000300.SH", "tushare", asof)
        if not sid:
            logger.warning(
                "CSI 300 index SID not found",
                event="index_get_csi300_bars_complete",
                sid_count=0,
            )
            return pl.DataFrame()

        # Query bars
        result = self._bars_store.read(
            dataset="index_daily",
            sids=[sid],
            start_date=start,
            end_date=end,
        )

        logger.debug(
            "CSI 300 bars fetched",
            event="index_get_csi300_bars_complete",
            row_count=len(result),
        )

        return result

    @traced("repository.index.get_csi300_constituents")
    def get_csi300_constituents(self, asof: str | None = None) -> list[int]:
        """
        Get CSI 300 index constituents (predefined shortcut).

        Args:
            asof: Point-in-time date. If None, returns current constituents.

        Returns:
            List of security IDs.

        """
        logger.debug(
            "Fetching CSI 300 constituents",
            event="index_get_csi300_constituents_start",
            asof=asof,
        )

        sids = self._index_weight_store.get_constituents_sids(
            index_id="000300.SH",
            asof=asof,
        )

        logger.debug(
            "CSI 300 constituents fetched",
            event="index_get_csi300_constituents_complete",
            sid_count=len(sids),
        )

        return sids

    @traced("repository.index.get_csi500_constituents")
    def get_csi500_constituents(self, asof: str | None = None) -> list[int]:
        """
        Get CSI 500 index constituents (predefined shortcut).

        Args:
            asof: Point-in-time date. If None, returns current constituents.

        Returns:
            List of security IDs.

        """
        logger.debug(
            "Fetching CSI 500 constituents",
            event="index_get_csi500_constituents_start",
            asof=asof,
        )

        sids = self._index_weight_store.get_constituents_sids(
            index_id="000905.SH",
            asof=asof,
        )

        logger.debug(
            "CSI 500 constituents fetched",
            event="index_get_csi500_constituents_complete",
            sid_count=len(sids),
        )

        return sids

    def _enrich_with_symbol(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Enrich constituents DataFrame with symbol.

        This method joins the constituents DataFrame with the security table
        to add the symbol column.

        Args:
            df: Constituents DataFrame with sid column.

        Returns:
            DataFrame with symbol column added.

        """
        # Get SIDs from the DataFrame
        sids = df["sid"].to_list()
        if not sids:
            return df

        # Query security symbols for the SIDs
        securities = self._security_store.find_securities(
            sids=sids,
            src_codes=None,
            source="tushare",
            asset_class=None,
            exchange=None,
            is_active=None,
            asof=None,
        )

        if securities.is_empty():
            return df

        # Select only sid and symbol columns for join
        security_df = securities.select(["sid", "symbol"])

        # Join
        return df.join(security_df, on="sid", how="left")
