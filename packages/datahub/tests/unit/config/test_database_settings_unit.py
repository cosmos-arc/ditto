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

        # 验证路径包含预期目录
        assert "duckdb" in str(settings.duckdb_path)
        assert "ditto.duckdb" in str(settings.duckdb_path)
        assert "sqlite" in str(settings.sqlite_path)
        assert "hub.sqlite" in str(settings.sqlite_path)

    def test_env_prefix(self, monkeypatch):
        """测试环境变量前缀."""
        # DatabaseSettings 使用 computed_field，环境变量不会直接影响路径
        # 但我们可以验证实例化成功
        settings = DatabaseSettings()
        assert settings.duckdb_path is not None
        assert settings.sqlite_path is not None

    def test_duckdb_path_is_absolute(self, monkeypatch):
        """测试 duckdb_path 是绝对路径."""
        for key in list(os.environ.keys()):
            if key.startswith("DB_"):
                monkeypatch.delenv(key, raising=False)

        settings = DatabaseSettings()
        assert settings.duckdb_path.is_absolute()

    def test_sqlite_path_is_absolute(self, monkeypatch):
        """测试 sqlite_path 是绝对路径."""
        for key in list(os.environ.keys()):
            if key.startswith("DB_"):
                monkeypatch.delenv(key, raising=False)

        settings = DatabaseSettings()
        assert settings.sqlite_path.is_absolute()

    def test_model_validate(self, monkeypatch):
        """测试 model_validate 方法."""
        for key in list(os.environ.keys()):
            if key.startswith("DB_"):
                monkeypatch.delenv(key, raising=False)

        # 即使传入空字典，computed_field 也会生成路径
        settings = DatabaseSettings.model_validate({})
        assert settings.duckdb_path is not None
        assert settings.sqlite_path is not None

    def test_extra_ignore(self, monkeypatch):
        """测试 extra='ignore' 忽略额外字段."""
        monkeypatch.setenv("DB_UNKNOWN_FIELD", "some_value")
        # 不应该抛出错误
        settings = DatabaseSettings()
        assert settings is not None
