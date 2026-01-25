"""复权因子命令单元测试."""

from unittest.mock import Mock

import pytest
from ditto_port.cli.commands import adj
from pytest_mock import MockerFixture
from typer import Context


@pytest.fixture
def mock_ctx():
    """创建 typer.Context mock。"""
    ctx = Mock(spec=Context)
    ctx.obj = {"data_root": "/mock/data", "verbose": False}
    return ctx


@pytest.mark.unit
class TestAdjCommands:
    """测试复权因子命令。"""

    def test_adj_factor_command_exists(self):
        """测试 adj-factor 命令存在且可调用。"""
        assert hasattr(adj, "adj_factor")
        assert callable(adj.adj_factor)

    def test_fund_adj_command_exists(self):
        """测试 fund-adj 命令存在且可调用。"""
        assert hasattr(adj, "fund_adj")
        assert callable(adj.fund_adj)

    def test_adj_factor_delegates_to_factory(self, mocker: MockerFixture, mock_ctx):
        """测试 adj-factor 命令委托给工厂函数。"""
        mock_impl = mocker.patch.object(adj, "_adj_factor_impl")
        adj.adj_factor(mock_ctx, "2024-01-02", False)
        mock_impl.assert_called_once_with(mock_ctx, "2024-01-02", False)

    def test_fund_adj_delegates_to_factory(self, mocker: MockerFixture, mock_ctx):
        """测试 fund-adj 命令委托给工厂函数。"""
        mock_impl = mocker.patch.object(adj, "_fund_adj_impl")
        adj.fund_adj(mock_ctx, "2024-01-02", True)
        mock_impl.assert_called_once_with(mock_ctx, "2024-01-02", True)
