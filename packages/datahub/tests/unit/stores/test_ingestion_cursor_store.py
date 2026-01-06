"""Tests for IngestionCursorStore."""

import pytest
from ditto_datahub.runtime.sqlite_pool import SQLitePool
from ditto_datahub.stores.ingestion_cursor import IngestionCursorStore
from ditto_datahub.stores.sqlite_client import SQLiteClient


@pytest.mark.unit
class TestIngestionCursorStore:
    """Tests for IngestionCursorStore."""

    def setup_method(self) -> None:
        """Set up test database."""
        self.pool = SQLitePool(":memory:")
        self.pool.init_schema()
        self.client = SQLiteClient(self.pool)
        self.store = IngestionCursorStore(self.client)

    def test_get_cursor_not_found(self) -> None:
        """验证获取不存在的游标返回 None。"""
        # Arrange
        dataset = "nonexistent_dataset"
        source = "tushare"

        # Act
        cursor = self.store.get_cursor(dataset, source)

        # Assert
        assert cursor is None

    def test_update_success_creates_new_cursor(self) -> None:
        """验证更新成功游标创建新记录。"""
        # Arrange
        dataset = "stock_daily"
        source = "tushare"
        trade_date = "2024-01-02"

        # Act
        cursor = self.store.update_success(dataset, source, trade_date)

        # Assert
        assert cursor.dataset == dataset
        assert cursor.source == source
        assert cursor.last_success == trade_date
        assert cursor.last_attempted == trade_date
        assert cursor.updated_at is not None

        # 验证可以读取
        retrieved = self.store.get_cursor(dataset, source)
        assert retrieved is not None
        assert retrieved.dataset == dataset
        assert retrieved.source == source
        assert retrieved.last_success == trade_date

    def test_update_success_updates_existing_cursor(self) -> None:
        """验证更新成功游标覆盖已存在的记录。"""
        # Arrange - 先创建一个游标
        dataset = "stock_daily"
        source = "tushare"
        self.store.update_success(dataset, source, "2024-01-02")

        # Act - 更新到新的日期
        cursor = self.store.update_success(dataset, source, "2024-01-03")

        # Assert
        assert cursor.last_success == "2024-01-03"
        assert cursor.last_attempted == "2024-01-03"

        # 验证只有一个记录
        retrieved = self.store.get_cursor(dataset, source)
        assert retrieved is not None
        assert retrieved.last_success == "2024-01-03"

    def test_update_attempted_creates_new_cursor(self) -> None:
        """验证更新尝试游标创建新记录（last_success 为 NULL）。"""
        # Arrange
        dataset = "stock_daily"
        source = "tushare"
        trade_date = "2024-01-02"

        # Act
        cursor = self.store.update_attempted(dataset, source, trade_date)

        # Assert
        assert cursor.dataset == dataset
        assert cursor.source == source
        assert cursor.last_success is None  # 首次尝试，last_success 为 NULL
        assert cursor.last_attempted == trade_date

        # 验证可以读取
        retrieved = self.store.get_cursor(dataset, source)
        assert retrieved is not None
        assert retrieved.last_success is None
        assert retrieved.last_attempted == trade_date

    def test_update_attempted_preserves_last_success(self) -> None:
        """验证更新尝试游标保留 last_success。"""
        # Arrange - 先创建一个成功的游标
        dataset = "stock_daily"
        source = "tushare"
        self.store.update_success(dataset, source, "2024-01-02")

        # Act - 更新尝试（模拟失败）
        cursor = self.store.update_attempted(dataset, source, "2024-01-03")

        # Assert
        assert cursor.last_success == "2024-01-02"  # 保留之前的成功日期
        assert cursor.last_attempted == "2024-01-03"  # 更新尝试日期

    def test_multiple_sources_independent_cursors(self) -> None:
        """验证多源的游标独立存储。"""
        # Arrange
        dataset = "stock_daily"
        source1 = "tushare"
        source2 = "akshare"

        # Act - 为不同源创建游标
        cursor1 = self.store.update_success(dataset, source1, "2024-01-02")
        cursor2 = self.store.update_success(dataset, source2, "2024-01-03")

        # Assert - 验证两个游标独立
        assert cursor1.dataset == cursor2.dataset
        assert cursor1.source != cursor2.source
        assert cursor1.last_success != cursor2.last_success

        # 验证可以独立读取
        retrieved1 = self.store.get_cursor(dataset, source1)
        retrieved2 = self.store.get_cursor(dataset, source2)

        assert retrieved1 is not None
        assert retrieved2 is not None
        assert retrieved1.source == source1
        assert retrieved2.source == source2
        assert retrieved1.last_success == "2024-01-02"
        assert retrieved2.last_success == "2024-01-03"

    def test_get_all_cursors_single_source(self) -> None:
        """验证获取单个源的所有游标。"""
        # Arrange - 创建多个数据集的游标
        self.store.update_success("stock_daily", "tushare", "2024-01-02")
        self.store.update_success("etf_daily", "tushare", "2024-01-03")
        self.store.update_success("stock_daily", "akshare", "2024-01-04")

        # Act
        tushare_cursors = self.store.get_all_cursors("tushare")
        akshare_cursors = self.store.get_all_cursors("akshare")

        # Assert
        assert len(tushare_cursors) == 2
        assert all(c.source == "tushare" for c in tushare_cursors)
        assert len(akshare_cursors) == 1
        assert akshare_cursors[0].source == "akshare"

    def test_get_all_cursors_empty(self) -> None:
        """验证获取不存在源的游标返回空列表。"""
        # Act
        cursors = self.store.get_all_cursors("nonexistent_source")

        # Assert
        assert cursors == []

    def test_default_source_parameter(self) -> None:
        """验证默认使用 tushare 作为源。"""
        # Arrange & Act
        cursor = self.store.update_success("stock_daily", "tushare", "2024-01-02")

        # Assert
        assert cursor.source == "tushare"

    def test_primary_key_constraint_dataset_source(self) -> None:
        """验证 (dataset, source) 复合主键约束。"""
        # Arrange
        dataset = "stock_daily"
        source = "tushare"

        # Act - 多次更新同一 dataset+source
        self.store.update_success(dataset, source, "2024-01-02")
        self.store.update_success(dataset, source, "2024-01-03")

        # Assert - 只有一个记录（被覆盖）
        cursors = self.store.get_all_cursors(source)
        stock_daily_cursors = [c for c in cursors if c.dataset == dataset]
        assert len(stock_daily_cursors) == 1
        assert stock_daily_cursors[0].last_success == "2024-01-03"
