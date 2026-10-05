"""数据源对账 Command — 跨源一致性校验的原子写操作."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import polars as pl
from ditto_data.quality.checkers.adjustment_events import (
    derive_event_adjustment_ratios,
    derive_factor_ratios,
)
from ditto_data.quality.golden import GoldenDatasetSpec
from ditto_data.quality.protocols import (
    AdjFactorReconcileContextProtocol,
    ComparisonStoreProtocol,
    ExDividendInstrumentSourceProtocol,
    InstrumentStoreProtocol,
    QualityEngineProtocol,
    SecondaryAdjustmentEventsSourceProtocol,
    SecondaryBarsSourceProtocol,
    SecondaryIdentityResolverProtocol,
)
from ditto_data.quality.quality_types import DQResult
from ditto_platform.foundation import logger

from ditto_application.exceptions import AppCommandError
from ditto_application.processes.quality.types import ReconciliationResult


@dataclass(frozen=True)
class ReconcileSourcesCommand:
    """数据源对账命令."""

    primary_df: pl.DataFrame
    trade_date: str
    dataset: str = "stock_daily"


class ReconcileSourcesHandler:
    """
    数据源对账 Command Handler — 跨源一致性校验.

    直接依赖 Protocol 实现（QualityEngine、辅源、ComparisonStore、
    InstrumentStore、辅源身份反解、除权日来源），编排
    enrich → filter → resolve → compare → write 的完整对账流程。

    #395 对账语义：比较键 instrument_id + trade_date（辅源帧经来源映射
    反解）；零交集 = 不可比较（passed=False，不算通过）；结果报告
    两侧数量/匹配数/主辅侧未匹配/重复键/差异数。
    """

    def __init__(  # noqa: PLR0913 — 协作端口按数据集一次注入，收拢对账编排
        self,
        engine: QualityEngineProtocol,
        secondary_source: SecondaryBarsSourceProtocol,
        comparison_store: ComparisonStoreProtocol,
        instrument_store: InstrumentStoreProtocol,
        secondary_identity_resolver: SecondaryIdentityResolverProtocol | None = None,
        ex_dividend_source: ExDividendInstrumentSourceProtocol | None = None,
        golden_dataset: GoldenDatasetSpec | None = None,
        secondary_events_source: SecondaryAdjustmentEventsSourceProtocol | None = None,
        adj_factor_context: AdjFactorReconcileContextProtocol | None = None,
    ) -> None:
        self._engine = engine
        self._secondary_source = secondary_source
        self._comparison_store = comparison_store
        self._instrument_store = instrument_store
        self._secondary_identity_resolver = secondary_identity_resolver
        self._ex_dividend_source = ex_dividend_source
        self._golden_dataset = golden_dataset
        self._secondary_events_source = secondary_events_source
        self._adj_factor_context = adj_factor_context

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

    # -- Private helpers (absorbed from QualityReconciliationService)

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
            raise AppCommandError("primary_df must contain 'instrument_id' column")

        primary_df = self._instrument_store.enrich_with_ticker(primary_df)

        if "ticker" not in primary_df.columns:
            raise AppCommandError("Failed to enrich primary_df with ticker")

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
        """获取辅助数据源、反解身份并执行 outer/anti 对比."""
        if dataset == "adj_factor":
            return self._execute_adj_factor_comparison(primary_df, trade_date, dataset)
        tickers = primary_df["ticker"].unique().cast(pl.String).to_list()

        secondary_result = self._fetch_secondary(tickers, trade_date, dataset)
        if isinstance(secondary_result, ReconciliationResult):
            return secondary_result
        secondary_df = secondary_result

        # 辅源帧（ticker 裸码）反解为 instrument_id：既有 fuyao 映射优先，
        # 缺失时按裸码前缀规则唯一匹配（只读，不写映射）。
        secondary_df = self._resolve_secondary_identities(secondary_df, trade_date)
        if secondary_df.is_empty() or "instrument_id" not in secondary_df.columns:
            return self._zero_intersection_result(
                trade_date, dataset, primary_df.height, secondary_df.height
            )

        context = self._comparison_context(trade_date)
        comparison = self._engine.compare_cross_source(
            primary=primary_df,
            secondary=secondary_df,
            dataset=dataset,
            context=context,
        )
        result = self._engine.check_cross_source(
            primary=primary_df,
            secondary=secondary_df,
            dataset=dataset,
            context=context,
        )

        comparison_df = self._convert_result_to_df(result, dataset, primary_df)
        if not comparison_df.is_empty():
            self._comparison_store.write_comparison(trade_date, comparison_df, dataset)

        if result.issues:
            self._send_alerts(result, trade_date, dataset)

        passed = comparison.comparable and not result.has_errors

        logger.info(
            "Daily reconciliation complete",
            event="reconciliation_complete",
            trade_date=trade_date,
            dataset=dataset,
            passed=passed,
            comparable=comparison.comparable,
            issue_count=len(result.issues),
            primary_count=comparison.primary_count,
            secondary_count=comparison.secondary_count,
            matched_count=comparison.matched_count,
            primary_unmatched_count=comparison.primary_unmatched_count,
            secondary_unmatched_count=comparison.secondary_unmatched_count,
            primary_duplicate_keys=comparison.primary_duplicate_keys,
            secondary_duplicate_keys=comparison.secondary_duplicate_keys,
            diff_count=comparison.diff_count,
        )

        return ReconciliationResult(
            trade_date=trade_date,
            dataset=dataset,
            passed=passed,
            issue_count=len(result.issues),
            comparable=comparison.comparable,
            primary_count=comparison.primary_count,
            secondary_count=comparison.secondary_count,
            matched_count=comparison.matched_count,
            primary_unmatched_count=comparison.primary_unmatched_count,
            secondary_unmatched_count=comparison.secondary_unmatched_count,
            primary_duplicate_keys=comparison.primary_duplicate_keys,
            secondary_duplicate_keys=comparison.secondary_duplicate_keys,
            diff_count=comparison.diff_count,
        )

    def _execute_adj_factor_comparison(
        self,
        primary_df: pl.DataFrame,
        trade_date: str,
        dataset: str,
    ) -> ReconciliationResult:
        """
        adj_factor 对账（#438）：事件流 vs 累积因子的同基准比例比较.

        不比较绝对因子（基期可能不同）：主源推 F(D)/F(prev)，事件按
        除权参考价公式推 prev_close/ref；缺前价/缺配股价等不可推导事件
        单列（field=event_underivable），零交集不可比较不算通过。
        """
        if self._secondary_events_source is None or self._adj_factor_context is None:
            raise AppCommandError(
                "adj_factor reconciliation requires events source and factor context"
            )

        events = self._secondary_events_source.fetch_adjustment_events(trade_date)
        if events.height == 0:
            logger.warning(
                "No secondary adjustment events found for comparison",
                event="reconciliation_no_secondary",
                trade_date=trade_date,
            )
            return ReconciliationResult(
                trade_date=trade_date,
                dataset=dataset,
                passed=False,
                issue_count=1,
                comparable=False,
                primary_count=primary_df.height,
                secondary_count=0,
            )
        events = self._resolve_secondary_identities(events, trade_date)
        if events.is_empty() or "instrument_id" not in events.columns:
            return self._zero_intersection_result(
                trade_date, dataset, primary_df.height, events.height
            )

        # 黄金集（或当日主源帧）限定比较范围：与 stock_daily 路径的
        # 过滤语义一致，未经允许的事件/因子变化行不参与本次对账。
        allowed_ids = primary_df["instrument_id"].unique().to_list()
        events = events.filter(pl.col("instrument_id").is_in(allowed_ids))
        if events.is_empty():
            return self._zero_intersection_result(
                trade_date, dataset, primary_df.height, 0
            )

        target = date.fromisoformat(trade_date)
        primary_cmp = derive_factor_ratios(
            self._adj_factor_context.factor_window(trade_date), target
        ).filter(pl.col("instrument_id").is_in(allowed_ids))
        secondary_cmp = derive_event_adjustment_ratios(
            events, self._adj_factor_context.previous_closes(trade_date)
        )
        # 可推导匹配数：两侧 adjustment_ratio 均非空的键交集。键匹配但
        # 全部不可推导时没有发生任何数值比较，不得报告 matched/通过。
        derivable_matches = (
            primary_cmp.filter(pl.col("adjustment_ratio").is_not_null())
            .join(
                secondary_cmp.filter(pl.col("adjustment_ratio").is_not_null()),
                on=["instrument_id", "trade_date"],
                how="inner",
            )
            .height
        )
        # 比较行全部落在事件日：差异行统一标记除权日，不与单位错误混排
        context = {
            "ex_dividend_instruments": frozenset(
                int(value) for value in secondary_cmp["instrument_id"].to_list()
            ),
        }
        comparison = self._engine.compare_cross_source(
            primary=primary_cmp,
            secondary=secondary_cmp,
            dataset=dataset,
            context=context,
        )
        result = self._engine.check_cross_source(
            primary=primary_cmp,
            secondary=secondary_cmp,
            dataset=dataset,
            context=context,
        )
        underivable = secondary_cmp.filter(pl.col("underivable_reason").is_not_null())

        frames = [
            frame
            for frame in (
                self._convert_result_to_df(result, dataset, primary_df),
                self._underivable_rows(underivable, dataset),
            )
            if frame.height
        ]
        comparison_df = (
            pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()
        )
        if not comparison_df.is_empty():
            self._comparison_store.write_comparison(trade_date, comparison_df, dataset)

        if result.issues:
            self._send_alerts(result, trade_date, dataset)

        comparable = comparison.comparable and derivable_matches > 0
        passed = comparable and not result.has_errors

        logger.info(
            "adj_factor reconciliation complete",
            event="reconciliation_complete",
            trade_date=trade_date,
            dataset=dataset,
            passed=passed,
            comparable=comparable,
            issue_count=len(result.issues),
            primary_count=comparison.primary_count,
            secondary_count=comparison.secondary_count,
            matched_count=derivable_matches,
            primary_unmatched_count=comparison.primary_unmatched_count,
            secondary_unmatched_count=comparison.secondary_unmatched_count,
            primary_duplicate_keys=comparison.primary_duplicate_keys,
            secondary_duplicate_keys=comparison.secondary_duplicate_keys,
            diff_count=comparison.diff_count,
            underivable_count=underivable.height,
        )

        # matched_count 报告实际完成数值比较的可推导匹配数：键级匹配中
        # 不可推导的部分单列为 secondary_underivable_count，不计入匹配，
        # 避免"零数值比较却报告通过"的错误匹配口径。
        return ReconciliationResult(
            trade_date=trade_date,
            dataset=dataset,
            passed=passed,
            issue_count=len(result.issues),
            comparable=comparable,
            primary_count=comparison.primary_count,
            secondary_count=comparison.secondary_count,
            matched_count=derivable_matches,
            primary_unmatched_count=comparison.primary_unmatched_count,
            secondary_unmatched_count=comparison.secondary_unmatched_count,
            primary_duplicate_keys=comparison.primary_duplicate_keys,
            secondary_duplicate_keys=comparison.secondary_duplicate_keys,
            diff_count=comparison.diff_count,
            secondary_underivable_count=underivable.height,
        )

    def _underivable_rows(
        self,
        underivable: pl.DataFrame,
        dataset: str,
    ) -> pl.DataFrame:
        """不可推导事件样本 → 对账落盘行（原因进 message，不伪造数值比较）."""
        if underivable.is_empty():
            return pl.DataFrame()
        return underivable.select(
            "instrument_id",
            "ticker",
            "trade_date",
            dataset=pl.lit(dataset),
            field=pl.lit("event_underivable"),
            primary_value=pl.lit(None, dtype=pl.Float64),
            secondary_value=pl.lit(None, dtype=pl.Float64),
            diff=pl.lit(None, dtype=pl.Float64),
            ex_dividend_day=pl.lit(True),
            severity=pl.lit("warning"),
            rule=pl.lit("cross_source_event_underivable"),
            message=pl.format(
                "辅源事件不可推导: kind={}, reason={}",
                pl.col("event_kind"),
                pl.col("underivable_reason"),
            ),
        )

    def _zero_intersection_result(
        self,
        trade_date: str,
        dataset: str,
        primary_count: int,
        secondary_count: int,
    ) -> ReconciliationResult:
        """辅源帧无法反解出任何身份：显式零交集不可比较（不算通过）."""
        logger.warning(
            "Secondary identities unresolved; comparison not comparable",
            event="reconciliation_zero_intersection",
            trade_date=trade_date,
            primary_count=primary_count,
            secondary_count=secondary_count,
        )
        return ReconciliationResult(
            trade_date=trade_date,
            dataset=dataset,
            passed=False,
            issue_count=1,
            comparable=False,
            primary_count=primary_count,
            secondary_count=secondary_count,
        )

    def _resolve_secondary_identities(
        self, secondary_df: pl.DataFrame, trade_date: str
    ) -> pl.DataFrame:
        """辅源帧 ticker → instrument_id（只读反解；无法唯一匹配的行剔除并计数）."""
        if (
            self._secondary_identity_resolver is None
            or "ticker" not in secondary_df.columns
            or secondary_df.is_empty()
        ):
            return secondary_df
        tickers = secondary_df["ticker"].unique().cast(pl.String).to_list()
        resolved = self._secondary_identity_resolver.resolve_secondary_ids(
            tickers, "fuyao", asof=trade_date
        )
        if not resolved:
            return secondary_df.clear()
        mapping_df = pl.DataFrame(
            {
                "ticker": list(resolved.keys()),
                "instrument_id": list(resolved.values()),
            },
            schema={"ticker": pl.String, "instrument_id": pl.Int64},
        )
        unresolved = (
            secondary_df.height
            - secondary_df.join(mapping_df, on="ticker", how="inner").height
        )
        if unresolved:
            logger.warning(
                "Secondary rows dropped with unresolved identities",
                event="reconciliation_secondary_unresolved",
                dropped_rows=unresolved,
                resolved_tickers=len(resolved),
            )
        return secondary_df.join(mapping_df, on="ticker", how="inner")

    def _comparison_context(self, trade_date: str) -> dict[str, object]:
        """构建比较上下文（除权日标的集合，缺失时空集不标记）."""
        if self._ex_dividend_source is None:
            return {}
        try:
            return {
                "ex_dividend_instruments": (
                    self._ex_dividend_source.ex_dividend_instruments(trade_date)
                )
            }
        except Exception as error:
            logger.warning(
                "Ex-dividend instrument lookup failed; diffs stay unflagged",
                event="reconciliation_ex_dividend_unavailable",
                error_type=type(error).__name__,
            )
            return {}

    def _fetch_secondary(
        self,
        tickers: list[str],
        trade_date: str,
        dataset: str,
    ) -> pl.DataFrame | ReconciliationResult:
        """获取辅助数据源。返回 DataFrame 或跳过结果."""
        secondary_df = self._secondary_source.fetch_stock_daily_bars(
            tickers, trade_date
        )

        if secondary_df.height == 0:
            logger.warning(
                "No secondary data found for comparison",
                event="reconciliation_no_secondary",
                trade_date=trade_date,
            )
            # 零辅源数据 = 零交集：不可比较，不算通过（旧语义的 skip 收紧）。
            return ReconciliationResult(
                trade_date=trade_date,
                dataset=dataset,
                passed=False,
                issue_count=1,
                comparable=False,
                primary_count=0,
                secondary_count=0,
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

    def _convert_result_to_df(
        self,
        result: DQResult,
        dataset: str,
        primary_df: pl.DataFrame,
    ) -> pl.DataFrame:
        """转换 DQResult → DataFrame（落盘列与 CLI 输出同步）。"""
        if not result.issues:
            return pl.DataFrame()

        ticker_by_id: dict[int, str] = {}
        if "ticker" in primary_df.columns and "instrument_id" in primary_df.columns:
            ticker_by_id = {
                instrument_id: ticker
                for row in primary_df.select("instrument_id", "ticker")
                .unique(subset=["instrument_id"])
                .to_dicts()
                if isinstance(instrument_id := row["instrument_id"], int)
                and isinstance(ticker := row["ticker"], str)
            }
        rows: list[dict[str, object]] = []
        for issue in result.issues:
            for sample in issue.sample_data:
                sample_instrument_id = sample.get("instrument_id")
                sample_ticker = (
                    ticker_by_id.get(sample_instrument_id, "")
                    if isinstance(sample_instrument_id, int)
                    else ""
                )
                rows.append(
                    {
                        "dataset": dataset,
                        "instrument_id": sample_instrument_id,
                        "ticker": sample_ticker,
                        "trade_date": sample.get("trade_date", ""),
                        "field": sample.get("field", ""),
                        "primary_value": sample.get("primary_value", ""),
                        "secondary_value": sample.get("secondary_value", ""),
                        "diff": sample.get("diff", ""),
                        "ex_dividend_day": bool(sample.get("ex_dividend_day", False)),
                        "severity": issue.severity.value,
                        "rule": issue.rule_name,
                        "message": issue.message,
                    }
                )
            if not issue.sample_data and issue.rule_name != "cross_source_compare":
                # 无样本的结构性发现（零交集/重复键）单独落一行
                rows.append(
                    {
                        "dataset": dataset,
                        "instrument_id": None,
                        "ticker": "",
                        "trade_date": "",
                        "field": "",
                        "primary_value": "",
                        "secondary_value": "",
                        "diff": "",
                        "ex_dividend_day": False,
                        "severity": issue.severity.value,
                        "rule": issue.rule_name,
                        "message": issue.message,
                    }
                )

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
