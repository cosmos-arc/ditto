"""
BacktestService — Port 层回测编排服务.

编排 Core 层 EngineLoop 执行 + 审计收集 + 结果持久化。

职责:
  - 接收预配置的 EngineLoop 构造参数
  - 创建并管理 ExecutionAuditCollector 生命周期
  - 构建 EngineConfig / EngineOptions → EngineLoop
  - 运行引擎 → 生成 BacktestReport
  - 持久化审计日志 (via ExecutionAuditService)
  - 持久化回测产物 (via StrategyArtifactService)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ditto_core.backtest.audit import ExecutionAuditCollector
from ditto_core.backtest.data_feed import DataFeed
from ditto_core.backtest.engine import (
    EngineConfig,
    EngineLoop,
    EngineMode,
    EngineOptions,
)
from ditto_core.backtest.risk.post_trade import PostTradeRiskGuard
from ditto_core.backtest.risk.pre_trade import CompositePreTradeCheck
from ditto_core.backtest.statistics import BacktestReport, build_report
from ditto_core.execution.brokerage import Brokerage
from ditto_core.execution.planner import ExecutionPlanner
from ditto_core.execution.reality import FeeModel
from ditto_core.execution.rules import InstrumentRuleProvider
from ditto_core.strategy.pipeline import StrategyPipeline
from ditto_datahub.models.strategy import ArtifactKind, StrategyArtifactRecord
from ditto_datahub.services.audit import ExecutionAuditService
from ditto_datahub.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)

__all__ = ["BacktestService", "BacktestServiceConfig", "BacktestServiceOptions"]


# ---------------------------------------------------------------------------
# BacktestServiceConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BacktestServiceConfig:
    """
    BacktestService 配置 — frozen, 运行前确定.

    Attributes:
        strategy_id: 策略 ID
        run_id: 运行 ID (空字符串时由引擎自动生成)
        start_date: 起始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        initial_cash: 初始资金
        benchmark_id: 基准标的 ID (None = 无基准)
        rebalance_freq: 调仓频率 (daily / weekly / monthly)
        engine_version: 引擎版本号

    """

    strategy_id: str = "default"
    run_id: str = ""
    start_date: str = ""
    end_date: str = ""
    initial_cash: float = 1_000_000.0
    benchmark_id: str | None = None
    rebalance_freq: str = "daily"
    engine_version: str = "0.1.0"


# ---------------------------------------------------------------------------
# BacktestServiceOptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BacktestServiceOptions:
    """
    BacktestService 可选组件 — 将可选依赖打包以减少构造参数数量.

    Attributes:
        fee_model: 手续费模型 (用于 PreTrade 估算)
        rule_provider: 三层规则提供者 (用于 Planner 涨跌停/lot_size 检查)
        post_trade_guard: PostTrade 风控扫描器
        audit_service: 审计日志持久化服务
        artifact_service: 策略产物持久化服务

    """

    fee_model: FeeModel | None = None
    rule_provider: InstrumentRuleProvider | None = None
    post_trade_guard: PostTradeRiskGuard | None = None
    audit_service: ExecutionAuditService | None = None
    artifact_service: StrategyArtifactService | None = None


# ---------------------------------------------------------------------------
# BacktestService
# ---------------------------------------------------------------------------


class BacktestService:
    """
    Port 层回测编排服务.

    接收 EngineLoop 的构造参数 + 可选持久化服务，内部管理
    ExecutionAuditCollector 生命周期，编排完整回测流程:

    1. 创建 ExecutionAuditCollector
    2. 构建 EngineConfig + EngineOptions
    3. 构造 EngineLoop 并运行
    4. 从 collector 构建 BacktestReport
    5. 持久化审计日志 + 策略产物

    Parameters
    ----------
        config: 服务配置
        pipeline: 策略 Pipeline
        planner: 执行计划器
        brokerage: 经纪商
        pre_trade_check: 组合 PreTrade 校验
        data_feed: 市场数据源
        options: 可选组件 (费率模型、规则提供者、风控、持久化服务)

    """

    def __init__(
        self,
        config: BacktestServiceConfig,
        pipeline: StrategyPipeline,
        planner: ExecutionPlanner,
        brokerage: Brokerage,
        pre_trade_check: CompositePreTradeCheck,
        data_feed: DataFeed,
        options: BacktestServiceOptions = BacktestServiceOptions(),
    ) -> None:
        self._config = config
        self._pipeline = pipeline
        self._planner = planner
        self._brokerage = brokerage
        self._pre_trade_check = pre_trade_check
        self._data_feed = data_feed
        self._options = options

    def run(self) -> BacktestReport:
        """
        执行完整回测流程: 运行引擎 → 生成报告 → 持久化结果.

        Returns:
            BacktestReport 回测报告。

        """
        run_id = self._config.run_id

        # 1. 创建审计收集器
        collector = ExecutionAuditCollector()

        # 2. 构建 EngineConfig
        engine_config = EngineConfig(
            start_date=self._config.start_date,
            end_date=self._config.end_date,
            initial_cash=self._config.initial_cash,
            benchmark_id=self._config.benchmark_id,
            mode=EngineMode.BACKTEST,
            strategy_id=self._config.strategy_id,
            strategy_run_id=run_id,
            rebalance_freq=self._config.rebalance_freq,
            engine_version=self._config.engine_version,
        )

        # 3. 构建 EngineOptions (注入 audit_collector)
        options = EngineOptions(
            fee_model=self._options.fee_model,
            rule_provider=self._options.rule_provider,
            post_trade_guard=self._options.post_trade_guard,
            audit_collector=collector,
        )

        # 4. 构造并运行 EngineLoop
        engine_loop = EngineLoop(
            config=engine_config,
            pipeline=self._pipeline,
            planner=self._planner,
            brokerage=self._brokerage,
            pre_trade_check=self._pre_trade_check,
            data_feed=self._data_feed,
            options=options,
        )
        result = engine_loop.run()

        # 5. 使用实际 run_id (引擎可能自动生成)
        actual_run_id = result.run_id

        # 6. 构建 BacktestReport
        report = build_report(collector, run_id=actual_run_id)

        # 7. 持久化审计日志
        self._persist_audit(actual_run_id, report)

        # 8. 持久化策略产物
        self._persist_artifact(actual_run_id, report)

        return report

    # -- internal persistence ------------------------------------------------

    def _persist_audit(self, run_id: str, report: BacktestReport) -> None:
        """持久化审计日志到 ExecutionAuditService。"""
        if self._options.audit_service is None:
            return
        self._options.audit_service.save_risk_log(run_id, report.risk_log)
        self._options.audit_service.save_pre_trade_log(run_id, report.pre_trade_log)

    def _persist_artifact(self, run_id: str, report: BacktestReport) -> None:
        """持久化回测报告到 StrategyArtifactService。"""
        if self._options.artifact_service is None:
            return
        artifact = StrategyArtifactRecord(
            artifact_id=f"artifact-{run_id}",
            strategy_id=self._config.strategy_id,
            run_id=run_id,
            artifact_type=ArtifactKind.BACKTEST_REPORT,
            file_path="",  # TODO: serialize report to file
            metadata={
                "initial_cash": self._config.initial_cash,
                "final_nav": report.final_nav,
                "total_trades": report.aggregated_trade_stats.total_trades,
                "sharpe_ratio": report.alpha_stats.sharpe_ratio,
                "max_drawdown": report.alpha_stats.max_drawdown,
                "period_start": report.period[0],
                "period_end": report.period[1],
            },
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        self._options.artifact_service.save_artifact(artifact)
