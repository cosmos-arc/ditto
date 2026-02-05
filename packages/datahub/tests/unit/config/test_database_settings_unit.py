"""DatabaseSettings 单元测试."""

import tempfile
from pathlib import Path

from ditto_datahub.config.database import DatabaseSettings


class TestDatabaseSettings:
    """DatabaseSettings 测试类."""

    def test_default_values(self):
        """测试默认值."""
        settings = DatabaseSettings()
        assert settings.duckdb_path is None
        assert settings.sqlite_path is None

    def test_explicit_values(self):
        """测试显式配置."""
        duckdb_path = Path("data/db/duckdb/ditto.duckdb")
        sqlite_path = Path("data/metadata/metadata.sqlite")
        settings = DatabaseSettings(
            duckdb_path=duckdb_path,
            sqlite_path=sqlite_path,
        )
        assert settings.duckdb_path == duckdb_path
        assert settings.sqlite_path == sqlite_path

    def test_duckdb_path_is_absolute(self):
        """测试 duckdb_path 是绝对路径."""
        with tempfile.TemporaryDirectory() as temp_dir:
            duckdb_path = Path(temp_dir) / "db" / "ditto.duckdb"
            settings = DatabaseSettings(duckdb_path=duckdb_path)
            assert settings.duckdb_path is not None
            assert settings.duckdb_path.is_absolute()

    def test_sqlite_path_is_absolute(self):
        """测试 sqlite_path 是绝对路径."""
        with tempfile.TemporaryDirectory() as temp_dir:
            sqlite_path = Path(temp_dir) / "metadata" / "metadata.sqlite"
            settings = DatabaseSettings(sqlite_path=sqlite_path)
            assert settings.sqlite_path is not None
            assert settings.sqlite_path.is_absolute()

    def test_model_validate(self):
        """测试 model_validate 方法."""
        settings = DatabaseSettings.model_validate(
            {
                "duckdb_path": "data/db/duckdb/ditto.duckdb",
                "sqlite_path": "data/metadata/metadata.sqlite",
            }
        )
        assert settings.duckdb_path == Path("data/db/duckdb/ditto.duckdb")
        assert settings.sqlite_path == Path("data/metadata/metadata.sqlite")

    def test_extra_ignore(self):
        """测试 extra='ignore' 忽略额外字段."""
        settings = DatabaseSettings.model_validate(
            {
                "duckdb_path": "data/db/duckdb/ditto.duckdb",
                "sqlite_path": "data/metadata/metadata.sqlite",
                "unknown_field": "some_value",
            }
        )
        assert settings is not None
