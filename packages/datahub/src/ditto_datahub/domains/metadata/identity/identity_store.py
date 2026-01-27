"""
IdentityStore for identity mapping with PIT support.

This module provides storage and retrieval for identity mappings
with Point-in-Time support for identifier resolution.

Following design document at docs/design/02_data_design.md
"""

from __future__ import annotations

from pathlib import Path

from ditto_foundation import logger, traced

from ditto_datahub.stores.base.sqlite_store import SQLiteStore


class IdentityStore(SQLiteStore):
    """
    Identity 映射存储。

    管理 identity_mapping 表，支持 PIT 查询。

    表结构:
        - sid: 证券内部标识符
        - source: 数据源标识
        - src_code: 数据源原始代码
        - effective_from: 生效开始日期
        - effective_to: 生效结束日期 (NULL 表示当前有效)
        - is_primary: 是否主标识符
    """

    def __init__(self, db_path: Path) -> None:
        """
        初始化 IdentityStore.

        Args:
            db_path: SQLite 数据库文件路径.

        """
        super().__init__(db_path)

    @traced("data.identity.resolve_sid")
    def resolve_sid(self, src_code: str, source: str, asof: str | None) -> int | None:
        """
        解析 src_code 到 sid（支持 PIT）.

        Args:
            src_code: 数据源原始代码.
            source: 数据源标识.
            asof: 时间点日期，None 表示当前.

        Returns:
            sid 或 None（如果未找到）.

        """
        logger.debug(
            "Starting identity SID resolution",
            event="identity_sid_resolve_start",
            src_code=src_code,
            source=source,
            asof=asof,
        )

        if asof:
            # PIT mode: 查询历史映射
            row = self.fetchone(
                """SELECT sid FROM identity_mapping
                WHERE source = ? AND src_code = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1""",
                [source, src_code, asof, asof],
            )
        else:
            # Current mode: 只查询当前有效映射（更快）
            row = self.fetchone(
                """SELECT sid FROM identity_mapping
                WHERE source = ? AND src_code = ?
                  AND effective_to IS NULL""",
                [source, src_code],
            )

        sid = int(row["sid"]) if row else None

        if sid:
            logger.debug(
                "Identity SID resolved successfully",
                event="identity_sid_resolve_complete",
                src_code=src_code,
                sid=sid,
            )
        else:
            logger.warning(
                "Identity SID not found",
                event="identity_sid_resolve_not_found",
                src_code=src_code,
                source=source,
                asof=asof,
            )

        return sid

    @traced("data.identity.resolve_sids_batch")
    def resolve_sids_batch(
        self,
        src_codes: list[str],
        source: str,
        asof: str | None,
    ) -> dict[str, int]:
        """
        批量解析 src_codes 到 sids.

        Args:
            src_codes: 数据源原始代码列表.
            source: 数据源标识.
            asof: 时间点日期.

        Returns:
            字典，映射 src_code 到 sid（仅包含找到的代码）.

        """
        logger.info(
            "Starting batch identity SID resolution",
            event="identity_sid_batch_resolve_start",
            source=source,
            asof=asof,
            input_count=len(src_codes),
        )

        result: dict[str, int] = {}
        for code in src_codes:
            sid = self.resolve_sid(code, source, asof)
            if sid:
                result[code] = sid

        logger.info(
            "Batch identity SID resolution completed",
            event="identity_sid_batch_resolve_complete",
            requested=len(src_codes),
            found=len(result),
            not_found=len(src_codes) - len(result),
        )

        return result

    @traced("data.identity.get_src_code")
    def get_src_code(self, sid: int, source: str, asof: str | None) -> str | None:
        """
        反向查询：sid 到 src_code.

        Args:
            sid: 证券内部标识符.
            source: 数据源标识.
            asof: 时间点日期.

        Returns:
            src_code 或 None（如果未找到）.

        """
        if asof:
            row = self.fetchone(
                """SELECT src_code FROM identity_mapping
                WHERE sid = ? AND source = ?
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to > ?)
                ORDER BY effective_from DESC
                LIMIT 1""",
                [sid, source, asof, asof],
            )
        else:
            row = self.fetchone(
                """SELECT src_code FROM identity_mapping
                WHERE sid = ? AND source = ?
                  AND effective_to IS NULL""",
                [sid, source],
            )

        return str(row["src_code"]) if row else None

    @traced("data.identity.register")
    def register(
        self,
        sid: int,
        src_code: str,
        source: str,
        effective_from: str,
        is_primary: bool = True,
    ) -> None:
        """
        注册 identity_mapping 记录.

        Args:
            sid: 证券内部标识符.
            src_code: 数据源原始代码.
            source: 数据源标识.
            effective_from: 生效开始日期.
            is_primary: 是否主标识符.

        """
        logger.info(
            "Starting identity registration",
            event="identity_register_start",
            sid=sid,
            src_code=src_code,
            source=source,
            effective_from=effective_from,
            is_primary=is_primary,
        )

        try:
            self.execute(
                """INSERT INTO identity_mapping
                (sid, source, src_code, effective_from, is_primary)
                VALUES (?, ?, ?, ?, ?)""",
                [
                    sid,
                    source,
                    src_code,
                    effective_from,
                    1 if is_primary else 0,
                ],
            )

            self.commit()

            logger.info(
                "Identity registered successfully",
                event="identity_register_complete",
                sid=sid,
                src_code=src_code,
                source=source,
            )

        except Exception as e:
            logger.error(
                "Identity registration failed",
                event="identity_register_failed",
                sid=sid,
                src_code=src_code,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise
