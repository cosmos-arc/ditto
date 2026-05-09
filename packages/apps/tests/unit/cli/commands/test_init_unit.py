"""CLI 初始化命令单元测试."""

from pathlib import Path

import pytest
from ditto_apps.cli.commands import init
from pytest_mock import MockerFixture
from typer import Context


@pytest.fixture
def mock_ctx():
    """创建 typer.Context mock."""
    from unittest.mock import MagicMock

    ctx = MagicMock(spec=Context)
    ctx.obj = {"data_root": None, "verbose": False}
    return ctx


@pytest.mark.unit
class TestInitConfigCommand:
    """测试 init config 命令。"""

    def test_init_config_uses_default_data_root(self, mocker: MockerFixture, mock_ctx):
        """测试使用默认数据根目录。"""
        # Arrange
        from ditto_platform.foundation import InitScope

        mocker.patch(
            "ditto_apps.cli.commands.init._load_data_root",
            return_value=Path("/mock/data"),
        )

        mock_coordinator = mocker.Mock()
        mock_coordinator.initialize.return_value = {
            "dq_config": mocker.Mock(
                success=True, skipped=False, message="DQ配置已初始化"
            ),
            "database_schema": mocker.Mock(
                success=True, skipped=False, message="数据库Schema已初始化"
            ),
        }
        mocker.patch(
            "ditto_apps.cli.commands.init._make_coordinator",
            return_value=mock_coordinator,
        )

        # Act
        init.config(mock_ctx, data_root=None, force=False)

        # Assert
        assert mock_coordinator.initialize.call_count == 1
        call_args = mock_coordinator.initialize.call_args
        assert call_args.kwargs["scope"] == InitScope.STARTUP
        assert call_args.kwargs["data_root"] == Path("/mock/data")

    def test_init_config_with_custom_data_root(self, mocker: MockerFixture, mock_ctx):
        """测试指定自定义数据根目录。"""
        # Arrange
        custom_root = "/custom/path"
        mock_coordinator = mocker.Mock()
        mock_coordinator.initialize.return_value = {
            "dq_config": mocker.Mock(
                success=True, skipped=False, message="DQ配置已初始化"
            ),
        }
        mocker.patch(
            "ditto_apps.cli.commands.init._make_coordinator",
            return_value=mock_coordinator,
        )

        # Act
        init.config(mock_ctx, data_root=custom_root, force=False)

        # Assert
        call_args = mock_coordinator.initialize.call_args
        assert call_args.kwargs["data_root"] == Path(custom_root)

    def test_init_config_with_force_flag(self, mocker: MockerFixture, mock_ctx):
        """测试强制重新初始化。"""
        # Arrange
        from ditto_platform.foundation import InitScope

        mock_coordinator = mocker.Mock()
        mock_coordinator.initialize.return_value = {}
        mocker.patch(
            "ditto_apps.cli.commands.init._make_coordinator",
            return_value=mock_coordinator,
        )

        # Act
        init.config(mock_ctx, data_root=None, force=True)

        # Assert
        call_args = mock_coordinator.initialize.call_args
        assert call_args.kwargs["scope"] == InitScope.ALWAYS
        assert call_args.kwargs["force"] is True

    def test_init_config_handles_failure(self, mocker: MockerFixture, mock_ctx):
        """测试初始化失败时正确处理。"""
        # Arrange
        mock_coordinator = mocker.Mock()
        mock_coordinator.initialize.return_value = {
            "dq_config": mocker.Mock(
                success=False, skipped=False, message="初始化失败"
            ),
        }
        mocker.patch(
            "ditto_apps.cli.commands.init._make_coordinator",
            return_value=mock_coordinator,
        )

        # Act & Assert
        # typer.Exit 实际上是 click.exceptions.Exit
        import click

        with pytest.raises(click.exceptions.Exit):
            init.config(mock_ctx, data_root=None, force=False)

    def test_make_coordinator_registers_feature_artifact_dirs(
        self,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """CLI 初始化协调器包含 features-owned artifact 目录。"""
        from ditto_data.config.data_store import DataStoreSettings
        from ditto_platform.foundation import InitScope

        data_root = tmp_path / "data"
        mocker.patch(
            "ditto_apps.cli.commands.init.load_data_store_settings",
            return_value=DataStoreSettings(data_root=data_root),
        )

        coordinator = init._make_coordinator()
        results = coordinator.initialize(scope=InitScope.STARTUP, data_root=data_root)

        assert results["data_root"].success
        assert (data_root / "features" / "technical" / "price").is_dir()
        assert (data_root / "factors" / "factors_narrow").is_dir()


@pytest.mark.unit
class TestInitDQCommand:
    """测试 init dq 命令。"""

    def test_init_dq_filters_results(self, mocker: MockerFixture, mock_ctx):
        """测试只显示 DQ 相关结果。"""
        # Arrange
        from ditto_platform.foundation import InitScope

        mock_coordinator = mocker.Mock()
        mock_coordinator.initialize.return_value = {
            "dq_config": mocker.Mock(
                success=True, skipped=False, message="DQ配置已初始化"
            ),
            "database_schema": mocker.Mock(
                success=True, skipped=False, message="数据库Schema已初始化"
            ),
        }
        mocker.patch(
            "ditto_apps.cli.commands.init._make_coordinator",
            return_value=mock_coordinator,
        )

        # Act
        init.dq(mock_ctx, data_root=None, force=False)

        # Assert - 应该只处理 dq 相关结果
        assert mock_coordinator.initialize.call_count == 1
        call_args = mock_coordinator.initialize.call_args
        assert call_args.kwargs["scope"] == InitScope.STARTUP


@pytest.mark.unit
class TestInitDBCommand:
    """测试 init db 命令。"""

    def test_init_db_filters_results(self, mocker: MockerFixture, mock_ctx):
        """测试只显示数据库相关结果。"""
        # Arrange
        from ditto_platform.foundation import InitScope

        mock_coordinator = mocker.Mock()
        mock_coordinator.initialize.return_value = {
            "dq_config": mocker.Mock(success=True, skipped=False, message="DQ配置"),
            "database_schema": mocker.Mock(
                success=True, skipped=False, message="数据库Schema已初始化"
            ),
        }
        mocker.patch(
            "ditto_apps.cli.commands.init._make_coordinator",
            return_value=mock_coordinator,
        )

        # Act
        init.db(mock_ctx, data_root=None, force=False)

        # Assert - 应该只处理 database 相关结果
        assert mock_coordinator.initialize.call_count == 1
        call_args = mock_coordinator.initialize.call_args
        assert call_args.kwargs["scope"] == InitScope.STARTUP
