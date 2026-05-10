"""
已发布策略 Spec 的运行时装配器.

Facade 委托到 deserialization + template_builders 子模块.
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.specs import StrategySpec
from ditto_strategy.contracts import StrategyCatalogReader
from ditto_strategy.models import StrategySpecRecord

from ditto_application.builders.deserialization import (
    deserialize_strategy_spec,
)
from ditto_application.builders.template_builders import (
    build_alpha_stages,
    build_portfolio_stages,
)
from ditto_application.exceptions import AppBuilderError
from ditto_application.processes.execution.factor_bridge import (
    CompiledExpressions,
    FactorBridge,
)

__all__ = [
    "PublishedStrategyRuntime",
    "StrategyRuntimeBuilder",
]


# ===========================================================================
# PublishedStrategyRuntime
# ===========================================================================


@dataclass(frozen=True)
class PublishedStrategyRuntime:
    """已发布策略的运行时定义。"""

    record: StrategySpecRecord
    spec: StrategySpec
    pipeline: StrategyPipeline
    compiled_expressions: CompiledExpressions | None = None


# ===========================================================================
# StrategyRuntimeBuilder
# ===========================================================================


class StrategyRuntimeBuilder:
    """从 published StrategySpecRecord 组装 Core runtime 对象。"""

    def __init__(self, *, catalog_service: StrategyCatalogReader) -> None:
        self._catalog_service = catalog_service

    def build_published_runtime(
        self,
        strategy_id: str,
        version: int | None = None,
    ) -> PublishedStrategyRuntime:
        """读取 published spec 并构造 ``StrategySpec + StrategyPipeline``。"""
        record = self._catalog_service.get_spec(strategy_id, version)
        if record is None:
            msg = (
                f"未找到策略定义: strategy_id={strategy_id}, "
                f"version={version if version is not None else 'latest'}"
            )
            raise AppBuilderError(msg)
        if record.status != "published":
            msg = (
                f"策略定义尚未发布为 published: strategy_id={strategy_id}, "
                f"version={record.version}, status={record.status}"
            )
            raise AppBuilderError(msg)

        spec = deserialize_strategy_spec(record)
        pipeline = _build_pipeline(spec)
        compiled = _compile_signal_expressions(spec)
        return PublishedStrategyRuntime(
            record=record,
            spec=spec,
            pipeline=pipeline,
            compiled_expressions=compiled,
        )


# ---------------------------------------------------------------------------
# Module-level helpers (private)
# ---------------------------------------------------------------------------


def _compile_signal_expressions(
    spec: StrategySpec,
) -> CompiledExpressions | None:
    """若 spec 包含 signal_expressions 则编译并返回，否则返回 None。"""
    if not spec.signal_expressions:
        return None
    bridge = FactorBridge()
    return bridge.compile_and_validate(
        expressions=spec.signal_expressions,
        weights=spec.signal_weights or (1.0,) * len(spec.signal_expressions),
    )


def _build_pipeline(spec: StrategySpec) -> StrategyPipeline:
    """根据模板类型构造对应的 ``StrategyPipeline``。"""
    alpha_stages = build_alpha_stages(spec)
    portfolio_stages = build_portfolio_stages(spec)
    return StrategyPipeline([*alpha_stages, *portfolio_stages])
