"""Execution package errors."""

from __future__ import annotations

from ditto_kernel.exceptions import DittoError

__all__ = [
    "AuditError",
    "ExecutionError",
    "FillProcessingError",
    "OrderStateError",
    "OrderSubmitError",
    "ReconciliationError",
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


class AuditError(ExecutionError):
    """审计失败."""
