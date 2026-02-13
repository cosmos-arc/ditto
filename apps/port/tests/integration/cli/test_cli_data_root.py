"""CLI --data-root 参数透传测试.

测试 --data-root 参数能够透传到 DI 容器的配置中，
覆盖配置文件中的默认值。
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from ditto_port.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

# 集成测试串行执行，避免并发副作用
pytestmark = pytest.mark.serial


@pytest.fixture(autouse=True)
def disable_stdout_logging():
    """在每个 CLI 测试前禁用 stdout 日志输出.

    解决 CliRunner I/O 错误：
    - loguru 的 stdout handler 可能在测试结束时导致 I/O 错误
    - 在测试开始前移除所有 handler
    """
    from loguru import logger as _logger

    # 移除默认 handler（包括 stdout）
    _logger.remove()
    # 测试结束后不恢复，让下一个测试重新配置


@pytest.mark.integration
class TestCLIDataRootPassthrough:
    """CLI --data-root 参数透传测试."""

    def test_data_root_sets_environment_variable(self, tmp_path: Path) -> None:
        """--data-root 参数应设置 DITTO_DATA_ROOT 环境变量."""
        custom_root = str(tmp_path / "custom_data")

        with patch.dict(os.environ, {}, clear=True):
            try:
                result = runner.invoke(app, [f"--data-root={custom_root}", "version"])

                assert result.exit_code == 0
                assert os.getenv("DITTO_DATA_ROOT") == custom_root
            except ValueError as e:
                if "I/O operation on closed file" not in str(e):
                    raise

    def test_data_root_not_set_when_not_provided(self, tmp_path: Path) -> None:
        """不提供 --data-root 参数时不应设置环境变量."""
        # 先清除可能存在的环境变量
        with patch.dict(os.environ, {}, clear=True):
            try:
                result = runner.invoke(app, ["version"])

                assert result.exit_code == 0
                # 不应设置 DITTO_DATA_ROOT
                assert os.getenv("DITTO_DATA_ROOT") is None
            except ValueError as e:
                if "I/O operation on closed file" not in str(e):
                    raise

    def test_data_root_overrides_existing_env(self, tmp_path: Path) -> None:
        """--data-root 参数应覆盖已存在的环境变量."""
        custom_root = str(tmp_path / "custom_data")
        existing_value = "/existing/path"

        with patch.dict(os.environ, {"DITTO_DATA_ROOT": existing_value}, clear=False):
            try:
                result = runner.invoke(app, [f"--data-root={custom_root}", "version"])

                assert result.exit_code == 0
                # CLI 参数应覆盖现有环境变量
                assert os.getenv("DITTO_DATA_ROOT") == custom_root
            except ValueError as e:
                if "I/O operation on closed file" not in str(e):
                    raise
