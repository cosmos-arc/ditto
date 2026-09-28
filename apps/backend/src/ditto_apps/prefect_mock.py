"""
Tree-scoped Prefect decorator mocks for backend unit collection.

Historically the backend unit conftest swapped ``prefect.flows.flow`` /
``prefect.tasks.task`` at conftest-import time, which leaked the mock into
every module imported later in the same process — including other owners'
tests in full-tree or CI shard entries. The helpers here keep the same mock,
but the conftest registers it as an import bracket on the layering plugin
(``register_import_bracket``): applied while backend unit test modules
import, restored for everything else (#330 B1).

``sys.modules`` caching means whichever scope imports ``ditto_apps.jobs.*``
first fixes that module's decoration for the whole process: a single-process
merged entry that collects the integration tree before ``unit`` hands unit
tests real-decorated modules (and vice versa). CI shard lanes never mix the
two scopes in one process (serial integration lane vs parallel lane), and
each entry in isolation decorates consistently. Serving both decorations in
one process needs per-scope import isolation — deferred to the D1 backend
jobs pilot (#330); eviction-based fixes are not viable: evicting on either
transition breaks the opposite scope, and evicting on both breaks
``mocker.patch`` identity for runtime patching (verified by reproduction).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import prefect.flows
import prefect.tasks

# [(flow, task) originals] — one entry while the mock is installed.
_saved: list[tuple[Any, Any]] = []


class MockTask:
    """Mock task that mimics the Prefect Task interface."""

    def __init__(self, func: Any) -> None:
        self.func = func
        # 复制函数的关键属性
        self.__name__ = getattr(func, "__name__", "mock_task")
        self.__doc__ = getattr(func, "__doc__", None)
        self.name = self.__name__
        self._is_prefect_task = True

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Call the wrapped function, filtering Prefect-specific arguments."""
        # 过滤掉 Prefect 特有的参数
        filtered_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k not in ("wait_for", "return_state", "refresh_cache")
        }
        return self.func(*args, **filtered_kwargs)

    def submit(self, *args: Any, **kwargs: Any) -> Any:
        """Mock submit that returns a future-like object."""
        # 过滤掉 Prefect 特有的参数
        filtered_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k not in ("wait_for", "return_state", "refresh_cache")
        }
        result = self.func(*args, **filtered_kwargs)
        future = Mock()
        future.result = Mock(return_value=result)
        return future

    def fn(self) -> Any:
        """Return the underlying function."""
        return self.func


def _mock_flow_decorator(*args: Any, **kwargs: Any) -> Any:
    """Mock @flow decorator that returns the function unchanged."""

    def decorator(func: Any) -> Any:
        # 添加 flow 的常用属性
        func.is_flow = True
        func.name = getattr(func, "__name__", "mock_flow")
        return func

    # Support @flow() and @flow syntax
    if args and callable(args[0]):
        return args[0]  # Direct @flow without parentheses
    return decorator


def _mock_task_decorator(*args: Any, **kwargs: Any) -> Any:
    """Mock @task decorator that returns a MockTask."""

    def decorator(func: Any) -> MockTask:
        return MockTask(func)

    # Support @task() and @task syntax
    if args and callable(args[0]):
        return MockTask(args[0])  # Direct @task without parentheses
    return decorator


def apply() -> None:
    """Swap Prefect's decorators for the unit-test stand-ins (idempotent)."""
    if _saved:
        return
    _saved.append((prefect.flows.flow, prefect.tasks.task))
    prefect.flows.flow = _mock_flow_decorator
    prefect.tasks.task = _mock_task_decorator


def restore() -> None:
    """Undo :func:`apply`; foreign imports must see the real decorators."""
    if not _saved:
        return
    prefect.flows.flow, prefect.tasks.task = _saved.pop()


def is_applied() -> bool:
    """Whether the mock decorators are currently installed."""
    return bool(_saved)
