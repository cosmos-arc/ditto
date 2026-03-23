"""
StrategyRunService — Port 层策略运行编排服务.

RESEARCH 模式: 单日信号生成 + 输出 TargetPortfolio
RECOMMENDATION 模式: 信号持久化 + 推送

职责:
  - 接收 StrategyPipeline + StrategyInputAssembler
  - 对给定交易日运行策略 Pipeline
  - RESEARCH: 返回 TargetPortfolio
  - RECOMMENDATION: 持久化信号到 StrategyArtifactService
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from ditto_core.backtest.data_feed import Slice
from ditto_core.strategy.context import StrategyContext
from ditto_core.strategy.models import TargetPortfolio
from ditto_core.strategy.pipeline import StrategyPipeline
from ditto_datahub.models.strategy import StrategyArtifactRecord
from ditto_datahub.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)

from ditto_port.services.strategy.input_assembler import StrategyInputAssembler

__all__ = [
    "StrategyRunMode",
    "StrategyRunResult",
    "StrategyRunService",
    "StrategyRunServiceConfig",
]


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
        run_id: 运行 ID (空字符串时自动生成)
        mode: 运行模式 (research / recommendation)

    """

    strategy_id: str = "default"
    run_id: str = ""
    mode: StrategyRunMode = StrategyRunMode.RESEARCH


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
    Port 层策略运行编排服务.

    对给定交易日运行策略 Pipeline，产出 TargetPortfolio。
    RESEARCH 模式仅返回结果，RECOMMENDATION 模式额外持久化信号。

    Parameters
    ----------
        config: 服务配置
        pipeline: 策略 Pipeline
        assembler: 输入组装器
        artifact_service: 策略产物持久化服务 (RECOMMENDATION 模式使用)

    """

    def __init__(
        self,
        config: StrategyRunServiceConfig,
        pipeline: StrategyPipeline,
        assembler: StrategyInputAssembler,
        *,
        artifact_service: StrategyArtifactService | None = None,
    ) -> None:
        self._config = config
        self._pipeline = pipeline
        self._assembler = assembler
        self._artifact_service = artifact_service

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
        run_id = self._config.run_id or uuid.uuid4().hex[:8]

        # 组装输入
        input_bundle = self._assembler.assemble(trade_date, slice_)

        # 运行 Pipeline
        context = StrategyContext()
        target = self._pipeline.run(context, input_bundle)

        # 构建 result
        result = StrategyRunResult(
            run_id=run_id,
            trade_date=trade_date,
            strategy_id=self._config.strategy_id,
            target=target,
            mode=self._config.mode,
        )

        # RECOMMENDATION 模式: 持久化信号
        if self._config.mode == StrategyRunMode.RECOMMENDATION:
            self._persist_signal(run_id, trade_date, target)

        return result

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
            artifact_type="signal_snapshot",
            file_path="",
            metadata={
                "trade_date": trade_date,
                "positions": dict(target.positions),
                "cash_target": target.cash_target,
            },
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        self._artifact_service.save_artifact(artifact)
