"""
UniverseService - 标的池子服务.

标的池查询、过滤、集合运算及调仓日程逻辑。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl
from ditto_infra.foundation import traced

from ditto_datahub.stores.capital.index_composition import IndexCompositionReader
from ditto_datahub.stores.metadata.instrument import InstrumentReader, SecurityQuery
from ditto_datahub.stores.metadata.universe import (
    UniverseReader,
    UniverseWriter,
)


class UniverseService:
    """标的池子服务."""

    def __init__(
        self,
        universe_reader: UniverseReader,
        universe_writer: UniverseWriter,
        instrument_reader: InstrumentReader,
        index_composition_reader: IndexCompositionReader,
        rebalance_reader: Any,
        rebalance_writer: Any,
    ) -> None:
        """
        初始化 UniverseService.

        Args:
            universe_reader: 标的池读取器.
            universe_writer: 标的池写入器.
            instrument_reader: 证券主数据读取器（用于上市天数过滤）.
            index_composition_reader: 指数成分股读取器.
            rebalance_reader: 标的池调仓日程读取器.
            rebalance_writer: 标的池调仓日程写入器.

        """
        self._universe_reader = universe_reader
        self._universe_writer = universe_writer
        self._instrument_reader = instrument_reader
        self._index_composition_reader = index_composition_reader
        self._rebalance_reader = rebalance_reader
        self._rebalance_writer = rebalance_writer

    # ============ 标的池查询 ============

    @traced("metadata.universe.get_universe")
    def get_universe(
        self,
        universe_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        查询标的池成分股.

        Args:
            universe_id: 标的池 ID.
            asof: 时间点日期.

        Returns:
            Instrument ID 列表.

        """
        return self._universe_reader.get_constituent_instrument_ids(universe_id, asof)

    @traced("metadata.universe.get_filtered_universe")
    def get_filtered_universe(
        self,
        universe_id: str,
        asof: str | None = None,
        volume_map: dict[int, float] | None = None,
        min_avg_volume: float | None = None,
        min_list_days: int = 0,
    ) -> list[int]:
        """
        获取过滤后的标的池成分股.

        支持两种过滤维度：
        - 流动性过滤：通过外部传入的 volume_map 进行成交量过滤
        - 上市天数过滤：排除上市时间不足 N 天的标的

        Args:
            universe_id: 标的池 ID.
            asof: 时间点日期（上市天数过滤时必需）.
            volume_map: {instrument_id: avg_volume} 外部传入的成交量数据.
            min_avg_volume: 最低平均成交量阈值.
            min_list_days: 最低上市天数（自然日），0 表示不过滤.

        Returns:
            过滤后的 instrument_id 列表.

        """
        ids = self._universe_reader.get_constituent_instrument_ids(universe_id, asof)

        # 上市天数过滤
        if min_list_days > 0:
            if asof is None:
                msg = "min_list_days > 0 时必须提供 asof 日期"
                raise ValueError(msg)
            ids = self._filter_by_list_days(ids, asof, min_list_days)

        # 流动性过滤
        if min_avg_volume is not None and volume_map is not None:
            ids = [iid for iid in ids if volume_map.get(iid, 0) >= min_avg_volume]

        return ids

    def _filter_by_list_days(
        self,
        instrument_ids: list[int],
        asof: str,
        min_list_days: int,
    ) -> list[int]:
        """
        按上市天数过滤 instrument_id 列表.

        查询各证券的 list_date，排除上市天数不足或 list_date 为 NULL 的标的。

        Args:
            instrument_ids: 待过滤的 instrument_id 列表.
            asof: 时间点日期 (YYYY-MM-DD).
            min_list_days: 最低上市天数（自然日）.

        Returns:
            过滤后的 instrument_id 列表.

        """
        if not instrument_ids:
            return []

        # 批量查询 list_date
        rows = self._instrument_reader.find_securities(
            SecurityQuery(instrument_ids=instrument_ids, is_active=None),
        ).select("instrument_id", "list_date")

        if rows.is_empty():
            return []

        asof_date = date.fromisoformat(asof)
        # 筛选：list_date 非空且 (asof_date - list_date).days >= min_list_days
        days_since_list = (asof_date - pl.col("list_date").dt.date()).dt.total_days()
        qualified = rows.filter(
            pl.col("list_date").is_not_null() & (days_since_list >= min_list_days)
        )

        return qualified["instrument_id"].to_list()

    @traced("metadata.universe.intersection")
    def universe_intersection(
        self,
        id_a: str,
        id_b: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        两个标的池的交集.

        Args:
            id_a: 标的池 A 的 ID.
            id_b: 标的池 B 的 ID.
            asof: 时间点日期.

        Returns:
            同时属于 A 和 B 的 instrument_id 列表.

        """
        set_a = set(self._universe_reader.get_constituent_instrument_ids(id_a, asof))
        set_b = set(self._universe_reader.get_constituent_instrument_ids(id_b, asof))
        return sorted(set_a & set_b)

    @traced("metadata.universe.union")
    def universe_union(
        self,
        id_a: str,
        id_b: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        两个标的池的并集.

        Args:
            id_a: 标的池 A 的 ID.
            id_b: 标的池 B 的 ID.
            asof: 时间点日期.

        Returns:
            属于 A 或 B 的 instrument_id 列表（去重、排序）.

        """
        set_a = set(self._universe_reader.get_constituent_instrument_ids(id_a, asof))
        set_b = set(self._universe_reader.get_constituent_instrument_ids(id_b, asof))
        return sorted(set_a | set_b)

    @traced("metadata.universe.subtract")
    def universe_subtract(
        self,
        id_a: str,
        id_b: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        标的池 A 减去 B 的差集.

        Args:
            id_a: 标的池 A 的 ID.
            id_b: 标的池 B 的 ID.
            asof: 时间点日期.

        Returns:
            属于 A 但不属于 B 的 instrument_id 列表（排序）.

        """
        set_a = set(self._universe_reader.get_constituent_instrument_ids(id_a, asof))
        set_b = set(self._universe_reader.get_constituent_instrument_ids(id_b, asof))
        return sorted(set_a - set_b)

    @traced("metadata.universe.sync_index_universe")
    def sync_index_universe(self, index_code: str, asof_date: date) -> int:
        """
        从指数成分数据同步到标的池.

        查询 IndexCompositionReader 获取指定指数在 asof_date 的成分股，
        原子写入到 UniverseWriter（以 index_code 作为 universe_id）。

        Args:
            index_code: 指数代码（如 "399300.XSHE"），同时作为 universe_id.
            asof_date: 时间点查询日期.

        Returns:
            同步的成分股数量，无数据时返回 0.

        """
        df = self._index_composition_reader.get(index_code, asof_date)

        if df.is_empty():
            return 0

        records = df.select("instrument_id", "effective_from").to_dicts()
        return self._universe_writer.replace_constituents(
            index_code, records, str(asof_date)
        )

    # ============ 标的池调仓日程 ============

    @traced("metadata.universe.get_next_rebalance")
    def get_next_rebalance(
        self,
        universe_id: str,
        after_date: str,
    ) -> dict[str, Any] | None:
        """
        获取标的池下一次调仓日程.

        Args:
            universe_id: 标的池 ID.
            after_date: 查询此日期之后的调仓日程.

        Returns:
            调仓日程字典或 None（未找到时）.

        """
        return self._rebalance_reader.get_next_rebalance(universe_id, after_date)

    @traced("metadata.universe.list_rebalances")
    def list_rebalances(self, universe_id: str) -> list[dict[str, Any]]:
        """
        列出标的池所有调仓日程.

        Args:
            universe_id: 标的池 ID.

        Returns:
            调仓日程列表（按 rebalance_date 倒序）.

        """
        return self._rebalance_reader.list_rebalances(universe_id)
