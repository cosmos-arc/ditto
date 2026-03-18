"""Tests for NameHistoryReader and NameHistoryWriter (T12)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_datahub.stores.metadata.instrument.name_history_reader import (
    NameHistoryReader,
)
from ditto_datahub.stores.metadata.instrument.name_history_writer import (
    NameHistoryWriter,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient


def _mock_cache() -> MagicMock:
    """创建 mock 缓存."""
    cache = MagicMock()
    cache.get.return_value = None
    return cache


class TestNameHistoryWriter:
    """Tests for NameHistoryWriter."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """初始化测试数据."""
        self.client = sqlite_client
        self.cache = _mock_cache()

        # 插入测试证券
        self.client.execute(
            """INSERT INTO instrument
            (instrument_id, ticker, name, exchange, asset_class, list_date)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [1000001, "000001", "平安银行", "SZSE", "stock", "2020-01-01"],
        )
        self.client.commit()

        self.writer = NameHistoryWriter(self.client, self.cache)

    def test_record_name_change(self) -> None:
        """正确记录名称变更."""
        self.writer.record_name_change(
            instrument_id=1000001,
            old_name="深发展A",
            new_name="平安银行",
            changed_date="2012-01-09",
        )

        rows = self.client.fetchall(
            "SELECT * FROM instrument_name_history WHERE instrument_id = ?",
            [1000001],
        )
        assert len(rows) == 1
        assert rows[0]["old_name"] == "深发展A"
        assert rows[0]["new_name"] == "平安银行"
        assert rows[0]["changed_date"] == "2012-01-09"

    def test_record_multiple_name_changes(self) -> None:
        """正确记录多次名称变更."""
        self.writer.record_name_change(
            instrument_id=1000001,
            old_name="深发展A",
            new_name="平安银行",
            changed_date="2012-01-09",
        )
        self.writer.record_name_change(
            instrument_id=1000001,
            old_name="平安银行",
            new_name="中国平安",
            changed_date="2020-06-01",
        )

        rows = self.client.fetchall(
            "SELECT * FROM instrument_name_history"
            " WHERE instrument_id = ? ORDER BY changed_date",
            [1000001],
        )
        assert len(rows) == 2

    def test_record_name_change_invalidates_cache(self) -> None:
        """写入名称变更后应失效相关缓存."""
        self.writer.record_name_change(
            instrument_id=1000001,
            old_name="深发展A",
            new_name="平安银行",
            changed_date="2012-01-09",
        )
        self.cache.invalidate_pattern.assert_called_with("instrument:name_history:*")


class TestNameHistoryReader:
    """Tests for NameHistoryReader."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """初始化测试数据."""
        self.client = sqlite_client
        self.cache = _mock_cache()

        # 插入测试证券
        self.client.execute(
            """INSERT INTO instrument
            (instrument_id, ticker, name, exchange, asset_class, list_date)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [1000001, "000001", "平安银行", "SZSE", "stock", "2020-01-01"],
        )

        # 插入名称变更历史
        self.client.execute(
            """INSERT INTO instrument_name_history
            (instrument_id, old_name, new_name, changed_date)
            VALUES (?, ?, ?, ?)""",
            [1000001, "深发展A", "平安银行", "2012-01-09"],
        )
        self.client.execute(
            """INSERT INTO instrument_name_history
            (instrument_id, old_name, new_name, changed_date)
            VALUES (?, ?, ?, ?)""",
            [1000001, "平安银行", "中国平安", "2020-06-01"],
        )
        self.client.commit()

        self.reader = NameHistoryReader(self.client, self.cache)

    def test_get_name_returns_latest_asof(self) -> None:
        """asof 日期后返回最新名称."""
        name = self.reader.get_name(1000001, "2025-01-01")
        assert name == "中国平安"

    def test_get_name_returns_historical_asof(self) -> None:
        """asof 日期在两次变更之间返回中间名称."""
        name = self.reader.get_name(1000001, "2015-01-01")
        assert name == "平安银行"

    def test_get_name_returns_none_before_first_change(self) -> None:
        """asof 日期在第一次变更之前返回 None."""
        name = self.reader.get_name(1000001, "2010-01-01")
        assert name is None

    def test_get_name_nonexistent_instrument(self) -> None:
        """不存在的证券返回 None."""
        name = self.reader.get_name(9999999, "2025-01-01")
        assert name is None

    def test_list_name_changes(self) -> None:
        """列出所有名称变更（按时间倒序）."""
        changes = self.reader.list_name_changes(1000001)
        assert len(changes) == 2
        assert changes[0]["changed_date"] == "2020-06-01"
        assert changes[1]["changed_date"] == "2012-01-09"

    def test_list_name_changes_empty(self) -> None:
        """没有变更历史时返回空列表."""
        self.client.execute(
            """INSERT INTO instrument
            (instrument_id, ticker, name, exchange, asset_class, list_date)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [1000002, "000002", "万科A", "SZSE", "stock", "2020-01-01"],
        )
        self.client.commit()

        changes = self.reader.list_name_changes(1000002)
        assert changes == []
