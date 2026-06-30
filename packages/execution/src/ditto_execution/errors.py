"""Execution package errors."""

from __future__ import annotations

from ditto_kernel.exceptions import DittoError

__all__ = [
    "AuditError",
    "ExecutionError",
    "FatalError",
    "FillProcessingError",
    "InsufficientFundsError",
    "OrderStateError",
    "OrderSubmitError",
    "ReconciliationError",
    "TemporaryError",
]


class ExecutionError(DittoError):
    """
    执行域基础异常.

    所有执行域异常的统一祖先，供上层统一捕获和映射。
    """


class OrderSubmitError(ExecutionError):
    """订单提交失败."""


class OrderStateError(ExecutionError):
    """订单状态转换非法."""


class FillProcessingError(ExecutionError):
    """成交处理失败."""


class ReconciliationError(ExecutionError):
    """对账失败."""


class TemporaryError(ExecutionError):
    """可重试错误 — 超时、网络抖动等暂时性故障."""


class FatalError(ExecutionError):
    """不可恢复错误 — 权限、配置等永久性故障."""


class InsufficientFundsError(OrderSubmitError):
    """资金不足 — 订单所需资金超过可用余额."""


class AuditError(ExecutionError):
    """审计失败."""
