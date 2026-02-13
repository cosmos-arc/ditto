"""Dishka FastAPI integration type stubs."""

from collections.abc import Awaitable, Callable

from dishka import AsyncContainer
from fastapi import FastAPI

__all__ = [
    "inject",
    "setup_dishka",
]

def inject[**P, R](func: Callable[P, Awaitable[R]], /) -> Callable[P, Awaitable[R]]:
    """装饰器：注入依赖到 FastAPI 路由处理函数."""

def setup_dishka(container: AsyncContainer, app: FastAPI) -> None:
    """集成 dishka 到 FastAPI 应用."""
