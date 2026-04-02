"""IngestionCursorWriter 单元测试."""

from datetime import datetime

from ditto_data.models.ingestion import IngestionCursor
from ditto_data.stores.runtime.ingestion.ingestion_cursor_writer import (
    IngestionCursorWriter,
)


class TestIngestionCursorWriter:
    """IngestionCursorWriter 测试套件."""

    def test_upsert_cursor_creates_new(self, sqlite_client) -> None:
        """新插入 cursor 记录."""
        writer = IngestionCursorWriter(sqlite_client)
        cursor = IngestionCursor(
            dataset="stock_daily",
            source="tushare",
            last_success="2024-01-15",
            last_attempted="2024-01-15",
            updated_at=datetime.now().isoformat(),
        )
        result = writer.upsert_cursor(cursor)

        assert result.dataset == "stock_daily"
        assert result.source == "tushare"
        assert result.last_success == "2024-01-15"
        assert result.last_attempted == "2024-01-15"
        assert result.updated_at is not None

    def test_upsert_cursor_idempotent(self, sqlite_client) -> None:
        """重复 upsert 幂等 — 相同数据多次写入结果一致."""
        writer = IngestionCursorWriter(sqlite_client)
        cursor = IngestionCursor(
            dataset="stock_daily",
            source="tushare",
            last_success="2024-01-15",
            last_attempted="2024-01-15",
            updated_at=datetime.now().isoformat(),
        )
        result1 = writer.upsert_cursor(cursor)
        result2 = writer.upsert_cursor(cursor)

        assert result1.dataset == result2.dataset
        assert result1.source == result2.source
        assert result1.last_success == result2.last_success
        assert result1.last_attempted == result2.last_attempted

    def test_upsert_cursor_updates_last_success(self, sqlite_client) -> None:
        """更新 last_success 字段."""
        writer = IngestionCursorWriter(sqlite_client)

        # 第一次插入
        cursor1 = IngestionCursor(
            dataset="stock_daily",
            source="tushare",
            last_success="2024-01-15",
            last_attempted="2024-01-15",
            updated_at=datetime.now().isoformat(),
        )
        writer.upsert_cursor(cursor1)

        # 更新 last_success
        cursor2 = IngestionCursor(
            dataset="stock_daily",
            source="tushare",
            last_success="2024-01-16",
            last_attempted="2024-01-16",
            updated_at=datetime.now().isoformat(),
        )
        result = writer.upsert_cursor(cursor2)

        assert result.last_success == "2024-01-16"
        assert result.last_attempted == "2024-01-16"

    def test_upsert_cursor_updates_last_attempted(self, sqlite_client) -> None:
        """更新 last_attempted 字段."""
        writer = IngestionCursorWriter(sqlite_client)

        # 第一次插入
        cursor1 = IngestionCursor(
            dataset="stock_daily",
            source="tushare",
            last_success="2024-01-15",
            last_attempted="2024-01-15",
            updated_at=datetime.now().isoformat(),
        )
        writer.upsert_cursor(cursor1)

        # 仅更新 last_attempted（模拟失败场景）
        cursor2 = IngestionCursor(
            dataset="stock_daily",
            source="tushare",
            last_success="2024-01-15",
            last_attempted="2024-01-16",
            updated_at=datetime.now().isoformat(),
        )
        result = writer.upsert_cursor(cursor2)

        assert result.last_success == "2024-01-15"
        assert result.last_attempted == "2024-01-16"

    def test_upsert_cursor_preserves_last_success_on_failure(
        self, sqlite_client
    ) -> None:
        """失败时保留 last_success，只更新 last_attempted."""
        writer = IngestionCursorWriter(sqlite_client)

        # 先写入成功记录
        success_cursor = IngestionCursor(
            dataset="stock_daily",
            source="tushare",
            last_success="2024-01-15",
            last_attempted="2024-01-15",
            updated_at=datetime.now().isoformat(),
        )
        writer.upsert_cursor(success_cursor)

        # 模拟后续失败：last_attempted 更新，last_success 保留
        fail_cursor = IngestionCursor(
            dataset="stock_daily",
            source="tushare",
            last_success="2024-01-15",
            last_attempted="2024-01-16",
            updated_at=datetime.now().isoformat(),
        )
        result = writer.upsert_cursor(fail_cursor)

        assert result.last_success == "2024-01-15"
        assert result.last_attempted == "2024-01-16"

    def test_upsert_cursor_with_none_values(self, sqlite_client) -> None:
        """插入 last_success 和 last_attempted 均为 None 的记录."""
        writer = IngestionCursorWriter(sqlite_client)
        cursor = IngestionCursor(
            dataset="stock_daily",
            source="tushare",
            last_success=None,
            last_attempted=None,
            updated_at=datetime.now().isoformat(),
        )
        result = writer.upsert_cursor(cursor)

        assert result.dataset == "stock_daily"
        assert result.source == "tushare"
        assert result.last_success is None
        assert result.last_attempted is None
