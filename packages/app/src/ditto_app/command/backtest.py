"""
回测触发 Command — 参数校验 + 因子预编译 + RunRecord 创建.

Handler 编排: StrategyCatalogService（读策略）+ FactorBridge（预编译）
+ RunLifecycleService（创建 RunRecord）。
Prefect flow 提交由 API 层负责（Interfaces 层边界）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

import orjson
from ditto_data.services.strategy.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_kernel.enums import RunStatus

from ditto_app.contracts import CostConfig
from ditto_app.process.execution.factor_bridge import FactorBridge
from ditto_app.process.execution.strategy_types import RunLifecycleService

__all__ = [
    "BacktestRunCommand",
    "BacktestRunHandler",
    "BacktestRunResult",
    "CancelRunHandler",
    "CostConfig",
    "RetryRunHandler",
]


@dataclass(frozen=True)
class BacktestRunCommand:
    """回测触发命令."""

    strategy_id: str
    start_date: str
    end_date: str
    initial_cash: float = 1_000_000.0
    parameter_overrides: tuple[str, ...] = ()
    cost_config: CostConfig | None = None


@dataclass(frozen=True)
class BacktestRunResult:
    """回测触发结果."""

    run_id: str
    strategy_id: str
    status: str
    cost_config: CostConfig | None = None


class BacktestRunHandler:
    """
    回测触发 Command Handler — 校验→预编译→创建记录.

    Parameters
    ----------
        catalog_service: 策略目录服务（读策略 Spec）
        run_service: 策略运行生命周期服务
        factor_bridge: 因子桥接（预编译表达式）

    """

    def __init__(
        self,
        *,
        catalog_service: StrategyCatalogService,
        run_service: RunLifecycleService,
        factor_bridge: FactorBridge,
    ) -> None:
        self._catalog_service = catalog_service
        self._run_service = run_service
        self._factor_bridge = factor_bridge

    def handle(self, command: BacktestRunCommand) -> BacktestRunResult:
        """
        处理回测触发命令.

        Args:
            command: 回测触发命令.

        Returns:
            BacktestRunResult 包含 run_id 和状态.

        Raises:
            ValueError: 策略不存在、日期非法、因子编译失败.

        """
        # 1. 校验日期
        self._validate_dates(command.start_date, command.end_date)

        # 2. 校验策略存在
        spec_record = self._catalog_service.get_spec(command.strategy_id)
        if spec_record is None:
            msg = f"Strategy not found: {command.strategy_id}"
            raise ValueError(msg)

        # 3. 预编译因子表达式（如果策略包含 signal_expressions）
        spec_json = spec_record.spec_json if hasattr(spec_record, "spec_json") else {}
        signal_expressions = _extract_signal_expressions(spec_json)
        signal_weights = _extract_signal_weights(spec_json)

        if signal_expressions:
            self._factor_bridge.compile_and_validate(signal_expressions, signal_weights)

        # 4. 序列化回测配置为 config_json
        config_data: dict[str, object] = {
            "start_date": command.start_date,
            "end_date": command.end_date,
            "initial_cash": command.initial_cash,
            "parameter_overrides": list(command.parameter_overrides),
        }
        if command.cost_config is not None:
            config_data["cost_config"] = {
                "commission_rate": command.cost_config.commission_rate,
                "commission_min": command.cost_config.commission_min,
                "stamp_duty_rate": command.cost_config.stamp_duty_rate,
                "slippage_bps": command.cost_config.slippage_bps,
                "impact_model": command.cost_config.impact_model,
            }
        config_json = orjson.dumps(config_data).decode("utf-8")

        # 5. 创建 RunRecord
        run_id = uuid.uuid4().hex[:8]
        self._run_service.create_run(
            run_id=run_id,
            strategy_id=command.strategy_id,
            mode="backtest",
            config_json=config_json,
        )

        return BacktestRunResult(
            run_id=run_id,
            strategy_id=command.strategy_id,
            status="pending",
            cost_config=command.cost_config,
        )

    @staticmethod
    def _validate_dates(start_date: str, end_date: str) -> None:
        """校验日期格式和范围."""
        try:
            start = date.fromisoformat(start_date)
        except ValueError:
            msg = f"日期格式无效: start_date='{start_date}', 期望 YYYY-MM-DD"
            raise ValueError(msg) from None

        try:
            end = date.fromisoformat(end_date)
        except ValueError:
            msg = f"日期格式无效: end_date='{end_date}', 期望 YYYY-MM-DD"
            raise ValueError(msg) from None

        if start > end:
            msg = f"日期范围无效: start_date={start_date} > end_date={end_date}"
            raise ValueError(msg)


def _extract_signal_expressions(
    spec_json: dict[str, object],
) -> tuple[str, ...]:
    """从 spec_json 提取 signal_expressions."""
    exprs = spec_json.get("signal_expressions")
    if not isinstance(exprs, (list, tuple)):
        return ()
    return tuple(str(e) for e in exprs)  # type: ignore[reportUnknownArgumentType, reportUnknownVariableType]


def _extract_signal_weights(
    spec_json: dict[str, object],
) -> tuple[float, ...]:
    """从 spec_json 提取 signal_weights."""
    weights = spec_json.get("signal_weights")
    if not isinstance(weights, (list, tuple)):
        return ()
    return tuple(float(w) for w in weights)  # type: ignore[reportUnknownArgumentType, reportUnknownVariableType]


# ---------------------------------------------------------------------------
# Cancel / Retry Command Handlers
# ---------------------------------------------------------------------------

_CANCEL_ALLOWED = {RunStatus.PENDING, RunStatus.RUNNING}
_RETRY_ALLOWED = {RunStatus.FAILED, RunStatus.CANCELLED}


class CancelRunHandler:
    """
    取消运行 Command Handler — 检查状态 + 标记取消.

    Parameters
    ----------
        run_service: 策略运行生命周期服务

    """

    def __init__(self, *, run_service: RunLifecycleService) -> None:
        self._run_service = run_service

    def handle(self, run_id: str) -> None:
        """
        处理取消运行命令.

        Raises:
            ValueError: 运行不存在或状态不允许取消.

        """
        record = self._run_service.get_run(run_id)
        if record is None:
            msg = f"Run not found: {run_id}"
            raise ValueError(msg)

        if record.status not in _CANCEL_ALLOWED:
            msg = f"Cannot cancel run in '{record.status}' status"
            raise ValueError(msg)

        self._run_service.mark_cancelled(run_id)


class RetryRunHandler:
    """
    重试运行 Command Handler — 检查状态 + 创建新运行.

    Parameters
    ----------
        run_service: 策略运行生命周期服务

    """

    def __init__(self, *, run_service: RunLifecycleService) -> None:
        self._run_service = run_service

    def handle(self, run_id: str) -> str:
        """
        处理重试运行命令.

        Returns:
            新运行 ID.

        Raises:
            ValueError: 运行不存在或状态不允许重试.

        """
        record = self._run_service.get_run(run_id)
        if record is None:
            msg = f"Run not found: {run_id}"
            raise ValueError(msg)

        if record.status not in _RETRY_ALLOWED:
            msg = f"Cannot retry run in '{record.status}' status"
            raise ValueError(msg)

        new_run_id = uuid.uuid4().hex[:8]
        self._run_service.create_run(
            run_id=new_run_id,
            strategy_id=record.strategy_id,
            strategy_version=record.strategy_version,
            mode=record.mode,
            parent_run_id=run_id,
            config_json=record.config_json,
        )
        return new_run_id
