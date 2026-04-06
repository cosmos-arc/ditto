"""
回测编排服务 — Process 模块.

包含 BacktestService 及其配置类，负责编排完整回测流程：
引擎运行 → 报告生成 → 审计日志持久化 → 策略产物持久化。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from ditto_data.models.strategy import ArtifactKind, StrategyArtifactRecord
from ditto_data.models.strategy_audit import (
    PreTradeDecisionPayload,
    RiskScanPayload,
)
from ditto_data.services.audit import ExecutionAuditService
from ditto_data.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_engine.alpha.pipeline import StrategyPipeline
from ditto_engine.backtest.audit import ExecutionAuditCollector
from ditto_engine.backtest.data_feed import DataFeed
from ditto_engine.backtest.engine import (
    EngineConfig,
    EngineLoop,
    EngineMode,
    EngineOptions,
)
from ditto_engine.backtest.manifest import RunManifest
from ditto_engine.backtest.statistics import (
    BacktestReport,
    build_report,
)
from ditto_engine.execution.brokerage import Brokerage
from ditto_engine.execution.planner import ExecutionPlanner
from ditto_engine.execution.reality import FeeModel
from ditto_engine.execution.rules import InstrumentRuleProvider
from ditto_engine.risk.post_trade import PostTradeRiskGuard
from ditto_engine.risk.pre_trade import CompositePreTradeCheck
from ditto_kernel.clock import SimulatedClock
from ditto_kernel.events import SimpleEventBus
from ditto_kernel.identity import InstrumentId

from ditto_app.process.strategy_types import (
    RunLifecycleService,
    write_backtest_artifacts,
)

__all__ = [
    "BacktestService",
    "BacktestServiceConfig",
    "BacktestServiceOptions",
]


# ---------------------------------------------------------------------------
# BacktestServiceConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BacktestServiceConfig:
    """
    BacktestService 配置 — frozen, 运行前确定.

    Attributes:
        strategy_id: 策略 ID
        strategy_version: 策略版本
        run_id: 运行 ID (空字符串时由服务预生成并传给引擎)
        start_date: 起始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        initial_cash: 初始资金
        benchmark_id: 基准标的 ID (None = 无基准)
        parameter_overrides: 参数覆盖列表
        rebalance_freq: 调仓频率 (daily / weekly / monthly)
        engine_version: 引擎版本号

    """

    strategy_id: str = "default"
    strategy_version: str = ""
    run_id: str = ""
    start_date: str = ""
    end_date: str = ""
    initial_cash: float = 1_000_000.0
    benchmark_id: InstrumentId | None = None
    parameter_overrides: tuple[str, ...] = ()
    rebalance_freq: str = "daily"
    engine_version: str = "0.1.0"


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
        artifact_dir: 回测产物序列化输出目录 (None = 使用默认临时目录)
        run_service: 策略运行生命周期服务 (None = 跳过生命周期管理)

    """

    fee_model: FeeModel | None = None
    rule_provider: InstrumentRuleProvider | None = None
    post_trade_guard: PostTradeRiskGuard | None = None
    audit_service: ExecutionAuditService | None = None
    artifact_service: StrategyArtifactService | None = None
    artifact_dir: str | None = None
    display_map: dict[InstrumentId, str] | None = None
    run_service: RunLifecycleService | None = None


# ---------------------------------------------------------------------------
# BacktestService
# ---------------------------------------------------------------------------


class BacktestService:
    """
    App 层回测编排服务.

    接收 EngineLoop 的构造参数 + 可选持久化服务，内部管理
    ExecutionAuditCollector 生命周期，编排完整回测流程:

    1. (可选) 创建策略运行记录
    2. 创建 ExecutionAuditCollector
    3. 构建 EngineConfig + EngineOptions
    4. 构造 EngineLoop 并运行
    5. 从 collector 构建 BacktestReport
    6. 持久化审计日志 + 策略产物
    7. (可选) 更新运行状态 (completed / failed)

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
        run_id = self._resolve_run_id()
        run_svc = self._options.run_service

        # 1. (可选) 创建运行记录
        if run_svc is not None:
            run_svc.create_run(
                run_id=run_id,
                strategy_id=self._config.strategy_id,
                strategy_version=self._config.strategy_version,
                mode="backtest",
            )
            run_svc.mark_running(run_id)

        try:
            return self._execute_backtest(run_id)
        except Exception as exc:
            if run_svc is not None:
                run_svc.mark_failed(run_id, str(exc))
            raise

    def _execute_backtest(self, run_id: str) -> BacktestReport:
        """执行回测核心逻辑。"""
        # 创建审计收集器
        collector = ExecutionAuditCollector()

        # 构建 EngineConfig
        engine_config = EngineConfig(
            start_date=self._config.start_date,
            end_date=self._config.end_date,
            initial_cash=self._config.initial_cash,
            benchmark_id=self._config.benchmark_id,
            mode=EngineMode.BACKTEST,
            strategy_id=self._config.strategy_id,
            strategy_version=self._config.strategy_version,
            strategy_run_id=run_id,
            parameter_overrides=self._config.parameter_overrides,
            rebalance_freq=self._config.rebalance_freq,
            engine_version=self._config.engine_version,
        )

        # 构造 SimulatedClock — 以回测起始日期为初始时刻
        _start = date.fromisoformat(self._config.start_date)
        clock = SimulatedClock(
            initial=datetime(_start.year, _start.month, _start.day, tzinfo=UTC),
        )

        # 构建 EngineOptions (注入 clock + event_bus + audit_collector)
        options = EngineOptions(
            clock=clock,
            event_bus=SimpleEventBus(),
            fee_model=self._options.fee_model,
            rule_provider=self._options.rule_provider,
            post_trade_guard=self._options.post_trade_guard,
            audit_collector=collector,
        )

        # 构造并运行 EngineLoop
        engine_loop = EngineLoop(
            config=engine_config,
            pipeline=self._pipeline,
            planner=self._planner,
            brokerage=self._brokerage,
            pre_trade_check=self._pre_trade_check,
            data_feed=self._data_feed,
            options=options,
        )
        engine_result = engine_loop.run()

        # 构建 BacktestReport
        report = build_report(collector, run_id=run_id)

        # 持久化审计日志
        self._persist_audit(run_id, report)

        # 持久化策略产物
        self._persist_artifact(run_id, report, manifest=engine_result.manifest)

        # 更新运行状态
        run_svc = self._options.run_service
        if run_svc is not None:
            run_svc.mark_completed(run_id)

        return report

    def _resolve_run_id(self) -> str:
        """在进入生命周期编排前固化 run_id。"""
        configured_run_id = self._config.run_id
        if configured_run_id:
            return configured_run_id
        return uuid.uuid4().hex[:8]

    # -- internal persistence ------------------------------------------------

    def _persist_audit(self, run_id: str, report: BacktestReport) -> None:
        """
        持久化审计日志到 ExecutionAuditService。

        App 层负责将 Core record 转换为 Data 本地 DTO。
        """
        if self._options.audit_service is None:
            return
        risk_payloads = tuple(
            RiskScanPayload(
                trade_date=r.trade_date,
                rule_id=r.rule_id,
                instrument_id=(
                    int(r.instrument_id) if r.instrument_id is not None else None
                ),
                scope=r.scope,
                severity=str(r.severity),
                action_taken=str(r.action_taken),
                detail=r.detail,
                current_value=r.current_value,
                threshold=r.threshold,
            )
            for r in report.risk_log
        )
        pre_trade_payloads = tuple(
            PreTradeDecisionPayload(
                trade_date=r.trade_date,
                order_id=r.order_id,
                instrument_id=int(r.instrument_id),
                direction=r.direction,
                original_quantity=r.original_quantity,
                final_quantity=r.final_quantity,
                decision=r.decision,
                reason=r.reason,
                check_sequence=r.check_sequence,
            )
            for r in report.pre_trade_log
        )
        self._options.audit_service.save_risk_log(run_id, risk_payloads)
        self._options.audit_service.save_pre_trade_log(run_id, pre_trade_payloads)

    def _persist_artifact(
        self,
        run_id: str,
        report: BacktestReport,
        manifest: RunManifest | None = None,
    ) -> None:
        """持久化回测报告到磁盘 + StrategyArtifactService。"""
        if self._options.artifact_service is None:
            return

        # 始终将产物序列化到磁盘
        output_dir: Path | None = None
        if self._options.artifact_dir is not None:
            output_dir = Path(self._options.artifact_dir) / run_id

        written = write_backtest_artifacts(
            report,
            output_dir=output_dir,
            manifest=manifest,
            display_map=self._options.display_map,
        )
        file_path = str(written.get("backtest_report", ""))

        artifact = StrategyArtifactRecord(
            artifact_id=f"artifact-{run_id}",
            strategy_id=self._config.strategy_id,
            run_id=run_id,
            artifact_type=ArtifactKind.BACKTEST_REPORT,
            file_path=file_path,
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
