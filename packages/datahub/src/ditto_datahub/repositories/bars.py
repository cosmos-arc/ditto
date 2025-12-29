"""Bars Repository for market data access."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations
from typing import TYPE_CHECKING, Any, Literal, cast

import polars as pl
from ditto_foundation import M, logger, traced

from ditto_datahub.dq.models import DQIssue
from ditto_datahub.stores.adj_factor_store import AdjFactorStore
from ditto_datahub.stores.bars_store import BarsStore
from ditto_datahub.stores.security_store import SecurityStore
from ditto_datahub.types import DQResult, SidRange

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
    failed_checks: list[DQResult] = field(default_factory=list)
    blocked: bool = False
    dq_result: DQResult | None = None


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
            df = self._apply_adj(df, resolved_sids, adj, start, end, asof)

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

            # Warn if multiple SIDs match the same symbol
            if len(sids) > 1:
                logger.warning(
                    "Multiple SIDs found for symbol, using first match",
                    event="symbol_multiple_matches",
                    symbol=identifier,
                    sids=sids,
                    selected_sid=sids[0],
                    match_count=len(sids),
                )

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
            dq_result: DQResult | None = None
            blocked = False

            if run_dq_check:
                check_result = self._dq_checker.check(df, dataset)
                dq_result = check_result

                # Check for L1 errors (blocking)
                if check_result.has_errors:
                    logger.error(
                        "DQ check failed with L1 errors - blocking write",
                        event="bars_dq_blocked",
                        dataset=dataset,
                        error_count=check_result.error_count,
                    )

                    # Save failed data to quarantine
                    for issue in check_result.issues:
                        if issue.severity.value == "error":
                            self._save_to_quarantine(
                                df=filter_failed_rows(df, issue),
                                dataset=dataset,
                                rule_id=issue.rule_name,
                                severity="error",
                            )

                    blocked = True

                    # Record metrics
                    M.data_errors.add(
                        check_result.error_count,
                        {"dataset": dataset, "operation": "write_blocked"},
                    )

                    return WriteResult(
                        file_path="",
                        checksum="",
                        rows_written=0,
                        rows_total=0,
                        failed_checks=[],
                        blocked=True,
                        dq_result=dq_result,
                    )

                # Log L2 warnings (non-blocking)
                if check_result.has_warnings:
                    logger.warning(
                        "DQ check found L2 warnings - proceeding",
                        event="bars_dq_warnings",
                        dataset=dataset,
                        warning_count=check_result.warn_count,
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

            # Generate DQ report if enabled
            if dq_result and not dq_result.passed:
                self._generate_dq_report(dq_result, dataset)

            # Record metrics
            M.data_records.add(len(df), {"dataset": "bars", "operation": "write"})

            return WriteResult(
                file_path=file_path,
                checksum=checksum,
                rows_written=len(df),
                rows_total=total_rows,
                failed_checks=[],
                blocked=False,
                dq_result=dq_result,
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
        asset_class: Literal["stock", "etf", "index"] | None,
        sids: list[int],
    ) -> str:
        """Determine dataset name from asset class or SIDs."""
        if asset_class:
            return f"{asset_class}_daily"

        # Check for mixed asset classes
        stock_range = SidRange.get_range("stock")
        etf_range = SidRange.get_range("etf")
        index_range = SidRange.get_range("index")

        has_stock = any(
            stock_range.min_sid <= sid <= stock_range.max_sid for sid in sids
        )
        has_etf = any(etf_range.min_sid <= sid <= etf_range.max_sid for sid in sids)
        has_index = any(
            index_range.min_sid <= sid <= index_range.max_sid for sid in sids
        )

        # Check for mixed asset classes
        asset_class_count = sum([has_stock, has_etf, has_index])
        if asset_class_count > 1:
            classes = []
            if has_stock:
                classes.append("stock")
            if has_etf:
                classes.append("ETF")
            if has_index:
                classes.append("index")
            raise ValueError(
                f"Mixed asset class query detected. SIDs contain {', '.join(classes)}. "
                "Please query each asset class separately."
            )

        if has_stock:
            return "stock_daily"
        if has_etf:
            return "etf_daily"
        if has_index:
            return "index_daily"

        return "stock_daily"  # Default

    def _apply_adj(
        self,
        df: pl.DataFrame,
        sids: list[int],
        adj: AdjType,
        start: str | None,
        end: str | None,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        应用价格调整（主入口）。

        Args:
            df: K线数据 DataFrame。
            sids: 要调整的 SID 列表。
            adj: 调整类型。
            start: adj_factor 读取的起始日期。
            end: adj_factor 读取的结束日期。
            asof: PIT 调整基准日期。如果提供，则使用该日期的最新因子。

        Returns:
            调整后的 DataFrame.

        """
        # 读取调整因子
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

        # 确保排序以正确处理 last() 聚合
        adj_df = adj_df.sort(["sid", "trade_date"])

        # 关联调整因子
        df = df.join(
            adj_df.select(["sid", "trade_date", "adj_factor"]),
            on=["sid", "trade_date"],
            how="left",
        )

        # 根据调整类型调用相应方法
        if adj == AdjType.QFQ:
            return self._apply_qfq_adj(df, adj_df, asof)
        else:  # HFQ
            return self._apply_hfq_adj(df, adj_df)

    def _apply_qfq_adj(
        self,
        df: pl.DataFrame,
        adj_df: pl.DataFrame,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        应用前复权（QFQ）调整。

        Tushare QFQ: adj_price = orig_price * cur_factor / latest_factor。
        当 asof 提供时，使用该日期的最新因子作为基准。

        Args:
            df: 已关联 adj_factor 的 K线数据。
            adj_df: 调整因子数据（已排序）。
            asof: PIT 基准日期。

        Returns:
            QFQ 调整后的 DataFrame.

        """
        # 计算 baseline（PIT 安全）
        #
        # 注意: 当前实现使用 trade_date 进行过滤，这存在 PIT 安全隐患。
        # 正确的做法应该是使用 knowledge_date（因子生效日期）进行过滤。
        #
        # PIT 安全要求:
        # - 复权因子的 knowledge_date 应该是因子实际可用的日期
        # - 对于 Tushare，通常是 T+1 日才可用（knowledge_date = trade_date + 1）
        #
        # 当前限制:
        # adj_factor 表目前没有 knowledge_date 字段，这需要:
        # 1. 修改 adj_factor 表结构添加 knowledge_date 列
        # 2. 更新 ingestion 逻辑以正确设置 knowledge_date
        # 3. 修改此处过滤条件为 knowledge_date <= asof_date
        #
        # TODO: 在未来的 Sprint 中添加 knowledge_date 支持
        # 追踪: https://github.com/your-org/ditto/issues/XXX
        baseline_df = adj_df
        if asof is not None:
            from datetime import date

            asof_date = date.fromisoformat(asof)
            # 临时方案: 使用 trade_date，假设因子当日可用
            # 正确方案: 应使用 knowledge_date <= asof_date
            baseline_df = adj_df.filter(pl.col("trade_date") <= asof_date)

        # 获取每个 SID 的最新因子
        latest_factors = baseline_df.group_by("sid").agg(
            pl.col("adj_factor").last().alias("latest_factor")
        )
        df = df.join(latest_factors, on="sid", how="left")

        # 应用 QFQ 公式，缺失值使用 1.0（返回原始价格）
        df = df.with_columns(
            [
                (
                    pl.col("open")
                    * pl.coalesce("adj_factor", 1.0)
                    / pl.coalesce("latest_factor", 1.0)
                ).alias("open"),
                (
                    pl.col("high")
                    * pl.coalesce("adj_factor", 1.0)
                    / pl.coalesce("latest_factor", 1.0)
                ).alias("high"),
                (
                    pl.col("low")
                    * pl.coalesce("adj_factor", 1.0)
                    / pl.coalesce("latest_factor", 1.0)
                ).alias("low"),
                (
                    pl.col("close")
                    * pl.coalesce("adj_factor", 1.0)
                    / pl.coalesce("latest_factor", 1.0)
                ).alias("close"),
            ]
        )
        return df.drop(["adj_factor", "latest_factor"])

    def _apply_hfq_adj(
        self,
        df: pl.DataFrame,
        adj_df: pl.DataFrame,
    ) -> pl.DataFrame:
        """
        应用后复权（HFQ）调整。

        后复权：adj_price = orig_price * cur_factor
        缺失值使用 1.0（返回原始价格）。

        Args:
            df: 已关联 adj_factor 的 K线数据。
            adj_df: 调整因子数据（未使用，保持参数一致性）。

        Returns:
            HFQ 调整后的 DataFrame.

        """
        # 应用 HFQ 公式，缺失值使用 1.0
        df = df.with_columns(
            [
                (pl.col("open") * pl.coalesce("adj_factor", 1.0)).alias("open"),
                (pl.col("high") * pl.coalesce("adj_factor", 1.0)).alias("high"),
                (pl.col("low") * pl.coalesce("adj_factor", 1.0)).alias("low"),
                (pl.col("close") * pl.coalesce("adj_factor", 1.0)).alias("close"),
            ]
        )
        return df.drop("adj_factor")

    def _save_to_quarantine(
        self,
        df: pl.DataFrame,
        dataset: str,
        rule_id: str,
        severity: str,
        trade_date: str | None = None,
    ) -> None:
        """
        Save failed data to quarantine store.

        Args:
            df: Failed data rows.
            dataset: Dataset name.
            rule_id: Rule that failed.
            severity: Severity level.
            trade_date: Optional trade date.

        """
        if df.is_empty():
            return

        try:
            from ditto_datahub.dq.models import DQIssue

            # Get quarantine store path from bars_store
            data_root = self._bars_store._data_root
            quarantine_path = data_root / "quarantine.db"

            from ditto_datahub.stores.quarantine_store import QuarantineStore

            quarantine_store = QuarantineStore(quarantine_path)
            quarantine_store.save_failed_data(
                dataset=dataset,
                rule_id=rule_id,
                severity=severity,
                failed_data=df,
                trade_date=trade_date,
            )

            logger.info(
                "Failed data saved to quarantine",
                event="quarantine_saved",
                dataset=dataset,
                rule_id=rule_id,
                rows=len(df),
            )

        except Exception as e:
            logger.error(
                "Failed to save to quarantine",
                event="quarantine_save_failed",
                dataset=dataset,
                rule_id=rule_id,
                error=str(e),
            )

    def _generate_dq_report(self, result: DQResult, dataset: str) -> None:
        """
        Generate DQ report and save to file.

        Args:
            result: DQ check result.
            dataset: Dataset name.

        """
        try:
            from datetime import datetime

            from ditto_datahub.dq.report import DQReportGenerator

            data_root = self._bars_store._data_root
            reports_dir = data_root / "reports" / "dq"
            reports_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = reports_dir / f"{dataset}_{timestamp}.md"

            generator = DQReportGenerator()
            generator.save_report(result, report_path, report_format="markdown")

            logger.info(
                "DQ report generated",
                event="dq_report_generated",
                dataset=dataset,
                report_path=str(report_path),
            )

        except Exception as e:
            logger.error(
                "Failed to generate DQ report",
                event="dq_report_failed",
                dataset=dataset,
                error=str(e),
            )


def filter_failed_rows(df: pl.DataFrame, issue: DQIssue) -> pl.DataFrame:
    """
    Filter failed rows based on DQ issue.

    Args:
        df: Input DataFrame.
        issue: DQ issue with rule information.

    Returns:
        Filtered DataFrame with failed rows.

    """
    rule_name = issue.rule_name.lower()

    # Handle not_null rule: filter rows where column is null
    if rule_name == "not_null":
        # Extract column name from message (format: "{col} has null values")
        message = issue.message.lower()
        for col in df.columns:
            if col.lower() in message and "has null values" in message:
                return df.filter(pl.col(col).is_null())
        # Fallback: check all columns for null values
        null_cols = [pl.col(c).is_null() for c in df.columns]
        if null_cols:
            return df.filter(pl.any_horizontal(null_cols))

    # Handle unique rule: filter duplicate rows
    if rule_name == "unique":
        # For unique constraint, find duplicate rows
        # Check all column combinations to find duplicates
        for col_count in range(1, len(df.columns) + 1):
            for cols in combinations(df.columns, col_count):
                duplicates = (
                    df.group_by(cols)
                    .agg(pl.len().alias("_count"))
                    .filter(pl.col("_count") > 1)
                )
                if not duplicates.is_empty():
                    # Join back to get original rows
                    return df.join(duplicates.select(cols), on=cols, how="inner")
        return df  # Fallback: return all rows

    # Handle foreign_key rule: filter rows with invalid FK
    if rule_name == "foreign_key":
        # Cannot filter without reference data
        # Return all rows for manual review
        return df

    # Handle type_check rule: filter rows with type issues
    if rule_name == "type_check":
        # Cannot filter without type info
        # Return all rows for manual review
        return df

    # Default: return all rows for manual review
    return df
