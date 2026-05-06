"""Execution 层 DI Provider 工厂."""

from __future__ import annotations

from dishka import Provider

from .storage import ExecutionStorageProvider

__all__ = ["get_execution_providers"]


def get_execution_providers() -> list[Provider]:
    """返回 Execution 层的所有 Provider."""
    return [ExecutionStorageProvider()]
