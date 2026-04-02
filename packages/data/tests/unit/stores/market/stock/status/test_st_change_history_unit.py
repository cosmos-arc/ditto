"""Tests for StChangeHistoryWriter and StChangeHistoryReader (P1-D)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_data.stores.market.stock.status.st_change_history_reader import (
    StChangeHistoryReader,
)
from ditto_data.stores.market.stock.status.st_change_history_writer import (
    StChangeHistoryWriter,
)
from ditto_data.stores.sqlite_client import SQLiteClient


def _mock_cache() -> MagicMock:
    """创建 mock 缓存."""
    cache = MagicMock()
    cache.get.return_value = None
    return cache


class TestStChangeHistoryWriter:
    """Tests for StChangeHistoryWriter."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """初始化测试数据."""
        self.client = sqlite_client
        self.cache = _mock_cache()

        # 插入测试证券（满足外键约束）
        self.client.execute(
            """INSERT INTO instrument
            (instrument_id, ticker, name, exchange, asset_class)
            VALUES (?, ?, ?, ?, ?)""",
            [1000001, "000001", "测试证券", "SZSE", "stock"],
        )
        self.client.commit()

        self.writer = StChangeHistoryWriter(self.client, self.cache)

    def test_record_st_change(self) -> None:
        """正确记录 ST 状态变更."""
        self.writer.record_st_change(
            instrument_id=1000001,
            prev_is_st=False,
            curr_is_st=True,
            st_type="ST",
            trade_date="2024-01-15",
        )

        rows = self.client.fetchall(
            "SELECT * FROM st_change_history WHERE instrument_id = ?",
            [1000001],
        )
        assert len(rows) == 1
        assert rows[0]["instrument_id"] == 1000001
        assert rows[0]["effective_from"] == "2024-01-15"
        assert rows[0]["is_st"] == 1
        assert rows[0]["st_type"] == "ST"
        assert rows[0]["effective_to"] is None

    def test_record_st_change_no_change(self) -> None:
        """is_st 状态未变化时不写入记录."""
        self.writer.record_st_change(
            instrument_id=1000001,
            prev_is_st=False,
            curr_is_st=False,
            st_type=None,
            trade_date="2024-01-15",
        )

        rows = self.client.fetchall(
            "SELECT * FROM st_change_history WHERE instrument_id = ?",
            [1000001],
        )
        assert len(rows) == 0

    def test_record_st_change_closes_previous(self) -> None:
        """新的 ST 变更应关闭前一条记录的 effective_to."""
        # 第一次变更：正常 -> ST
        self.writer.record_st_change(
            instrument_id=1000001,
            prev_is_st=False,
            curr_is_st=True,
            st_type="ST",
            trade_date="2024-01-15",
        )

        # 第二次变更：ST -> 正常（撤销 ST）
        self.writer.record_st_change(
            instrument_id=1000001,
            prev_is_st=True,
            curr_is_st=False,
            st_type=None,
            trade_date="2024-06-01",
        )

        rows = self.client.fetchall(
            "SELECT * FROM st_change_history WHERE instrument_id = ?"
            " ORDER BY effective_from",
            [1000001],
        )
        assert len(rows) == 2
        # 第一条记录应被关闭
        assert rows[0]["effective_from"] == "2024-01-15"
        assert rows[0]["is_st"] == 1
        assert rows[0]["st_type"] == "ST"
        assert rows[0]["effective_to"] == "2024-06-01"
        # 第二条记录应为当前有效
        assert rows[1]["effective_from"] == "2024-06-01"
        assert rows[1]["is_st"] == 0
        assert rows[1]["st_type"] is None
        assert rows[1]["effective_to"] is None

    def test_record_st_change_closes_previous_st_to_st_star(self) -> None:
        """ST 变更为 ST* 应关闭前一条记录并插入新记录."""
        self.writer.record_st_change(
            instrument_id=1000001,
            prev_is_st=False,
            curr_is_st=True,
            st_type="ST",
            trade_date="2024-01-15",
        )

        self.writer.record_st_change(
            instrument_id=1000001,
            prev_is_st=True,
            curr_is_st=True,
            st_type="ST*",
            trade_date="2024-03-01",
        )

        rows = self.client.fetchall(
            "SELECT * FROM st_change_history WHERE instrument_id = ?"
            " ORDER BY effective_from",
            [1000001],
        )
        assert len(rows) == 2
        assert rows[0]["st_type"] == "ST"
        assert rows[0]["effective_to"] == "2024-03-01"
        assert rows[1]["st_type"] == "ST*"
        assert rows[1]["effective_to"] is None

    def test_record_st_change_invalidates_cache(self) -> None:
        """写入 ST 变更后应失效相关缓存."""
        self.writer.record_st_change(
            instrument_id=1000001,
            prev_is_st=False,
            curr_is_st=True,
            st_type="ST",
            trade_date="2024-01-15",
        )
        self.cache.invalidate_pattern.assert_called_with("st_change_history:*")


class TestStChangeHistoryReader:
    """Tests for StChangeHistoryReader."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """初始化测试数据."""
        self.client = sqlite_client
        self.cache = _mock_cache()

        # 插入测试证券（满足外键约束）
        self.client.execute(
            """INSERT INTO instrument
            (instrument_id, ticker, name, exchange, asset_class)
            VALUES (?, ?, ?, ?, ?)""",
            [1000001, "000001", "测试证券", "SZSE", "stock"],
        )

        # 插入 ST 变更历史数据
        self.client.execute(
            """INSERT INTO st_change_history
            (instrument_id, effective_from, is_st, st_type, effective_to)
            VALUES (?, ?, ?, ?, ?)""",
            [1000001, "2024-01-15", 1, "ST", "2024-06-01"],
        )
        self.client.execute(
            """INSERT INTO st_change_history
            (instrument_id, effective_from, is_st, st_type, effective_to)
            VALUES (?, ?, ?, ?, ?)""",
            [1000001, "2024-06-01", 0, None, None],
        )
        self.client.commit()

        self.reader = StChangeHistoryReader(self.client, self.cache)

    def test_get_st_status_returns_current(self) -> None:
        """查询当前有效日期应返回最新 ST 状态."""
        result = self.reader.get_st_status(1000001, "2024-07-01")
        assert result is not None
        assert result["is_st"] is False
        assert result["st_type"] is None
        assert result["effective_from"] == "2024-06-01"

    def test_get_st_status_returns_historical_st(self) -> None:
        """查询 ST 期间的日期应返回 ST 状态."""
        result = self.reader.get_st_status(1000001, "2024-03-01")
        assert result is not None
        assert result["is_st"] is True
        assert result["st_type"] == "ST"
        assert result["effective_from"] == "2024-01-15"

    def test_get_st_status_before_first_change(self) -> None:
        """查询第一次变更之前的日期应返回 None."""
        result = self.reader.get_st_status(1000001, "2023-01-01")
        assert result is None

    def test_get_st_status_on_effective_to_boundary(self) -> None:
        """在 effective_to 边界上应不包含已关闭的记录（PIT 安全）."""
        # effective_to = 2024-06-01，查询 2024-06-01 应返回第二条记录
        result = self.reader.get_st_status(1000001, "2024-06-01")
        assert result is not None
        assert result["is_st"] is False
        assert result["effective_from"] == "2024-06-01"

    def test_get_st_status_nonexistent_instrument(self) -> None:
        """不存在的证券返回 None."""
        result = self.reader.get_st_status(9999999, "2024-07-01")
        assert result is None

    def test_get_st_status_on_effective_from_boundary(self) -> None:
        """在 effective_from 边界上应包含新记录（PIT 安全）."""
        # effective_from = 2024-01-15，查询 2024-01-15 应返回 ST 记录
        result = self.reader.get_st_status(1000001, "2024-01-15")
        assert result is not None
        assert result["is_st"] is True
        assert result["st_type"] == "ST"
        assert result["effective_from"] == "2024-01-15"
