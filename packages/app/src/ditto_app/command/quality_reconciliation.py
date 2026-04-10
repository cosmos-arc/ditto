"""数据源对账 Command — 跨源一致性校验的原子写操作."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl
from ditto_data.quality.golden import GoldenDatasetSpec
from ditto_data.quality.protocols import (
    ComparisonStoreProtocol,
    InstrumentStoreProtocol,
    QualityEngineProtocol,
    TdxSourceProtocol,
)
from ditto_infra.foundation import logger
from ditto_kernel.quality import DQResult, ReconciliationResult


@dataclass(frozen=True)
class ReconcileSourcesCommand:
    """数据源对账命令."""

    primary_df: pl.DataFrame
    trade_date: str
    dataset: str = "stock_daily"


class ReconcileSourcesHandler:
    """
    数据源对账 Command Handler — 跨源一致性校验.

    直接依赖 Protocol 实现（QualityEngine、TdxSource、ComparisonStore、
    InstrumentStore），编排 enrich → filter → compare → write 的完整对账流程。
    """

    def __init__(
        self,
        engine: QualityEngineProtocol,
        tdx_source: TdxSourceProtocol,
        comparison_store: ComparisonStoreProtocol,
        instrument_store: InstrumentStoreProtocol,
        golden_dataset: GoldenDatasetSpec | None = None,
    ) -> None:
        self._engine = engine
        self._tdx_source = tdx_source
        self._comparison_store = comparison_store
        self._instrument_store = instrument_store
        self._golden_dataset = golden_dataset

    def handle(self, cmd: ReconcileSourcesCommand) -> ReconciliationResult:
        """执行跨源对账，返回对账结果."""
        logger.info(
            "Starting daily quality reconciliation",
            event="reconciliation_start",
            trade_date=cmd.trade_date,
            dataset=cmd.dataset,
        )

        try:
            enriched = self._enrich_and_filter(
                cmd.primary_df,
                cmd.trade_date,
                cmd.dataset,
            )
            if isinstance(enriched, ReconciliationResult):
                return enriched

            return self._execute_comparison(enriched, cmd.trade_date, cmd.dataset)
        except Exception as e:
            return self._handle_reconciliation_error(cmd.trade_date, cmd.dataset, e)

    # -- Private helpers (absorbed from QualityReconciliationService) --

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

    def _execute_comparison(
        self,
        primary_df: pl.DataFrame,
        trade_date: str,
        dataset: str,
    ) -> ReconciliationResult:
        """获取辅助数据源并执行对比."""
        tickers = primary_df["ticker"].unique().cast(pl.String).to_list()

        secondary_result = self._fetch_secondary(tickers, trade_date, dataset)
        if isinstance(secondary_result, ReconciliationResult):
            return secondary_result

        result = self._engine.check_cross_source(
            primary=primary_df,
            secondary=secondary_result,
            dataset=dataset,
        )

        comparison_df = self._convert_result_to_df(result, dataset)
        if not comparison_df.is_empty():
            self._comparison_store.write_comparison(trade_date, comparison_df, dataset)

        if result.issues:
            self._send_alerts(result, trade_date, dataset)

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
        """应用黄金数据集过滤."""
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
        """转换 DQResult -> DataFrame."""
        if not result.issues:
            return pl.DataFrame()

        rows: list[dict[str, object]] = []
        for issue in result.issues:
            for sample in issue.sample_data:
                row: dict[str, object] = {
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

    def _send_alerts(self, result: DQResult, trade_date: str, dataset: str) -> None:
        """发送告警."""
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
