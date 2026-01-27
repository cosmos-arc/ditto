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

        # 验证路径结构（使用 normalize_path 处理跨平台路径差异）
        def normalize_path(path_str: str) -> str:
            return path_str.replace("\\", "/")

        assert normalize_path(str(settings.data_root)).endswith("data/ditto")
        assert normalize_path(str(settings.log_root)).endswith("data/ditto/logs")
        assert normalize_path(str(settings.backup_root)).endswith("data/ditto/backups")
        assert normalize_path(str(settings.temp_root)).endswith("data/ditto/temp")

    def test_all_paths_are_absolute(self):
        """测试所有路径都是绝对路径（在设置了 DATA_ROOT 环境变量时）."""
        import os

        # 设置 DATA_ROOT 环境变量
        original_value = os.environ.get("DATA_ROOT")
        try:
            os.environ["DATA_ROOT"] = (
                "D:\\test\\ditto" if os.name == "nt" else "/tmp/test/ditto"
            )
            settings = FileStorageSettings()

            assert settings.data_root.is_absolute()
            assert settings.log_root.is_absolute()
            assert settings.backup_root.is_absolute()
            assert settings.temp_root.is_absolute()
        finally:
            if original_value is None:
                os.environ.pop("DATA_ROOT", None)
            else:
                os.environ["DATA_ROOT"] = original_value

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
