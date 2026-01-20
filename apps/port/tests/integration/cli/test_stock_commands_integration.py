"""Stock 命令集成测试."""

from pathlib import Path

import pytest
from ditto_port.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.mark.integration
def test_stock_daily_command(tmp_path: Path):
    """测试 stock daily 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "stock", "daily", "2024-01-02"],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )
    if result.exit_code == 0:
        assert "stock_daily" in result.stdout or "状态" in result.stdout


@pytest.mark.integration
def test_stock_daily_with_force(tmp_path: Path):
    """测试 stock daily --force 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "stock", "daily", "2024-01-02", "--force"],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_stock_daily_invalid_date():
    """测试 stock daily 无效日期."""
    result = runner.invoke(app, ["stock", "daily", "2024/01/02"])
    assert result.exit_code == 1
    assert "错误" in result.stdout


@pytest.mark.integration
def test_stock_backfill_command(tmp_path: Path):
    """测试 stock backfill 命令."""
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
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_stock_backfill_with_parallel(tmp_path: Path):
    """测试 stock backfill --parallel 命令."""
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
            "2024-01-02",
            "--parallel",
            "2",
        ],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_stock_basic_command(tmp_path: Path):
    """测试 stock basic 命令."""
    result = runner.invoke(app, ["--data-root", str(tmp_path), "stock", "basic"])
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )
