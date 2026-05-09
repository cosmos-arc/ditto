"""Tests for RebalanceReader and RebalanceWriter (T15)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_data.storage.metadata.universe.rebalance_reader import (
    RebalanceReader,
)
from ditto_data.storage.metadata.universe.rebalance_writer import (
    RebalanceWriter,
)
from ditto_platform.foundation import SQLiteClient


def _mock_cache() -> MagicMock:
    """创建 mock 缓存."""
    cache = MagicMock()
    cache.get.return_value = None
    return cache


class TestRebalanceWriter:
    """Tests for RebalanceWriter."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """初始化测试数据."""
        self.client = sqlite_client
        self.cache = _mock_cache()

        # 创建测试标的池
        self.client.execute(
            """INSERT INTO universe
            (universe_id, name, description, universe_type)
            VALUES (?, ?, ?, ?)""",
            ["csi300", "沪深300", "沪深300成分股", "index"],
        )
        self.client.commit()

        self.writer = RebalanceWriter(self.client, self.cache)

    def test_record_rebalance(self) -> None:
        """正确记录调仓日程."""
        self.writer.record_rebalance(
            universe_id="csi300",
            rebalance_date="2025-06-20",
            description="半年度调仓",
        )

        rows = self.client.fetchall(
            "SELECT * FROM universe_rebalance WHERE universe_id = ?",
            ["csi300"],
        )
        assert len(rows) == 1
        assert rows[0]["rebalance_date"] == "2025-06-20"
        assert rows[0]["description"] == "半年度调仓"

    def test_record_rebalance_without_description(self) -> None:
        """不传 description 时正确记录."""
        self.writer.record_rebalance(
            universe_id="csi300",
            rebalance_date="2025-12-20",
        )

        rows = self.client.fetchall(
            "SELECT * FROM universe_rebalance WHERE universe_id = ?",
            ["csi300"],
        )
        assert len(rows) == 1
        assert rows[0]["description"] is None

    def test_record_rebalance_invalidates_cache(self) -> None:
        """写入调仓日程后应失效相关缓存."""
        self.writer.record_rebalance(
            universe_id="csi300",
            rebalance_date="2025-06-20",
        )
        self.cache.invalidate_pattern.assert_called_with("universe:rebalance:*")


class TestRebalanceReader:
    """Tests for RebalanceReader."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """初始化测试数据."""
        self.client = sqlite_client
        self.cache = _mock_cache()

        # 创建测试标的池
        self.client.execute(
            """INSERT INTO universe
            (universe_id, name, description, universe_type)
            VALUES (?, ?, ?, ?)""",
            ["csi300", "沪深300", "沪深300成分股", "index"],
        )

        # 插入调仓日程
        self.client.execute(
            """INSERT INTO universe_rebalance
            (universe_id, rebalance_date, description)
            VALUES (?, ?, ?)""",
            ["csi300", "2025-06-20", "半年度调仓"],
        )
        self.client.execute(
            """INSERT INTO universe_rebalance
            (universe_id, rebalance_date, description)
            VALUES (?, ?, ?)""",
            ["csi300", "2025-12-20", "年度调仓"],
        )
        self.client.commit()

        self.reader = RebalanceReader(self.client, self.cache)

    def test_get_next_rebalance(self) -> None:
        """获取下一次调仓日程."""
        result = self.reader.get_next_rebalance("csi300", "2025-01-01")
        assert result is not None
        assert result["rebalance_date"] == "2025-06-20"

    def test_get_next_rebalance_no_future(self) -> None:
        """没有未来调仓日程时返回 None."""
        result = self.reader.get_next_rebalance("csi300", "2026-01-01")
        assert result is None

    def test_get_next_rebalance_nonexistent_universe(self) -> None:
        """不存在的标的池返回 None."""
        result = self.reader.get_next_rebalance("nonexistent", "2025-01-01")
        assert result is None

    def test_list_rebalances(self) -> None:
        """列出所有调仓日程（按时间倒序）."""
        results = self.reader.list_rebalances("csi300")
        assert len(results) == 2
        assert results[0]["rebalance_date"] == "2025-12-20"
        assert results[1]["rebalance_date"] == "2025-06-20"

    def test_list_rebalances_empty(self) -> None:
        """没有调仓日程时返回空列表."""
        self.client.execute(
            """INSERT INTO universe
            (universe_id, name, description, universe_type)
            VALUES (?, ?, ?, ?)""",
            ["empty_uv", "空标的池", "空标的池", "custom"],
        )
        self.client.commit()

        results = self.reader.list_rebalances("empty_uv")
        assert results == []
