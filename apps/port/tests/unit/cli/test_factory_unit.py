"""CLI 命令工厂函数单元测试."""

import pytest
from click.exceptions import Exit as ClickExit
from ditto_port.cli.commands.factory import (
    create_backfill_command,
    create_basic_command,
    create_daily_command,
)
from pytest_mock import MockerFixture

# Mock data root path for testing
MOCK_DATA_ROOT = "D:/mock/ditto/data"


@pytest.mark.unit
def test_create_daily_command_returns_callable():
    """测试 create_daily_command 返回可调用对象"""
    cmd = create_daily_command("test_dataset", "测试描述")

    assert callable(cmd)
    assert cmd.__doc__ == "测试描述"


@pytest.mark.unit
def test_create_daily_command_validates_date(app_ctx, mocker: MockerFixture):
    """测试 create_daily_command 验证日期格式"""

    cmd = create_daily_command("test_dataset", "测试描述")

    # Mock context
    ctx = mocker.Mock()
    ctx.obj = {"data_root": MOCK_DATA_ROOT, "verbose": False}

    # 测试无效日期格式
    mock_validate = mocker.patch("ditto_port.cli.commands.factory.validate_date_format")
    mock_validate.side_effect = ClickExit(1)

    with pytest.raises(ClickExit):
        cmd(ctx, "invalid-date", False)

    mock_validate.assert_called_once_with("invalid-date")


@pytest.mark.unit
def test_create_daily_command_uses_create_executor(app_ctx, mocker: MockerFixture):
    """测试 create_daily_command 使用 create_executor 上下文管理器"""

    cmd = create_daily_command("test_dataset", "测试描述")

    # Mock context
    ctx = mocker.Mock()
    ctx.obj = {"data_root": MOCK_DATA_ROOT, "verbose": False}

    # Mock executor
    mock_executor = mocker.Mock()
    mock_executor.ingest_daily.return_value = {
        "dataset": "test_dataset",
        "trade_date": "2024-01-02",
        "status": "success",
        "row_count": 100,
        "message": "成功",
        "error": None,
    }

    mock_create_exec = mocker.patch("ditto_port.cli.commands.factory.create_executor")
    # 设置 context manager 返回值
    mock_create_exec.return_value.__enter__.return_value = mock_executor
    mocker.patch("ditto_port.cli.commands.factory.validate_date_format")
    mocker.patch("ditto_port.cli.commands.factory.print_ingestion_result")
    cmd(ctx, "2024-01-02", False)

    # 验证 create_executor 被正确调用（DI 迁移后不再传参）
    mock_create_exec.assert_called_once_with()
    # 验证 executor.ingest_daily 被调用
    mock_executor.ingest_daily.assert_called_once_with(
        "test_dataset", "2024-01-02", False
    )


@pytest.mark.unit
def test_create_daily_command_calls_ingest_daily(app_ctx, mocker: MockerFixture):
    """测试 create_daily_command 调用 ingest_daily"""

    cmd = create_daily_command("test_dataset", "测试描述")

    # Mock context
    ctx = mocker.Mock()
    ctx.obj = {"data_root": MOCK_DATA_ROOT, "verbose": False}

    mock_executor = mocker.Mock()
    mock_executor.ingest_daily.return_value = {
        "dataset": "test_dataset",
        "trade_date": "2024-01-02",
        "status": "success",
        "row_count": 100,
        "message": "成功",
        "error": None,
    }

    mock_create_exec = mocker.patch("ditto_port.cli.commands.factory.create_executor")
    mock_create_exec.return_value.__enter__.return_value = mock_executor
    mocker.patch("ditto_port.cli.commands.factory.validate_date_format")
    mock_print = mocker.patch("ditto_port.cli.commands.factory.print_ingestion_result")
    cmd(ctx, "2024-01-02", False)

    # 验证调用 executor.ingest_daily
    mock_executor.ingest_daily.assert_called_once_with(
        "test_dataset", "2024-01-02", False
    )

    # 验证调用 print_ingestion_result
    mock_print.assert_called_once()


@pytest.mark.unit
def test_create_daily_command_with_force_flag(app_ctx, mocker: MockerFixture):
    """测试 create_daily_command 传递 force 参数"""

    cmd = create_daily_command("test_dataset", "测试描述")

    ctx = mocker.Mock()
    ctx.obj = {"data_root": MOCK_DATA_ROOT, "verbose": False}

    mock_executor = mocker.Mock()
    mock_executor.ingest_daily.return_value = {
        "dataset": "test_dataset",
        "trade_date": "2024-01-02",
        "status": "success",
        "row_count": 100,
        "message": "成功",
        "error": None,
    }

    mock_create_exec = mocker.patch("ditto_port.cli.commands.factory.create_executor")
    mock_create_exec.return_value.__enter__.return_value = mock_executor
    mocker.patch("ditto_port.cli.commands.factory.validate_date_format")
    mocker.patch("ditto_port.cli.commands.factory.print_ingestion_result")
    cmd(ctx, "2024-01-02", force=True)

    mock_executor.ingest_daily.assert_called_once_with(
        "test_dataset", "2024-01-02", True
    )


@pytest.mark.unit
def test_create_backfill_command_returns_callable():
    """测试 create_backfill_command 返回可调用对象"""
    cmd = create_backfill_command("test_dataset", "测试描述")

    assert callable(cmd)
    assert cmd.__doc__ == "测试描述"


@pytest.mark.unit
def test_create_backfill_command_validates_dates(app_ctx, mocker: MockerFixture):
    """测试 create_backfill_command 验证开始和结束日期"""

    cmd = create_backfill_command("test_dataset", "测试描述")

    ctx = mocker.Mock()
    ctx.obj = {"data_root": MOCK_DATA_ROOT}

    mock_executor = mocker.Mock()
    mock_executor.backfill_range.return_value = {
        "dataset": "test_dataset",
        "total_dates": 5,
        "success_count": 5,
        "skipped_count": 0,
        "failed_count": 0,
    }

    mock_create_exec = mocker.patch("ditto_port.cli.commands.factory.create_executor")
    mock_create_exec.return_value.__enter__.return_value = mock_executor
    mock_validate = mocker.patch("ditto_port.cli.commands.factory.validate_date_format")
    mocker.patch("ditto_port.cli.commands.factory.print_backfill_summary")
    cmd(ctx, "2024-01-01", "2024-01-05", 1)

    # 验证调用了两次 validate_date_format
    assert mock_validate.call_count == 2
    mock_validate.assert_any_call("2024-01-01")
    mock_validate.assert_any_call("2024-01-05")


@pytest.mark.unit
def test_create_backfill_command_calls_backfill_range(app_ctx, mocker: MockerFixture):
    """测试 create_backfill_command 调用 backfill_range"""

    cmd = create_backfill_command("test_dataset", "测试描述")

    ctx = mocker.Mock()
    ctx.obj = {"data_root": MOCK_DATA_ROOT}

    mock_executor = mocker.Mock()
    mock_executor.backfill_range.return_value = {
        "dataset": "test_dataset",
        "total_dates": 5,
        "success_count": 4,
        "skipped_count": 1,
        "failed_count": 0,
    }

    mock_create_exec = mocker.patch("ditto_port.cli.commands.factory.create_executor")
    mock_create_exec.return_value.__enter__.return_value = mock_executor
    mocker.patch("ditto_port.cli.commands.factory.validate_date_format")
    mock_print = mocker.patch("ditto_port.cli.commands.factory.print_backfill_summary")
    cmd(ctx, "2024-01-01", "2024-01-05", parallel=2)

    mock_executor.backfill_range.assert_called_once_with(
        "test_dataset", "2024-01-01", "2024-01-05", 2
    )

    mock_print.assert_called_once()


@pytest.mark.unit
def test_create_basic_command_returns_callable():
    """测试 create_basic_command 返回可调用对象"""
    cmd = create_basic_command("test_dataset", "测试描述")

    assert callable(cmd)
    assert cmd.__doc__ == "测试描述"


@pytest.mark.unit
def test_create_basic_command_calls_ingest_daily_with_empty_date(
    app_ctx, mocker: MockerFixture
):
    """测试 create_basic_command 调用 ingest_daily 并传入空字符串作为日期"""

    cmd = create_basic_command("test_dataset", "测试描述")

    ctx = mocker.Mock()
    ctx.obj = {"data_root": MOCK_DATA_ROOT, "verbose": False}

    mock_executor = mocker.Mock()
    mock_executor.ingest_daily.return_value = {
        "dataset": "test_dataset",
        "trade_date": "",
        "status": "success",
        "row_count": 500,
        "message": "成功",
        "error": None,
    }

    mock_create_exec = mocker.patch("ditto_port.cli.commands.factory.create_executor")
    mock_create_exec.return_value.__enter__.return_value = mock_executor
    mock_print = mocker.patch("ditto_port.cli.commands.factory.print_ingestion_result")
    cmd(ctx, force=True)

    # 验证调用 ingest_daily 时日期为空字符串
    mock_executor.ingest_daily.assert_called_once_with("test_dataset", "", True)

    mock_print.assert_called_once()


@pytest.mark.unit
def test_create_basic_command_with_force_flag(app_ctx, mocker: MockerFixture):
    """测试 create_basic_command 传递 force 参数"""

    cmd = create_basic_command("test_dataset", "测试描述")

    ctx = mocker.Mock()
    ctx.obj = {"data_root": MOCK_DATA_ROOT, "verbose": False}

    mock_executor = mocker.Mock()
    mock_executor.ingest_daily.return_value = {
        "dataset": "test_dataset",
        "trade_date": "",
        "status": "skipped",
        "row_count": None,
        "message": "已存在",
        "error": None,
    }

    mock_create_exec = mocker.patch("ditto_port.cli.commands.factory.create_executor")
    mock_create_exec.return_value.__enter__.return_value = mock_executor
    mocker.patch("ditto_port.cli.commands.factory.print_ingestion_result")
    cmd(ctx, force=False)

    mock_executor.ingest_daily.assert_called_once_with("test_dataset", "", False)


@pytest.mark.unit
def test_factory_preserves_docstring():
    """测试工厂函数保留描述字符串作为文档"""
    daily_cmd = create_daily_command("test", "每日数据摄取")
    backfill_cmd = create_backfill_command("test", "历史数据回补")
    basic_cmd = create_basic_command("test", "基础信息摄取")

    assert daily_cmd.__doc__ == "每日数据摄取"
    assert backfill_cmd.__doc__ == "历史数据回补"
    assert basic_cmd.__doc__ == "基础信息摄取"
