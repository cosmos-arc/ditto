"""DatabaseSettings 单元测试."""

import os

from ditto_datahub.config.database import DatabaseSettings


class TestDatabaseSettings:
    """DatabaseSettings 测试类."""

    def test_default_values(self, monkeypatch):
        """测试默认值."""
        # 清除环境变量
        for key in list(os.environ.keys()):
            if key.startswith("DB_"):
                monkeypatch.delenv(key, raising=False)

        settings = DatabaseSettings()

        # 验证路径是 Path 对象
        assert hasattr(settings.duckdb_path, "mkdir")
        assert hasattr(settings.sqlite_path, "mkdir")

        # 验证路径结构（基于 DataRootConfig）
        # sqlite_path 指向 metadata/metadata.sqlite
        assert "metadata" in str(settings.sqlite_path)
        assert "metadata.sqlite" in str(settings.sqlite_path)
        # duckdb_path 指向 db/duckdb/ditto.duckdb
        assert "duckdb" in str(settings.duckdb_path)
        assert "ditto.duckdb" in str(settings.duckdb_path)

    def test_env_prefix(self, monkeypatch):
        """测试环境变量前缀."""
        # DatabaseSettings 支持通过环境变量覆盖路径
        settings = DatabaseSettings()
        assert settings.duckdb_path is not None
        assert settings.sqlite_path is not None

    def test_duckdb_path_is_absolute(self, monkeypatch):
        """测试 duckdb_path 是绝对路径（在设置了 DATA_ROOT 时）."""
        for key in list(os.environ.keys()):
            if key.startswith("DB_"):
                monkeypatch.delenv(key, raising=False)

        # 设置 DATA_ROOT 环境变量
        original_value = os.environ.get("DATA_ROOT")
        try:
            os.environ["DATA_ROOT"] = (
                "D:\\test\\ditto" if os.name == "nt" else "/tmp/test/ditto"
            )
            settings = DatabaseSettings()
            assert settings.duckdb_path.is_absolute()
        finally:
            if original_value is None:
                os.environ.pop("DATA_ROOT", None)
            else:
                os.environ["DATA_ROOT"] = original_value

    def test_sqlite_path_is_absolute(self, monkeypatch):
        """测试 sqlite_path 是绝对路径（在设置了 DATA_ROOT 时）."""
        for key in list(os.environ.keys()):
            if key.startswith("DB_"):
                monkeypatch.delenv(key, raising=False)

        # 设置 DATA_ROOT 环境变量
        original_value = os.environ.get("DATA_ROOT")
        try:
            os.environ["DATA_ROOT"] = (
                "D:\\test\\ditto" if os.name == "nt" else "/tmp/test/ditto"
            )
            settings = DatabaseSettings()
            assert settings.sqlite_path.is_absolute()
        finally:
            if original_value is None:
                os.environ.pop("DATA_ROOT", None)
            else:
                os.environ["DATA_ROOT"] = original_value

    def test_model_validate(self, monkeypatch):
        """测试 model_validate 方法."""
        for key in list(os.environ.keys()):
            if key.startswith("DB_"):
                monkeypatch.delenv(key, raising=False)

        # 即使传入空字典，也会使用 DataRootConfig 的默认值
        settings = DatabaseSettings.model_validate({})
        assert settings.duckdb_path is not None
        assert settings.sqlite_path is not None

    def test_extra_ignore(self, monkeypatch):
        """测试 extra='ignore' 忽略额外字段."""
        monkeypatch.setenv("DB_UNKNOWN_FIELD", "some_value")
        # 不应该抛出错误
        settings = DatabaseSettings()
        assert settings is not None
