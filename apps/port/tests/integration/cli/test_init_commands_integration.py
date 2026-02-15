"""Init 命令集成测试."""

from pathlib import Path

import pytest
from ditto_port.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

# 集成测试串行执行，避免并发副作用
pytestmark = pytest.mark.serial


@pytest.mark.integration
def test_init_config_default_command(tmp_path: Path):
    """测试 init config 命令（默认数据根目录）."""
    result = runner.invoke(
        app,
        ["init", "config"],
    )
    # 命令应该成功执行（可能跳过已存在的配置）
    output = result.stdout + result.stderr
    assert result.exit_code == 0 or "already exists" in output.lower()


@pytest.mark.integration
def test_init_config_with_data_root(tmp_path: Path):
    """测试 init config --data-root 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "init", "config"],
    )
    # 命令应该成功执行
    assert result.exit_code == 0


@pytest.mark.integration
def test_init_config_with_force(tmp_path: Path):
    """测试 init config --force 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "init", "config", "--force"],
    )
    assert result.exit_code == 0


@pytest.mark.integration
def test_init_dq_command(tmp_path: Path):
    """测试 init dq 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "init", "dq"],
    )
    # 命令应该成功执行
    assert result.exit_code == 0


@pytest.mark.integration
def test_init_dq_with_force(tmp_path: Path):
    """测试 init dq --force 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "init", "dq", "--force"],
    )
    assert result.exit_code == 0


@pytest.mark.integration
def test_init_db_command(tmp_path: Path):
    """测试 init db 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "init", "db"],
    )
    # 命令应该成功执行
    assert result.exit_code == 0


@pytest.mark.integration
def test_init_db_with_force(tmp_path: Path):
    """测试 init db --force 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "init", "db", "--force"],
    )
    assert result.exit_code == 0
