"""质量服务 — 写入时 DQ 编排、L3 批量检查、质量对账（应用层）."""

from __future__ import annotations

__all__ = [
    "ComparisonStoreProtocol",
    "InstrumentStoreProtocol",
    "L3BatchService",
    "QualityReconciliationService",
    "QualityService",
    "ReconciliationResult",
    "TdxSourceProtocol",
]

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol

import polars as pl
import polars.exceptions as pl_exceptions
from ditto_data.ingestion.quality_record_service import QualityRecordService
from ditto_data.quality import QualityEngine
from ditto_data.quality.golden import GoldenDatasetSpec
from ditto_data.quality.spec import DQIssue, DQResult
from ditto_infra.foundation import logger

from ditto_app.query.market import MarketQueryFacade
from ditto_app.query.metadata import MetadataQueryFacade

# ---------------------------------------------------------------------------
# 领域模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReconciliationResult:
    """对账结果（强类型）."""

    trade_date: str
    dataset: str
    passed: bool
    issue_count: int
    skipped: bool = False
    skip_reason: str | None = None
    error: str | None = None

    @property
    def has_error(self) -> bool:
        """是否存在异常."""
        return self.error is not None

    def to_dict(self) -> dict[str, object]:
        """转换为字典（兼容旧代码）."""
        result: dict[str, object] = {
            "trade_date": self.trade_date,
            "dataset": self.dataset,
            "passed": self.passed,
            "issue_count": self.issue_count,
        }
        if self.skipped and self.skip_reason:
            result["skipped"] = self.skip_reason
        if self.error:
            result["error"] = self.error
        return result


# ---------------------------------------------------------------------------
# 写入时 DQ 检查
# ---------------------------------------------------------------------------


class QualityService:
    """
    Quality service for write-time DQ checks.

    Application Layer: Orchestrates L1/L2 checks during data ingestion.
    Handles quarantine logic and metrics/logging.
    """

    def __init__(
        self,
        engine: QualityEngine,
        quarantine_writer: QualityRecordService | None = None,
    ) -> None:
        """
        Initialize quality service.

        Args:
            engine: Quality engine instance
            quarantine_writer: Optional quarantine writer for failed data

        """
        self._engine = engine
        self._quarantine_writer = quarantine_writer

    def check_and_quarantine(
        self,
        df: pl.DataFrame,
        dataset: str,
        context: dict[str, Any] | None = None,
    ) -> tuple[pl.DataFrame, bool]:
        """
        Execute DQ checks and quarantine bad data if needed.

        Args:
            df: Data to check
            dataset: Dataset identifier
            context: Additional context (e.g., reference_values for FK checks)

        Returns:
            Tuple of (df, should_block):
                - df: Original DataFrame (unchanged;
                  quarantine copies bad rows to separate store)
                - should_block: Whether to block ingestion (True if L1 errors found)

        """
        result = self._engine.check(
            df=df,
            dataset=dataset,
            levels=["l1", "l2"],
            context=context,
        )

        self._log_check_result(result, dataset)

        if result.issues:
            self._quarantine_data(df, result, dataset)

        return df, result.has_errors

    def _log_check_result(self, result: DQResult, dataset: str) -> None:
        """记录 DQ 检查结果."""
        if result.issues:
            logger.warning(
                "DQ issues found during write",
                event="dq_write_check",
                dataset=dataset,
                issue_count=len(result.issues),
                error_count=result.error_count,
                warn_count=result.warn_count,
            )
        else:
            logger.debug(
                "DQ check passed",
                event="dq_write_check",
                dataset=dataset,
            )

    def _quarantine_data(
        self,
        _df: pl.DataFrame,
        result: DQResult,
        dataset: str,
    ) -> None:
        """
        Quarantine data with quality issues.

        Saves failed data to quarantine store if available.

        Args:
            df: Data with issues
            result: DQ check result
            dataset: Dataset identifier

        """
        if self._quarantine_writer is None:
            logger.info(
                "Quarantine store not configured, skipping quarantine",
                event="dq_quarantine_skipped",
                dataset=dataset,
                issue_count=len(result.issues),
            )
            return

        for issue in result.issues:
            if issue.affected_rows == 0 or not issue.sample_data:
                continue
            self._save_quarantine_issue(dataset, issue)

    def _save_quarantine_issue(self, dataset: str, issue: DQIssue) -> None:
        """保存单个 issue 的隔离数据."""
        assert self._quarantine_writer is not None  # noqa: S101  # guarded by _quarantine_data
        try:
            failed_df = pl.DataFrame(issue.sample_data)
            self._quarantine_writer.save_failed_data(
                dataset=dataset,
                rule_id=issue.rule_name,
                severity=issue.severity.value,
                failed_data=failed_df,
                trade_date=None,
            )
            logger.info(
                "Quarantined bad data",
                event="dq_quarantine",
                dataset=dataset,
                rule_id=issue.rule_name,
                severity=issue.severity.value,
                affected_rows=issue.affected_rows,
            )
        except Exception as e:
            logger.error(
                "Failed to quarantine data",
                event="dq_quarantine_failed",
                dataset=dataset,
                rule_id=issue.rule_name,
                error=str(e),
            )


# ---------------------------------------------------------------------------
# L3 批量统计检查
# ---------------------------------------------------------------------------


class L3BatchService:
    """
    L3 batch check service.

    Application Layer: Orchestrates L3 statistical anomaly checks.
    Fetches historical data via facade and injects into Core Engine.
    """

    def __init__(
        self,
        engine: QualityEngine,
        market_facade: MarketQueryFacade,
        metadata_facade: MetadataQueryFacade,
    ) -> None:
        """
        Initialize L3 batch service.

        Args:
            engine: Quality engine instance
            market_facade: MarketQueryFacade for data access
            metadata_facade: MetadataQueryFacade for data access

        """
        self._engine = engine
        self._market_facade = market_facade
        self._metadata_facade = metadata_facade

    def check_dataset(
        self,
        dataset: str,
        trade_date: str,
        asset_class: Literal["stock", "etf", "index"] | None = None,
        market_wide: bool = False,
    ) -> dict[str, Any]:
        """
        Orchestrate L3 check for a dataset.

        Args:
            dataset: Dataset identifier
            trade_date: Trade date to check (YYYY-MM-DD)
            asset_class: Asset class for market-wide queries
            market_wide: Whether to use market-wide query mode

        Returns:
            Check result summary

        """
        logger.info(
            "Starting L3 batch check",
            event="l3_batch_start",
            dataset=dataset,
            trade_date=trade_date,
        )

        try:
            historical, current, calendar = self._fetch_check_data(
                trade_date,
                asset_class,
                market_wide,
            )
            result = self._engine.check_statistical(
                dataset=dataset,
                current=current,
                historical=historical,
                calendar=calendar,
            )
            return self._format_check_result(dataset, trade_date, result)
        except (pl_exceptions.ComputeError, pl_exceptions.SchemaError, ValueError) as e:
            return self._handle_check_error(dataset, trade_date, e, is_data_error=True)
        except Exception as e:
            return self._handle_check_error(dataset, trade_date, e, is_data_error=False)

    def _handle_check_error(
        self,
        dataset: str,
        trade_date: str,
        error: Exception,
        *,
        is_data_error: bool,
    ) -> dict[str, Any]:
        """统一处理 L3 检查异常，记录日志并返回错误结果."""
        event_name = (
            "l3_batch_check_data_processing_failed"
            if is_data_error
            else "l3_batch_check_unknown_error"
        )
        logger.exception(
            event_name,
            event="l3_batch_error",
            dataset=dataset,
            trade_date=trade_date,
            error_type=type(error).__name__,
        )
        return {
            "dataset": dataset,
            "trade_date": trade_date,
            "passed": False,
            "error": f"{type(error).__name__}: {error!s}",
        }

    def _fetch_check_data(
        self,
        trade_date: str,
        asset_class: Literal["stock", "etf", "index"] | None,
        market_wide: bool,
    ) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
        """获取 L3 检查所需的历史、当前和日历数据."""
        historical, current = self._fetch_data(
            trade_date=trade_date,
            asset_class=asset_class,
            market_wide=market_wide,
        )
        calendar = self._fetch_calendar(trade_date=trade_date)
        return historical, current, calendar

    def _format_check_result(
        self,
        dataset: str,
        trade_date: str,
        result: DQResult,
    ) -> dict[str, Any]:
        """格式化 L3 检查结果."""
        if result.issues:
            logger.warning(
                "L3 issues found",
                event="l3_batch_issues",
                dataset=dataset,
                count=len(result.issues),
            )
            if result.has_alerts:
                self._send_alert(trade_date, dataset, result.issues)
        else:
            logger.info(
                "L3 check passed",
                event="l3_batch_passed",
                dataset=dataset,
            )

        return {
            "dataset": dataset,
            "trade_date": trade_date,
            "passed": result.passed,
            "issue_count": len(result.issues),
            "alert_count": result.alert_count,
            "issues": result.issues,
        }

    def _fetch_data(
        self,
        trade_date: str,
        window: int = 120,
        asset_class: Literal["stock", "etf", "index"] | None = None,
        market_wide: bool = False,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        """
        Fetch historical and current data via MarketQueryFacade.

        Args:
            trade_date: Trade date (YYYY-MM-DD)
            window: Lookback window for historical data (days)
            asset_class: Asset class filter
            market_wide: Market-wide query mode

        Returns:
            Tuple of (historical_df, current_df)

        """
        # Calculate start date with buffer for weekends
        trade_dt = datetime.fromisoformat(trade_date)
        start_dt = trade_dt - timedelta(days=window * 2)
        start_date = start_dt.strftime("%Y-%m-%d")

        # Fetch historical data
        historical = self._market_facade.find_bars(
            instrument_ids=None,
            start=start_date,
            end=trade_date,
            market_wide=market_wide,
            asset_class=asset_class,
        )

        # Fetch current data
        current = self._market_facade.find_bars(
            instrument_ids=None,
            start=trade_date,
            end=trade_date,
            market_wide=market_wide,
            asset_class=asset_class,
        )

        return historical, current

    def _fetch_calendar(self, trade_date: str, lookback_days: int = 10) -> pl.DataFrame:
        """
        Fetch trading calendar via MetadataQueryFacade.

        Args:
            trade_date: Trade date (YYYY-MM-DD)
            lookback_days: Days to look back

        Returns:
            Calendar DataFrame

        """
        # Calculate start date
        trade_dt = datetime.fromisoformat(trade_date)
        start_dt = trade_dt - timedelta(days=lookback_days * 2)
        start_date = start_dt.strftime("%Y-%m-%d")

        return self._metadata_facade.list_calendar_range(
            start=start_date,
            end=trade_date,
            only_open=True,
        )

    def _send_alert(
        self,
        trade_date: str,
        dataset: str,
        issues: list[DQIssue],
    ) -> None:
        """
        Send DQ alert notification.

        Args:
            trade_date: Trade date
            dataset: Dataset name
            issues: List of DQ issues

        """
        logger.warning(
            "DQ alert notification",
            event="dq_alert",
            trade_date=trade_date,
            dataset=dataset,
            issue_count=len(issues),
            issues=[
                {"level": i.level.value, "rule": i.rule_name, "message": i.message}
                for i in issues
            ],
        )


# ---------------------------------------------------------------------------
# 质量对账
# ---------------------------------------------------------------------------


class InstrumentStoreProtocol(Protocol):
    """Protocol for instrument enrichment dependency."""

    def enrich_with_ticker(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add ticker column from instrument id."""
        ...


class TdxSourceProtocol(Protocol):
    """Protocol for TDX source dependency."""

    def fetch_stock_daily_bars(
        self, tickers: list[str], trade_date: str
    ) -> pl.DataFrame:
        """Fetch TDX stock daily bars."""
        ...


class ComparisonStoreProtocol(Protocol):
    """Protocol for reconciliation result persistence."""

    def write_comparison(
        self, trade_date: str, comparison_df: pl.DataFrame, dataset: str
    ) -> None:
        """Persist comparison dataframe."""
        ...


class QualityReconciliationService:
    """
    质量对账服务.

    App 层：编排协调
    - 获取多源数据
    - 应用黄金数据集过滤
    - 调用 Engine 层引擎进行对比
    - 转换 DQResult → DataFrame
    - 存储对比结果
    - 触发告警

    标识符体系：
    - 入口使用 instrument_id（内部 ID）
    - 对比使用 ticker（统一格式，如 000001）
    - 数据源使用 source_ticker（数据源特定格式，如 000001.SZ）
    """

    def __init__(
        self,
        engine: QualityEngine,
        tdx_source: TdxSourceProtocol,
        comparison_store: ComparisonStoreProtocol,
        instrument_store: InstrumentStoreProtocol,
        golden_dataset: GoldenDatasetSpec | None = None,
    ) -> None:
        """
        初始化质量对账服务.

        Args:
            engine: 质量引擎
            tdx_source: 通达信数据源
            comparison_store: 对比结果存储
            instrument_store: 证券存储（用于 instrument_id → ticker 转换）
            golden_dataset: 黄金数据集配置（可选）

        """
        self._engine = engine
        self._tdx_source = tdx_source
        self._comparison_store = comparison_store
        self._instrument_store = instrument_store
        self._golden_dataset = golden_dataset

    async def daily_reconciliation(
        self,
        primary_df: pl.DataFrame,
        trade_date: str,
        dataset: str = "stock_daily",
    ) -> ReconciliationResult:
        """
        每日质量对账.

        App 层：编排流程

        标识符转换流程：
        1. 接收包含 instrument_id 的 primary_df
        2. 使用 InstrumentStore 将 instrument_id 转换为 ticker
        3. 应用黄金数据集过滤（如果配置）
        4. 使用 ticker 作为对比的 key_column
        5. 各数据源内部将 ticker 转换为各自的 source_ticker 格式

        Args:
            primary_df: 主数据源（Tushare 已读取的数据，必须包含 instrument_id 列）
            trade_date: 交易日期（YYYYMMDD）
            dataset: 数据集标识

        Returns:
            对账结果摘要

        """
        logger.info(
            "Starting daily quality reconciliation",
            event="reconciliation_start",
            trade_date=trade_date,
            dataset=dataset,
        )

        try:
            enriched = self._enrich_and_filter(primary_df, trade_date, dataset)
            if isinstance(enriched, ReconciliationResult):
                return enriched

            return await self._execute_comparison(enriched, trade_date, dataset)
        except Exception as e:
            return self._handle_reconciliation_error(trade_date, dataset, e)

    def _handle_reconciliation_error(
        self,
        trade_date: str,
        dataset: str,
        error: Exception,
    ) -> ReconciliationResult:
        """统一处理对账异常，记录日志并返回错误结果."""
        logger.exception(
            "Reconciliation failed",
            event="reconciliation_error",
            trade_date=trade_date,
            dataset=dataset,
            error_type=type(error).__name__,
        )
        return ReconciliationResult(
            trade_date=trade_date,
            dataset=dataset,
            passed=False,
            issue_count=0,
            error=f"{type(error).__name__}: {error!s}",
        )

    def _enrich_and_filter(
        self,
        primary_df: pl.DataFrame,
        trade_date: str,
        dataset: str,
    ) -> pl.DataFrame | ReconciliationResult:
        """添加 ticker 列并应用黄金数据集过滤。返回过滤后的 DataFrame 或跳过结果."""
        if "instrument_id" not in primary_df.columns:
            raise ValueError("primary_df must contain 'instrument_id' column")

        primary_df = self._instrument_store.enrich_with_ticker(primary_df)

        if "ticker" not in primary_df.columns:
            raise ValueError("Failed to enrich primary_df with ticker")

        primary_df = self._apply_golden_dataset_filter(primary_df)

        if primary_df.is_empty():
            logger.info(
                "Golden dataset filter resulted in empty dataset",
                event="reconciliation_golden_empty",
                trade_date=trade_date,
                dataset=dataset,
            )
            return ReconciliationResult(
                trade_date=trade_date,
                dataset=dataset,
                passed=True,
                issue_count=0,
                skipped=True,
                skip_reason="golden_dataset_filter_empty",
            )

        return primary_df

    async def _execute_comparison(
        self,
        primary_df: pl.DataFrame,
        trade_date: str,
        dataset: str,
    ) -> ReconciliationResult:
        """获取辅助数据源并执行对比."""
        tickers = primary_df["ticker"].unique().to_list()

        secondary_result = self._fetch_secondary(tickers, trade_date, dataset)
        if isinstance(secondary_result, ReconciliationResult):
            return secondary_result

        # 配置文件使用 key_columns: [ticker, trade_date]
        result = self._engine.check_cross_source(
            primary=primary_df,
            secondary=secondary_result,
            dataset=dataset,
        )

        comparison_df = self._convert_result_to_df(result, dataset)
        if not comparison_df.is_empty():
            self._comparison_store.write_comparison(trade_date, comparison_df, dataset)

        if result.issues:
            await self._send_alerts(result, trade_date, dataset)

        logger.info(
            "Daily reconciliation complete",
            event="reconciliation_complete",
            trade_date=trade_date,
            dataset=dataset,
            passed=result.passed,
            issue_count=len(result.issues),
        )

        return ReconciliationResult(
            trade_date=trade_date,
            dataset=dataset,
            passed=result.passed,
            issue_count=len(result.issues),
        )

    def _fetch_secondary(
        self,
        tickers: list[str],
        trade_date: str,
        dataset: str,
    ) -> pl.DataFrame | ReconciliationResult:
        """获取辅助数据源。返回 DataFrame 或跳过结果."""
        # TdxSource 内部将 ticker 转换为 TDX 格式的 source_ticker
        secondary_df = self._tdx_source.fetch_stock_daily_bars(tickers, trade_date)

        if secondary_df.height == 0:
            logger.warning(
                "No TDX data found for comparison",
                event="reconciliation_no_secondary",
                trade_date=trade_date,
            )
            return ReconciliationResult(
                trade_date=trade_date,
                dataset=dataset,
                passed=True,
                issue_count=0,
                skipped=True,
                skip_reason="no_secondary_data",
            )

        return secondary_df

    def _apply_golden_dataset_filter(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        应用黄金数据集过滤.

        Args:
            df: 包含 ticker 列的 DataFrame

        Returns:
            过滤后的 DataFrame

        """
        if not self._golden_dataset or not self._golden_dataset.is_enabled:
            return df

        golden_tickers = self._golden_dataset.get_tickers()
        logger.debug(
            "Applying golden dataset filter",
            event="golden_filter_apply",
            golden_count=len(golden_tickers),
            input_count=df.height,
        )
        return df.filter(pl.col("ticker").is_in(golden_tickers))

    def _convert_result_to_df(self, result: DQResult, dataset: str) -> pl.DataFrame:
        """
        转换 DQResult → DataFrame.

        App 层职责：处理跨层数据转换.

        Args:
            result: DQResult from Core layer
            dataset: Dataset identifier

        Returns:
            DataFrame for storage

        """
        if not result.issues:
            return pl.DataFrame()

        rows: list[dict[str, Any]] = []
        for issue in result.issues:
            # 每个样本是一行记录
            for sample in issue.sample_data:
                row: dict[str, Any] = {
                    "dataset": dataset,
                    "ticker": sample.get("ticker", ""),
                    "trade_date": sample.get("trade_date", ""),
                    "field": sample.get("field", ""),
                    "primary_value": sample.get("primary_value", ""),
                    "secondary_value": sample.get("secondary_value", ""),
                    "diff": sample.get("diff", ""),
                    "severity": issue.severity.value,
                    "rule": issue.rule_name,
                    "message": issue.message,
                }
                rows.append(row)

        return pl.DataFrame(rows)

    async def _send_alerts(
        self, result: DQResult, trade_date: str, dataset: str
    ) -> None:
        """
        发送告警.

        Args:
            result: DQResult
            trade_date: 交易日期
            dataset: 数据集标识

        """
        # TODO: 实现告警发送（邮件、钉钉、微信等）
        logger.warning(
            "Quality reconciliation alert",
            event="reconciliation_alert",
            trade_date=trade_date,
            dataset=dataset,
            issue_count=len(result.issues),
            issues=[
                {
                    "severity": i.severity.value,
                    "rule": i.rule_name,
                    "message": i.message,
                }
                for i in result.issues
            ],
        )
