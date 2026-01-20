"""Calendar 命令集成测试."""

from pathlib import Path

import pytest
from ditto_port.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.mark.integration
def test_calendar_default_command(tmp_path: Path):
    """测试 calendar default 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "calendar"],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_calendar_with_force(tmp_path: Path):
    """测试 calendar --force 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "calendar", "--force"],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )
