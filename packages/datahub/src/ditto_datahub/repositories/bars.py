"""Bars Repository for market data access."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal, cast

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.types import SidRange

if TYPE_CHECKING:
    from ditto_datahub.runtime.dq_checker import DQChecker
    from ditto_datahub.runtime.file_lock import FileLockManager


class AdjType(Enum):
    """Adjustment type for price data."""

    NONE = "none"  # No adjustment
    QFQ = "qfq"  # Forward adjustment (前复权)
    HFQ = "hfq"  # Backward adjustment (后复权)


@dataclass(frozen=True)
class WriteResult:
    """Result of writing bars data."""

    file_path: str
    checksum: str
    rows_written: int
    rows_total: int
    failed_checks: list[Any] = field(default_factory=list)


class BarsRepository:
    """
    Market data repository for OHLCV bars.

    Provides domain-level interface for bars data operations,
    coordinating multiple stores for data access, adjustment,
    and identifier resolution.
    """

    def __init__(
        self,
        bars_store: BarsStore,
        adj_factor_store: AdjFactorStore,
        security_store: SecurityStore,
        dq_checker: DQChecker,
        file_lock: FileLockManager,
    ) -> None:
        """
        Initialize BarsRepository.

        Args:
            bars_store: Bars data store.
            adj_factor_store: Adjustment factor store.
            security_store: Security store for identifier resolution.
            dq_checker: Data quality checker.
            file_lock: File lock manager for concurrent writes.

        """
        self._bars_store = bars_store
        self._adj_factor_store = adj_factor_store
        self._security_store = security_store
        self._dq_checker = dq_checker
        self._file_lock = file_lock

    @traced("repository.bars.get")
    def get(
        self,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,
        symbols: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        adj: AdjType = AdjType.NONE,
        asof: str | None = None,
        asset_class: Literal["stock", "etf"] | None = None,
        with_symbol: bool = False,
    ) -> pl.DataFrame:
        """
        Get bars data.

        Args:
            sids: Filter by SIDs.
            src_codes: Filter by source codes.
            symbols: Filter by symbols.
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD).
            adj: Adjustment type.
            asof: Point-in-time date for identifier resolution.
            asset_class: Asset class filter.
            with_symbol: Add symbol column to result.

        Returns:
            Bars data DataFrame.

        """
        logger.debug(
            "Fetching bars data",
            event="bars_get_start",
            start=start,
            end=end,
            adj=adj.value,
        )

        # 1. Resolve identifiers to SIDs
        resolved_sids = self._resolve_sids(sids, src_codes, symbols, asof)

        if not resolved_sids:
            return pl.DataFrame()

        # 2. Determine dataset
        dataset = self._determine_dataset(asset_class, resolved_sids)

        # 3. Read raw data
        df = self._bars_store.read(
            dataset=dataset,
            sids=resolved_sids,
            start_date=start,
            end_date=end,
        )

        if df.is_empty():
            return pl.DataFrame()

        # 4. Apply adjustment if needed
        if adj != AdjType.NONE:
            df = self._apply_adj(df, resolved_sids, adj, start, end)

        # 5. Add symbol column if requested
        if with_symbol:
            df = self._security_store.enrich_with_symbol(df)

        logger.debug(
            "Bars data fetched",
            event="bars_get_complete",
            row_count=len(df),
            adj=adj.value,
        )

        # Record metrics
        M.data_records.add(
            len(df), {"dataset": "bars", "operation": "get", "adj": adj.value}
        )

        return df

    def get_single(
        self,
        identifier: str,
        start: str,
        end: str,
        source: str = "tushare",
        adj: AdjType = AdjType.NONE,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        Get bars data for a single security.

        Args:
            identifier: Source code or symbol.
            start: Start date (YYYY-MM-DD).
            end: End date (YYYY-MM-DD).
            source: Data source identifier.
            adj: Adjustment type.
            asof: Point-in-time date.

        Returns:
            Bars data DataFrame.

        """
        # Resolve identifier (try src_code first, then symbol)
        sid = self._security_store.resolve_sid(identifier, source, asof)
        if not sid:
            # Try as symbol
            sids = self._security_store.resolve_by_symbol(identifier, source)
            if not sids:
                return pl.DataFrame()
            sid = sids[0]

        # Get data
        return self.get(
            sids=[sid],
            start=start,
            end=end,
            adj=adj,
            with_symbol=True,
        )

    @traced("repository.bars.write")
    def write(
        self,
        df: pl.DataFrame,
        year: int,
        dataset: str = "stock_daily",
        source: str = "tushare",
        run_dq_check: bool = True,
    ) -> WriteResult:
        """
        Write bars data.

        Args:
            df: Bars data DataFrame.
            year: Year partition for storage.
            dataset: Dataset name.
            source: Data source identifier.
            run_dq_check: Whether to run data quality checks.

        Returns:
            Write result with file path and checksum.

        """
        logger.info(
            "Writing bars data",
            event="bars_write_start",
            dataset=dataset,
            year=year,
            row_count=len(df),
        )

        # Use file lock for concurrent safety
        lock_name = f"bars_write_{dataset}_{year}"
        with self._file_lock.acquire(lock_name, timeout=60.0):
            # Data quality check
            failed_checks = []
            if run_dq_check:
                check_result = self._dq_checker.check(df, dataset)
                failed_checks = [r for r in check_result.results if not r.passed]

                # Log failures
                for check in failed_checks:
                    logger.warning(
                        "Data quality check failed",
                        event="bars_dq_check_failed",
                        dataset=dataset,
                        rule=check.rule_name,
                        affected_rows=check.affected_rows,
                    )

            # Write data
            file_path, checksum = self._bars_store.write(dataset, df, year)

            # Get total rows after write
            total_rows = len(
                self._bars_store.read(
                    dataset=dataset,
                    sids=None,
                    start_date=f"{year}-01-01",
                    end_date=f"{year}-12-31",
                )
            )

            logger.info(
                "Bars data written",
                event="bars_write_complete",
                dataset=dataset,
                year=year,
                file_path=file_path,
                checksum=checksum,
                rows_written=len(df),
                rows_total=total_rows,
            )

            # Record metrics
            M.data_records.add(len(df), {"dataset": "bars", "operation": "write"})

            return WriteResult(
                file_path=file_path,
                checksum=checksum,
                rows_written=len(df),
                rows_total=total_rows,
                failed_checks=failed_checks,
            )

    def _resolve_sids(
        self,
        sids: list[int] | None,
        src_codes: list[str] | None,
        symbols: list[str] | None,
        asof: str | None,
        source: str = "tushare",
    ) -> list[int]:
        """Resolve identifiers to SID list."""
        resolved = set()

        if sids:
            resolved.update(sids)

        if src_codes:
            mapping = self._security_store.resolve_sids_batch(src_codes, source, asof)
            resolved.update(mapping.values())

        if symbols:
            for symbol in symbols:
                sids_from_symbol = self._security_store.resolve_by_symbol(
                    symbol, source
                )
                resolved.update(sids_from_symbol)

        return sorted(resolved)

    def _determine_dataset(
        self,
        asset_class: Literal["stock", "etf"] | None,
        sids: list[int],
    ) -> str:
        """Determine dataset name from asset class or SIDs."""
        if asset_class:
            return f"{asset_class}_daily"

        # Check for mixed asset classes
        stock_range = SidRange.get_range("stock")
        etf_range = SidRange.get_range("etf")

        has_stock = any(
            stock_range.min_sid <= sid <= stock_range.max_sid for sid in sids
        )
        has_etf = any(etf_range.min_sid <= sid <= etf_range.max_sid for sid in sids)

        if has_stock and has_etf:
            raise ValueError(
                "Mixed asset class query detected. SIDs contain both stock and ETF. "
                "Please query each asset class separately."
            )

        if has_stock:
            return "stock_daily"
        if has_etf:
            return "etf_daily"

        return "stock_daily"  # Default

    def _apply_adj(
        self,
        df: pl.DataFrame,
        sids: list[int],
        adj: AdjType,
        start: str | None,
        end: str | None,
    ) -> pl.DataFrame:
        """Apply price adjustment."""
        # Read adjustment factors
        adj_df = self._adj_factor_store.read(
            dataset="adj_factor",
            sids=sids,
            start_date=start,
            end_date=end,
        )

        if adj_df.is_empty():
            logger.warning(
                "No adjustment factor data available",
                event="bars_adj_not_available",
                adj_type=adj.value,
            )
            return df

        # Ensure sorting for correct last() aggregation (defensive programming)
        adj_df = adj_df.sort(["sid", "trade_date"])

        # Join adjustment factors
        df = df.join(
            adj_df.select(["sid", "trade_date", "adj_factor"]),
            on=["sid", "trade_date"],
            how="left",
        )

        if adj == AdjType.QFQ:
            # Forward adjustment: use latest factor
            latest_factors = adj_df.group_by("sid").agg(
                pl.col("adj_factor").last().alias("latest_factor")
            )
            df = df.join(latest_factors, on="sid", how="left")
            # Use coalesce(adj_factor, 1.0) for missing values (returns original price)
            df = df.with_columns(
                [
                    (
                        pl.col("open")
                        * pl.coalesce("latest_factor", 1.0)
                        / pl.coalesce("adj_factor", 1.0)
                    ).alias("open"),
                    (
                        pl.col("high")
                        * pl.coalesce("latest_factor", 1.0)
                        / pl.coalesce("adj_factor", 1.0)
                    ).alias("high"),
                    (
                        pl.col("low")
                        * pl.coalesce("latest_factor", 1.0)
                        / pl.coalesce("adj_factor", 1.0)
                    ).alias("low"),
                    (
                        pl.col("close")
                        * pl.coalesce("latest_factor", 1.0)
                        / pl.coalesce("adj_factor", 1.0)
                    ).alias("close"),
                ]
            )
            df = df.drop(["adj_factor", "latest_factor"])

        else:  # HFQ
            # Backward adjustment: use current factor
            # Use coalesce(adj_factor, 1.0) for missing values (returns original price)
            df = df.with_columns(
                [
                    (pl.col("open") * pl.coalesce("adj_factor", 1.0)).alias("open"),
                    (pl.col("high") * pl.coalesce("adj_factor", 1.0)).alias("high"),
                    (pl.col("low") * pl.coalesce("adj_factor", 1.0)).alias("low"),
                    (pl.col("close") * pl.coalesce("adj_factor", 1.0)).alias("close"),
                ]
            )
            df = df.drop("adj_factor")

        return df
