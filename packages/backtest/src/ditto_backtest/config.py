"""
引擎配置 — EngineMode + EngineConfig.

从 engine.py 提取，消除 engine.py ↔ result.py 循环依赖。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from ditto_execution.trade_builder import TradeMatchingMethod
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.parameters import (
    EffectiveParameter,
    canonical_parameter_hash,
)
from ditto_strategy.errors import StrategySpecError

from ditto_backtest.context_inputs import (
    ReplayContextInputRef,
    normalize_context_input_refs,
)

__all__ = [
    "EngineConfig",
    "EngineMode",
    "validate_canonical_sha256",
    "validate_effective_parameter_identity",
    "validate_research_snapshot_identity",
    "validate_spec_hash",
]

_CANONICAL_SPEC_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def validate_canonical_sha256(value: object, *, field_name: str) -> str:
    """Validate one bare lowercase SHA-256 identity with field-aware errors."""
    if not isinstance(value, str) or not _CANONICAL_SPEC_HASH_RE.fullmatch(value):
        msg = f"{field_name} must be a 64-character lowercase SHA-256 hex digest"
        raise ValueError(msg)
    return value


def validate_spec_hash(spec_hash: object) -> str:
    """校验并返回 StrategySpec codec 产生的完整小写 SHA-256。"""
    return validate_canonical_sha256(spec_hash, field_name="spec_hash")


def validate_effective_parameter_identity(
    parameter_hash: object,
    effective_parameters: object,
) -> tuple[EffectiveParameter, ...]:
    """Validate complete canonical values and their exact content hash."""
    expected_hash = validate_canonical_sha256(
        parameter_hash,
        field_name="parameter_hash",
    )
    if not isinstance(effective_parameters, tuple):
        msg = "effective_parameters must be tuple[EffectiveParameter, ...]"
        raise ValueError(msg)
    validated_parameters: list[EffectiveParameter] = []
    for item in cast(tuple[object, ...], effective_parameters):
        if not isinstance(item, EffectiveParameter):
            msg = "effective_parameters must be tuple[EffectiveParameter, ...]"
            raise ValueError(msg)
        validated_parameters.append(item)
    parameter_values = tuple(validated_parameters)
    paths = tuple(item.path for item in parameter_values)
    if paths != tuple(sorted(paths)):
        msg = "effective_parameters must use canonical path order"
        raise ValueError(msg)
    try:
        actual_hash = canonical_parameter_hash(parameter_values)
    except StrategySpecError as exc:
        raise ValueError(str(exc)) from exc
    if actual_hash != expected_hash:
        msg = "parameter_hash does not match effective_parameters"
        raise ValueError(msg)
    return parameter_values


def validate_research_snapshot_identity(
    snapshot_id: object,
    manifest_hash: object,
) -> tuple[str, str] | None:
    """Validate an opaque snapshot ID and immutable manifest identity as one pair."""
    if snapshot_id is None and manifest_hash is None:
        return None
    if snapshot_id is None or manifest_hash is None:
        msg = (
            "research_snapshot_id and research_snapshot_manifest_hash "
            "must be provided together"
        )
        raise ValueError(msg)
    if (
        not isinstance(snapshot_id, str)
        or not snapshot_id
        or snapshot_id != snapshot_id.strip()
    ):
        msg = "research_snapshot_id must be None or a non-empty canonical string"
        raise ValueError(msg)
    try:
        snapshot_id.encode("utf-8")
    except UnicodeEncodeError:
        msg = "research_snapshot_id must have a canonical UTF-8 identity"
        raise ValueError(msg) from None
    validated_hash = validate_canonical_sha256(
        manifest_hash,
        field_name="research_snapshot_manifest_hash",
    )
    return snapshot_id, validated_hash


class EngineMode(StrEnum):
    """引擎运行模式。"""

    BACKTEST = "backtest"


@dataclass(frozen=True)
class EngineConfig:
    """
    引擎配置 -- frozen, 运行前确定.

    Attributes:
        start_date: 起始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        initial_cash: 初始资金
        benchmark_id: 基准标的 ID (None = 无基准)
        mode: 运行模式
        trade_matching: 成交匹配算法
        strategy_id: 策略 ID
        strategy_version: 策略版本
        strategy_run_id: 策略运行 ID
        parameter_overrides: 参数覆盖列表
        rebalance_freq: 调仓频率 (daily / weekly / monthly)
        engine_version: 引擎版本号 (用于 manifest/diff 追踪)
        execution_delay: 信号延迟执行天数 (T+N)，尾部信号自动 flush
        knowledge_lag_days: 知识延迟天数
            （PIT 语义：knowledge_date = decision_date - lag）

    """

    start_date: str
    end_date: str
    initial_cash: float
    spec_hash: str
    base_spec_hash: str
    parameter_hash: str
    effective_parameters: tuple[EffectiveParameter, ...]
    research_snapshot_id: str | None
    research_snapshot_manifest_hash: str | None
    context_input_refs: tuple[ReplayContextInputRef, ...] = ()
    benchmark_id: InstrumentId | None = None
    mode: EngineMode = EngineMode.BACKTEST
    trade_matching: TradeMatchingMethod = TradeMatchingMethod.FIFO
    strategy_id: str = "default"
    strategy_version: str = ""
    strategy_run_id: str = ""
    parameter_overrides: tuple[str, ...] = ()
    rebalance_freq: str = "daily"
    engine_version: str = "0.1.0"
    execution_delay: int = 0
    knowledge_lag_days: int = 1

    def __post_init__(self) -> None:
        """执行边界必须携带完整 canonical StrategySpec hash。"""
        validate_spec_hash(self.spec_hash)
        validate_canonical_sha256(self.base_spec_hash, field_name="base_spec_hash")
        validate_effective_parameter_identity(
            self.parameter_hash,
            self.effective_parameters,
        )
        validate_research_snapshot_identity(
            self.research_snapshot_id,
            self.research_snapshot_manifest_hash,
        )
        object.__setattr__(
            self,
            "context_input_refs",
            normalize_context_input_refs(self.context_input_refs),
        )
        if self.parameter_overrides:
            msg = (
                "parameter_overrides cannot carry unresolved legacy values; "
                "use effective_parameters"
            )
            raise ValueError(msg)
