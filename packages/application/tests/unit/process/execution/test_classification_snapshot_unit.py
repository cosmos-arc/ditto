"""分类快照闭包单元测试 — build_classification_snapshot_fn PIT 行业查询.

验证 classification_snapshot 闭包:逐标的经 facade 查询 industry_mapping,
产出 instrument_id / sector_id 截面,PIT asof 透传为 knowledge_date ISO 字符串。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import polars as pl
from ditto_application.processes.execution.classification_snapshot import (
    build_classification_snapshot_fn,
)
from ditto_kernel.identity import InstrumentId


class _StubFacade:
    """Stub ClassificationReadFacade — 记录调用,返回预设行业."""

    def __init__(self, industry_map: dict[int, dict[str, Any] | None]) -> None:
        self._industry_map = industry_map
        self.calls: list[tuple[int, str | None]] = []

    def get_stock_industry(
        self,
        instrument_id: int,
        asof: str | None = None,
    ) -> dict[str, Any] | None:
        self.calls.append((instrument_id, asof))
        return self._industry_map.get(instrument_id)


class TestBuildClassificationSnapshotFn:
    def test_empty_instrument_ids_returns_empty_schema(self) -> None:
        """空标的列表返回空 schema(instrument_id + sector_id)."""
        fn = build_classification_snapshot_fn(_StubFacade({}))
        df = fn([], date(2024, 6, 1))
        assert df.is_empty()
        assert set(df.columns) == {"instrument_id", "sector_id"}

    def test_delegates_per_instrument_with_pit_asof(self) -> None:
        """逐标的委托 facade,PIT asof 透传为 knowledge_date ISO 字符串."""
        facade = _StubFacade(
            {
                1: {"industry_id": "801010", "instrument_id": 1},
                2: {"industry_id": "801020", "instrument_id": 2},
            },
        )
        fn = build_classification_snapshot_fn(facade)
        df = fn([InstrumentId(1), InstrumentId(2)], date(2024, 6, 1))

        assert df.height == 2
        assert df["sector_id"].to_list() == ["801010", "801020"]
        assert facade.calls == [(1, "2024-06-01"), (2, "2024-06-01")]

    def test_missing_industry_returns_null_sector_id(self) -> None:
        """facade 返回 None(无行业映射)→ sector_id 为 null,不抛错."""
        facade = _StubFacade({1: {"industry_id": "801010"}})
        fn = build_classification_snapshot_fn(facade)
        df = fn([InstrumentId(1), InstrumentId(2)], date(2024, 6, 1))

        assert df.height == 2
        assert df["sector_id"].to_list() == ["801010", None]

    def test_industry_dict_none_returns_null(self) -> None:
        """industry 显式 None → sector_id null."""
        facade = _StubFacade({1: None})
        fn = build_classification_snapshot_fn(facade)
        df = fn([InstrumentId(1)], date(2024, 6, 1))
        assert df["sector_id"].to_list() == [None]

    def test_sector_id_coerced_to_str(self) -> None:
        """industry_id 非 str(如 int)时强制转 str,保证 schema 一致."""
        facade = _StubFacade({1: {"industry_id": 801010}})
        fn = build_classification_snapshot_fn(facade)
        df = fn([InstrumentId(1)], date(2024, 6, 1))
        assert df["sector_id"].to_list() == ["801010"]
        assert df.schema["sector_id"] == pl.Utf8

    def test_deterministic(self) -> None:
        """相同输入两次调用产出相等 DataFrame."""
        facade = _StubFacade(
            {1: {"industry_id": "801010"}, 2: {"industry_id": "801020"}},
        )
        fn = build_classification_snapshot_fn(facade)
        df1 = fn([InstrumentId(1), InstrumentId(2)], date(2024, 6, 1))
        df2 = fn([InstrumentId(1), InstrumentId(2)], date(2024, 6, 1))
        assert df1.equals(df2)
