"""交易日历命令单元测试."""

import pytest
from ditto_port.cli.commands import calendar
from pytest_mock import MockerFixture
from typer import Context


@pytest.fixture
def mock_ctx():
    """创建 typer.Context mock."""
    from unittest.mock import MagicMock

    ctx = MagicMock(spec=Context)
    ctx.obj = {"data_root": "/mock/data", "verbose": False}
    ctx.invoked_subcommand = None
    return ctx


@pytest.mark.unit
class TestCalendarCommands:
    """测试交易日历命令。"""

    def test_calendar_update_calls_executor(self, mocker: MockerFixture, mock_ctx):
        """测试 calendar update 命令调用 executor。"""
        # Arrange
        mock_executor = mocker.Mock()
        mock_executor.ingest_daily.return_value = {
            "dataset": "calendar",
            "status": "success",
            "message": "交易日历已更新",
        }
        mock_create_exec = mocker.patch(
            "ditto_port.cli.commands.calendar.create_executor"
        )
        mock_create_exec.return_value.__enter__.return_value = mock_executor
        mock_print = mocker.patch(
            "ditto_port.cli.commands.calendar.print_ingestion_result"
        )

        # Act
        calendar.update(mock_ctx, force=False)

        # Assert
        mock_executor.ingest_daily.assert_called_once_with("calendar", "", False)
        mock_print.assert_called_once()

    def test_calendar_callback_invokes_update_when_no_subcommand(
        self, mocker: MockerFixture, mock_ctx
    ):
        """测试没有子命令时调用默认更新操作。"""
        # Arrange
        mock_ctx.invoked_subcommand = None

        # Act - calendar 是一个 typer.Typer app，需要通过 app() 调用
        # 或者直接测试 registered callback
        calendar.calendar(mock_ctx, force=False)

        # Assert - ctx.invoke 应该被调用
        mock_ctx.invoke.assert_called_once()
        # 验证第一个参数是 update 函数
        assert mock_ctx.invoke.call_args[0][0] == calendar.update

    def test_calendar_callback_skips_update_when_subcommand_exists(
        self, mocker: MockerFixture, mock_ctx
    ):
        """测试有子命令时不调用默认更新操作。"""
        # Arrange
        mock_ctx.invoked_subcommand = "some_subcommand"

        # Act
        calendar.calendar(mock_ctx, force=False)

        # Assert
        mock_ctx.invoke.assert_not_called()
