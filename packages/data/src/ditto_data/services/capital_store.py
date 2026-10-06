"""Capital domain store with dedicated query/write methods."""

from __future__ import annotations

from datetime import date

import polars as pl
from ditto_platform.foundation import OnDuplicate, logger

from ditto_data.services.deps import CapitalReaders, CapitalWriters


class CapitalStore:
    """
    Capital domain unified store.

    Thin wrapper around Reader/Writer components with dependency injection.
    Delegates all operations to the underlying readers and writers.
    """

    def __init__(
        self,
        read_ports: CapitalReaders,
        write_ports: CapitalWriters,
    ) -> None:
        """
        Initialize CapitalStore.

        Args:
            read_ports: Capital domain read ports (all readers).
            write_ports: Capital domain write ports (all writers).

        """
        self._read_ports = read_ports
        self._write_ports = write_ports

        logger.debug(
            "CapitalStore initialized",
            event="capital_store_init_complete",
        )

    # Query methods (get_*)

    def get_margin_trading(self, instrument_id: int, as_of_date: date) -> pl.DataFrame:
        """
        Query margin trading data for an instrument.

        Args:
            instrument_id: The instrument ID to query.
            as_of_date: The point-in-time query date.

        Returns:
            DataFrame with margin trading data.

        """
        return self._read_ports.margin_trading.get(instrument_id, as_of_date)

    def get_pledge_ratio(self, instrument_id: int, as_of_date: date) -> pl.DataFrame:
        """
        Query pledge ratio data for an instrument.

        Args:
            instrument_id: The instrument ID to query.
            as_of_date: The point-in-time query date.

        Returns:
            DataFrame with pledge ratio data.

        """
        return self._read_ports.pledge_ratio.get(instrument_id, as_of_date)

    def get_valuation_metrics(
        self, instrument_id: int, as_of_date: date
    ) -> pl.DataFrame:
        """
        Query valuation metrics data for an instrument.

        Args:
            instrument_id: The instrument ID to query.
            as_of_date: The point-in-time query date.

        Returns:
            DataFrame with valuation metrics data.

        """
        return self._read_ports.valuation_metrics.get(instrument_id, as_of_date)

    def get_index_composition(self, index_id: str, as_of_date: date) -> pl.DataFrame:
        """
        Query index composition data for an index.

        Args:
            index_id: The index ID to query.
            as_of_date: The point-in-time query date.

        Returns:
            DataFrame with index composition data.

        """
        return self._read_ports.index_composition.get(index_id, as_of_date)

    # Write methods (save_*)

    def save_margin_trading(self, df: pl.DataFrame) -> int:
        """
        Save margin trading data.

        Args:
            df: DataFrame with margin trading data to save.

        Returns:
            Number of records written.

        """
        return self._write_ports.margin_trading.write(df)

    def save_pledge_ratio(self, df: pl.DataFrame) -> int:
        """
        Save pledge ratio data.

        Args:
            df: DataFrame with pledge ratio data to save.

        Returns:
            Number of records written.

        """
        return self._write_ports.pledge_ratio.write(df)

    def save_valuation_metrics(self, df: pl.DataFrame) -> int:
        """
        Save valuation metrics data.

        Args:
            df: DataFrame with valuation metrics data to save.

        Returns:
            Number of records written.

        """
        return self._write_ports.valuation_metrics.write(df)

    def save_index_composition(self, df: pl.DataFrame) -> int:
        """
        Save index composition data.

        Args:
            df: DataFrame with index composition data to save.

        Returns:
            Number of records written.

        """
        return self._write_ports.index_composition.write(df)

    def save_index_valuation(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save index daily valuation rows (market cap in 元, shares in 股)."""
        writer = self._write_ports.index_valuation
        if writer is None:
            raise ValueError("index_valuation writer not configured")
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_index_weight(self, df: pl.DataFrame) -> int:
        """Save canonical effective-dated index weights."""
        return self._write_ports.index_composition.write(df)

    # ── #518/#519/#520/#523 日频资金面/席位/北向/筹码（parquet 追加观察）──

    def save_moneyflow(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save moneyflow rows（金额万元/量手）."""
        writer = self._write_ports.moneyflow
        if writer is None:
            raise ValueError("moneyflow writer not configured")
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_cyq_perf(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save daily chip performance rows（价格元/winner_rate %）."""
        writer = self._write_ports.cyq_perf
        if writer is None:
            raise ValueError("cyq_perf writer not configured")
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_hk_hold(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save northbound holding rows（vol 股/ratio %）."""
        writer = self._write_ports.hk_hold
        if writer is None:
            raise ValueError("hk_hold writer not configured")
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_hsgt_top10(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save HSGT top-10 rows（金额元；改制后买/卖/净为 null）."""
        writer = self._write_ports.hsgt_top10
        if writer is None:
            raise ValueError("hsgt_top10 writer not configured")
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_top_list(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save dragon-tiger stock rows（金额元，reason 进主键）."""
        writer = self._write_ports.top_list
        if writer is None:
            raise ValueError("top_list writer not configured")
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def save_top_inst(
        self,
        df: pl.DataFrame,
        year: int,
        on_duplicate: OnDuplicate = OnDuplicate.ERROR,
    ) -> int:
        """Save dragon-tiger seat rows（金额元，exalter+side 进主键）."""
        writer = self._write_ports.top_inst
        if writer is None:
            raise ValueError("top_inst writer not configured")
        result = writer.write(df, year, on_duplicate=on_duplicate)
        return result.added + result.updated

    def get_moneyflows(self, start: str, end: str) -> pl.DataFrame:
        """Read market-wide moneyflow rows（L3 巡检用）."""
        reader = self._read_ports.moneyflow
        if reader is None:
            raise ValueError("moneyflow reader not configured")
        return reader.read(start_date=start, end_date=end)

    def get_cyq_perfs(self, start: str, end: str) -> pl.DataFrame:
        """Read market-wide chip performance rows（L3 巡检用）."""
        reader = self._read_ports.cyq_perf
        if reader is None:
            raise ValueError("cyq_perf reader not configured")
        return reader.read(start_date=start, end_date=end)
