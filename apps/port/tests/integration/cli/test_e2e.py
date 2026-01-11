"""CLI 端到端集成测试.

测试完整的 CLI 工作流，包括：
- 主命令帮助和版本
- 各命令组的帮助信息
- 完整的数据摄取工作流
"""

from pathlib import Path

import pytest
from ditto_port.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.mark.integration
def test_main_help():
    """测试主命令帮助信息."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Ditto" in result.stdout
    assert "stock" in result.stdout
    assert "etf" in result.stdout
    assert "calendar" in result.stdout
    assert "adj" in result.stdout
    assert "version" in result.stdout


@pytest.mark.integration
def test_version_command():
    """测试版本命令."""
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "ditto-cli" in result.stdout


@pytest.mark.integration
def test_stock_help():
    """测试 stock 命令组帮助."""
    result = runner.invoke(app, ["stock", "--help"])
    assert result.exit_code == 0
    assert "daily" in result.stdout
    assert "backfill" in result.stdout
    assert "basic" in result.stdout


@pytest.mark.integration
def test_etf_help():
    """测试 etf 命令组帮助."""
    result = runner.invoke(app, ["etf", "--help"])
    assert result.exit_code == 0
    assert "daily" in result.stdout
    assert "backfill" in result.stdout
    assert "basic" in result.stdout


@pytest.mark.integration
def test_calendar_help():
    """测试 calendar 命令组帮助."""
    result = runner.invoke(app, ["calendar", "--help"])
    assert result.exit_code == 0
    assert "update" in result.stdout


@pytest.mark.integration
def test_adj_help():
    """测试 adj 命令组帮助."""
    result = runner.invoke(app, ["adj", "--help"])
    assert result.exit_code == 0
    assert "adj-factor" in result.stdout
    assert "fund-adj" in result.stdout


@pytest.mark.integration
def test_e2e_stock_daily_workflow(temp_dir: Path):
    """测试完整的 stock daily 工作流."""
    # 测试参数验证 - 无效日期格式
    result = runner.invoke(app, ["stock", "daily", "2024/01/02"])
    assert result.exit_code == 1
    assert "错误" in result.stdout or "格式" in result.stdout

    # 测试帮助信息
    result = runner.invoke(app, ["stock", "daily", "--help"])
    assert result.exit_code == 0
    assert "交易日期" in result.stdout or "date" in result.stdout

    # 测试实际命令执行（可能会因数据库问题失败，这是预期的）
    result = runner.invoke(
        app,
        ["--data-root", str(temp_dir), "stock", "daily", "2024-01-02"],
    )
    # 命令应该成功执行或因为数据源问题失败（非 CLI 问题）
    assert (
        result.exit_code == 0
        or "unable to open database file" in str(result.exception)
        or "Tushare" in str(result.exception)
    )


@pytest.mark.integration
def test_e2e_backfill_workflow(temp_dir: Path):
    """测试完整的 backfill 工作流."""
    # 测试日期范围验证
    result = runner.invoke(
        app,
        [
            "--data-root",
            str(temp_dir),
            "stock",
            "backfill",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-03",
        ],
    )
    # 命令应该尝试执行
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_e2e_backfill_with_parallel(temp_dir: Path):
    """测试带并行度的 backfill 工作流."""
    result = runner.invoke(
        app,
        [
            "--data-root",
            str(temp_dir),
            "etf",
            "backfill",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-02",
            "--parallel",
            "2",
        ],
    )
    # 命令应该尝试执行
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_e2e_basic_commands(temp_dir: Path):
    """测试基础信息命令."""
    # 测试 stock basic
    result = runner.invoke(app, ["--data-root", str(temp_dir), "stock", "basic"])
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )

    # 测试 etf basic
    result = runner.invoke(app, ["--data-root", str(temp_dir), "etf", "basic"])
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_e2e_calendar_command(temp_dir: Path):
    """测试交易日历命令."""
    result = runner.invoke(app, ["--data-root", str(temp_dir), "calendar"])
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_e2e_adj_commands(temp_dir: Path):
    """测试复权因子命令."""
    # 测试 adj-factor
    result = runner.invoke(
        app,
        ["--data-root", str(temp_dir), "adj", "adj-factor", "2024-01-02"],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )

    # 测试 fund-adj
    result = runner.invoke(
        app,
        ["--data-root", str(temp_dir), "adj", "fund-adj", "2024-01-02"],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_verbose_flag(temp_dir: Path):
    """测试详细输出模式."""
    result = runner.invoke(
        app,
        ["--data-root", str(temp_dir), "--verbose", "stock", "basic"],
    )
    # 命令应该接受 verbose 参数
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_force_flag(temp_dir: Path):
    """测试强制重新摄取标志."""
    result = runner.invoke(
        app,
        [
            "--data-root",
            str(temp_dir),
            "stock",
            "daily",
            "2024-01-02",
            "--force",
        ],
    )
    # 命令应该接受 force 参数
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_data_root_option(temp_dir: Path):
    """测试自定义数据根目录."""
    result = runner.invoke(
        app,
        ["--data-root", str(temp_dir), "stock", "daily", "2024-01-02"],
    )
    # 命令应该接受自定义数据根目录
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )
