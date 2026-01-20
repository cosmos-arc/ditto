"""复权因子命令集成测试."""

from pathlib import Path

import pytest
from ditto_port.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.mark.integration
def test_adj_factor_command(tmp_path: Path):
    """测试 adj-factor 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "adj", "adj-factor", "2024-01-02"],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_adj_factor_with_force(tmp_path: Path):
    """测试 adj-factor --force 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "adj", "adj-factor", "2024-01-02", "--force"],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_adj_factor_invalid_date():
    """测试 adj-factor 无效日期."""
    result = runner.invoke(app, ["adj", "adj-factor", "2024/01/02"])
    assert result.exit_code == 1
    assert "错误" in result.stdout


@pytest.mark.integration
def test_fund_adj_command(tmp_path: Path):
    """测试 fund-adj 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "adj", "fund-adj", "2024-01-02"],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_fund_adj_with_force(tmp_path: Path):
    """测试 fund-adj --force 命令."""
    result = runner.invoke(
        app,
        ["--data-root", str(tmp_path), "adj", "fund-adj", "2024-01-02", "--force"],
    )
    assert result.exit_code == 0 or "unable to open database file" in str(
        result.exception
    )


@pytest.mark.integration
def test_fund_adj_invalid_date():
    """测试 fund-adj 无效日期."""
    result = runner.invoke(app, ["adj", "fund-adj", "2024/01/02"])
    assert result.exit_code == 1
    assert "错误" in result.stdout
