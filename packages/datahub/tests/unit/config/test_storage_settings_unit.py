"""FileStorageSettings 单元测试."""

from ditto_datahub.config.storage import FileStorageSettings


class TestFileStorageSettings:
    """FileStorageSettings 测试类."""

    def test_default_values(self):
        """测试默认值."""
        settings = FileStorageSettings()

        # 验证路径是 Path 对象
        assert hasattr(settings.data_root, "mkdir")
        assert hasattr(settings.log_root, "mkdir")
        assert hasattr(settings.backup_root, "mkdir")
        assert hasattr(settings.temp_root, "mkdir")

        # 验证路径名称包含预期目录
        assert "data" in str(settings.data_root).lower()
        assert "logs" in str(settings.log_root).lower()
        assert "backup" in str(settings.backup_root).lower()
        assert (
            "temp" in str(settings.temp_root).lower()
            or "cache" in str(settings.temp_root).lower()
        )

    def test_all_paths_are_absolute(self):
        """测试所有路径都是绝对路径."""
        settings = FileStorageSettings()

        assert settings.data_root.is_absolute()
        assert settings.log_root.is_absolute()
        assert settings.backup_root.is_absolute()
        assert settings.temp_root.is_absolute()

    def test_model_validate(self):
        """测试 model_validate 方法."""
        settings = FileStorageSettings.model_validate({})
        assert settings.data_root is not None
        assert settings.log_root is not None
        assert settings.backup_root is not None
        assert settings.temp_root is not None

    def test_extra_ignore(self, monkeypatch):
        """测试 extra='ignore' 忽略额外字段."""
        monkeypatch.setenv("UNKNOWN_FIELD", "some_value")
        # 不应该抛出错误
        settings = FileStorageSettings()
        assert settings is not None
