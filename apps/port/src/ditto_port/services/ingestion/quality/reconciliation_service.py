"""质量对账服务 - Port 层编排."""

from typing import Any, Protocol

import polars as pl
from ditto_core.quality.spec import DQResult
from loguru import logger


class InstrumentStoreProtocol(Protocol):
    """Protocol for instrument enrichment dependency."""

    def enrich_with_symbol(self, df: pl.DataFrame) -> pl.DataFrame:
        """Add symbol column from instrument id."""
        ...


class TdxSourceProtocol(Protocol):
    """Protocol for TDX source dependency."""

    def fetch_stock_daily_bars(
        self, symbols: list[str], trade_date: str
    ) -> pl.DataFrame:
        """Fetch TDX stock daily bars."""
        ...


class ComparisonStoreProtocol(Protocol):
    """Protocol for reconciliation result persistence."""

    async def write_comparison(
        self, trade_date: str, comparison_df: pl.DataFrame, dataset: str
    ) -> None:
        """Persist comparison dataframe."""
        ...


class QualityReconciliationService:
    """
    质量对账服务.

    Port 层：编排协调
    - 获取多源数据
    - 调用 Core 层引擎进行对比
    - 转换 DQResult → DataFrame
    - 存储对比结果
    - 触发告警

    标识符体系：
    - 入口使用 instrument_id（内部 ID）
    - 对比使用 symbol（统一格式，如 000001）
    - 数据源使用 source_ticker（数据源特定格式，如 000001.SZ）
    """

    def __init__(
        self,
        engine: Any,  # QualityEngine
        tdx_source: TdxSourceProtocol,
        comparison_store: ComparisonStoreProtocol,
        instrument_store: InstrumentStoreProtocol,
    ) -> None:
        """
        初始化质量对账服务.

        Args:
            engine: 质量引擎
            tdx_source: 通达信数据源
            comparison_store: 对比结果存储
            instrument_store: 证券存储（用于 instrument_id → symbol 转换）

        """
        self._engine = engine
        self._tdx_source = tdx_source
        self._comparison_store = comparison_store
        self._instrument_store = instrument_store

    async def daily_reconciliation(
        self,
        primary_df: pl.DataFrame,
        trade_date: str,
        dataset: str = "stock_daily",
    ) -> dict[str, Any]:
        """
        每日质量对账.

        Port 层：编排流程

        标识符转换流程：
        1. 接收包含 instrument_id 的 primary_df
        2. 使用 InstrumentStore 将 instrument_id 转换为 symbol
        3. 使用 symbol 作为对比的 key_column
        4. 各数据源内部将 symbol 转换为各自的 source_ticker 格式

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

            # 2. 添加 symbol 列（instrument_id → symbol 转换）
            primary_df = self._instrument_store.enrich_with_symbol(primary_df)

            if "symbol" not in primary_df.columns:
                raise ValueError("Failed to enrich primary_df with symbol")

            # 3. 提取 symbol 列表
            symbols = primary_df["symbol"].unique().to_list()

            # 4. 获取辅助数据源（TDX）
            # TdxSource 内部将 symbol 转换为 TDX 格式的 source_ticker
            secondary_df = self._tdx_source.fetch_stock_daily_bars(symbols, trade_date)

            if secondary_df.height == 0:
                logger.warning(
                    "No TDX data found for comparison",
                    event="reconciliation_no_secondary",
                    trade_date=trade_date,
                )
                return {
                    "trade_date": trade_date,
                    "dataset": dataset,
                    "passed": True,
                    "issue_count": 0,
                    "skipped": "no_secondary_data",
                }

            # 5. 调用 Core 层引擎进行对比
            # 配置文件使用 key_columns: [symbol, trade_date]
            result = self._engine.check_cross_source(
                primary=primary_df,
                secondary=secondary_df,
                dataset=dataset,
            )

            # 6. 转换 DQResult → DataFrame（Port 层职责）
            comparison_df = self._convert_result_to_df(result, dataset)

            # 7. 存储对比结果
            if not comparison_df.is_empty():
                await self._comparison_store.write_comparison(
                    trade_date, comparison_df, dataset
                )

            # 8. 判断是否需要告警
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

            return {
                "trade_date": trade_date,
                "dataset": dataset,
                "passed": result.passed,
                "issue_count": len(result.issues),
            }

        except Exception as e:
            logger.exception(
                "Reconciliation failed",
                event="reconciliation_error",
                trade_date=trade_date,
                dataset=dataset,
                error_type=type(e).__name__,
            )
            return {
                "trade_date": trade_date,
                "dataset": dataset,
                "passed": False,
                "issue_count": 0,  # 错误情况下不进行 issue 计数
                "error": f"{type(e).__name__}: {e!s}",
            }

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
                    "symbol": sample.get("symbol", ""),
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
