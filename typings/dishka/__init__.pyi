"""
Dishka 类型存根文件.

修复 dishka 的类型注解问题，使其与 pyright 兼容。
"""

from collections.abc import Callable
from typing import Any, overload

from dishka.entities.scope import BaseScope

__all__ = ["Provider", "Scope", "provide"]

class Provider:
    """依赖提供者基类."""

    scope: BaseScope

class Scope:
    """依赖作用域."""

    APP: BaseScope
    REQUEST: BaseScope
    ACTION: BaseScope
    STEP: BaseScope

@overload
def provide(
    source: type[Any] | None = None,
    *,
    scope: BaseScope | None = None,
    provides: Any = None,
    cache: bool = True,
) -> Any: ...
@overload
def provide(
    source: Callable[..., Any] | classmethod[Any, Any, Any] | staticmethod[Any, Any],
    *,
    scope: BaseScope | None = None,
    provides: Any = None,
    cache: bool = True,
) -> Any: ...
def provide(
    source: Any = None,
    *,
    scope: BaseScope | None = None,
    provides: Any = None,
    cache: bool = True,
) -> Any:
    """
    装饰器：标记提供依赖的方法.

    Args:
        source: 提供者（类或方法）
        scope: 依赖作用域
        provides: 提供的类型
        cache: 是否缓存

    Returns:
        装饰后的函数

    """
