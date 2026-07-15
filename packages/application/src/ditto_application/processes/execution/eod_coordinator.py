"""EOD 纯业务编排：逐策略数据就绪判断、运行和信号发布。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from ditto_application.processes.execution.signal_package import SignalPackage

__all__ = [
    "DatasetReadiness",
    "EodCoordinator",
    "EodStrategyOutcome",
    "EodStrategyRequest",
]


@dataclass(frozen=True)
class DatasetReadiness:
    """一个数据集在目标信号日的可用状态。"""

    dataset: str
    status: Literal["ready", "missing", "stale", "dq_failed", "unknown"]
    snapshot_id: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class EodStrategyRequest:
    """EOD 运行所需的已发布策略身份和数据依赖。"""

    strategy_id: str
    strategy_version: str
    required_datasets: tuple[str, ...]


@dataclass(frozen=True)
class EodStrategyOutcome:
    """单策略机器可读 EOD 结果。"""

    strategy_id: str
    strategy_version: str
    batch_key: str
    status: Literal["completed", "no_rebalance", "blocked", "failed", "rerun_conflict"]
    required_dataset_states: tuple[DatasetReadiness, ...]
    artifact_id: str | None = None
    checksum: str | None = None
    reason: str = ""


type EodOutcomeStatus = Literal[
    "completed", "no_rebalance", "blocked", "failed", "rerun_conflict"
]


type _RunStrategy = Callable[[EodStrategyRequest, str, str], object]
type _PublishSignals = Callable[[object, Mapping[str, str]], SignalPackage]


class EodCoordinator:
    """让调度器和 CLI 共享同一套逐策略 EOD 决策。"""

    def __init__(
        self,
        *,
        run_strategy: _RunStrategy,
        publish_signals: _PublishSignals,
    ) -> None:
        self._run_strategy = run_strategy
        self._publish_signals = publish_signals

    def run(
        self,
        *,
        signal_date: str,
        strategies: Sequence[EodStrategyRequest],
        dataset_states: Mapping[str, DatasetReadiness],
        strategy_id: str | None = None,
    ) -> tuple[EodStrategyOutcome, ...]:
        """按策略独立校验依赖并运行；不相关数据集失败不会扩散。"""
        outcomes: list[EodStrategyOutcome] = []
        for request in strategies:
            if strategy_id is not None and request.strategy_id != strategy_id:
                continue
            batch_key = (
                f"eod-{signal_date}-{request.strategy_id}-{request.strategy_version}"
            )
            required = tuple(
                dataset_states.get(
                    dataset,
                    DatasetReadiness(dataset=dataset, status="unknown"),
                )
                for dataset in request.required_datasets
            )
            blocked = [state for state in required if state.status != "ready"]
            if blocked:
                outcomes.append(
                    EodStrategyOutcome(
                        strategy_id=request.strategy_id,
                        strategy_version=request.strategy_version,
                        batch_key=batch_key,
                        status="blocked",
                        required_dataset_states=required,
                        reason=",".join(
                            f"{state.dataset}:{state.status}" for state in blocked
                        ),
                    )
                )
                continue
            try:
                target = self._run_strategy(request, signal_date, batch_key)
                package = self._publish_signals(
                    target,
                    {state.dataset: state.snapshot_id or "" for state in required},
                )
                status = package.outcome
                if status not in {
                    "completed",
                    "no_rebalance",
                    "rerun_conflict",
                }:
                    status = "failed"
                outcomes.append(
                    EodStrategyOutcome(
                        strategy_id=request.strategy_id,
                        strategy_version=request.strategy_version,
                        batch_key=batch_key,
                        status=cast("EodOutcomeStatus", status),
                        required_dataset_states=required,
                        artifact_id=package.artifact_id,
                        checksum=package.checksum,
                    )
                )
            except Exception as exc:
                outcomes.append(
                    EodStrategyOutcome(
                        strategy_id=request.strategy_id,
                        strategy_version=request.strategy_version,
                        batch_key=batch_key,
                        status="failed",
                        required_dataset_states=required,
                        reason=f"{type(exc).__name__}: {exc}",
                    )
                )
        return tuple(outcomes)
