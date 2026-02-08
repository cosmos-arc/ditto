"""
IndustryBasicStore for industry master data.

支持申万行业分类的存储和查询。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl
from ditto_foundation import traced

from ditto_datahub.stores.base.sqlite_store import SQLiteStore
from ditto_datahub.stores.metadata.industry.models import IndustryBasic


class IndustryBasicStore(SQLiteStore):
    """申万行业主数据存储."""

    def __init__(self, db_path: Path) -> None:
        """
        初始化 IndustryBasicStore.

        Args:
            db_path: SQLite 数据库文件路径.

        """
        super().__init__(db_path)

    @traced("data.industry.get_all")
    def get_all(
        self,
        is_active: bool = True,
        industry_level: str | None = None,
    ) -> pl.DataFrame:
        """
        获取所有行业信息.

        Args:
            is_active: 是否只返回活跃行业
            industry_level: 行业级别过滤

        Returns:
            行业信息 DataFrame

        """
        sql = "SELECT * FROM industry_basic WHERE 1=1"
        params: list[object] = []

        if is_active:
            sql += " AND is_active = ?"
            params.append(1 if is_active else 0)

        if industry_level:
            sql += " AND industry_level = ?"
            params.append(industry_level)

        with self._get_connection() as conn:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()

        if not rows:
            return pl.DataFrame()

        return pl.DataFrame([dict(row) for row in rows])

    @traced("data.industry.get_by_id")
    def get_by_id(self, industry_id: str) -> dict[str, Any] | None:
        """
        根据 ID 获取行业信息.

        Args:
            industry_id: 行业 ID

        Returns:
            行业信息字典

        """
        return self.fetchone(
            "SELECT * FROM industry_basic WHERE industry_id = ?",
            [industry_id],
        )

    @traced("data.industry.register")
    def register(self, industry: IndustryBasic) -> None:
        """
        注册行业信息.

        Args:
            industry: 行业基本信息

        """
        self.execute(
            """INSERT OR REPLACE INTO industry_basic
            (industry_id, industry_name, industry_level, parent_id, is_active)
            VALUES (?, ?, ?, ?, ?)""",
            [
                industry.industry_id,
                industry.industry_name,
                industry.industry_level,
                industry.parent_id,
                1 if industry.is_active else 0,
            ],
        )
        self.commit()
