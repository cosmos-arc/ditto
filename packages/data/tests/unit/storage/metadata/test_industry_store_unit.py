"""Tests for IndustryReader, IndustryWriter, IndustryMappingWriter (CQRS pattern)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_data.models.metadata import IndustryBasic, IndustryMapping
from ditto_data.storage.metadata.industry.industry_mapping_reader import (
    IndustryMappingReader,
)
from ditto_data.storage.metadata.industry.industry_mapping_writer import (
    IndustryMappingWriter,
)
from ditto_data.storage.metadata.industry.industry_reader import IndustryReader
from ditto_data.storage.metadata.industry.industry_writer import IndustryWriter
from ditto_platform.foundation import SQLiteClient


def _mock_cache() -> MagicMock:
    """Create a mock cache for testing."""
    cache = MagicMock()
    cache.get.return_value = None
    return cache


class TestIndustryBasicSourceField:
    """Tests for IndustryBasic source field (T07)."""

    def test_industry_basic_default_source_is_sw(self) -> None:
        """IndustryBasic source defaults to 'sw'."""
        industry = IndustryBasic(
            industry_id="801010.SI",
            industry_name="农林牧渔",
            industry_level="L1",
        )
        assert industry.source == "sw"

    def test_industry_basic_explicit_source_csrc(self) -> None:
        """IndustryBasic source can be explicitly set to 'csrc'."""
        industry = IndustryBasic(
            industry_id="M0001",
            industry_name="农、林、牧、渔业",
            industry_level="L1",
            source="csrc",
        )
        assert industry.source == "csrc"

    def test_industry_basic_source_field_in_dataclass(self) -> None:
        """IndustryBasic source field is part of frozen dataclass."""
        industry = IndustryBasic(
            industry_id="801010.SI",
            industry_name="农林牧渔",
            industry_level="L1",
            source="sw",
        )
        # frozen=True: cannot set attribute
        with pytest.raises(AttributeError):
            industry.source = "csrc"  # type: ignore[misc]


class TestIndustryWriterSource:
    """Tests for IndustryWriter with source field (T07)."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 自动注入已初始化的数据库客户端.

        schema.sql 已包含 industry_basic 表定义.
        """
        self.client = sqlite_client
        self.cache = _mock_cache()
        self.writer = IndustryWriter(self.client, self.cache)

    def test_register_sw_industry(self) -> None:
        """注册 SW 行业时 source 字段正确写入."""
        industry = IndustryBasic(
            industry_id="801010.SI",
            industry_name="农林牧渔",
            industry_level="L1",
            source="sw",
        )
        self.writer.register(industry)

        row = self.client.fetchone(
            "SELECT * FROM industry_basic WHERE industry_id = ?",
            ["801010.SI"],
        )
        assert row is not None
        assert row["source"] == "sw"

    def test_register_csrc_industry(self) -> None:
        """注册 CSRC 行业时 source 字段正确写入."""
        industry = IndustryBasic(
            industry_id="M0001",
            industry_name="农、林、牧、渔业",
            industry_level="L1",
            source="csrc",
        )
        self.writer.register(industry)

        row = self.client.fetchone(
            "SELECT * FROM industry_basic WHERE industry_id = ?",
            ["M0001"],
        )
        assert row is not None
        assert row["source"] == "csrc"


class TestIndustryReaderSource:
    """Tests for IndustryReader source filtering (T07)."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 注入已初始化的数据库客户端.

        schema.sql 已包含 industry_basic 表定义.
        """
        self.client = sqlite_client
        self.cache = _mock_cache()
        self.reader = IndustryReader(self.client, self.cache)

        # 插入测试数据
        self.client.execute(
            """INSERT INTO industry_basic
            (industry_id, industry_name, industry_level, source)
            VALUES (?, ?, ?, ?)""",
            ["801010.SI", "农林牧渔", "L1", "sw"],
        )
        self.client.execute(
            """INSERT INTO industry_basic
            (industry_id, industry_name, industry_level, source)
            VALUES (?, ?, ?, ?)""",
            ["M0001", "农、林、牧、渔业", "L1", "csrc"],
        )
        self.client.execute(
            """INSERT INTO industry_basic
            (industry_id, industry_name, industry_level, source)
            VALUES (?, ?, ?, ?)""",
            ["801020.SI", "采掘", "L1", "sw"],
        )
        self.client.commit()

    def test_get_all_without_source_filter(self) -> None:
        """不传 source 时返回所有行业的分类."""
        result = self.reader.get_all()
        assert len(result) == 3

    def test_get_all_filter_by_source_sw(self) -> None:
        """按 source='sw' 过滤只返回 SW 行业的分类."""
        result = self.reader.get_all(source="sw")
        assert len(result) == 2
        sources = result["source"].to_list()
        assert all(s == "sw" for s in sources)

    def test_get_all_filter_by_source_csrc(self) -> None:
        """按 source='csrc' 过滤只返回 CSRC 行业的分类."""
        result = self.reader.get_all(source="csrc")
        assert len(result) == 1
        assert result["industry_id"][0] == "M0001"


class TestIndustryMappingWriterSource:
    """Tests for IndustryMappingWriter source parameterization (T07)."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """使用 fixture 注入已初始化的数据库客户端.

        schema.sql 已包含 industry_mapping 表定义.
        """
        self.client = sqlite_client
        self.cache = _mock_cache()
        self.writer = IndustryMappingWriter(self.client, self.cache)

        # 插入测试用证券数据（满足 instrument 外键约束）
        self.client.execute(
            """INSERT INTO instrument
            (instrument_id, ticker, name, exchange, asset_class, list_date)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [1000001, "000001", "测试证券", "SZSE", "stock", "2020-01-01"],
        )

        # 插入测试用行业数据（满足 industry_basic 外键约束）
        self.client.execute(
            """INSERT INTO industry_basic
            (industry_id, industry_name, industry_level, source)
            VALUES (?, ?, ?, ?)""",
            ["801010.SI", "农林牧渔", "L1", "sw"],
        )
        self.client.execute(
            """INSERT INTO industry_basic
            (industry_id, industry_name, industry_level, source)
            VALUES (?, ?, ?, ?)""",
            ["M0001", "农、林、牧、渔业", "L1", "csrc"],
        )
        self.client.commit()

    def test_update_mapping_with_sw_source(self) -> None:
        """SW 行业映射正确写入 source='sw'."""
        mapping = IndustryMapping(
            instrument_id=1000001,
            industry_id="801010.SI",
            source="sw",
            effective_from="2024-01-01",
            entry_reason="new",
        )
        self.writer.update_mapping(mapping)

        rows = self.client.fetchall(
            "SELECT * FROM industry_mapping WHERE instrument_id = ?",
            [1000001],
        )
        assert len(rows) == 1
        assert rows[0]["source"] == "sw"

    def test_update_mapping_with_csrc_source(self) -> None:
        """CSRC 行业映射正确写入 source='csrc'."""
        mapping = IndustryMapping(
            instrument_id=1000001,
            industry_id="M0001",
            source="csrc",
            effective_from="2024-01-01",
            entry_reason="new",
        )
        self.writer.update_mapping(mapping)

        rows = self.client.fetchall(
            "SELECT * FROM industry_mapping WHERE instrument_id = ?",
            [1000001],
        )
        assert len(rows) == 1
        assert rows[0]["source"] == "csrc"

    def test_update_mapping_default_source(self) -> None:
        """IndustryMapping source 默认值为 'sw'."""
        mapping = IndustryMapping(
            instrument_id=1000001,
            industry_id="801010.SI",
            effective_from="2024-01-01",
        )
        self.writer.update_mapping(mapping)

        rows = self.client.fetchall(
            "SELECT * FROM industry_mapping WHERE instrument_id = ?",
            [1000001],
        )
        assert len(rows) == 1
        assert rows[0]["source"] == "sw"


class TestIndustryMappingReaderAllLevels:
    """Tests for IndustryMappingReader.get_stock_industries_all_levels (T14)."""

    @pytest.fixture(autouse=True)
    def setup(self, sqlite_client: SQLiteClient) -> None:
        """初始化测试数据."""
        self.client = sqlite_client
        self.cache = _mock_cache()
        self.reader = IndustryMappingReader(self.client, self.cache)

        # 插入测试证券
        self.client.execute(
            """INSERT INTO instrument
            (instrument_id, ticker, name, exchange, asset_class, list_date)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [1000001, "000001", "测试证券", "SZSE", "stock", "2020-01-01"],
        )

        # 插入行业主数据（L1 -> L2 -> L3 层级结构）
        self.client.execute(
            """INSERT INTO industry_basic
            (industry_id, industry_name, industry_level, parent_id, source)
            VALUES (?, ?, ?, ?, ?)""",
            ["801010.SI", "农林牧渔", "L1", None, "sw"],
        )
        self.client.execute(
            """INSERT INTO industry_basic
            (industry_id, industry_name, industry_level, parent_id, source)
            VALUES (?, ?, ?, ?, ?)""",
            ["801011.SI", "种植业", "L2", "801010.SI", "sw"],
        )
        self.client.execute(
            """INSERT INTO industry_basic
            (industry_id, industry_name, industry_level, parent_id, source)
            VALUES (?, ?, ?, ?, ?)""",
            ["801012.SI", "粮食种植", "L3", "801011.SI", "sw"],
        )

        # 插入历史行业主数据（用于 PIT 测试，先于映射插入以满足 FK）
        self.client.execute(
            """INSERT INTO industry_basic
            (industry_id, industry_name, industry_level, parent_id, source)
            VALUES (?, ?, ?, ?, ?)""",
            ["801020.SI", "采掘", "L1", None, "sw"],
        )

        # 插入行业映射（当前有效）
        self.client.execute(
            """INSERT INTO industry_mapping
            (instrument_id, industry_id, source, effective_from, entry_reason)
            VALUES (?, ?, ?, ?, ?)""",
            [1000001, "801010.SI", "sw", "2024-01-01", "new"],
        )
        self.client.execute(
            """INSERT INTO industry_mapping
            (instrument_id, industry_id, source, effective_from, entry_reason)
            VALUES (?, ?, ?, ?, ?)""",
            [1000001, "801011.SI", "sw", "2024-01-01", "new"],
        )
        self.client.execute(
            """INSERT INTO industry_mapping
            (instrument_id, industry_id, source, effective_from, entry_reason)
            VALUES (?, ?, ?, ?, ?)""",
            [1000001, "801012.SI", "sw", "2024-01-01", "new"],
        )

        # 插入历史映射（用于 PIT 测试）
        self.client.execute(
            """INSERT INTO industry_mapping
            (instrument_id, industry_id, source, effective_from,
             effective_to, entry_reason)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [1000001, "801020.SI", "sw", "2020-01-01", "2024-01-01", "changed"],
        )
        self.client.commit()

    def test_get_all_levels_current(self) -> None:
        """当前状态下获取所有级别的行业分类."""
        results = self.reader.get_stock_industries_all_levels(
            instrument_id=1000001,
        )
        assert len(results) == 3
        levels = [r["industry_level"] for r in results]
        assert levels == ["L1", "L2", "L3"]

    def test_get_all_levels_pit_historical(self) -> None:
        """PIT 查询返回历史行业分类."""
        results = self.reader.get_stock_industries_all_levels(
            instrument_id=1000001,
            asof="2022-06-01",
        )
        # 应该只返回历史映射（801020.SI, L1）
        assert len(results) == 1
        assert results[0]["industry_id"] == "801020.SI"
        assert results[0]["industry_level"] == "L1"
        assert results[0]["industry_name"] == "采掘"

    def test_get_all_levels_pit_returns_newer(self) -> None:
        """PIT 查询在变更后返回新分类."""
        results = self.reader.get_stock_industries_all_levels(
            instrument_id=1000001,
            asof="2025-01-01",
        )
        # 应该返回当前有效的三个行业
        assert len(results) == 3
        levels = [r["industry_level"] for r in results]
        assert levels == ["L1", "L2", "L3"]

    def test_get_all_levels_nonexistent_instrument(self) -> None:
        """不存在的证券返回空列表."""
        results = self.reader.get_stock_industries_all_levels(
            instrument_id=9999999,
        )
        assert results == []

    def test_get_all_levels_with_source_filter(self) -> None:
        """按 source 过滤行业分类."""
        # 插入 CSRC 行业
        self.client.execute(
            """INSERT INTO industry_basic
            (industry_id, industry_name, industry_level, source)
            VALUES (?, ?, ?, ?)""",
            ["M0001", "农、林、牧、渔业", "L1", "csrc"],
        )
        self.client.execute(
            """INSERT INTO industry_mapping
            (instrument_id, industry_id, source, effective_from, entry_reason)
            VALUES (?, ?, ?, ?, ?)""",
            [1000001, "M0001", "csrc", "2024-01-01", "new"],
        )
        self.client.commit()

        results_sw = self.reader.get_stock_industries_all_levels(
            instrument_id=1000001,
            source="sw",
        )
        results_csrc = self.reader.get_stock_industries_all_levels(
            instrument_id=1000001,
            source="csrc",
        )
        assert len(results_sw) == 3
        assert len(results_csrc) == 1
        assert results_csrc[0]["industry_id"] == "M0001"
