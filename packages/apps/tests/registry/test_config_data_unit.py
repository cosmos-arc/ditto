"""ConfigProvider Data 配置测试."""

from pathlib import Path
from typing import cast

from dishka import make_container
from ditto_apps.registry.infra import ConfigProvider
from ditto_apps.registry.infra import config as config_module
from ditto_data.config import (
    DataSourceSettings,
    FileStorageSettings,
)
from ditto_data.config.data_store import DataStoreSettings
from ditto_platform.foundation import ConfigLoader


class TestConfigProviderData:
    """ConfigProvider Data 配置测试类."""

    def test_data_store_settings_provider(self, monkeypatch):
        """测试 data_store_settings provider."""
        # 设置环境
        monkeypatch.setenv("ENVIRONMENT", "testing")

        # 创建容器
        container = make_container(ConfigProvider())

        # 获取 data_store_settings
        settings = container.get(DataStoreSettings)

        # 验证
        assert isinstance(settings, DataStoreSettings)
        assert settings.data_root is not None
        assert settings.resolved_duckdb_path is not None
        assert settings.resolved_sqlite_path is not None

        # 清理
        container.close()

    def test_ditto_data_root_overrides_environment_config(
        self,
        monkeypatch,
        tmp_path: Path,
    ) -> None:
        """Docker 使用的 DITTO_DATA_ROOT 必须覆盖环境配置文件。"""
        container_data_root = tmp_path / "container-data"
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DITTO_DATA_ROOT", str(container_data_root))

        container = make_container(ConfigProvider())
        try:
            settings = container.get(DataStoreSettings)
            assert settings.data_root == container_data_root
        finally:
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

    def test_blank_optional_secret_values_use_model_defaults(self, monkeypatch) -> None:
        """Empty env-file fields must not become invalid None-valued secrets."""
        monkeypatch.setattr(
            config_module,
            "load_env_file",
            lambda _loader, _name: {
                "tushare_token": None,
                "fred_api_key": None,
            },
        )
        monkeypatch.setattr(
            config_module,
            "_load_keyring_secret",
            lambda _service, _key: None,
        )

        settings = ConfigProvider().data_source_settings(cast(ConfigLoader, object()))

        assert settings.tushare_token == ""
        assert settings.fred_api_key == ""

    def test_runtime_secret_preload_populates_parent_memory(self, monkeypatch) -> None:
        """The server parent resolves both provider secrets before worker fork."""
        monkeypatch.setattr(config_module, "_PRELOADED_KEYRING_SECRETS", {})
        monkeypatch.setattr(
            config_module,
            "_read_keyring_secret",
            lambda service, key: f"{service}-{key}-secret",
        )

        config_module.preload_runtime_secrets()

        assert config_module._PRELOADED_KEYRING_SECRETS == {
            ("tushare", "token"): "tushare-token-secret",
            ("fred", "api_key"): "fred-api_key-secret",
        }

    def test_preloaded_secret_avoids_worker_keychain_io(self, monkeypatch) -> None:
        """Forked workers inherit parent memory and do not reopen Keychain."""
        monkeypatch.setattr(
            config_module,
            "_PRELOADED_KEYRING_SECRETS",
            {("tushare", "token"): "parent-resolved-secret"},
        )

        def fail_read(_service: str, _key: str) -> str | None:
            raise AssertionError("worker attempted Keychain I/O")

        monkeypatch.setattr(config_module, "_read_keyring_secret", fail_read)

        assert (
            config_module._load_keyring_secret("tushare", "token")
            == "parent-resolved-secret"
        )

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

    def test_all_data_settings_together(self, monkeypatch):
        """测试所有 Data 配置一起获取."""
        # 设置环境
        monkeypatch.setenv("ENVIRONMENT", "testing")

        # 创建容器
        container = make_container(ConfigProvider())

        # 获取所有配置
        data_store_settings = container.get(DataStoreSettings)
        data_source_settings = container.get(DataSourceSettings)
        file_storage_settings = container.get(FileStorageSettings)

        # 验证所有配置都正确
        assert isinstance(data_store_settings, DataStoreSettings)
        assert isinstance(data_source_settings, DataSourceSettings)
        assert isinstance(file_storage_settings, FileStorageSettings)

        # 验证单例特性：多次获取是同一实例
        data_store_settings_2 = container.get(DataStoreSettings)
        assert data_store_settings is data_store_settings_2

        # 清理
        container.close()
