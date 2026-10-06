"""
初始化集成测试.

测试 init(), shutdown() 等核心功能.

使用真实组件验证可观测性系统初始化和关闭流程与 OpenTelemetry SDK 的集成.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, TypedDict, Unpack, cast

import pytest
from ditto_platform.foundation import (
    Metrics,
    init,
    reset_for_testing,
    shutdown,
)
from ditto_platform.foundation.config.environment import Environment
from ditto_platform.foundation.observability._registry import (
    is_initialized as _is_initialized,
)
from ditto_platform.foundation.observability.config import ObservabilityConfig


class _OtlpHttpSink:
    """本地一次性 OTLP HTTP 接收端：真实 POST 往返，零 mock（#348）."""

    def __init__(self) -> None:
        self._posts: list[str] = []
        sink = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # http.server 约定命名
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                sink._posts.append(self.path)
                self.send_response(200)
                self.end_headers()

            def log_message(self, fmt: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def metrics_endpoint(self) -> str:
        return (
            f"http://127.0.0.1:{self._server.server_address[1]}"
            "/opentelemetry/v1/metrics"
        )

    @property
    def metrics_posts(self) -> int:
        return sum(1 for path in self._posts if path.endswith("/v1/metrics"))


@pytest.fixture
def otlp_http_sink() -> Iterator[_OtlpHttpSink]:
    """启动/关闭本地 OTLP sink（生产传输接缝的确定性真实端点）."""
    sink = _OtlpHttpSink()
    sink._thread.start()
    yield sink
    sink._server.shutdown()
    sink._server.server_close()
    sink._thread.join(timeout=5)


class _TestConfigKwargs(TypedDict, total=False):
    """_test_config 覆写参数的精确键型（调用侧受检，#540）."""

    service_name: str
    environment: Environment
    pytest_running: bool
    assertions_enabled: bool | None
    verbose_logging: bool | None


def _test_config(**overrides: Unpack[_TestConfigKwargs]) -> ObservabilityConfig:
    values: dict[str, object] = {
        "environment": Environment.TESTING,
        "pytest_running": True,
        "assertions_enabled": True,
        "verbose_logging": False,
    }
    # 覆写参数经 Unpack[TypedDict] 调用侧受检；合并字典构造点单点放宽。
    return ObservabilityConfig(**cast("dict[str, Any]", {**values, **overrides}))


@pytest.mark.integration
class TestInit:
    """测试 init() 函数."""

    def test_init_sets_registry_flag(self) -> None:
        """测试 init() 设置注册表标志."""
        reset_for_testing()
        assert _is_initialized() is False

        init(_test_config(), force=True)
        assert _is_initialized() is True

    def test_init_idempotent_without_force(self) -> None:
        """测试无 force 参数时 init() 幂等."""
        reset_for_testing()
        init(_test_config(), force=True)
        first_registry_state = _is_initialized()

        # [REVIEW] force，应该被忽略
        init(_test_config())
        second_registry_state = _is_initialized()

        assert first_registry_state is True
        assert second_registry_state is True

    def test_init_with_custom_parameters(self, otlp_http_sink: _OtlpHttpSink) -> None:
        """测试使用自定义参数初始化（生产 OTLP 传输走本地真实 sink）.

        生产 metrics 路径构造 PeriodicExportingMetricReader + OTLP
        exporter；vm_endpoint 指向本地 sink，shutdown 的末次导出发生
        真实 HTTP POST 并被断言，替代原先 provider 泄漏到进程退出的
        隐式行为（连接被拒会触发 exporter 内建指数退避重试 ~15s）.
        """
        reset_for_testing()
        config = ObservabilityConfig(
            service_name="test_service",
            environment=Environment.PRODUCTION,
            log_level="WARNING",
            vm_endpoint=otlp_http_sink.metrics_endpoint,
        )
        # finally 内 shutdown：任何失败路径下 provider 关闭都发生在 sink
        # fixture 拆除之前（sink 先拆会让末次导出撞上已关闭端点的退避）
        try:
            init(config, force=True)
            assert _is_initialized() is True

            # 记录真实数据点：空采集时 SDK 可不触发导出，记录后 shutdown
            # 的末次导出确定性携带数据（reader.shutdown join 前完成 POST）
            Metrics.api_requests.add(1, {"endpoint": "/health"})
        finally:
            shutdown()
        assert otlp_http_sink.metrics_posts > 0, "生产 reader 关闭时应完成真实导出"

    def test_init_environment_alias_dev(self) -> None:
        """测试环境简写 'dev' 映射到 'development'."""
        reset_for_testing()
        init(_test_config(), force=True)
        with pytest.raises(RuntimeError):
            init(_test_config(service_name="other"))

    def test_init_environment_alias_test(self) -> None:
        """测试环境简写 'test' 映射到 'testing'."""
        reset_for_testing()
        init(_test_config(), force=True)
        init(_test_config(), force=True)
        assert _is_initialized() is True

    def test_init_environment_alias_prod(self) -> None:
        """测试环境简写 'prod' 映射到 'production'."""
        reset_for_testing()
        init(_test_config(), force=True)
        assert _is_initialized() is True


@pytest.mark.integration
class TestShutdown:
    """测试 shutdown() 函数."""

    def test_shutdown_clears_registry_flag(self) -> None:
        """测试 shutdown() 清除注册表标志."""
        reset_for_testing()
        init(_test_config(), force=True)
        assert _is_initialized() is True

        shutdown()
        assert _is_initialized() is False

    def test_shutdown_idempotent(self) -> None:
        """测试多次 shutdown() 幂等."""
        reset_for_testing()
        init(_test_config(), force=True)

        # [REVIEW] shutdown
        shutdown()
        assert _is_initialized() is False

        # [REVIEW] shutdown 不应该报错
        shutdown()
        assert _is_initialized() is False

    def test_shutdown_without_init(self) -> None:
        """测试未初始化时 shutdown() 不报错."""
        reset_for_testing()
        assert _is_initialized() is False

        # [REVIEW]
        shutdown()
        assert _is_initialized() is False

    def test_shutdown_logs_debug_message(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """测试 shutdown() 记录调试日志."""
        reset_for_testing()
        init(_test_config(assertions_enabled=False), force=True)

        with caplog.at_level("DEBUG"):
            shutdown()

        # [REVIEW](即使 shutdown 失败也会记录调试信息)
        # [REVIEW] OpenTelemetry provider 的行为
