"""质量巡检服务 — L3 批量统计检查."""

from __future__ import annotations

__all__ = [
    "QualityPatrolService",
]

from datetime import datetime, timedelta
from typing import Literal

import polars as pl
import polars.exceptions as pl_exceptions
from ditto_data.quality.protocols import QualityEngineProtocol
from ditto_infra.foundation import logger
from ditto_infra.services.notification import AlertManager, alert_dq_failure
from ditto_kernel.quality import DQIssue, DQResult

from ditto_app.query.market import MarketQueryFacade
from ditto_app.query.metadata import MetadataQueryFacade

_CALENDAR_BUFFER_MULTIPLIER = 2  # 周末/假日缓冲系数

# ---------------------------------------------------------------------------
# L3 批量统计检查
# ---------------------------------------------------------------------------

# NOTE: L3CheckResult 临时从 ditto_kernel.quality 导入（Phase D 清理）。
from ditto_kernel.quality import L3CheckResult  # noqa: E402


class QualityPatrolService:
    """
    质量巡检服务（原 L3BatchService）.

    应用层：编排 L3 统计异常检查。
    通过 facade 获取历史数据并注入核心引擎。
    """

    def __init__(
        self,
        engine: QualityEngineProtocol,
        market_facade: MarketQueryFacade,
        metadata_facade: MetadataQueryFacade,
        alert_manager: AlertManager | None = None,
    ) -> None:
        """
        初始化质量巡检服务.

        Args:
            engine: 质量引擎实例
            market_facade: 行情查询 facade，用于数据访问
            metadata_facade: 元数据查询 facade，用于数据访问
            alert_manager: 告警管理器，可选。未配置时退化为日志告警。

        """
        self._engine = engine
        self._market_facade = market_facade
        self._metadata_facade = metadata_facade
        self._alert_manager = alert_manager

    def check_dataset(
        self,
        dataset: str,
        trade_date: str,
        asset_class: Literal["stock", "etf", "index"] | None = None,
        market_wide: bool = False,
    ) -> L3CheckResult:
        """
        对数据集执行 L3 检查.

        Args:
            dataset: 数据集标识
            trade_date: 待检查的交易日期（YYYY-MM-DD）
            asset_class: 资产类别，用于全市场查询
            market_wide: 是否使用全市场查询模式

        Returns:
            检查结果摘要

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
    ) -> L3CheckResult:
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
        return L3CheckResult(
            dataset=dataset,
            trade_date=trade_date,
            passed=False,
            issue_count=0,
            error=f"{type(error).__name__}: {error!s}",
        )

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
    ) -> L3CheckResult:
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

        return L3CheckResult(
            dataset=dataset,
            trade_date=trade_date,
            passed=result.passed,
            issue_count=len(result.issues),
            alert_count=result.alert_count,
            issues=tuple(result.issues),
        )

    def _fetch_data(
        self,
        trade_date: str,
        window: int = 120,
        asset_class: Literal["stock", "etf", "index"] | None = None,
        market_wide: bool = False,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        """
        通过 MarketQueryFacade 获取历史和当前数据.

        Args:
            trade_date: 交易日期（YYYY-MM-DD）
            window: 历史数据的回溯窗口（天）
            asset_class: 资产类别过滤
            market_wide: 全市场查询模式

        Returns:
            元组 (historical_df, current_df)

        """
        # 计算包含周末/假日缓冲的起始日期
        trade_dt = datetime.fromisoformat(trade_date)
        start_dt = trade_dt - timedelta(days=window * _CALENDAR_BUFFER_MULTIPLIER)
        start_date = start_dt.strftime("%Y-%m-%d")

        # end=trade_date 包含当日数据（与 current 重叠），这是预存行为。
        # 引擎内部使用 historical 构建参考分布时需排除 current 行。
        # 注: end=trade_date 前一天可避免参考分布污染，但需引擎侧同步调整，
        # 暂保持当前行为以确保回测一致性。
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
        通过 MetadataQueryFacade 获取交易日历.

        Args:
            trade_date: 交易日期（YYYY-MM-DD）
            lookback_days: 回溯天数

        Returns:
            交易日历 DataFrame

        """
        # 计算起始日期
        trade_dt = datetime.fromisoformat(trade_date)
        start_dt = trade_dt - timedelta(
            days=lookback_days * _CALENDAR_BUFFER_MULTIPLIER,
        )
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
        发送 DQ 告警通知.

        通过 AlertManager 发送多渠道告警；未配置时退化为日志记录。

        Args:
            trade_date: 交易日期
            dataset: 数据集名称
            issues: DQ 问题列表

        """
        failed_rules = [i.rule_name for i in issues]
        logger.warning(
            "DQ alert notification",
            event="dq_alert",
            trade_date=trade_date,
            dataset=dataset,
            issue_count=len(issues),
        )
        if self._alert_manager is None:
            return
        alert_dq_failure(
            manager=self._alert_manager,
            dataset=dataset,
            trade_date=trade_date,
            failed_rules=failed_rules,
            error_count=len(issues),
        )
