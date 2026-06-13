"""
回测编排服务 — Process 模块.

包含 BacktestService 及其配置类，负责编排完整回测流程：
引擎运行 → 报告生成 → 审计日志持久化 → 策略产物持久化。

审计持久化逻辑委托给 backtest_audit 模块，
因子 bundle 构建委托给 factor_bridge 模块。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import orjson
from ditto_backtest.audit import ExecutionAuditCollector
from ditto_backtest.config import EngineConfig, EngineMode
from ditto_backtest.data_feed import DataFeed
from ditto_backtest.engine import (
    EngineLoop,
    EngineLoopDeps,
    EngineOptions,
    EngineResult,
)
from ditto_backtest.manifest import RunManifest
from ditto_backtest.result import BacktestCheckpoint, BacktestRuntimeStateSnapshot
from ditto_backtest.simulation import SlippageModel
from ditto_backtest.statistics import (
    BacktestReport,
    build_report,
)
from ditto_backtest.steps import StepContext
from ditto_backtest.synchronizer import BacktestSynchronizer
from ditto_data.lineage.contracts import DataLineageRecorder
from ditto_execution.audit import ExecutionAuditService
from ditto_execution.brokerage import Brokerage
from ditto_execution.planner import ExecutionPlanner
from ditto_kernel.clock import SimulatedClock
from ditto_kernel.events import SimpleEventBus
from ditto_kernel.identity import InstrumentId
from ditto_kernel.time_semantics import DEFAULT_PIT_TIME_COLUMN, PIT_POLICY_FAIL_CLOSED
from ditto_kernel.trading import FeeModel, InstrumentRuleProvider
from ditto_risk.post_trade import PostTradeRiskGuard
from ditto_risk.pre_trade import CompositePreTradeCheck
from ditto_strategy.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from ditto_strategy.runs.models import StrategyRunCheckpointRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunCheckpointWriterProtocol,
)

from ditto_application.config import DEFAULT_INITIAL_CASH
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.backtest_audit import (
    ArtifactPersistConfig,
    ArtifactPersistContext,
    persist_artifact,
    persist_audit,
    resolve_run_id,
)
from ditto_application.processes.execution.backtest_lineage import (
    record_backtest_lineage,
)
from ditto_application.processes.execution.backtest_process_types import (
    BacktestLineageConfig,
)
from ditto_application.processes.execution.factor_bridge import (
    CompiledExpressions,
    FactorBridge,
    build_factor_aware_bundle_builder,
)
from ditto_application.processes.execution.strategy_input import (
    write_backtest_artifacts,
)
from ditto_application.processes.execution.strategy_types import (
    RunLifecycleService,
    mark_run_failed,
)

# re-export for test monkeypatch compatibility
_ = write_backtest_artifacts

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
        parent_run_id: 父运行 ID（用于重试/衍生场景）
        execution_delay: 信号延迟执行天数
        resume_*: checkpoint-backed resume state evidence

    """

    strategy_id: str = "default"
    strategy_version: str = ""
    run_id: str = ""
    parent_run_id: str = ""
    start_date: str = ""
    end_date: str = ""
    initial_cash: float = DEFAULT_INITIAL_CASH
    benchmark_id: InstrumentId | None = None
    parameter_overrides: tuple[str, ...] = ()
    rebalance_freq: str = "daily"
    engine_version: str = "0.1.0"
    execution_delay: int = 0
    resume_from_run_id: str = ""
    resume_checkpoint_trade_date: str = ""
    resume_checkpoint_completed_days: int = 0
    resume_checkpoint_total_days: int = 0
    resume_checkpoint_nav: float = 0.0
    resume_checkpoint_order_count: int = 0
    resume_checkpoint_fill_count: int = 0
    resume_account_state_json: str = ""
    resume_account_state_hash: str = ""
    resume_settlement_state_json: str = ""
    resume_settlement_state_hash: str = ""
    resume_runtime_state_json: str = ""
    resume_runtime_state_hash: str = ""


@dataclass(frozen=True)
class BacktestServiceOptions:
    """
    BacktestService 可选组件 — 将可选依赖打包以减少构造参数数量.

    Attributes:
        fee_model: 手续费模型 (用于 PreTrade 估算)
        slippage_model: 滑点模型 (None = 引擎默认)
        rule_provider: 三层规则提供者 (用于 Planner 涨跌停/lot_size 检查)
        post_trade_guard: PostTrade 风控扫描器
        audit_service: 审计日志持久化服务
        artifact_service: 策略产物持久化服务
        artifact_dir: 回测产物序列化输出目录 (None = 使用默认临时目录)
        run_service: 策略运行生命周期服务 (None = 跳过生命周期管理)
        checkpoint_writer: 策略运行 checkpoint 写入端口 (None = 跳过恢复点持久化)
        compiled_expressions: 编译后的因子表达式 (None = 使用默认信号)
        lineage_recorder: 数据血缘记录器 (None = 跳过 lineage 记录)
        allow_experimental_data: 是否显式允许 experimental 数据集进入运行时
        restore_runtime_state: 已解析的 checkpoint runtime-state

    """

    fee_model: FeeModel | None = None
    slippage_model: SlippageModel | None = None
    rule_provider: InstrumentRuleProvider | None = None
    post_trade_guard: PostTradeRiskGuard | None = None
    audit_service: ExecutionAuditService | None = None
    artifact_service: StrategyArtifactService | None = None
    artifact_dir: str | None = None
    display_map: dict[InstrumentId, str] | None = None
    run_service: RunLifecycleService | None = None
    checkpoint_writer: StrategyRunCheckpointWriterProtocol | None = None
    compiled_expressions: CompiledExpressions | None = None
    lineage_recorder: DataLineageRecorder | None = None
    allow_experimental_data: bool = False
    restore_runtime_state: BacktestRuntimeStateSnapshot | None = None


def _assert_resume_hash(*, label: str, expected: str, actual: str) -> None:
    """Validate optional checkpoint hash evidence when provided."""
    if expected and expected != actual:
        msg = f"{label} mismatch: expected {expected}, got {actual}"
        raise AppProcessError(msg)


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

        # 1. (可选) 创建运行记录（get_or_create 语义，保留 API 预写入的 config_json）
        if run_svc is not None:
            existing = run_svc.get_run(run_id)
            if existing is None:
                config_json = orjson.dumps(
                    {
                        "start_date": self._config.start_date,
                        "end_date": self._config.end_date,
                        "initial_cash": self._config.initial_cash,
                        "benchmark_id": self._config.benchmark_id,
                        "parameter_overrides": list(self._config.parameter_overrides),
                        "rebalance_freq": self._config.rebalance_freq,
                        "execution_delay": self._config.execution_delay,
                        "resume_from_run_id": self._config.resume_from_run_id,
                        "resume_checkpoint_trade_date": (
                            self._config.resume_checkpoint_trade_date
                        ),
                        "resume_checkpoint_completed_days": (
                            self._config.resume_checkpoint_completed_days
                        ),
                        "resume_checkpoint_total_days": (
                            self._config.resume_checkpoint_total_days
                        ),
                        "resume_checkpoint_nav": self._config.resume_checkpoint_nav,
                        "resume_checkpoint_order_count": (
                            self._config.resume_checkpoint_order_count
                        ),
                        "resume_checkpoint_fill_count": (
                            self._config.resume_checkpoint_fill_count
                        ),
                        "resume_account_state_json": (
                            self._config.resume_account_state_json
                        ),
                        "resume_account_state_hash": (
                            self._config.resume_account_state_hash
                        ),
                        "resume_settlement_state_json": (
                            self._config.resume_settlement_state_json
                        ),
                        "resume_settlement_state_hash": (
                            self._config.resume_settlement_state_hash
                        ),
                        "resume_runtime_state_json": (
                            self._config.resume_runtime_state_json
                        ),
                        "resume_runtime_state_hash": (
                            self._config.resume_runtime_state_hash
                        ),
                        "allow_experimental_data": (
                            self._options.allow_experimental_data
                        ),
                        "pit_policy": PIT_POLICY_FAIL_CLOSED,
                        "pit_time_column": DEFAULT_PIT_TIME_COLUMN,
                        "unsafe_time_policy": "",
                    },
                ).decode()
                run_svc.create_run(
                    run_id=run_id,
                    strategy_id=self._config.strategy_id,
                    strategy_version=self._config.strategy_version,
                    mode=EngineMode.BACKTEST.value,
                    parent_run_id=self._config.parent_run_id,
                    config_json=config_json,
                )
            run_svc.mark_running(run_id)

        try:
            return self._execute_backtest(run_id)
        except Exception as exc:
            mark_run_failed(run_svc, run_id, exc)
            raise

    def _execute_backtest(self, run_id: str) -> BacktestReport:
        """执行回测核心逻辑。"""
        collector = ExecutionAuditCollector()
        engine_config = self._build_engine_config(run_id)
        options = self._build_engine_options(run_id, collector)

        # 构造 Synchronizer + EngineLoop
        clock = self._build_clock()
        synchronizer = BacktestSynchronizer(
            data_feed=self._data_feed,
            clock=clock,
            start_date=self._config.start_date,
        )
        engine_loop = EngineLoop(
            config=engine_config,
            deps=EngineLoopDeps(
                pipeline=self._pipeline,
                planner=self._planner,
                brokerage=self._brokerage,
                pre_trade_check=self._pre_trade_check,
                data_feed=self._data_feed,
                synchronizer=synchronizer,
                options=options,
            ),
        )
        t0 = time.monotonic()
        engine_result = engine_loop.run()
        elapsed = time.monotonic() - t0

        # 回测指标记录（application 桥接 backtest → platform Metrics）
        try:
            from ditto_platform.foundation import Metrics as _Metrics  # noqa: PLC0415

            _Metrics.backtest_duration.record(elapsed)
            _Metrics.backtest_trading_days.add(
                engine_result.total_trades + len(engine_result.skipped_dates)
            )
        except Exception:  # noqa: S110
            pass  # 指标记录不阻断主流程

        # 构建 BacktestReport
        report = build_report(collector, run_id=run_id)

        # 持久化 + 更新状态
        self._post_process(run_id, report, engine_result)

        return report

    def _build_clock(self) -> SimulatedClock:
        """构造回测模拟时钟。"""
        _start = date.fromisoformat(self._config.start_date)
        return SimulatedClock(
            initial=datetime(_start.year, _start.month, _start.day, tzinfo=UTC),
        )

    def _build_engine_config(self, run_id: str) -> EngineConfig:
        """从服务配置构建 EngineConfig。"""
        return EngineConfig(
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
            execution_delay=self._config.execution_delay,
        )

    def _build_engine_options(
        self,
        run_id: str,
        collector: ExecutionAuditCollector,
    ) -> EngineOptions:
        """构建 EngineOptions — 含 event_bus/cancel/progress 回调。"""
        # 构建自定义 input_bundle_builder (含因子信号注入)
        compiled = self._options.compiled_expressions
        input_bundle_builder = (
            self._build_factor_aware_bundle_builder(compiled, run_id=run_id)
            if compiled is not None
            else None
        )

        run_svc = self._options.run_service

        # 协作式取消 — 轮询 run_service.is_cancelled()
        should_stop: Callable[[], bool] | None = None
        if run_svc is not None:

            def _check_cancelled() -> bool:
                return run_svc.is_cancelled(run_id)

            should_stop = _check_cancelled

        # 进度上报 — 每日更新 run_service
        on_progress: Callable[[int, int], None] | None = None
        if run_svc is not None:

            def _report_progress(completed: int, total: int) -> None:
                pct = round(completed / total * 100, 1) if total > 0 else 0.0
                run_svc.update_progress(
                    run_id,
                    progress_pct=pct,
                    current_step="engine",
                    completed_days=completed,
                    total_days=total,
                )

            on_progress = _report_progress

        # checkpoint 持久化 — 引擎保持 storage-free，由 App 层写入运行控制面。
        checkpoint_writer = self._options.checkpoint_writer
        on_checkpoint: Callable[[BacktestCheckpoint], None] | None = None
        if checkpoint_writer is not None:

            def _save_checkpoint(checkpoint: BacktestCheckpoint) -> None:
                checkpoint_writer.save_checkpoint(
                    StrategyRunCheckpointRecord(
                        run_id=run_id,
                        strategy_id=self._config.strategy_id,
                        strategy_version=self._config.strategy_version,
                        mode=EngineMode.BACKTEST.value,
                        completed_trade_date=checkpoint.completed_trade_date,
                        resume_from=checkpoint.resume_from,
                        completed_days=checkpoint.completed_days,
                        total_days=checkpoint.total_days,
                        nav=checkpoint.nav,
                        order_count=checkpoint.order_count,
                        fill_count=checkpoint.fill_count,
                        account_state_json=checkpoint.account_state_json,
                        account_state_hash=checkpoint.account_state_hash,
                        settlement_state_json=checkpoint.settlement_state_json,
                        settlement_state_hash=checkpoint.settlement_state_hash,
                        runtime_state_json=checkpoint.runtime_state_json,
                        runtime_state_hash=checkpoint.runtime_state_hash,
                    )
                )

            on_checkpoint = _save_checkpoint

        # Step 完成回调 — 桥接到 platform Metrics
        on_step_complete: Callable[[str, float, bool], None] | None = None
        try:
            from ditto_platform.foundation import (  # noqa: PLC0415
                Metrics as _StepMetrics,
            )

            def _on_step_complete(
                step_name: str,
                duration: float,
                success: bool,
            ) -> None:
                _StepMetrics.backtest_step_duration.record(
                    duration,
                    {"step": step_name},
                )
                if not success:
                    _StepMetrics.backtest_step_failures.add(
                        1,
                        {"step": step_name},
                    )

            on_step_complete = _on_step_complete
        except Exception:  # noqa: S110
            pass  # Metrics 不可用时静默跳过

        return EngineOptions(
            event_bus=SimpleEventBus(),
            fee_model=self._options.fee_model,
            rule_provider=self._options.rule_provider,
            post_trade_guard=self._options.post_trade_guard,
            audit_collector=collector,
            input_bundle_builder=input_bundle_builder,
            should_stop=should_stop,
            on_progress=on_progress,
            on_checkpoint=on_checkpoint,
            restore_runtime_state=self._restore_runtime_state(),
            on_step_complete=on_step_complete,
        )

    def _restore_runtime_state(self) -> BacktestRuntimeStateSnapshot | None:
        """Load and verify checkpoint runtime-state evidence from config/options."""
        if self._options.restore_runtime_state is not None:
            return self._options.restore_runtime_state
        if not self._config.resume_runtime_state_json:
            return None
        try:
            snapshot = BacktestRuntimeStateSnapshot.from_json(
                self._config.resume_runtime_state_json,
            )
        except ValueError as exc:
            msg = "Invalid resume_runtime_state_json"
            raise AppProcessError(msg) from exc
        _assert_resume_hash(
            label="resume_runtime_state_hash",
            expected=self._config.resume_runtime_state_hash,
            actual=snapshot.state_hash,
        )
        return snapshot

    def _post_process(
        self,
        run_id: str,
        report: BacktestReport,
        engine_result: EngineResult,
    ) -> None:
        """持久化审计/产物 + 更新运行状态。"""
        self._persist_audit(run_id, report)
        self._persist_artifact(run_id, report, manifest=engine_result.manifest)
        self._record_lineage(run_id, manifest=engine_result.manifest)

        run_svc = self._options.run_service
        if run_svc is not None:
            if engine_result.cancelled:
                run_svc.mark_cancelled(run_id)
            else:
                run_svc.mark_completed(run_id)

    def _build_factor_aware_bundle_builder(
        self,
        compiled: CompiledExpressions,
        *,
        run_id: str,
    ) -> Callable[[StepContext], StrategyInputBundle]:
        """
        构建含因子信号注入的 input_bundle_builder。委托给 factor_bridge 模块。

        Args:
            compiled: 编译后的因子表达式。
            run_id: 由 run() 统一生成的运行标识，确保 bundle.run_id 与 run record 一致。

        """
        return build_factor_aware_bundle_builder(
            bridge=FactorBridge(),
            compiled=compiled,
            data_feed=self._data_feed,
            strategy_id=self._config.strategy_id,
            run_id=run_id,
        )

    def _record_lineage(
        self,
        run_id: str,
        *,
        manifest: RunManifest | None,
    ) -> None:
        """Record data lineage for a completed backtest run."""
        record_backtest_lineage(
            recorder=self._options.lineage_recorder,
            run_id=run_id,
            config=BacktestLineageConfig(
                strategy_id=self._config.strategy_id,
                strategy_version=self._config.strategy_version,
                start_date=self._config.start_date,
                end_date=self._config.end_date,
            ),
            manifest=manifest,
        )

    def _resolve_run_id(self) -> str:
        """在进入生命周期编排前固化 run_id。"""
        return resolve_run_id(self._config.run_id)

    # -- internal persistence ------------------------------------------------

    def _persist_audit(self, run_id: str, report: BacktestReport) -> None:
        """持久化审计日志到 ExecutionAuditService。委托给 backtest_audit 模块。"""
        if self._options.audit_service is None:
            return
        persist_audit(run_id, report, self._options.audit_service)

    def _persist_artifact(
        self,
        run_id: str,
        report: BacktestReport,
        manifest: RunManifest | None = None,
    ) -> None:
        """持久化回测报告到磁盘 + StrategyArtifactService。"""
        if self._options.artifact_service is None:
            return
        persist_artifact(
            ArtifactPersistContext(
                run_id=run_id,
                report=report,
                manifest=manifest,
                resume_provenance=_resume_provenance_from_config(self._config),
            ),
            ArtifactPersistConfig(
                strategy_id=self._config.strategy_id,
                initial_cash=self._config.initial_cash,
                rebalance_freq=self._config.rebalance_freq,
                artifact_service=self._options.artifact_service,
                write_fn=write_backtest_artifacts,
                artifact_dir=self._options.artifact_dir,
                display_map=self._options.display_map,
            ),
        )


def _resume_provenance_from_config(
    config: BacktestServiceConfig,
) -> dict[str, object] | None:
    """Build normalized checkpoint provenance for restored child-run artifacts."""
    if not config.resume_from_run_id:
        return None
    return {
        "from_run_id": config.resume_from_run_id,
        "checkpoint_trade_date": config.resume_checkpoint_trade_date,
        "checkpoint_completed_days": config.resume_checkpoint_completed_days,
        "checkpoint_total_days": config.resume_checkpoint_total_days,
        "checkpoint_nav": config.resume_checkpoint_nav,
        "checkpoint_order_count": config.resume_checkpoint_order_count,
        "checkpoint_fill_count": config.resume_checkpoint_fill_count,
        "account_state_hash": config.resume_account_state_hash,
        "settlement_state_hash": config.resume_settlement_state_hash,
        "runtime_state_hash": config.resume_runtime_state_hash,
    }
