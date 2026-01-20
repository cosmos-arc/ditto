"""Stock 数据摄取命令单元测试."""

from unittest.mock import MagicMock

import pytest
from ditto_port.cli.commands import stock
from typer import Context
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def mock_ctx():
    """创建 typer.Context mock."""
    ctx = MagicMock(spec=Context)
    ctx.obj = {"data_root": "/mock/data", "verbose": False}
    return ctx


@pytest.mark.unit
class TestStockCommands:
    """测试 Stock 命令。"""

    def test_stock_daily_command_exists(self):
        """测试 stock daily 命令存在且可调用。"""
        assert hasattr(stock, "daily")
        assert callable(stock.daily)

    def test_stock_backfill_command_exists(self):
        """测试 stock backfill 命令存在且可调用。"""
        assert hasattr(stock, "backfill")
        assert callable(stock.backfill)

    def test_stock_basic_command_exists(self):
        """测试 stock basic 命令存在且可调用。"""
        assert hasattr(stock, "basic")
        assert callable(stock.basic)

    def test_stock_daily_delegates_to_factory(self, mocker, mock_ctx):
        """测试 stock daily 命令委托给工厂函数。"""
        # Arrange - mock the factory implementation
        mock_impl = mocker.patch.object(stock, "_daily_impl")

        # Act
        stock.daily(mock_ctx, "2024-01-02", False)

        # Assert
        mock_impl.assert_called_once_with(mock_ctx, "2024-01-02", False)

    def test_stock_backfill_delegates_to_factory(self, mocker, mock_ctx):
        """测试 stock backfill 命令委托给工厂函数。"""
        # Arrange - mock the factory implementation
        mock_impl = mocker.patch.object(stock, "_backfill_impl")

        # Act
        stock.backfill(mock_ctx, "2024-01-01", "2024-01-31", 2)

        # Assert
        mock_impl.assert_called_once_with(mock_ctx, "2024-01-01", "2024-01-31", 2)

    def test_stock_basic_delegates_to_factory(self, mocker, mock_ctx):
        """测试 stock basic 命令委托给工厂函数。"""
        # Arrange - mock the factory implementation
        mock_impl = mocker.patch.object(stock, "_basic_impl")

        # Act
        stock.basic(mock_ctx, True)

        # Assert
        mock_impl.assert_called_once_with(mock_ctx, True)
