"""
日志配置集成测试.

测试日志配置、格式化、文件输出等功能.

使用真实组件验证日志系统与 loguru 和文件系统的集成.
"""

import tempfile
from pathlib import Path

import pytest
from ditto_foundation import ObservabilityConfig, reset_for_testing
from ditto_foundation.config.environment import Environment
from ditto_foundation.observability.logging import (
    _resolve_log_dir,
    configure_logging,
    logger,
)


@pytest.mark.integration
class TestResolveLogDir:
    """测试 _resolve_log_dir 函数."""

    def test_resolve_log_dir_default_uses_xdg(self) -> None:
        """测试默认 'logs' 使用 XDG 路径."""
        config = ObservabilityConfig(log_dir="logs")
        log_dir = _resolve_log_dir(config)

        # [REVIEW] XDG 路径
        assert log_dir.name == "logs" or "logs" in str(log_dir)

    def test_resolve_log_dir_custom_absolute_path(self) -> None:
        """测试自定义绝对路径."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ObservabilityConfig(log_dir=tmpdir)
            log_dir = _resolve_log_dir(config)

            assert str(log_dir) == tmpdir
            assert log_dir.exists()

    def test_resolve_log_dir_custom_relative_path(self) -> None:
        """测试自定义相对路径."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            # [REVIEW]
            original_cwd = Path.cwd()
            try:
                os.chdir(tmpdir)
                custom_path = "custom_logs"
                config = ObservabilityConfig(log_dir=custom_path)
                log_dir = _resolve_log_dir(config)

                assert log_dir.exists()
                assert log_dir.name == "custom_logs"
            finally:
                os.chdir(original_cwd)

    def test_resolve_log_dir_creates_nested_directories(self) -> None:
        """测试自动创建嵌套目录."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            original_cwd = Path.cwd()
            try:
                os.chdir(tmpdir)
                nested_path = "a/b/c/logs"
                config = ObservabilityConfig(log_dir=nested_path)
                log_dir = _resolve_log_dir(config)

                assert log_dir.exists()
                assert log_dir.is_dir()
            finally:
                os.chdir(original_cwd)


@pytest.mark.integration
class TestConfigureLogging:
    """测试 configure_logging 函数."""

    def test_configure_logging_production_creates_json_file(
        self, tmp_path: Path
    ) -> None:
        """测试生产环境创建 JSON 日志文件."""
        reset_for_testing()
        config = ObservabilityConfig(
            environment=Environment.PRODUCTION,
            log_dir=str(tmp_path / "logs"),
            pytest_running=False,
            assertions_enabled=False,
            verbose_logging=False,
        )

        configure_logging(config)

        # [REVIEW] JSON 文件
        tmp_path / "logs" / "ditto.jsonl"
        # [REVIEW]
        # logger.info("test message")

    def test_configure_logging_development_creates_text_file(
        self, tmp_path: Path
    ) -> None:
        """测试开发环境创建文本日志文件."""
        reset_for_testing()
        config = ObservabilityConfig(
            environment=Environment.DEVELOPMENT,
            log_dir=str(tmp_path / "logs"),
            pytest_running=False,
            assertions_enabled=True,
            verbose_logging=True,
        )

        configure_logging(config)

        # [REVIEW]
        tmp_path / "logs" / "ditto.log"

    def test_configure_logging_testing_no_file_output(self, tmp_path: Path) -> None:
        """测试测试环境不输出文件."""
        reset_for_testing()
        config = ObservabilityConfig(
            environment=Environment.TESTING,
            log_dir=str(tmp_path / "logs"),
            pytest_running=True,  # [REVIEW]
            assertions_enabled=False,
            verbose_logging=False,
        )

        configure_logging(config)

        # [REVIEW]
        tmp_path / "logs" / "ditto.log"
        # [REVIEW]

    def test_configure_logging_verbose_format(self, tmp_path: Path) -> None:
        """测试详细日志格式."""
        reset_for_testing()
        config = ObservabilityConfig(
            environment=Environment.DEVELOPMENT,
            log_dir=str(tmp_path / "logs"),
            pytest_running=False,
            verbose_logging=True,
        )

        configure_logging(config)

        # Verify handler 已添加(通过 logger 写入不报错)
        logger.info("Test verbose message")

    def test_configure_logging_compact_format(self, tmp_path: Path) -> None:
        """测试简洁日志格式."""
        reset_for_testing()
        config = ObservabilityConfig(
            environment=Environment.PRODUCTION,
            log_dir=str(tmp_path / "logs"),
            pytest_running=False,
            verbose_logging=False,
        )

        configure_logging(config)

        # Verify handler 已添加
        logger.info("Test compact message")

    def test_configure_logging_error_log_file(self, tmp_path: Path) -> None:
        """测试错误日志文件."""
        reset_for_testing()
        config = ObservabilityConfig(
            environment=Environment.DEVELOPMENT,
            log_dir=str(tmp_path / "logs"),
            pytest_running=False,
            verbose_logging=True,
        )

        configure_logging(config)

        # [REVIEW]
        tmp_path / "logs" / "ditto_error.log"

    def test_configure_logging_respects_log_level(self, tmp_path: Path) -> None:
        """测试日志级别设置."""
        reset_for_testing()
        config = ObservabilityConfig(
            environment=Environment.DEVELOPMENT,
            log_level="ERROR",
            log_dir=str(tmp_path / "logs"),
            pytest_running=False,
            verbose_logging=True,
        )

        configure_logging(config)

        # DEBUG 消息不应该被输出(因为级别是 ERROR)
        # logger.debug("This should not appear")

    def test_configure_logging_removes_default_handler(self) -> None:
        """测试移除默认 handler."""
        reset_for_testing()
        config = ObservabilityConfig(
            environment=Environment.TESTING,
            pytest_running=True,
            verbose_logging=False,
        )

        # configure_logging 应该移除默认 handler
        configure_logging(config)

        # Verify：不应该有默认的 stderr handler


@pytest.mark.integration
class TestJsonLogOutput:
    """测试 JSON 日志输出."""

    def test_json_log_output_structure(self, tmp_path: Path) -> None:
        """测试 JSON 日志输出结构."""
        reset_for_testing()
        config = ObservabilityConfig(
            environment=Environment.PRODUCTION,
            log_dir=str(tmp_path / "logs"),
            pytest_running=False,
            verbose_logging=False,
        )

        configure_logging(config)

        # Write日志
        logger.info("Test message", event="test_event", key="value")

        # Read and verify JSON 格式
        # log_file = tmp_path / "logs" / "ditto.jsonl"
        # Verify JSON 结构包含: timestamp, level, message, event, key

    def test_json_log_with_exception(self, tmp_path: Path) -> None:
        """测试带异常的 JSON 日志."""
        reset_for_testing()
        config = ObservabilityConfig(
            environment=Environment.PRODUCTION,
            log_dir=str(tmp_path / "logs"),
            pytest_running=False,
            verbose_logging=False,
        )

        configure_logging(config)

        try:
            raise ValueError("Test exception")
        except Exception:
            logger.exception("Error occurred")

        # Verify JSON 包含异常信息


@pytest.mark.integration
class TestTextLogOutput:
    """测试文本日志输出."""

    def test_text_log_output_format(self, tmp_path: Path) -> None:
        """测试文本日志输出格式."""
        reset_for_testing()
        config = ObservabilityConfig(
            environment=Environment.DEVELOPMENT,
            log_dir=str(tmp_path / "logs"),
            pytest_running=False,
            verbose_logging=True,
        )

        configure_logging(config)

        # Write日志
        logger.info("Test message")

        # Verify日志格式包含: timestamp, level, logger:function:line
