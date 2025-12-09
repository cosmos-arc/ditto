"""配置模块测试."""

import pytest

# Try to import config modules at the top level
try:
    from ditto_foundation.config.settings import Settings, get_settings
except ImportError:
    Settings = None
    get_settings = None


def test_import_config() -> None:
    """测试配置模块导入."""
    if Settings is None:
        pytest.skip("依赖未安装: config.settings")

    assert Settings is not None


def test_basic_config() -> None:
    """测试基础配置功能."""
    if Settings is None:
        pytest.skip("依赖未安装: config.settings")

    # 创建配置实例(会自动创建必要目录)
    settings = Settings()

    # 验证基本属性
    assert hasattr(settings, "system")
    assert hasattr(settings, "database")
    assert hasattr(settings, "data_source")

    # 验证环境
    assert settings.system.ditto_env in ["development", "testing", "production"]


if __name__ == "__main__":
    # 简单的配置测试
    print("=== 配置模块测试 ===")
    if get_settings is not None:
        settings = get_settings()
        print("✅ 配置模块加载成功")
        print(f"环境: {settings.system.ditto_env}")
        print("数据库路径:")
        print(f"  DuckDB: {settings.database.duckdb_path}")
        print(f"  SQLite: {settings.database.sqlite_path}")
    else:
        print("❌ 配置模块加载失败")
        print("需要先安装依赖: pip install pydantic pydantic-settings")
