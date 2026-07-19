"""
回测触发 Command — 参数校验 + 因子预编译 + RunRecord 创建.

Handler 编排: StrategyCatalogService（读策略）+ FactorBridge（预编译）
+ RunLifecycleService（创建 RunRecord）。
Prefect flow 提交由 apps API 层负责（apps 边界）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import cast

import orjson
from ditto_kernel.strategy import RunStatus
from ditto_strategy.alpha.node_registry import default_node_registry
from ditto_strategy.alpha.parameters import (
    CandidateParameter,
    EffectiveParameter,
    ParameterBinder,
    ParameterValue,
    legacy_parameter_path,
)
from ditto_strategy.alpha.spec_codec import adapt_legacy_strategy_spec
from ditto_strategy.contracts import StrategyCatalogReader
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunCheckpointReaderProtocol,
)

from ditto_application.config import DEFAULT_INITIAL_CASH
from ditto_application.contracts import CostConfig
from ditto_application.exceptions import AppCommandError
from ditto_application.processes.execution.factor_bridge import FactorBridge
from ditto_application.processes.execution.strategy_types import RunLifecycleService
from ditto_application.strategy_spec_deserialization import deserialize_strategy_spec

__all__ = [
    "BacktestRunCommand",
    "BacktestRunHandler",
    "BacktestRunResult",
    "CancelRunCommand",
    "CancelRunHandler",
    "CostConfig",
    "ResumeRunCommand",
    "ResumeRunHandler",
    "RetryRunCommand",
    "RetryRunHandler",
    "parse_candidate_parameters",
]


@dataclass(frozen=True)
class BacktestRunCommand:
    """回测触发命令."""

    strategy_id: str
    start_date: str
    end_date: str
    strategy_version: int | None = None
    initial_cash: float = DEFAULT_INITIAL_CASH
    parameter_overrides: tuple[str, ...] = ()
    cost_config: CostConfig | None = None
    allow_experimental_data: bool = False


@dataclass(frozen=True)
class BacktestRunResult:
    """回测触发结果."""

    run_id: str
    strategy_id: str
    status: str
    strategy_version: int | None = None
    candidate_parameters: tuple[CandidateParameter, ...] = ()
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
        catalog_service: StrategyCatalogReader,
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
            AppCommandError: 策略不存在、日期非法、因子编译失败.

        """
        # 1. 校验日期
        self._validate_dates(command.start_date, command.end_date)

        # 2. Resolve published once, then lock the exact immutable version.
        spec_record = self._resolve_exact_published_record(command)

        # 3. 预编译因子表达式（如果策略包含 signal_expressions）
        spec_json = spec_record.spec_json
        signal_expressions = _extract_signal_expressions(spec_json)
        signal_weights = _extract_signal_weights(spec_json, command.strategy_id)

        if signal_expressions:
            # 未指定权重时，自动生成等权
            if not signal_weights:
                signal_weights = tuple(
                    1.0 / len(signal_expressions) for _ in signal_expressions
                )
            self._factor_bridge.compile_and_validate(signal_expressions, signal_weights)

        # 4. Parse the legacy wire syntax once and bind it to the exact spec.
        candidate_parameters = parse_candidate_parameters(command.parameter_overrides)
        try:
            legacy_spec = deserialize_strategy_spec(spec_record)
            binding = ParameterBinder(registry=default_node_registry()).bind(
                adapt_legacy_strategy_spec(legacy_spec),
                candidate_parameters=candidate_parameters,
            )
        except StrategySpecError as exc:
            raise AppCommandError(str(exc), details=exc.details) from exc

        # 5. Persist only typed candidate/effective values and immutable identities.
        config_data: dict[str, object] = {
            "start_date": command.start_date,
            "end_date": command.end_date,
            "strategy_version": spec_record.version,
            "initial_cash": command.initial_cash,
            "candidate_parameters": _parameter_payload(candidate_parameters),
            "effective_parameters": _parameter_payload(
                binding.effective_parameters,
            ),
            "base_spec_hash": binding.base_spec_hash,
            "spec_hash": binding.resolved_spec_hash,
            "parameter_hash": binding.parameter_hash,
            "allow_experimental_data": command.allow_experimental_data,
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

        # 6. 创建 RunRecord with the same exact catalog version.
        run_id = uuid.uuid4().hex[:8]
        self._run_service.create_run(
            run_id=run_id,
            strategy_id=command.strategy_id,
            strategy_version=str(spec_record.version),
            mode="backtest",
            config_json=config_json,
        )

        return BacktestRunResult(
            run_id=run_id,
            strategy_id=command.strategy_id,
            status="pending",
            strategy_version=spec_record.version,
            candidate_parameters=candidate_parameters,
            cost_config=command.cost_config,
        )

    def _resolve_exact_published_record(
        self,
        command: BacktestRunCommand,
    ) -> StrategySpecRecord:
        expected_version: int | None
        if command.strategy_version is not None:
            if (
                type(command.strategy_version) is not int
                or command.strategy_version <= 0
            ):
                raise AppCommandError(
                    "strategy_version must be a positive integer",
                    details={"field": "strategy_version"},
                )
            expected_version = command.strategy_version
            exact = self._catalog_service.get_spec(
                command.strategy_id,
                expected_version,
            )
        else:
            selected = self._catalog_service.get_latest_published(command.strategy_id)
            if selected is None:
                expected_version = None
                exact = None
            else:
                expected_version = selected.version
                exact = self._catalog_service.get_spec(
                    command.strategy_id,
                    expected_version,
                )
        if exact is None:
            msg = f"Strategy not found: {command.strategy_id}"
            raise AppCommandError(msg)
        if (
            exact.strategy_id != command.strategy_id
            or exact.version != expected_version
            or exact.status != "published"
        ):
            raise AppCommandError(
                "Backtest requires one exact published strategy version",
                details={
                    "strategy_id": command.strategy_id,
                    "expected_strategy_version": expected_version,
                    "actual_strategy_version": exact.version,
                    "version_status": exact.status,
                },
            )
        return exact

    @staticmethod
    def _validate_dates(start_date: str, end_date: str) -> None:
        """校验日期格式和范围."""
        try:
            start = date.fromisoformat(start_date)
        except ValueError:
            msg = f"日期格式无效: start_date='{start_date}', 期望 YYYY-MM-DD"
            raise AppCommandError(msg) from None

        try:
            end = date.fromisoformat(end_date)
        except ValueError:
            msg = f"日期格式无效: end_date='{end_date}', 期望 YYYY-MM-DD"
            raise AppCommandError(msg) from None

        if start > end:
            msg = f"日期范围无效: start_date={start_date} > end_date={end_date}"
            raise AppCommandError(msg)


def _extract_signal_expressions(
    spec_json: dict[str, object],
) -> tuple[str, ...]:
    """从 spec_json 提取 signal_expressions."""
    raw = spec_json.get("signal_expressions")
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in cast(list[object], raw))


def _extract_signal_weights(
    spec_json: dict[str, object],
    strategy_id: str,
) -> tuple[float, ...]:
    """从 spec_json 提取 signal_weights."""
    raw = spec_json.get("signal_weights")
    if not isinstance(raw, list):
        return ()
    weights: list[float] = []
    for index, item in enumerate(cast(list[object], raw)):
        value = str(item)
        try:
            weights.append(float(value))
        except ValueError:
            msg = (
                f"invalid signal_weights[{index}] for strategy_id={strategy_id}: "
                f"{value}"
            )
            raise AppCommandError(
                msg,
                strategy_id=strategy_id,
                field="signal_weights",
                index=index,
                value=value,
            ) from None
    return tuple(weights)


def _parameter_payload(
    parameters: tuple[CandidateParameter, ...] | tuple[EffectiveParameter, ...],
) -> list[dict[str, ParameterValue]]:
    return [
        {"path": parameter.path, "value": parameter.value} for parameter in parameters
    ]


def _require_override_strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise AppCommandError(
            "parameter_overrides must be tuple[str, ...]",
            details={"field": "parameter_overrides"},
        )
    overrides: list[str] = []
    for item in cast(tuple[object, ...], value):
        if not isinstance(item, str):
            raise AppCommandError(
                "parameter_overrides must be tuple[str, ...]",
                details={"field": "parameter_overrides"},
            )
        overrides.append(item)
    return tuple(overrides)


def parse_candidate_parameters(
    parameter_overrides: tuple[str, ...],
) -> tuple[CandidateParameter, ...]:
    """Parse the legacy ``key=value`` syntax into strict typed candidates once."""
    parameter_overrides = _require_override_strings(parameter_overrides)
    candidates: list[CandidateParameter] = []
    seen_paths: set[str] = set()
    for index, raw in enumerate(parameter_overrides):
        if "=" not in raw:
            raise AppCommandError(
                "parameter override must use key=value syntax",
                details={"field": "parameter_overrides", "index": index},
            )
        raw_name, raw_value = raw.split("=", 1)
        name = raw_name.strip()
        value_text = raw_value.strip()
        if not name or not value_text:
            raise AppCommandError(
                "parameter override key and value must be non-empty",
                details={"field": "parameter_overrides", "index": index},
            )
        path = name if name.startswith("/") else legacy_parameter_path(name)
        if path in seen_paths:
            raise AppCommandError(
                "duplicate parameter override path",
                details={
                    "field": "parameter_overrides",
                    "index": index,
                    "path": path,
                },
            )
        try:
            decoded = orjson.loads(value_text)
        except orjson.JSONDecodeError:
            if value_text in {"NaN", "Infinity", "-Infinity"}:
                raise AppCommandError(
                    "parameter override value is not a finite JSON scalar",
                    details={
                        "field": "parameter_overrides",
                        "index": index,
                        "path": path,
                    },
                ) from None
            decoded = value_text
        if decoded is None or type(decoded) not in {bool, int, float, str}:
            raise AppCommandError(
                "parameter override value must be a JSON scalar",
                details={
                    "field": "parameter_overrides",
                    "index": index,
                    "path": path,
                },
            )
        try:
            candidate = CandidateParameter(path=path, value=decoded)
        except StrategySpecError as exc:
            raise AppCommandError(str(exc), details=exc.details) from exc
        seen_paths.add(path)
        candidates.append(candidate)
    return tuple(candidates)


# ---------------------------------------------------------------------------
# Cancel / Retry Command Handlers
# ---------------------------------------------------------------------------

_CANCEL_ALLOWED = {RunStatus.PENDING, RunStatus.RUNNING}
_RETRY_ALLOWED = {RunStatus.FAILED, RunStatus.CANCELLED}
_RESUME_ALLOWED = {RunStatus.FAILED, RunStatus.CANCELLED}


@dataclass(frozen=True)
class CancelRunCommand:
    """取消运行命令."""

    run_id: str


@dataclass(frozen=True)
class RetryRunCommand:
    """重试运行命令."""

    run_id: str


@dataclass(frozen=True)
class ResumeRunCommand:
    """从 checkpoint 恢复运行命令."""

    run_id: str


class CancelRunHandler:
    """
    取消运行 Command Handler — 检查状态 + 标记取消.

    Parameters
    ----------
        run_service: 策略运行生命周期服务

    """

    def __init__(self, *, run_service: RunLifecycleService) -> None:
        self._run_service = run_service

    def handle(self, command: CancelRunCommand) -> None:
        """
        处理取消运行命令.

        Args:
            command: 取消运行命令.

        Raises:
            ValueError: 运行不存在或状态不允许取消.

        """
        run_id = command.run_id
        record = self._run_service.get_run(run_id)
        if record is None:
            msg = f"Run not found: {run_id}"
            raise AppCommandError(msg)

        if record.status not in _CANCEL_ALLOWED:
            msg = f"Cannot cancel run in '{record.status}' status"
            raise AppCommandError(msg)

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

    def handle(self, command: RetryRunCommand) -> str:
        """
        处理重试运行命令.

        Args:
            command: 重试运行命令.

        Returns:
            新运行 ID.

        Raises:
            ValueError: 运行不存在或状态不允许重试.

        """
        run_id = command.run_id
        record = self._run_service.get_run(run_id)
        if record is None:
            msg = f"Run not found: {run_id}"
            raise AppCommandError(msg)

        if record.status not in _RETRY_ALLOWED:
            msg = f"Cannot retry run in '{record.status}' status"
            raise AppCommandError(msg)

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


class ResumeRunHandler:
    """
    从 checkpoint 恢复运行 Command Handler — 检查状态 + 创建子运行.

    当前恢复命令负责把 latest checkpoint 转换为新的 child run 配置，并从
    ``resume_from`` 日期开始重新提交回测。完整账户/持仓状态恢复与 replay proof
    由后续恢复链路补齐。
    """

    def __init__(
        self,
        *,
        run_service: RunLifecycleService,
        checkpoint_reader: StrategyRunCheckpointReaderProtocol,
    ) -> None:
        self._run_service = run_service
        self._checkpoint_reader = checkpoint_reader

    def handle(self, command: ResumeRunCommand) -> str:
        """
        处理 checkpoint 恢复命令.

        Args:
            command: checkpoint 恢复命令.

        Returns:
            新运行 ID.

        Raises:
            AppCommandError: 运行不存在、状态不允许恢复或无可恢复 checkpoint.

        """
        run_id = command.run_id
        record = self._run_service.get_run(run_id)
        if record is None:
            msg = f"Run not found: {run_id}"
            raise AppCommandError(msg)

        if record.status not in _RESUME_ALLOWED:
            msg = f"Cannot resume run in '{record.status}' status"
            raise AppCommandError(msg)

        checkpoint = self._checkpoint_reader.get_latest_checkpoint(run_id)
        if checkpoint is None or not checkpoint.can_resume:
            msg = f"No resumable checkpoint for run: {run_id}"
            raise AppCommandError(msg)

        config_data = _load_config_json(record.config_json)
        config_data["start_date"] = checkpoint.resume_from
        config_data["resume_from_run_id"] = run_id
        config_data["resume_checkpoint_trade_date"] = checkpoint.completed_trade_date
        config_data["resume_checkpoint_completed_days"] = checkpoint.completed_days
        config_data["resume_checkpoint_total_days"] = checkpoint.total_days
        config_data["resume_checkpoint_nav"] = checkpoint.nav
        config_data["resume_checkpoint_order_count"] = checkpoint.order_count
        config_data["resume_checkpoint_fill_count"] = checkpoint.fill_count
        if checkpoint.account_state_json:
            config_data["resume_account_state_json"] = checkpoint.account_state_json
        if checkpoint.account_state_hash:
            config_data["resume_account_state_hash"] = checkpoint.account_state_hash
        if checkpoint.settlement_state_json:
            config_data["resume_settlement_state_json"] = (
                checkpoint.settlement_state_json
            )
        if checkpoint.settlement_state_hash:
            config_data["resume_settlement_state_hash"] = (
                checkpoint.settlement_state_hash
            )
        if checkpoint.runtime_state_json:
            config_data["resume_runtime_state_json"] = checkpoint.runtime_state_json
        if checkpoint.runtime_state_hash:
            config_data["resume_runtime_state_hash"] = checkpoint.runtime_state_hash
        config_json = orjson.dumps(config_data).decode("utf-8")

        new_run_id = uuid.uuid4().hex[:8]
        self._run_service.create_run(
            run_id=new_run_id,
            strategy_id=record.strategy_id,
            strategy_version=record.strategy_version,
            mode=record.mode,
            parent_run_id=run_id,
            config_json=config_json,
        )
        return new_run_id


def _load_config_json(config_json: str) -> dict[str, object]:
    """Load run config JSON as a mutable dict."""
    if not config_json:
        return {}
    raw = orjson.loads(config_json)
    if not isinstance(raw, dict):
        msg = "Run config_json must be an object"
        raise AppCommandError(msg)
    raw_dict = cast(dict[object, object], raw)
    return {str(key): value for key, value in raw_dict.items()}
