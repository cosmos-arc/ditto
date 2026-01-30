"""Index Accessor for index data and constituents access."""

from __future__ import annotations

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.domains.metadata.instrument import InstrumentStore
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.index_weight_store import IndexWeightStore


class IndexAccessor:
    """
    Index data accessor.

    Provides domain-level interface for index data operations,
    coordinating BarsStore, IndexWeightStore, and InstrumentStore.

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
        instrument_store: InstrumentStore,
    ) -> None:
        """
        Initialize IndexAccessor.

        Args:
            bars_store: Bars store for index daily data.
            index_weight_store: Index weight store for constituents.
            instrument_store: Instrument store for symbol resolution.

        """
        self._bars_store = bars_store
        self._index_weight_store = index_weight_store
        self._instrument_store = instrument_store

    @traced("accessor.index.get_bars")
    def get_bars(
        self,
        sids: list[int] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> pl.DataFrame:
        """
        Query index daily bars.

        注意: 只接受 sids 参数，不再接受 symbols。
        请使用 DataHub 的便捷方法进行标识符转换。

        Args:
            sids: Filter by SIDs.
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD).

        Returns:
            Index bars DataFrame.

        Raises:
            ValueError: If sids is None.

        """
        if not sids:
            raise ValueError("sids must be provided")

        logger.debug(
            "Fetching index bars",
            event="index_get_bars_start",
            sids_count=len(sids),
            start=start,
            end=end,
        )

        # Query bars from store
        result: pl.DataFrame = self._bars_store.read(
            dataset="index_daily",
            sids=sids,
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

    @traced("accessor.index.get_constituents")
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
            constituents = self._instrument_store.enrich_with_symbol(constituents)

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

    @traced("accessor.index.get_constituents_sids")
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

    @traced("accessor.index.get_csi300_bars")
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
        sid = self._instrument_store.resolve_sid("000300.SH", "tushare", asof)
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

    @traced("accessor.index.get_csi300_constituents")
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

    @traced("accessor.index.get_csi500_constituents")
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
