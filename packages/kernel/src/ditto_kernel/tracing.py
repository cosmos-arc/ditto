"""
Kernel-level tracing — 零外部依赖的可插拔追踪装饰器.

业务包（engine 等）通过此模块声明 tracing 意图；
默认为 no-op（无副作用），可通过 install_trace_handler 注入真实实现。

此模块不引入任何第三方依赖，满足 Kernel 零外部依赖约束。
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")

# 模块级 handler 槽 — 默认 None 表示 no-op
_trace_handler: Callable[..., Any] | None = None


def install_trace_handler(handler: Callable[..., Any]) -> None:
    """
    安装全局 trace handler.

    安装后，所有 @traced 装饰的函数在调用时会将
    (operation, fn, *args, **kwargs) 委托给 handler 执行。

    Args:
        handler: 接受 (operation: str, fn, *args, **kwargs) 的可调用对象.

    """
    global _trace_handler  # noqa: PLW0603
    _trace_handler = handler


def reset_trace_handler() -> None:
    """恢复 no-op 行为（清除已安装的 handler）."""
    global _trace_handler  # noqa: PLW0603
    _trace_handler = None


def traced(operation: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """
    可插拔追踪装饰器.

    默认 no-op（仅保留函数签名不变）；
    安装 handler 后，委托给 handler 执行。

    Parameters
    ----------
    operation:
        语义化操作名称。

    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            if _trace_handler is not None:
                return _trace_handler(operation, func, *args, **kwargs)
            return func(*args, **kwargs)

        return wrapper

    return decorator


__all__ = ["install_trace_handler", "reset_trace_handler", "traced"]
