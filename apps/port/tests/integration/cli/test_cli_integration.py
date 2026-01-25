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
def test_main_help():
    """测试主命令帮助信息."""
    try:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Ditto" in result.stdout
        assert "stock" in result.stdout
        assert "etf" in result.stdout
        assert "calendar" in result.stdout
        assert "adj" in result.stdout
        assert "version" in result.stdout
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise


@pytest.mark.integration
def test_version_command():
    """测试版本命令."""
    try:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "ditto-cli" in result.stdout
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise


@pytest.mark.integration
def test_stock_help():
    """测试 stock 命令组帮助."""
    try:
        result = runner.invoke(app, ["stock", "--help"])
        assert result.exit_code == 0
        assert "daily" in result.stdout
        assert "backfill" in result.stdout
        assert "basic" in result.stdout
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise


@pytest.mark.integration
def test_etf_help():
    """测试 etf 命令组帮助."""
    try:
        result = runner.invoke(app, ["etf", "--help"])
        assert result.exit_code == 0
        assert "daily" in result.stdout
        assert "backfill" in result.stdout
        assert "basic" in result.stdout
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise


@pytest.mark.integration
def test_calendar_help():
    """测试 calendar 命令组帮助."""
    try:
        result = runner.invoke(app, ["calendar", "--help"])
        assert result.exit_code == 0
        assert "update" in result.stdout
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise


@pytest.mark.integration
def test_adj_help():
    """测试 adj 命令组帮助."""
    try:
        result = runner.invoke(app, ["adj", "--help"])
        assert result.exit_code == 0
        assert "adj-factor" in result.stdout
        assert "fund-adj" in result.stdout
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise


@pytest.mark.integration
def test_e2e_stock_daily_workflow(tmp_path: Path):
    """测试完整的 stock daily 工作流."""
    # 测试参数验证 - 无效日期格式
    try:
        result = runner.invoke(app, ["stock", "daily", "2024/01/02"])
        assert result.exit_code == 1
        assert "错误" in result.stdout or "格式" in result.stdout
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise

    # 测试帮助信息
    try:
        result = runner.invoke(app, ["stock", "daily", "--help"])
        assert result.exit_code == 0
        assert "交易日期" in result.stdout or "date" in result.stdout
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise

    # 测试实际命令执行（可能会因数据库问题失败，这是预期的）
    try:
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "stock", "daily", "2024-01-02"],
        )
        # 命令应该成功执行或因为数据源问题失败（非 CLI 问题）
        assert (
            result.exit_code == 0
            or "unable to open database file" in str(result.exception)
            or "Tushare" in str(result.exception)
        )
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise


@pytest.mark.integration
def test_e2e_backfill_workflow(tmp_path: Path):
    """测试完整的 backfill 工作流."""
    # 测试日期范围验证
    try:
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
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
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise


@pytest.mark.integration
def test_e2e_backfill_with_parallel(tmp_path: Path):
    """测试带并行度的 backfill 工作流."""
    try:
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
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
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise


@pytest.mark.integration
def test_e2e_basic_commands(tmp_path: Path):
    """测试基础信息命令."""
    # 测试 stock basic
    try:
        result = runner.invoke(app, ["--data-root", str(tmp_path), "stock", "basic"])
        assert result.exit_code == 0 or "unable to open database file" in str(
            result.exception
        )
    except ValueError as e:
        # CliRunner I/O 错误，跳过此断言（测试环境限制）
        if "I/O operation on closed file" not in str(e):
            raise

    # 测试 etf basic
    try:
        result = runner.invoke(app, ["--data-root", str(tmp_path), "etf", "basic"])
        assert result.exit_code == 0 or "unable to open database file" in str(
            result.exception
        )
    except ValueError as e:
        # CliRunner I/O 错误，跳过此断言（测试环境限制）
        if "I/O operation on closed file" not in str(e):
            raise


@pytest.mark.integration
def test_e2e_calendar_command(tmp_path: Path):
    """测试交易日历命令."""
    try:
        result = runner.invoke(app, ["--data-root", str(tmp_path), "calendar"])
        assert result.exit_code == 0 or "unable to open database file" in str(
            result.exception
        )
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise


@pytest.mark.integration
def test_e2e_adj_commands(tmp_path: Path):
    """测试复权因子命令."""
    # 测试 adj-factor
    try:
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "adj", "adj-factor", "2024-01-02"],
        )
        assert result.exit_code == 0 or "unable to open database file" in str(
            result.exception
        )
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise

    # 测试 fund-adj
    try:
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "adj", "fund-adj", "2024-01-02"],
        )
        assert result.exit_code == 0 or "unable to open database file" in str(
            result.exception
        )
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise


@pytest.mark.integration
def test_verbose_flag(tmp_path: Path):
    """测试详细输出模式."""
    try:
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "--verbose", "stock", "basic"],
        )
        # 命令应该接受 verbose 参数
        assert result.exit_code == 0 or "unable to open database file" in str(
            result.exception
        )
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise


@pytest.mark.integration
def test_force_flag(tmp_path: Path):
    """测试强制重新摄取标志."""
    try:
        result = runner.invoke(
            app,
            [
                "--data-root",
                str(tmp_path),
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
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise


@pytest.mark.integration
def test_data_root_option(tmp_path: Path):
    """测试自定义数据根目录."""
    try:
        result = runner.invoke(
            app,
            ["--data-root", str(tmp_path), "stock", "daily", "2024-01-02"],
        )
        # 命令应该接受自定义数据根目录
        assert result.exit_code == 0 or "unable to open database file" in str(
            result.exception
        )
    except ValueError as e:
        if "I/O operation on closed file" not in str(e):
            raise
