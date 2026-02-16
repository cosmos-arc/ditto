"""
Dishka 类型存根文件.

修复 dishka 的类型注解问题，使其与 pyright 兼容。
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeVar, overload

from dishka.entities.scope import BaseScope

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = [
    "FromComponent",
    "Provider",
    "Scope",
    "make_async_container",
    "make_container",
    "provide",
    "setup_dishka",
]

_T = TypeVar("_T")

class Container:
    """同步容器接口."""

    def get(self, type_: type[_T]) -> _T: ...
    def close(self) -> None: ...

class AsyncContainer:
    """异步容器接口."""

    async def get(self, dependency_type: type[_T]) -> _T: ...
    async def close(self) -> None: ...

class Provider:
    """依赖提供者基类."""

    scope: BaseScope

class Scope:
    """依赖作用域."""

    APP: BaseScope
    REQUEST: BaseScope
    ACTION: BaseScope
    STEP: BaseScope

class FromComponent:
    """组件标记，用于依赖注入."""

    component: Any
    def __init__(self, component: Any = ...) -> None: ...

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

def make_async_container(*providers: Provider) -> AsyncContainer:
    """
    创建异步容器.

    Args:
        *providers: Provider 实例

    Returns:
        异步容器实例

    """

def make_container(*providers: Provider) -> Container:
    """
    创建同步容器.

    Args:
        *providers: Provider 实例

    Returns:
        同步容器实例

    """

def setup_dishka(container: AsyncContainer, app: FastAPI) -> None:
    """
    集成 dishka 到 FastAPI.

    Args:
        container: dishka 异步容器实例
        app: FastAPI 应用实例

    """
