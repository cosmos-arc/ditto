"""
Kernel tracing 模块单元测试.

覆盖：
- @traced 默认 no-op（透传，返回正确值）
- install_trace_handler 使 @traced 委托给 handler
- reset_trace_handler 恢复 no-op 行为
- handler 接收正确的 (operation, fn, *args, **kwargs)
"""

from __future__ import annotations

from typing import Any

import pytest
from ditto_kernel.tracing import (
    install_trace_handler,
    reset_trace_handler,
    traced,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_handler() -> Any:
    """每个测试前后确保 handler 被重置."""
    reset_trace_handler()
    yield
    reset_trace_handler()


# ---------------------------------------------------------------------------
# No-op 行为测试
# ---------------------------------------------------------------------------


class TestTracedNoOp:
    """@traced 默认 no-op 行为."""

    def test_returns_correct_value(self) -> None:
        """装饰后的函数返回原始值."""

        @traced("test.op")
        def add(a: int, b: int) -> int:
            return a + b

        assert add(2, 3) == 5

    def test_preserves_function_name(self) -> None:
        """functools.wraps 保留原始函数名."""

        @traced("test.op")
        def my_function() -> None:
            pass

        assert my_function.__name__ == "my_function"

    def test_passes_kwargs_correctly(self) -> None:
        """关键字参数正确传递."""

        @traced("test.op")
        def greet(name: str, greeting: str = "hello") -> str:
            return f"{greeting}, {name}"

        assert greet(name="world", greeting="hi") == "hi, world"

    def test_no_side_effects_by_default(self) -> None:
        """默认 no-op 无副作用."""

        calls: list[str] = []

        @traced("test.op")
        def side_effect() -> None:
            calls.append("called")

        side_effect()
        assert calls == ["called"]

    def test_preserves_return_none(self) -> None:
        """返回 None 的函数正确工作."""

        @traced("test.op")
        def void() -> None:
            pass

        result = void()
        assert result is None


# ---------------------------------------------------------------------------
# install_trace_handler 测试
# ---------------------------------------------------------------------------


class TestInstallTraceHandler:
    """install_trace_handler 使 @traced 委托给 handler."""

    def test_handler_receives_operation_name(self) -> None:
        """handler 接收正确的 operation 名称."""
        captured: list[str] = []

        def handler(operation: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
            captured.append(operation)
            return fn(*args, **kwargs)

        install_trace_handler(handler)

        @traced("my.operation")
        def dummy() -> int:
            return 42

        dummy()
        assert captured == ["my.operation"]

    def test_handler_receives_function(self) -> None:
        """handler 接收原始函数对象."""
        received_fn: list[Any] = []

        def handler(operation: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
            received_fn.append(fn)
            return fn(*args, **kwargs)

        install_trace_handler(handler)

        def target(x: int) -> int:
            return x * 2

        decorated = traced("op")(target)
        decorated(5)

        assert received_fn[0] is target

    def test_handler_receives_positional_args(self) -> None:
        """handler 接收正确的位置参数."""
        received_args: list[tuple[Any, ...]] = []

        def handler(operation: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
            received_args.append(args)
            return fn(*args, **kwargs)

        install_trace_handler(handler)

        @traced("op")
        def compute(a: int, b: int, c: int) -> int:
            return a + b + c

        compute(1, 2, 3)
        assert received_args[0] == (1, 2, 3)

    def test_handler_receives_kwargs(self) -> None:
        """handler 接收正确的关键字参数."""
        received_kwargs: list[dict[str, Any]] = []

        def handler(operation: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
            received_kwargs.append(kwargs)
            return fn(*args, **kwargs)

        install_trace_handler(handler)

        @traced("op")
        def search(query: str, limit: int = 10) -> str:
            return f"{query}:{limit}"

        search("test", limit=20)
        assert received_kwargs[0] == {"limit": 20}

    def test_handler_return_value_is_forwarded(self) -> None:
        """handler 的返回值作为装饰函数的返回值."""

        def handler(operation: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
            result = fn(*args, **kwargs)
            return result * 10

        install_trace_handler(handler)

        @traced("op")
        def compute(x: int) -> int:
            return x + 1

        assert compute(3) == 40  # (3+1) * 10

    def test_handler_can_short_circuit(self) -> None:
        """handler 可以不调用原始函数直接返回."""

        def handler(operation: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
            return -1

        install_trace_handler(handler)

        @traced("op")
        def never_called() -> int:
            raise AssertionError("Should not be called")

        assert never_called() == -1


# ---------------------------------------------------------------------------
# reset_trace_handler 测试
# ---------------------------------------------------------------------------


class TestResetTraceHandler:
    """reset_trace_handler 恢复 no-op 行为."""

    def test_restores_noop_after_install(self) -> None:
        """重置后 @traced 恢复 no-op."""
        call_count = 0

        def handler(operation: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            return fn(*args, **kwargs)

        install_trace_handler(handler)

        @traced("op")
        def dummy() -> int:
            return 1

        dummy()
        assert call_count == 1

        reset_trace_handler()
        dummy()
        # handler 不再被调用
        assert call_count == 1

    def test_returns_correct_value_after_reset(self) -> None:
        """重置后函数返回原始值."""

        def handler(operation: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
            return -999

        install_trace_handler(handler)

        @traced("op")
        def compute(x: int) -> int:
            return x + 1

        # handler 拦截
        assert compute(5) == -999

        # 重置后恢复原始行为
        reset_trace_handler()
        assert compute(5) == 6

    def test_multiple_install_reset_cycles(self) -> None:
        """多次 install/reset 循环正确工作."""
        values: list[str] = []

        def handler_a(op: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
            values.append("a")
            return fn(*args, **kwargs)

        def handler_b(op: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
            values.append("b")
            return fn(*args, **kwargs)

        @traced("op")
        def noop() -> int:
            return 0

        install_trace_handler(handler_a)
        noop()

        install_trace_handler(handler_b)
        noop()

        reset_trace_handler()
        noop()

        assert values == ["a", "b"]
