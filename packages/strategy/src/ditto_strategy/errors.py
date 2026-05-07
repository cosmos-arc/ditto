"""Strategy package error types."""

from __future__ import annotations

from ditto_kernel.exceptions import DittoError

__all__ = [
    "PipelineExecutionError",
    "SignalGenerationError",
    "StrategyError",
    "StrategySpecError",
    "TemplateNotFoundError",
]


class StrategyError(DittoError):
    """
    策略域基础异常.

    所有策略域异常的统一祖先，供上层统一捕获和映射。
    """


class StrategySpecError(StrategyError):
    """策略规格验证失败（公共 API 契约违背）."""

    @property
    def spec_name(self) -> str:
        """返回关联的策略规格名称."""
        return str(self.details.get("spec_name", ""))


class SignalGenerationError(StrategyError):
    """信号生成阶段失败."""


class PipelineExecutionError(StrategyError):
    """Pipeline 执行阶段失败."""


class TemplateNotFoundError(StrategyError):
    """策略模板不存在."""
