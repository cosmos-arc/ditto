"""IngestionCursorReader 单元测试."""

from datetime import datetime

from ditto_datahub.models.ingestion import IngestionCursor
from ditto_datahub.stores.runtime.ingestion.ingestion_cursor_reader import (
    IngestionCursorReader,
)
from ditto_datahub.stores.runtime.ingestion.ingestion_cursor_writer import (
    IngestionCursorWriter,
)


def _init_tables(sqlite_client) -> IngestionCursorWriter:
    """辅助函数：初始化表结构（Writer 构造函数会创建表）."""
    return IngestionCursorWriter(sqlite_client)


def _write_cursor(
    sqlite_client,
    dataset: str,
    source: str,
    last_success: str | None,
    last_attempted: str | None,
) -> IngestionCursor:
    """辅助函数：通过 Writer 写入 cursor 记录."""
    writer = _init_tables(sqlite_client)
    cursor = IngestionCursor(
        dataset=dataset,
        source=source,
        last_success=last_success,
        last_attempted=last_attempted,
        updated_at=datetime.now().isoformat(),
    )
    return writer.upsert_cursor(cursor)


class TestIngestionCursorReader:
    """IngestionCursorReader 测试套件."""

    def test_get_cursor_returns_none_for_missing(self, sqlite_client) -> None:
        """查询不存在的 cursor 返回 None."""
        _init_tables(sqlite_client)  # 确保表存在
        reader = IngestionCursorReader(sqlite_client)
        result = reader.get_cursor("nonexistent_dataset", "tushare")
        assert result is None

    def test_get_cursor_returns_cursor(self, sqlite_client) -> None:
        """查询存在的 cursor 返回正确数据."""
        _write_cursor(
            sqlite_client, "stock_daily", "tushare", "2024-01-15", "2024-01-15"
        )

        reader = IngestionCursorReader(sqlite_client)
        result = reader.get_cursor("stock_daily", "tushare")

        assert result is not None
        assert result.dataset == "stock_daily"
        assert result.source == "tushare"
        assert result.last_success == "2024-01-15"
        assert result.last_attempted == "2024-01-15"

    def test_list_cursors_all(self, sqlite_client) -> None:
        """列出所有 cursor 记录."""
        _write_cursor(
            sqlite_client, "stock_daily", "tushare", "2024-01-15", "2024-01-15"
        )
        _write_cursor(
            sqlite_client, "index_daily", "tushare", "2024-01-14", "2024-01-14"
        )

        reader = IngestionCursorReader(sqlite_client)
        results = reader.list_cursors()

        assert len(results) == 2
        datasets = {r.dataset for r in results}
        assert datasets == {"stock_daily", "index_daily"}

    def test_list_cursors_by_source(self, sqlite_client) -> None:
        """按 source 过滤列出 cursor 记录."""
        _write_cursor(
            sqlite_client, "stock_daily", "tushare", "2024-01-15", "2024-01-15"
        )
        _write_cursor(
            sqlite_client, "index_daily", "eastmoney", "2024-01-14", "2024-01-14"
        )

        reader = IngestionCursorReader(sqlite_client)
        results = reader.list_cursors(source="tushare")

        assert len(results) == 1
        assert results[0].dataset == "stock_daily"
        assert results[0].source == "tushare"

    def test_get_last_success_returns_date(self, sqlite_client) -> None:
        """返回最后成功的日期字符串."""
        _write_cursor(
            sqlite_client, "stock_daily", "tushare", "2024-01-15", "2024-01-15"
        )

        reader = IngestionCursorReader(sqlite_client)
        result = reader.get_last_success("stock_daily", "tushare")

        assert result == "2024-01-15"

    def test_get_last_success_returns_none(self, sqlite_client) -> None:
        """无成功记录时返回 None."""
        # 写入一条没有 last_success 的记录
        _write_cursor(sqlite_client, "stock_daily", "tushare", None, "2024-01-15")

        reader = IngestionCursorReader(sqlite_client)
        result = reader.get_last_success("stock_daily", "tushare")

        assert result is None

    def test_get_last_success_default_source(self, sqlite_client) -> None:
        """默认 source 为 'tushare'."""
        _write_cursor(
            sqlite_client, "stock_daily", "tushare", "2024-01-15", "2024-01-15"
        )

        reader = IngestionCursorReader(sqlite_client)
        result = reader.get_last_success("stock_daily")

        assert result == "2024-01-15"
