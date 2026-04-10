"""Market 域摄取命令单元测试."""

import pytest
from ditto_interfaces.cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.mark.unit
def test_ingest_fx_command_exists() -> None:
    """测试汇率摄取命令存在."""
    result = runner.invoke(app, ["ingest", "market", "fx", "--help"])
    assert result.exit_code == 0


@pytest.mark.unit
def test_ingest_commodity_command_exists() -> None:
    """测试商品摄取命令存在."""
    result = runner.invoke(app, ["ingest", "market", "commodity", "--help"])
    assert result.exit_code == 0
