"""Tests for MetadataService universe & status methods (T03/T04/T08/T09)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.sources import ExchangeTransformers
from ditto_datahub.sources.tushare.transformer import TushareExchangeTransformer
from ditto_datahub.stores.metadata.universe.universe_writer import UniverseWriter


@pytest.fixture
def mock_dependencies() -> dict[str, MagicMock]:
    """创建 MetadataService 的 mock 依赖."""
    return {
        "instrument_reader": MagicMock(),
        "instrument_writer": MagicMock(),
        "name_history_reader": MagicMock(),
        "name_history_writer": MagicMock(),
        "calendar_reader": MagicMock(),
        "calendar_writer": MagicMock(),
        "industry_reader": MagicMock(),
        "industry_writer": MagicMock(),
        "industry_mapping_reader": MagicMock(),
        "industry_mapping_writer": MagicMock(),
        "universe_reader": MagicMock(),
        "universe_writer": MagicMock(),
        "rebalance_reader": MagicMock(),
        "rebalance_writer": MagicMock(),
        "instrument_id_allocator": MagicMock(),
    }


@pytest.fixture
def exchange_transformers() -> ExchangeTransformers:
    """创建 ExchangeTransformers 实例."""
    return ExchangeTransformers(
        tushare=TushareExchangeTransformer(),
        tdx=MagicMock(),
    )


@pytest.fixture
def service(
    mock_dependencies: dict[str, MagicMock],
    exchange_transformers: ExchangeTransformers,
) -> MetadataService:
    """创建 MetadataService 实例."""
    return MetadataService(
        instrument_reader=mock_dependencies["instrument_reader"],
        instrument_writer=mock_dependencies["instrument_writer"],
        name_history_reader=mock_dependencies["name_history_reader"],
        name_history_writer=mock_dependencies["name_history_writer"],
        calendar_reader=mock_dependencies["calendar_reader"],
        calendar_writer=mock_dependencies["calendar_writer"],
        industry_reader=mock_dependencies["industry_reader"],
        industry_writer=mock_dependencies["industry_writer"],
        industry_mapping_reader=mock_dependencies["industry_mapping_reader"],
        industry_mapping_writer=mock_dependencies["industry_mapping_writer"],
        universe_reader=mock_dependencies["universe_reader"],
        universe_writer=mock_dependencies["universe_writer"],
        rebalance_reader=mock_dependencies["rebalance_reader"],
        rebalance_writer=mock_dependencies["rebalance_writer"],
        instrument_id_allocator=mock_dependencies["instrument_id_allocator"],
        exchange_transformers=exchange_transformers,
    )


# ============ T03: get_stock_status ============


class TestGetStockStatus:
    """测试 get_stock_status PIT 查询."""

    def test_get_stock_status_returns_defaults_when_no_data(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """无数据时返回默认值."""
        mock_dependencies["instrument_reader"].get_by_instrument_id.return_value = None
        mock_dependencies["instrument_reader"].get_stock_extension.return_value = None

        result = service.get_stock_status(1000001, "2024-01-15")

        assert result == {
            "is_st": False,
            "list_status": "L",
            "is_suspended": False,
        }

    def test_get_stock_status_with_instrument_data(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """有 instrument 数据但无 stock 扩展数据时，从 instrument 取 is_st."""
        mock_dependencies["instrument_reader"].get_by_instrument_id.return_value = {
            "instrument_id": 1000001,
            "ticker": "000001",
            "is_st": True,
        }
        mock_dependencies["instrument_reader"].get_stock_extension.return_value = None

        result = service.get_stock_status(1000001, "2024-01-15")

        assert result["is_st"] is True
        assert result["list_status"] == "L"
        assert result["is_suspended"] is False

    def test_get_stock_status_with_full_data(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """完整数据时合并 instrument 和 instrument_stock."""
        mock_dependencies["instrument_reader"].get_by_instrument_id.return_value = {
            "instrument_id": 1000001,
            "ticker": "000001",
            "is_st": True,
        }
        mock_dependencies["instrument_reader"].get_stock_extension.return_value = {
            "instrument_id": 1000001,
            "list_status": "P",
            "industry_id": "ind_001",
        }

        result = service.get_stock_status(1000001, "2024-01-15")

        assert result["is_st"] is True
        assert result["list_status"] == "P"
        assert result["is_suspended"] is True  # P = 暂停上市


# ============ T04: find_securities min_list_days ============


class TestFindSecuritiesMinListDays:
    """测试 find_securities 的 min_list_days 过滤."""

    def test_find_securities_with_min_list_days(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """min_list_days + asof 同时提供时应透传给 reader."""
        mock_dependencies[
            "instrument_reader"
        ].find_securities.return_value = __import__("polars").DataFrame()

        service.find_securities(
            asset_class="stock",
            asof="2024-06-15",
            min_list_days=60,
        )

        mock_dependencies["instrument_reader"].find_securities.assert_called_once_with(
            instrument_ids=None,
            source_tickers=None,
            source="tushare",
            asset_class="stock",
            exchange=None,
            is_active=True,
            asof="2024-06-15",
            min_list_days=60,
        )

    def test_find_securities_min_list_days_without_asof(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """无 asof 时 min_list_days 仍然透传，但 reader 侧不应用过滤."""
        mock_dependencies[
            "instrument_reader"
        ].find_securities.return_value = __import__("polars").DataFrame()

        service.find_securities(
            asset_class="stock",
            min_list_days=60,
        )

        mock_dependencies["instrument_reader"].find_securities.assert_called_once_with(
            instrument_ids=None,
            source_tickers=None,
            source="tushare",
            asset_class="stock",
            exchange=None,
            is_active=True,
            asof=None,
            min_list_days=60,
        )

    def test_find_securities_default_no_min_list_days(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """默认不传 min_list_days."""
        mock_dependencies[
            "instrument_reader"
        ].find_securities.return_value = __import__("polars").DataFrame()

        service.find_securities(asset_class="stock")

        call_kwargs = mock_dependencies["instrument_reader"].find_securities.call_args
        assert call_kwargs.kwargs.get("min_list_days") is None


# ============ T08: get_filtered_universe ============


class TestGetFilteredUniverse:
    """测试 get_filtered_universe 流动性过滤."""

    def test_get_filtered_universe_no_filter(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """无过滤条件时直接返回成分股."""
        mock_dependencies[
            "universe_reader"
        ].get_constituent_instrument_ids.return_value = [1, 2, 3, 4, 5]

        result = service.get_filtered_universe("csi300")

        assert result == [1, 2, 3, 4, 5]
        mock_dependencies[
            "universe_reader"
        ].get_constituent_instrument_ids.assert_called_once_with("csi300", None)

    def test_get_filtered_universe_no_filter_with_asof(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """asof 有效但无流动性过滤时直接返回."""
        mock_dependencies[
            "universe_reader"
        ].get_constituent_instrument_ids.return_value = [1, 2, 3]

        result = service.get_filtered_universe("csi300", asof="2024-01-15")

        assert result == [1, 2, 3]
        mock_dependencies[
            "universe_reader"
        ].get_constituent_instrument_ids.assert_called_once_with("csi300", "2024-01-15")

    def test_get_filtered_universe_with_volume_filter(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """有 volume_map 和 min_avg_volume 时应过滤低成交量标的."""
        mock_dependencies[
            "universe_reader"
        ].get_constituent_instrument_ids.return_value = [1, 2, 3, 4, 5]

        volume_map = {1: 1000000, 2: 500000, 3: 100000, 4: 50000, 5: 10}

        result = service.get_filtered_universe(
            "csi300",
            asof="2024-01-15",
            volume_map=volume_map,
            min_avg_volume=200000,
        )

        # 只有 1 (1M) 和 2 (500K) 大于 200K
        assert result == [1, 2]

    def test_get_filtered_universe_volume_map_missing_instrument(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """volume_map 中缺少的 instrument 默认视为 0 成交量."""
        mock_dependencies[
            "universe_reader"
        ].get_constituent_instrument_ids.return_value = [1, 2, 3]

        volume_map = {1: 1000000}  # 2, 3 不在 map 中

        result = service.get_filtered_universe(
            "csi300",
            volume_map=volume_map,
            min_avg_volume=200000,
        )

        assert result == [1]

    def test_get_filtered_universe_only_volume_map_no_threshold(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """有 volume_map 但无 min_avg_volume 时不过滤."""
        mock_dependencies[
            "universe_reader"
        ].get_constituent_instrument_ids.return_value = [1, 2, 3]

        result = service.get_filtered_universe(
            "csi300",
            volume_map={1: 10, 2: 20},
        )

        assert result == [1, 2, 3]


# ============ T09: replace_constituents & set operations ============


class TestReplaceConstituents:
    """测试 UniverseWriter.replace_constituents 原子替换."""

    def test_replace_constituents_atomic(
        self,
    ) -> None:
        """replace_constituents 应原子替换所有成分股."""
        mock_client = MagicMock()
        mock_cache = MagicMock()
        writer = UniverseWriter(mock_client, mock_cache)

        records = [
            {"instrument_id": 10, "effective_from": "2024-01-15"},
            {"instrument_id": 20, "effective_from": "2024-01-15"},
        ]

        count = writer.replace_constituents("test_uv", records, "2024-01-15")

        assert count == 2

        # 应先关闭当前成分
        mock_client.execute.assert_any_call(
            """UPDATE universe_constituent
            SET effective_to = ?
            WHERE universe_id = ? AND effective_to IS NULL""",
            ["2024-01-15", "test_uv"],
        )

        # 应批量插入新成分
        mock_client.executemany.assert_called_once()
        call_args = mock_client.executemany.call_args
        assert "INSERT INTO universe_constituent" in call_args[0][0]
        assert len(call_args[0][1]) == 2

        # 只应 commit 一次（原子性）
        assert mock_client.commit.call_count == 1

        # 应失效缓存
        mock_cache.invalidate_pattern.assert_called_once_with("universe:constituents:*")

    def test_replace_constituents_empty_records(
        self,
    ) -> None:
        """空记录列表应返回 0 且不做任何操作."""
        mock_client = MagicMock()
        mock_cache = MagicMock()
        writer = UniverseWriter(mock_client, mock_cache)

        count = writer.replace_constituents("test_uv", [], "2024-01-15")

        assert count == 0
        mock_client.execute.assert_not_called()
        mock_client.executemany.assert_not_called()
        mock_client.commit.assert_not_called()


class TestUniverseSetOperations:
    """测试标的池集合运算."""

    def test_universe_intersection(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """交集应返回两个标的池共有的 instrument_id."""
        mock_deps = mock_dependencies["universe_reader"]
        mock_deps.get_constituent_instrument_ids.side_effect = lambda uid, asof: {
            "a": [1, 2, 3, 4],
            "b": [3, 4, 5, 6],
        }[uid]

        result = service.universe_intersection("a", "b")

        assert sorted(result) == [3, 4]

    def test_universe_union(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """并集应返回两个标的池所有 instrument_id（去重）."""
        mock_deps = mock_dependencies["universe_reader"]
        mock_deps.get_constituent_instrument_ids.side_effect = lambda uid, asof: {
            "a": [1, 2, 3],
            "b": [3, 4, 5],
        }[uid]

        result = service.universe_union("a", "b")

        assert sorted(result) == [1, 2, 3, 4, 5]

    def test_universe_subtract(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """差集应返回 A 中有但 B 中没有的 instrument_id."""
        mock_deps = mock_dependencies["universe_reader"]
        mock_deps.get_constituent_instrument_ids.side_effect = lambda uid, asof: {
            "a": [1, 2, 3, 4],
            "b": [3, 4, 5, 6],
        }[uid]

        result = service.universe_subtract("a", "b")

        assert sorted(result) == [1, 2]

    def test_universe_intersection_empty(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """无交集应返回空列表."""
        mock_deps = mock_dependencies["universe_reader"]
        mock_deps.get_constituent_instrument_ids.side_effect = lambda uid, asof: {
            "a": [1, 2],
            "b": [3, 4],
        }[uid]

        result = service.universe_intersection("a", "b")

        assert result == []

    def test_universe_operations_pass_asof(
        self,
        service: MetadataService,
        mock_dependencies: dict[str, MagicMock],
    ) -> None:
        """集合运算应将 asof 透传给 reader."""
        mock_deps = mock_dependencies["universe_reader"]
        mock_deps.get_constituent_instrument_ids.return_value = [1, 2, 3]

        service.universe_intersection("a", "b", asof="2024-01-15")

        assert mock_deps.get_constituent_instrument_ids.call_count == 2
        for c in mock_deps.get_constituent_instrument_ids.call_args_list:
            # Positional args: (universe_id, asof)
            assert c[0][1] == "2024-01-15"
