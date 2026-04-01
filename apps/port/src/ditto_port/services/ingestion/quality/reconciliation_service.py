"""质量对账服务 - Port 层编排."""

from typing import Any, Protocol

import polars as pl
from ditto_data.quality.golden import GoldenDatasetSpec
from ditto_data.quality.spec import DQResult
from loguru import logger

from .models import ReconciliationResult


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

    Port 层：编排协调
    - 获取多源数据
    - 应用黄金数据集过滤
    - 调用 Core 层引擎进行对比
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
        engine: Any,  # QualityEngine
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
    ) -> "ReconciliationResult":
        """
        每日质量对账.

        Port 层：编排流程

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
            # 1. 验证输入
            if "instrument_id" not in primary_df.columns:
                raise ValueError("primary_df must contain 'instrument_id' column")

            # 2. 添加 ticker 列（instrument_id → ticker 转换）
            primary_df = self._instrument_store.enrich_with_ticker(primary_df)

            if "ticker" not in primary_df.columns:
                raise ValueError("Failed to enrich primary_df with ticker")

            # 3. 应用黄金数据集过滤
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

            # 4. 提取 ticker 列表
            tickers = primary_df["ticker"].unique().to_list()

            # 5. 获取辅助数据源（TDX）
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

            # 6. 调用 Core 层引擎进行对比
            # 配置文件使用 key_columns: [ticker, trade_date]
            result = self._engine.check_cross_source(
                primary=primary_df,
                secondary=secondary_df,
                dataset=dataset,
            )

            # 7. 转换 DQResult → DataFrame（Port 层职责）
            comparison_df = self._convert_result_to_df(result, dataset)

            # 8. 存储对比结果
            if not comparison_df.is_empty():
                self._comparison_store.write_comparison(
                    trade_date, comparison_df, dataset
                )

            # 9. 判断是否需要告警
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

        except Exception as e:
            logger.exception(
                "Reconciliation failed",
                event="reconciliation_error",
                trade_date=trade_date,
                dataset=dataset,
                error_type=type(e).__name__,
            )
            return ReconciliationResult(
                trade_date=trade_date,
                dataset=dataset,
                passed=False,
                issue_count=0,
                error=f"{type(e).__name__}: {e!s}",
            )

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

        Port 层职责：处理跨层数据转换.

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
