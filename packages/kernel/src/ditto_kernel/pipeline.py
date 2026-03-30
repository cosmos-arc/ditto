"""
Stage/Pipeline Protocol + Context.

满足 kernel Protocol/薄实现准入标准：
1. 预期跨层使用：core + datahub + port
2. 零业务逻辑：纯组合原语
3. 无外部依赖：仅标准库
4. 实现体 < 30 行
5. 无 I/O
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ditto_kernel.clock import Clock
from ditto_kernel.events import EventBus
from ditto_kernel.provider import DataProvider

__all__ = ["Context", "Pipeline", "Stage"]


@dataclass(frozen=True)
class Context:
    """
    Pipeline 执行上下文.

    组合三大系统抽象（Clock + DataProvider + EventBus），
    为 Stage 提供统一的运行环境访问入口。

    Attributes:
        clock: 时间抽象（回测用 SimulatedClock，实盘用 RealtimeClock）
        provider: 数据访问抽象
        events: 事件总线
        metadata: 运行时元数据（run_id 等）

    """

    clock: Clock
    provider: DataProvider
    events: EventBus
    metadata: dict[str, Any] = field(default_factory=dict)


class Stage(Protocol):
    """
    计算阶段抽象.

    所有策略、风控、执行步骤统一为 Stage。
    """

    @property
    def name(self) -> str:
        """阶段名称."""
        ...

    def process(self, data: Any, ctx: Context) -> Any:
        """处理输入数据，返回输出数据."""
        ...


class Pipeline:
    """
    不可变 Pipeline — 按序执行 Stage.

    add_stage 返回新 Pipeline（原 Pipeline 不变）。
    """

    def __init__(self, stages: tuple[Stage, ...] = ()) -> None:
        self._stages = stages

    def add_stage(self, stage: Stage) -> Pipeline:
        """添加 stage，返回新 Pipeline."""
        return Pipeline((*self._stages, stage))

    def execute(self, data: Any, ctx: Context) -> Any:
        """按序执行所有 stage."""
        result = data
        for stage in self._stages:
            result = stage.process(result, ctx)
        return result
