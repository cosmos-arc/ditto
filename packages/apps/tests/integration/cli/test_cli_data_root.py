"""CLI --data-root 参数传递测试.

测试 --data-root 参数能够存储到 CLI 上下文中，
供后续 create_cli_executor 使用。

重构后（ENG-004）：
- data_root 不再设置 os.environ，而是存储在 ctx.obj 中
- 避免全局副作用，采用显式参数传递
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from ditto_apps.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

# 集成测试串行执行，避免并发副作用
# cli_test: 禁用 observability 自动重置，避免 I/O 冲突
pytestmark = [pytest.mark.integration, pytest.mark.serial, pytest.mark.cli_test]


class TestCLIDataRootPassthrough:
    """CLI --data-root 参数传递测试."""

    def test_data_root_not_set_as_env_var(self, tmp_path: Path) -> None:
        """--data-root 参数不应设置 DITTO_DATA_ROOT 环境变量（消除副作用）."""
        custom_root = str(tmp_path / "custom_data")

        with patch.dict(os.environ, {}, clear=True):
            result = runner.invoke(app, [f"--data-root={custom_root}", "version"])

            assert result.exit_code == 0
            # 环境变量不应被设置（消除副作用）
            assert os.getenv("DITTO_DATA_ROOT") is None

    def test_data_root_not_set_when_not_provided(self, tmp_path: Path) -> None:
        """不提供 --data-root 参数时不应设置环境变量."""
        # 先清除可能存在的环境变量
        with patch.dict(os.environ, {}, clear=True):
            result = runner.invoke(app, ["version"])

            assert result.exit_code == 0
            # 不应设置 DITTO_DATA_ROOT
            assert os.getenv("DITTO_DATA_ROOT") is None

    def test_existing_env_not_overridden(self, tmp_path: Path) -> None:
        """--data-root 参数不应覆盖已存在的环境变量（显式传递，无副作用）."""
        custom_root = str(tmp_path / "custom_data")
        existing_value = "/existing/path"

        with patch.dict(os.environ, {"DITTO_DATA_ROOT": existing_value}, clear=False):
            result = runner.invoke(app, [f"--data-root={custom_root}", "version"])

            assert result.exit_code == 0
            # CLI 参数不应覆盖环境变量（消除副作用）
            # data_root 存储在 ctx.obj 中，不设置 os.environ
            assert os.getenv("DITTO_DATA_ROOT") == existing_value
