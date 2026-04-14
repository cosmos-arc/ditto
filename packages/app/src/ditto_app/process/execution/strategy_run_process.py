"""
策略运行编排服务 — Process 模块.

包含 StrategyRunService（策略运行编排）和 StrategyFacade（对外暴露入口）。
StrategyRunService 对给定交易日运行策略 Pipeline，产出 TargetPortfolio。
StrategyFacade 封装 catalog-backed 策略执行入口。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from ditto_data.models.strategy import ArtifactKind, StrategyArtifactRecord
from ditto_data.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_engine.alpha.context import StrategyContext
from ditto_engine.alpha.models import TargetPortfolio
from ditto_engine.alpha.pipeline import StrategyPipeline
from ditto_engine.alpha.specs import StrategySpec
from ditto_engine.alpha.validation import validate_spec_params
from ditto_engine.backtest.data_feed import Slice
from ditto_engine.backtest.statistics import BacktestReport

from ditto_app.process.execution.backtest_process import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_app.process.execution.strategy_input import StrategyInputAssembler
from ditto_app.process.execution.strategy_types import (
    RunLifecycleService,
    mark_run_failed,
)

__all__ = [
    "StrategyFacade",
    "StrategyRunMode",
    "StrategyRunResult",
    "StrategyRunService",
    "StrategyRunServiceConfig",
]


# ---------------------------------------------------------------------------
# StrategyRunMode
# ---------------------------------------------------------------------------


class StrategyRunMode(StrEnum):
    """策略运行模式。"""

    RESEARCH = "research"
    RECOMMENDATION = "recommendation"


# ---------------------------------------------------------------------------
# StrategyRunServiceConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategyRunServiceConfig:
    """
    StrategyRunService 配置 — frozen, 运行前确定.

    Attributes:
        strategy_id: 策略 ID
        strategy_version: 策略版本
        run_id: 运行 ID (空字符串时自动生成)
        mode: 运行模式 (research / recommendation)
        spec: 策略定义（可选，设置后 run() 会先校验参数）

    """

    strategy_id: str = "default"
    strategy_version: str = ""
    run_id: str = ""
    mode: StrategyRunMode = StrategyRunMode.RESEARCH
    spec: StrategySpec | None = None


# ---------------------------------------------------------------------------
# StrategyRunResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategyRunResult:
    """
    策略运行结果.

    Attributes:
        run_id: 运行 ID
        trade_date: 交易日期
        strategy_id: 策略 ID
        target: 目标持仓
        mode: 运行模式

    """

    run_id: str
    trade_date: str
    strategy_id: str
    target: TargetPortfolio
    mode: StrategyRunMode


# ---------------------------------------------------------------------------
# StrategyRunService
# ---------------------------------------------------------------------------


class StrategyRunService:
    """
    App 层策略运行编排服务.

    对给定交易日运行策略 Pipeline，产出 TargetPortfolio。
    RESEARCH 模式仅返回结果，RECOMMENDATION 模式额外持久化信号。

    Parameters
    ----------
        config: 服务配置
        pipeline: 策略 Pipeline
        assembler: 输入组装器
        artifact_service: 策略产物持久化服务 (RECOMMENDATION 模式使用)
        run_service: 策略运行生命周期服务

    """

    def __init__(
        self,
        config: StrategyRunServiceConfig,
        pipeline: StrategyPipeline,
        assembler: StrategyInputAssembler,
        *,
        artifact_service: StrategyArtifactService | None = None,
        run_service: RunLifecycleService | None = None,
    ) -> None:
        self._config = config
        self._pipeline = pipeline
        self._assembler = assembler
        self._artifact_service = artifact_service
        self._run_service = run_service

    @property
    def mode(self) -> StrategyRunMode:
        """当前运行模式。"""
        return self._config.mode

    def run(self, trade_date: str, slice_: Slice) -> StrategyRunResult:
        """
        执行单日策略运行.

        Args:
            trade_date: 交易日期
            slice_: 市场数据切片

        Returns:
            StrategyRunResult 包含 TargetPortfolio。

        """
        run_id = self._resolve_run_id()
        run_svc = self._run_service
        if run_svc is not None:
            existing = run_svc.get_run(run_id)
            if existing is None:
                run_svc.create_run(
                    run_id=run_id,
                    strategy_id=self._config.strategy_id,
                    strategy_version=self._config.strategy_version,
                    mode=str(self._config.mode),
                    parent_run_id="",
                )
            run_svc.mark_running(run_id)

        try:
            return self._execute_run(trade_date, slice_, run_id=run_id)
        except Exception as exc:
            mark_run_failed(run_svc, run_id, exc)
            raise

    def _execute_run(
        self,
        trade_date: str,
        slice_: Slice,
        *,
        run_id: str,
    ) -> StrategyRunResult:
        """执行策略核心运行逻辑。"""
        if self._config.spec is not None:
            self._validate_params(self._config.spec)

        input_bundle = self._assembler.assemble(trade_date, slice_, run_id=run_id)

        context = StrategyContext()
        target = self._pipeline.run(context, input_bundle)

        result = StrategyRunResult(
            run_id=run_id,
            trade_date=trade_date,
            strategy_id=self._config.strategy_id,
            target=target,
            mode=self._config.mode,
        )

        if self._config.mode == StrategyRunMode.RECOMMENDATION:
            self._persist_signal(run_id, trade_date, target)

        run_svc = self._run_service
        if run_svc is not None:
            run_svc.mark_completed(run_id)

        return result

    def _resolve_run_id(self) -> str:
        """在运行前固化真实 run_id。"""
        configured_run_id = self._config.run_id
        if configured_run_id:
            return configured_run_id
        return uuid.uuid4().hex[:8]

    # -- internal validation -------------------------------------------------

    @staticmethod
    def _validate_params(spec: StrategySpec) -> None:
        """校验 spec 参数，不合法时抛出 ValueError。"""
        errors = validate_spec_params(spec)
        if errors:
            raise ValueError(
                f"策略参数校验失败 [{spec.strategy_id}]: {'; '.join(errors)}"
            )

    # -- internal persistence ------------------------------------------------

    def _persist_signal(
        self,
        run_id: str,
        trade_date: str,
        target: TargetPortfolio,
    ) -> None:
        """持久化信号到 StrategyArtifactService。"""
        if self._artifact_service is None:
            return
        artifact = StrategyArtifactRecord(
            artifact_id=f"signal-{run_id}-{trade_date}",
            strategy_id=self._config.strategy_id,
            run_id=run_id,
            artifact_type=ArtifactKind.SIGNAL_SNAPSHOT,
            file_path="",
            metadata={
                "trade_date": trade_date,
                "positions": dict(target.positions),
                "cash_target": target.cash_target,
            },
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        self._artifact_service.save_artifact(artifact)


# ===========================================================================
# StrategyFacade — 对外暴露 catalog-backed 策略执行入口
# ===========================================================================


class _StrategyServiceFactoryProto(Protocol):
    """StrategyFacade 所需的工厂协议（避免循环导入 builders）。"""

    def build_strategy_run_service_from_catalog(
        self,
        *,
        config: StrategyRunServiceConfig,
        version: int | None = None,
        assembler: StrategyInputAssembler | None = None,
    ) -> StrategyRunService: ...

    def build_backtest_service_from_catalog(
        self,
        *,
        config: BacktestServiceConfig,
        version: int | None = None,
        options: BacktestServiceOptions | None = None,
        source: str = "tushare",
    ) -> BacktestService: ...


class _StrategySliceBuilderProto(Protocol):
    """StrategyFacade 所需的 Slice 构建协议。"""

    def build_published_slice(
        self,
        strategy_id: str,
        *,
        trade_date: str,
        version: int | None = None,
        source: str = "tushare",
    ) -> Slice: ...


class StrategyFacade:
    """对外暴露 catalog-backed 策略执行入口。"""

    def __init__(
        self,
        *,
        factory: _StrategyServiceFactoryProto,
        slice_builder: _StrategySliceBuilderProto | None = None,
    ) -> None:
        self._factory = factory
        self._slice_builder = slice_builder

    def run_strategy_from_catalog(
        self,
        *,
        config: StrategyRunServiceConfig,
        trade_date: str,
        slice_: Slice,
        version: int | None = None,
    ) -> StrategyRunResult:
        """从 published catalog 构造并执行 research/recommendation。"""
        service = self._factory.build_strategy_run_service_from_catalog(
            config=config,
            version=version,
        )
        return service.run(trade_date, slice_)

    def run_strategy_for_date_from_catalog(
        self,
        *,
        config: StrategyRunServiceConfig,
        trade_date: str,
        version: int | None = None,
        source: str = "tushare",
    ) -> StrategyRunResult:
        """从 published catalog 自动组装单日 Slice 并执行 research/recommendation。"""
        if self._slice_builder is None:
            msg = "StrategySliceBuilder 未配置, 无法自动组装单日 Slice"
            raise ValueError(msg)
        slice_ = self._slice_builder.build_published_slice(
            config.strategy_id,
            trade_date=trade_date,
            version=version,
            source=source,
        )
        return self.run_strategy_from_catalog(
            config=config,
            trade_date=trade_date,
            slice_=slice_,
            version=version,
        )

    def run_backtest_from_catalog(
        self,
        *,
        config: BacktestServiceConfig,
        version: int | None = None,
        options: BacktestServiceOptions | None = None,
        source: str = "tushare",
    ) -> BacktestReport:
        """从 published catalog 构造并执行完整回测。"""
        service = self._factory.build_backtest_service_from_catalog(
            config=config,
            version=version,
            options=options,
            source=source,
        )
        return service.run()
