"""
数据库连接管理组件.

提供通用数据库连接池和连接管理功能，支持并发访问和事务管理。
"""

from ditto_infra.foundation.db.sqlite_pool import SQLitePool

__all__ = ["SQLitePool"]
