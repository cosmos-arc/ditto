"""ETF 数据摄取命令单元测试."""

from unittest.mock import MagicMock

import pytest
from ditto_port.cli.commands import etf
from typer import Context


@pytest.fixture
def mock_ctx():
    """创建 typer.Context mock."""
    ctx = MagicMock(spec=Context)
    ctx.obj = {"data_root": "/mock/data", "verbose": False}
    return ctx


@pytest.mark.unit
class TestETFCommands:
    """测试 ETF 命令。"""

    def test_etf_daily_command_exists(self):
        """测试 etf daily 命令存在且可调用。"""
        assert hasattr(etf, "daily")
        assert callable(etf.daily)

    def test_etf_backfill_command_exists(self):
        """测试 etf backfill 命令存在且可调用。"""
        assert hasattr(etf, "backfill")
        assert callable(etf.backfill)

    def test_etf_basic_command_exists(self):
        """测试 etf basic 命令存在且可调用。"""
        assert hasattr(etf, "basic")
        assert callable(etf.basic)

    def test_etf_daily_delegates_to_factory(self, mocker, mock_ctx):
        """测试 etf daily 命令委托给工厂函数。"""
        mock_impl = mocker.patch.object(etf, "_daily_impl")
        etf.daily(mock_ctx, "2024-01-02", False)
        mock_impl.assert_called_once_with(mock_ctx, "2024-01-02", False)

    def test_etf_backfill_delegates_to_factory(self, mocker, mock_ctx):
        """测试 etf backfill 命令委托给工厂函数。"""
        mock_impl = mocker.patch.object(etf, "_backfill_impl")
        etf.backfill(mock_ctx, "2024-01-01", "2024-01-31", 2)
        mock_impl.assert_called_once_with(mock_ctx, "2024-01-01", "2024-01-31", 2)

    def test_etf_basic_delegates_to_factory(self, mocker, mock_ctx):
        """测试 etf basic 命令委托给工厂函数。"""
        mock_impl = mocker.patch.object(etf, "_basic_impl")
        etf.basic(mock_ctx, True)
        mock_impl.assert_called_once_with(mock_ctx, True)
