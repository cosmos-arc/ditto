"""Metadata 域摄取命令单元测试."""

from unittest.mock import MagicMock, Mock

import click
import pytest
from ditto_port.cli.commands.ingest import metadata
from ditto_port.cli.main import app
from pytest_mock import MockerFixture
from typer import Context
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    """创建 CLI 测试运行器."""
    return CliRunner()


@pytest.fixture
def mock_ctx():
    """创建 typer.Context mock."""
    ctx = Mock(spec=Context)
    ctx.obj = {"data_root": "/mock/data", "verbose": False}
    return ctx


@pytest.mark.unit
class TestMetadataCommands:
    """Metadata 命令测试."""

    def test_ingest_metadata_calendar_command_exists(self) -> None:
        """测试 calendar 命令存在且可调用."""
        assert hasattr(metadata, "calendar")
        assert callable(metadata.calendar)

    def test_ingest_metadata_basic_command_exists(self) -> None:
        """测试 basic 命令存在且可调用."""
        assert hasattr(metadata, "basic")
        assert callable(metadata.basic)

    def test_ingest_metadata_calendar_delegates_to_factory(
        self, mocker: MockerFixture, mock_ctx: Mock
    ) -> None:
        """测试 calendar 命令委托给工厂函数."""
        mock_impl = mocker.patch.object(metadata, "_calendar_impl")
        metadata.calendar(mock_ctx, "2024-01-02", False)
        mock_impl.assert_called_once_with(mock_ctx, "2024-01-02", False)

    def test_ingest_metadata_calendar_with_force(
        self, mocker: MockerFixture, mock_ctx: Mock
    ) -> None:
        """测试 calendar 命令支持 force 参数."""
        mock_impl = mocker.patch.object(metadata, "_calendar_impl")
        metadata.calendar(mock_ctx, "2024-01-02", True)
        mock_impl.assert_called_once_with(mock_ctx, "2024-01-02", True)

    def test_ingest_metadata_basic_stock(
        self, mocker: MockerFixture, mock_ctx: Mock
    ) -> None:
        """测试 basic stock 命令委托给正确的工厂函数."""
        mock_impl = mocker.patch.object(metadata, "_stock_basic_impl")
        metadata.basic(mock_ctx, "stock", False)
        mock_impl.assert_called_once_with(mock_ctx, False)

    def test_ingest_metadata_basic_etf(
        self, mocker: MockerFixture, mock_ctx: Mock
    ) -> None:
        """测试 basic etf 命令委托给正确的工厂函数."""
        mock_impl = mocker.patch.object(metadata, "_etf_basic_impl")
        metadata.basic(mock_ctx, "etf", False)
        mock_impl.assert_called_once_with(mock_ctx, False)

    def test_ingest_metadata_basic_index(
        self, mocker: MockerFixture, mock_ctx: Mock
    ) -> None:
        """测试 basic index 命令委托给正确的工厂函数."""
        mock_impl = mocker.patch.object(metadata, "_index_basic_impl")
        metadata.basic(mock_ctx, "index", False)
        mock_impl.assert_called_once_with(mock_ctx, False)

    def test_ingest_metadata_basic_unknown_asset(
        self, mocker: MockerFixture, mock_ctx: Mock
    ) -> None:
        """测试 basic 命令处理未知资产类型."""
        # Mock all implementations to ensure they're not called
        mocker.patch.object(metadata, "_stock_basic_impl")
        mocker.patch.object(metadata, "_etf_basic_impl")
        mocker.patch.object(metadata, "_index_basic_impl")

        # typer.Exit raises click.exceptions.Exit
        with pytest.raises(click.exceptions.Exit):
            metadata.basic(mock_ctx, "unknown", False)

    def test_ingest_metadata_basic_case_insensitive(
        self, mocker: MockerFixture, mock_ctx: Mock
    ) -> None:
        """测试 basic 命令资产类型大小写不敏感."""
        mock_impl = mocker.patch.object(metadata, "_stock_basic_impl")
        metadata.basic(mock_ctx, "STOCK", False)
        mock_impl.assert_called_once_with(mock_ctx, False)


@pytest.mark.unit
class TestMetadataCommandIntegration:
    """Metadata 命令集成测试（通过 CLI Runner）."""

    def test_ingest_metadata_calendar_success(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试摄取交易日历."""
        mock_executor = MagicMock()
        mock_executor.ingest_daily.return_value = {
            "dataset": "calendar",
            "trade_date": "2024-01-02",
            "status": "success",
            "row_count": 1,
            "message": "成功",
            "error": None,
        }
        # Mock at factory level where create_executor is imported
        mock_create_exec = mocker.patch(
            "ditto_port.cli.commands.factory.create_executor"
        )
        mock_create_exec.return_value.__enter__.return_value = mock_executor

        result = runner.invoke(app, ["ingest", "metadata", "calendar", "2024-01-02"])
        assert result.exit_code == 0

    def test_ingest_metadata_basic_stock_success(
        self, runner: CliRunner, mocker: MockerFixture
    ) -> None:
        """测试摄取股票基础信息."""
        mock_executor = MagicMock()
        mock_executor.ingest_daily.return_value = {
            "dataset": "stock_basic",
            "trade_date": "",
            "status": "success",
            "row_count": 500,
            "message": "成功",
            "error": None,
        }
        # Mock at factory level where create_executor is imported
        mock_create_exec = mocker.patch(
            "ditto_port.cli.commands.factory.create_executor"
        )
        mock_create_exec.return_value.__enter__.return_value = mock_executor

        result = runner.invoke(app, ["ingest", "metadata", "basic", "stock"])
        assert result.exit_code == 0

    def test_ingest_metadata_calendar_help(self, runner: CliRunner) -> None:
        """测试 calendar 命令帮助."""
        result = runner.invoke(app, ["ingest", "metadata", "calendar", "--help"])
        assert result.exit_code == 0
        assert "摄取交易日历" in result.output

    def test_ingest_metadata_basic_help(self, runner: CliRunner) -> None:
        """测试 basic 命令帮助."""
        result = runner.invoke(app, ["ingest", "metadata", "basic", "--help"])
        assert result.exit_code == 0
        assert "基础信息" in result.output
