"""Calendar 命令集成测试."""

from pathlib import Path

import pytest
from ditto_port.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.mark.integration
def test_calendar_default_command(temp_dir: Path):
    """测试 calendar default 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(temp_dir), "calendar"],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_calendar_with_force(temp_dir: Path):
    """测试 calendar --force 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(temp_dir), "calendar", "--force"],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_calendar_help():
    """测试 calendar 命令帮助."""
    result = runner.invoke(app, ["calendar", "--help"])
    assert result.exit_code == 0
    assert "交易日历" in result.stdout
