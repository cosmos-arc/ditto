"""Tests for DataHub configuration initialization providers."""

from pathlib import Path
from unittest.mock import Mock, patch

import yaml
from ditto_datahub.init_providers import (
    DatabaseSchemaProvider,
    DQConfigProvider,
    register_datahub_providers,
)
from ditto_foundation.config.initializer import (
    InitScope,
    reset_coordinator_for_testing,
)


class TestDQConfigProvider:
    """Test DQ configuration initialization provider."""

    def test_check_missing_dir_returns_true(self, tmp_path: Path) -> None:
        """
        测试 check() 在配置目录不存在时返回 True。

        Given: 配置目录不存在
        When: 调用 check()
        Then: 返回 True（需要初始化）
        """
        # Arrange
        provider = DQConfigProvider()
        data_root = tmp_path / "data"

        # Act
        need_init = provider.check(data_root)

        # Assert
        assert need_init is True

    def test_check_returns_true_when_config_dir_is_empty(self, tmp_path: Path) -> None:
        """
        测试 check() 在配置目录为空时返回 True。

        Given: 配置目录存在但没有配置文件
        When: 调用 check()
        Then: 返回 True（需要初始化）
        """
        # Arrange
        provider = DQConfigProvider()
        data_root = tmp_path / "data"
        config_dir = data_root / "config" / "dq"
        config_dir.mkdir(parents=True)

        # Act
        need_init = provider.check(data_root)

        # Assert
        assert need_init is True

    def test_check_returns_false_when_config_files_exist(self, tmp_path: Path) -> None:
        """
        测试 check() 在配置文件存在时返回 False。

        Given: 配置目录中有配置文件
        When: 调用 check()
        Then: 返回 False（无需初始化）
        """
        # Arrange
        provider = DQConfigProvider()
        data_root = tmp_path / "data"
        config_dir = data_root / "config" / "dq"
        config_dir.mkdir(parents=True)

        # 创建一个配置文件
        config_file = config_dir / "test.yml"
        config_file.write_text("dataset: test", encoding="utf-8")

        # Act
        need_init = provider.check(data_root)

        # Assert
        assert need_init is False

    def test_initialize_copies_config_files(self, tmp_path: Path) -> None:
        """
        测试 initialize() 复制配置文件。

        Given: 包内默认配置目录有配置文件
        When: 调用 initialize()
        Then: 应创建 config/dq 目录并复制配置文件
        """
        # Arrange
        provider = DQConfigProvider()
        data_root = tmp_path / "data"

        # 创建模拟的包内配置目录
        package_config_dir = tmp_path / "package_config"
        package_config_dir.mkdir()

        # 创建默认配置文件
        default_config = {
            "dataset": "test_dataset",
            "description": "Test",
            "l1_technical": [],
            "l2_business": [],
            "l3_statistical": [],
        }

        config_file = package_config_dir / "test_dataset.yml"
        with config_file.open("w", encoding="utf-8") as f:
            yaml.dump(default_config, f)

        # Mock 包内配置目录路径
        with patch.object(
            DQConfigProvider,
            "_get_package_config_dir",
            return_value=package_config_dir,
        ):
            # Act
            result = provider.initialize(data_root)

        # Assert
        assert result.success is True
        assert result.skipped is False
        assert "1 files copied" in result.message

        user_config_dir = data_root / "config" / "dq"
        assert user_config_dir.exists()
        assert (user_config_dir / "test_dataset.yml").exists()

        # 验证文件内容正确
        with (user_config_dir / "test_dataset.yml").open(encoding="utf-8") as f:
            loaded_config = yaml.safe_load(f)
        assert loaded_config["dataset"] == "test_dataset"

    def test_initialize_skips_existing_files(self, tmp_path: Path) -> None:
        """
        测试 initialize() 跳过已存在的文件。

        Given: 用户配置目录中已有配置文件
        When: 调用 initialize()
        Then: 应跳过已存在的文件，不覆盖
        """
        # Arrange
        provider = DQConfigProvider()
        data_root = tmp_path / "data"
        user_config_dir = data_root / "config" / "dq"
        user_config_dir.mkdir(parents=True)

        # 创建现有配置文件
        existing_config = {
            "dataset": "existing_dataset",
            "description": "Existing",
            "l1_technical": [],
            "l2_business": [],
            "l3_statistical": [],
        }

        existing_file = user_config_dir / "existing_dataset.yml"
        with existing_file.open("w", encoding="utf-8") as f:
            yaml.dump(existing_config, f)

        # 记录文件内容
        original_content = existing_file.read_text(encoding="utf-8")

        # 创建模拟的包内配置目录（包含同名文件）
        package_config_dir = tmp_path / "package_config"
        package_config_dir.mkdir()

        new_config = {
            "dataset": "new_dataset",
            "description": "New",
            "l1_technical": [],
            "l2_business": [],
            "l3_statistical": [],
        }

        new_file = package_config_dir / "existing_dataset.yml"
        with new_file.open("w", encoding="utf-8") as f:
            yaml.dump(new_config, f)

        # Mock 包内配置目录路径
        with patch.object(
            DQConfigProvider,
            "_get_package_config_dir",
            return_value=package_config_dir,
        ):
            # Act
            result = provider.initialize(data_root)

        # Assert
        assert result.success is True
        assert existing_file.exists()
        assert existing_file.read_text(encoding="utf-8") == original_content

    def test_initialize_handles_both_yml_and_yaml(self, tmp_path: Path) -> None:
        """
        测试 initialize() 处理 .yml 和 .yaml 文件。

        Given: 包内配置目录有 .yml 和 .yaml 文件
        When: 调用 initialize()
        Then: 应复制所有配置文件
        """
        # Arrange
        provider = DQConfigProvider()
        data_root = tmp_path / "data"

        # 创建模拟的包内配置目录
        package_config_dir = tmp_path / "package_config"
        package_config_dir.mkdir()

        # 创建 .yml 文件
        yml_file = package_config_dir / "test1.yml"
        yml_file.write_text("dataset: test1", encoding="utf-8")

        # 创建 .yaml 文件
        yaml_file = package_config_dir / "test2.yaml"
        yaml_file.write_text("dataset: test2", encoding="utf-8")

        # Mock 包内配置目录路径
        with patch.object(
            DQConfigProvider,
            "_get_package_config_dir",
            return_value=package_config_dir,
        ):
            # Act
            result = provider.initialize(data_root)

        # Assert
        assert result.success is True
        user_config_dir = data_root / "config" / "dq"
        assert (user_config_dir / "test1.yml").exists()
        assert (user_config_dir / "test2.yaml").exists()

    def test_initialize_returns_error_when_package_config_not_found(
        self, tmp_path: Path
    ) -> None:
        """
        测试 initialize() 在包内配置目录不存在时返回错误。

        Given: 包内配置目录不存在
        When: 调用 initialize()
        Then: 返回失败结果
        """
        # Arrange
        provider = DQConfigProvider()
        data_root = tmp_path / "data"

        # Mock 包内配置目录路径为不存在的路径
        with patch.object(
            DQConfigProvider,
            "_get_package_config_dir",
            return_value=tmp_path / "nonexistent",
        ):
            # Act
            result = provider.initialize(data_root)

        # Assert
        assert result.success is False
        assert "not found" in result.message.lower()

    def test_provider_properties(self) -> None:
        """
        测试提供者属性。

        Given: DQConfigProvider 实例
        When: 访问属性
        Then: 返回正确的值
        """
        # Arrange
        provider = DQConfigProvider()

        # Act & Assert
        assert provider.name == "dq_config"
        assert provider.scope == InitScope.STARTUP


class TestDatabaseSchemaProvider:
    """Test database schema initialization provider."""

    def test_check_returns_true_when_db_not_exists(self, tmp_path: Path) -> None:
        """
        测试 check() 在数据库不存在时返回 True。

        Given: 数据库文件不存在
        When: 调用 check()
        Then: 返回 True（需要初始化）
        """
        # Arrange
        provider = DatabaseSchemaProvider()
        data_root = tmp_path / "data"

        # Act
        need_init = provider.check(data_root)

        # Assert
        assert need_init is True

    def test_check_returns_false_when_db_exists(self, tmp_path: Path) -> None:
        """
        测试 check() 在数据库存在时返回 False。

        Given: 数据库文件存在
        When: 调用 check()
        Then: 返回 False（无需初始化）
        """
        # Arrange
        provider = DatabaseSchemaProvider()
        data_root = tmp_path / "data"
        meta_dir = data_root / "meta"
        meta_dir.mkdir(parents=True)
        db_file = meta_dir / "hub.sqlite"
        db_file.write_text("fake db", encoding="utf-8")

        # Act
        need_init = provider.check(data_root)

        # Assert
        assert need_init is False

    @patch("ditto_datahub.init_providers.SQLitePool")
    def test_initialize_creates_schema(self, mock_pool: Mock, tmp_path: Path) -> None:
        """
        测试 initialize() 创建数据库 schema。

        Given: 数据库不存在
        When: 调用 initialize()
        Then: 应创建数据库并初始化 schema
        """
        # Arrange
        provider = DatabaseSchemaProvider()
        data_root = tmp_path / "data"

        # Mock SQLitePool 实例
        mock_instance = Mock()
        mock_pool.return_value = mock_instance

        # Act
        result = provider.initialize(data_root)

        # Assert
        assert result.success is True
        assert result.skipped is False

        # 验证数据库路径正确（现在包含 schema_path 参数）
        expected_db_path = str(data_root / "meta" / "hub.sqlite")
        mock_pool.assert_called_once()
        call_args = mock_pool.call_args
        assert call_args[0][0] == expected_db_path
        assert "schema_path" in call_args[1]
        assert call_args[1]["schema_path"].name == "schema.sql"

        # 验证 schema 初始化被调用
        mock_instance.init_schema.assert_called_once()

        # 验证连接被关闭
        mock_instance.close.assert_called_once()

    @patch("ditto_datahub.init_providers.SQLitePool")
    def test_initialize_handles_errors(self, mock_pool: Mock, tmp_path: Path) -> None:
        """
        测试 initialize() 处理错误。

        Given: SQLitePool 抛出异常
        When: 调用 initialize()
        Then: 返回失败结果
        """
        # Arrange
        provider = DatabaseSchemaProvider()
        data_root = tmp_path / "data"

        # Mock SQLitePool 抛出异常
        mock_pool.side_effect = Exception("Database error")

        # Act
        result = provider.initialize(data_root)

        # Assert
        assert result.success is False
        assert "Database error" in result.message

    def test_provider_properties(self) -> None:
        """
        测试提供者属性。

        Given: DatabaseSchemaProvider 实例
        When: 访问属性
        Then: 返回正确的值
        """
        # Arrange
        provider = DatabaseSchemaProvider()

        # Act & Assert
        assert provider.name == "database_schema"
        assert provider.scope == InitScope.STARTUP


class TestRegisterDataHubProviders:
    """Test DataHub providers registration."""

    def test_register_datahub_providers(self) -> None:
        """
        测试注册 DataHub 提供者。

        Given: 重置后的协调器
        When: 调用 register_datahub_providers()
        Then: 应注册 DQConfigProvider 和 DatabaseSchemaProvider
        """
        # Arrange
        from ditto_foundation.config.initializer import get_config_coordinator

        reset_coordinator_for_testing()
        coordinator = get_config_coordinator()

        # Act
        register_datahub_providers()

        # Assert
        status = coordinator.check(Path.cwd())
        assert "dq_config" in status
        assert "database_schema" in status
