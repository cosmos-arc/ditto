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
# cli_test: 禁用 observability 自动重置，避免 I/O 冲突
pytestmark = [pytest.mark.integration, pytest.mark.serial, pytest.mark.cli_test]


class TestCLIDataRootPassthrough:
    """CLI --data-root 参数透传测试."""

    def test_data_root_sets_environment_variable(self, tmp_path: Path) -> None:
        """--data-root 参数应设置 DITTO_DATA_ROOT 环境变量."""
        custom_root = str(tmp_path / "custom_data")

        with patch.dict(os.environ, {}, clear=True):
            result = runner.invoke(app, [f"--data-root={custom_root}", "version"])

            assert result.exit_code == 0
            assert os.getenv("DITTO_DATA_ROOT") == custom_root

    def test_data_root_not_set_when_not_provided(self, tmp_path: Path) -> None:
        """不提供 --data-root 参数时不应设置环境变量."""
        # 先清除可能存在的环境变量
        with patch.dict(os.environ, {}, clear=True):
            result = runner.invoke(app, ["version"])

            assert result.exit_code == 0
            # 不应设置 DITTO_DATA_ROOT
            assert os.getenv("DITTO_DATA_ROOT") is None

    def test_data_root_overrides_existing_env(self, tmp_path: Path) -> None:
        """--data-root 参数应覆盖已存在的环境变量."""
        custom_root = str(tmp_path / "custom_data")
        existing_value = "/existing/path"

        with patch.dict(os.environ, {"DITTO_DATA_ROOT": existing_value}, clear=False):
            result = runner.invoke(app, [f"--data-root={custom_root}", "version"])

            assert result.exit_code == 0
            # CLI 参数应覆盖现有环境变量
            assert os.getenv("DITTO_DATA_ROOT") == custom_root
