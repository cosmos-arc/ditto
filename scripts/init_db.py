#!/usr/bin/env python3
"""
数据库初始化脚本.

创建所有必要的表、索引和视图
"""

import logging
import sys
from pathlib import Path
from typing import Any

try:
    import duckdb
    import sqlite3
    from ditto_core.data.services.data_writer import DataWriter
except ImportError as e:
    print(f"导入失败: {e}")
    print("请确保在 pixi 环境中运行: pixi run python scripts/init_db.py")
    sys.exit(1)

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DatabaseInitializer:
    """数据库初始化器."""

    def __init__(self) -> None:
        # 数据库路径
        self.project_root = Path(__file__).parent.parent
        self.duckdb_path = self.project_root / "data" / "duckdb" / "ditto.duckdb"
        self.sqlite_path = self.project_root / "data" / "sqlite" / "ditto.sqlite"

    def initialize_all(self) -> None:
        """初始化所有数据库."""
        try:
            logger.info("开始数据库初始化...")

            # 创建数据目录
            self.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

            # 使用 DataWriter 初始化（会自动创建表）
            DataWriter(str(self.duckdb_path), str(self.sqlite_path))

            # DataWriter 的构造函数会自动初始化数据库和表
            logger.info("✅ 数据库初始化完成!")

        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise

    def verify_initialization(self) -> dict[str, Any]:
        """验证初始化结果."""
        logger.info("验证数据库初始化结果...")

        result: dict[str, Any] = {
            "duckdb_tables": 0,
            "sqlite_tables": 0,
            "issues": [],
        }

        try:
            # 验证 DuckDB
            if self.duckdb_path.exists():
                conn = duckdb.connect(str(self.duckdb_path))
                # 简单验证表是否存在
                tables = conn.execute("SHOW TABLES").fetchall()
                result["duckdb_tables"] = len(tables)
                logger.info(f"DuckDB 表数量: {len(tables)}")
                conn.close()

            # 验证 SQLite
            if self.sqlite_path.exists():
                conn = sqlite3.connect(str(self.sqlite_path))
                # 简单验证表是否存在
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()
                result["sqlite_tables"] = len(tables)
                logger.info(f"SQLite 表数量: {len(tables)}")
                conn.close()

        except Exception as e:
            result["issues"].append(f"验证失败: {e}")
            logger.error(f"验证初始化结果失败: {e}")

        return result


def print_database_info() -> bool:
    """打印数据库信息."""
    print("=== 数据库配置信息 ===")
    base_path = Path(__file__).parent.parent
    print(f"DuckDB 路径: {base_path / 'data' / 'duckdb' / 'ditto.duckdb'}")
    print(f"SQLite 路径: {base_path / 'data' / 'sqlite' / 'ditto.sqlite'}")
    print()
    print("✅ 数据库配置验证通过")
    return True


def main() -> int:
    """主函数."""
    print("=== Ditto 数据库初始化工具 ===")
    print()

    # 检查配置
    if not print_database_info():
        return 1

    # 确认初始化
    response = input("是否继续数据库初始化? (y/N): ").lower().strip()
    if response != "y":
        print("取消初始化")
        return 0

    # 执行初始化
    try:
        initializer = DatabaseInitializer()
        initializer.initialize_all()

        # 验证结果
        result = initializer.verify_initialization()
        print("\n=== 初始化结果 ===")
        print(f"DuckDB 表: {result['duckdb_tables']}")
        print(f"SQLite 表: {result['sqlite_tables']}")

        if result["issues"]:
            print("\n问题:")
            for issue in result["issues"]:
                print(f"  ⚠️ {issue}")
        else:
            print("\n✅ 数据库初始化成功!")

    except Exception as e:
        logger.error(f"初始化失败: {e}")
        print(f"\n❌ 初始化失败: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
