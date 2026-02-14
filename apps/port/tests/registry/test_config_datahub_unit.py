"""ConfigProvider DataHub 配置测试."""

from dishka import make_container
from ditto_datahub.config import (
    DatabaseSettings,
    DataSourceSettings,
    FileStorageSettings,
)
from ditto_port.registry.config import ConfigProvider


class TestConfigProviderDataHub:
    """ConfigProvider DataHub 配置测试类."""

    def test_database_settings_provider(self, monkeypatch):
        """测试 database_settings provider."""
        # 设置环境
        monkeypatch.setenv("ENVIRONMENT", "testing")

        # 创建容器
        container = make_container(ConfigProvider())

        # 获取 database_settings
        database_settings = container.get(DatabaseSettings)

        # 验证
        assert isinstance(database_settings, DatabaseSettings)
        assert database_settings.duckdb_path is not None
        assert database_settings.sqlite_path is not None

        # 清理
        container.close()

    def test_data_source_settings_provider(self, monkeypatch):
        """测试 data_source_settings provider."""
        # 设置环境
        monkeypatch.setenv("ENVIRONMENT", "testing")

        # 创建容器
        container = make_container(ConfigProvider())

        # 获取 data_source_settings
        data_source_settings = container.get(DataSourceSettings)

        # 验证
        assert isinstance(data_source_settings, DataSourceSettings)
        assert data_source_settings.http_base_url is not None
        assert data_source_settings.http_timeout > 0
        assert data_source_settings.retry_max_attempts > 0

        # 清理
        container.close()

    def test_file_storage_settings_provider(self, monkeypatch):
        """测试 file_storage_settings provider."""
        # 设置环境
        monkeypatch.setenv("ENVIRONMENT", "testing")

        # 创建容器
        container = make_container(ConfigProvider())

        # 获取 file_storage_settings
        file_storage_settings = container.get(FileStorageSettings)

        # 验证
        assert isinstance(file_storage_settings, FileStorageSettings)
        assert file_storage_settings.data_root is not None
        assert file_storage_settings.log_root is not None
        assert file_storage_settings.backup_root is not None
        assert file_storage_settings.temp_root is not None

        # 清理
        container.close()

    def test_all_datahub_settings_together(self, monkeypatch):
        """测试所有 DataHub 配置一起获取."""
        # 设置环境
        monkeypatch.setenv("ENVIRONMENT", "testing")

        # 创建容器
        container = make_container(ConfigProvider())

        # 获取所有配置
        database_settings = container.get(DatabaseSettings)
        data_source_settings = container.get(DataSourceSettings)
        file_storage_settings = container.get(FileStorageSettings)

        # 验证所有配置都正确
        assert isinstance(database_settings, DatabaseSettings)
        assert isinstance(data_source_settings, DataSourceSettings)
        assert isinstance(file_storage_settings, FileStorageSettings)

        # 验证单例特性：多次获取是同一实例
        database_settings_2 = container.get(DatabaseSettings)
        assert database_settings is database_settings_2

        # 清理
        container.close()
