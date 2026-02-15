"""CLI 主命令集成测试.

测试主命令帮助、版本以及全局选项。
"""

import pytest
from ditto_port.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()

# 集成测试串行执行，避免并发副作用
pytestmark = [pytest.mark.integration, pytest.mark.serial]


def test_main_help() -> None:
    """测试主命令帮助信息."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Ditto" in result.stdout
    assert "init" in result.stdout
    assert "ingest" in result.stdout
    assert "backfill" in result.stdout
    assert "query" in result.stdout
    assert "version" in result.stdout


def test_version_command() -> None:
    """测试版本命令."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "ditto-cli" in result.stdout


def test_verbose_flag() -> None:
    """测试详细输出模式."""
    result = runner.invoke(app, ["--verbose", "version"])
    assert result.exit_code == 0
    assert "ditto-cli" in result.stdout


def test_init_help() -> None:
    """测试 init 命令组帮助."""
    result = runner.invoke(app, ["init", "--help"])
    assert result.exit_code == 0
    assert "config" in result.stdout
    assert "dq" in result.stdout
    assert "db" in result.stdout


def test_ingest_help() -> None:
    """测试 ingest 命令组帮助."""
    result = runner.invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0
    assert "metadata" in result.stdout
    assert "market" in result.stdout


def test_backfill_help() -> None:
    """测试 backfill 命令组帮助."""
    result = runner.invoke(app, ["backfill", "--help"])
    assert result.exit_code == 0
    assert "metadata" in result.stdout
    assert "market" in result.stdout


def test_query_help() -> None:
    """测试 query 命令组帮助."""
    result = runner.invoke(app, ["query", "--help"])
    assert result.exit_code == 0
    assert "metadata" in result.stdout
    assert "market" in result.stdout
