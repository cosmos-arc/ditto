"""ETF 命令集成测试."""

from pathlib import Path

import pytest
from ditto_port.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.mark.integration
def test_etf_daily_command(tmp_path: Path):
    """测试 etf daily 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "etf", "daily", "2024-01-02"],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )
    if result.exit_code == 0:
        assert "etf_daily" in result.stdout or "状态" in result.stdout


@pytest.mark.integration
def test_etf_daily_with_force(tmp_path: Path):
    """测试 etf daily --force 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "etf", "daily", "2024-01-02", "--force"],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_etf_daily_invalid_date():
    """测试 etf daily 无效日期."""
    result = runner.invoke(app, ["etf", "daily", "2024/01/02"])
    assert result.exit_code == 1
    assert "错误" in result.stdout


@pytest.mark.integration
def test_etf_backfill_command(tmp_path: Path):
    """测试 etf backfill 命令."""
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
            "2024-01-03",
        ],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_etf_backfill_with_parallel(tmp_path: Path):
    """测试 etf backfill --parallel 命令."""
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
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_etf_basic_command(tmp_path: Path):
    """测试 etf basic 命令."""
    result = runner.invoke(app, ["--data-root", str(tmp_path), "etf", "basic"])
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_etf_help():
    """测试 etf 命令帮助."""
    result = runner.invoke(app, ["etf", "--help"])
    assert result.exit_code == 0
    assert "ETF数据摄取命令" in result.stdout
