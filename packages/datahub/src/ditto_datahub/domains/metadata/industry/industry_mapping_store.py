"""
IndustryMappingStore for stock-industry mapping with PIT support.

支持股票-行业映射的 PIT 查询。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ditto_foundation import traced

from ditto_datahub.stores.base.sqlite_store import SQLiteStore


class IndustryMappingStore(SQLiteStore):
    """股票-行业映射存储."""

    def __init__(self, db_path: Path) -> None:
        """
        初始化 IndustryMappingStore.

        Args:
            db_path: SQLite 数据库文件路径.

        """
        super().__init__(db_path)

    @traced("data.industry.get_stocks")
    def get_stocks(
        self,
        industry_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        获取行业的所有成分股.

        Args:
            industry_id: 行业 ID
            asof: Point-in-time 查询日期

        Returns:
            SID 列表

        """
        if asof:
            rows = self.fetchall(
                """SELECT sid FROM industry_mapping
                WHERE industry_id = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY sid""",
                [industry_id, asof, asof],
            )
        else:
            rows = self.fetchall(
                """SELECT sid FROM industry_mapping
                WHERE industry_id = ? AND effective_to IS NULL
                ORDER BY sid""",
                [industry_id],
            )

        return [int(r["sid"]) for r in rows]

    @traced("data.industry.get_stock_industry")
    def get_stock_industry(
        self,
        sid: int,
        asof: str | None = None,
    ) -> dict[str, Any] | None:
        """
        获取股票所属行业.

        Args:
            sid: 证券 ID
            asof: Point-in-time 查询日期

        Returns:
            行业映射信息

        """
        if asof:
            return self.fetchone(
                """SELECT * FROM industry_mapping
                WHERE sid = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1""",
                [sid, asof, asof],
            )
        else:
            return self.fetchone(
                """SELECT * FROM industry_mapping
                WHERE sid = ? AND effective_to IS NULL""",
                [sid],
            )

    @traced("data.industry.update_mapping")
    def update_mapping(
        self,
        sid: int,
        industry_id: str,
        effective_from: str,
        entry_reason: str | None = None,
    ) -> None:
        """
        更新股票的行业映射.

        Args:
            sid: 证券 ID
            industry_id: 行业 ID
            effective_from: 生效日期
            entry_reason: 入选原因

        """
        # 失效旧映射
        self.execute(
            """UPDATE industry_mapping
            SET effective_to = ?
            WHERE sid = ? AND effective_to IS NULL""",
            [effective_from, sid],
        )

        # 插入新映射
        self.execute(
            """INSERT INTO industry_mapping
            (sid, industry_id, source, effective_from, entry_reason)
            VALUES (?, ?, 'sw', ?, ?)""",
            [sid, industry_id, effective_from, entry_reason],
        )
        self.commit()
