"""
分类快照 — 行业分类 PIT 查询,注入回测 DataFeed 的数据通道闭包.

回测路径需要个股行业分类列(sector_id)注入 market_data,供
stock_sector_rotation 模板的结构列校验与因子中性化(neutralize_by="sector_id")使用。

架构边界(对齐 fundamental_snapshot.py):
  - backtest 的 ``ProviderBackedDataFeed`` 只做数据通道(委托 Callable),
    不含 PIT 查询业务逻辑。
  - 本模块在 application processes 层,封装经 ``ClassificationReadFacade`` 的 PIT 查询。
  - 返回的 ``ClassificationSnapshotFn`` 闭包被注入 ProviderBackedDataFeed。

``ClassificationReadFacade`` 由 ``InstrumentService`` 满足(其 ``get_stock_industry``
委托 ``IndustryMappingReader`` 做 PIT 查询),由 apps composition root 注入。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date
from typing import Any, Protocol

import polars as pl
from ditto_kernel.identity import InstrumentId

__all__ = [
    "ClassificationReadFacade",
    "ClassificationSnapshotFn",
    "build_classification_snapshot_fn",
]

# 与 ditto_backtest.data_feed.ClassificationSnapshotFn 同型(结构相等)。
# 不跨层 import 以避免 application processes 反向依赖 backtest 类型别名。
ClassificationSnapshotFn = Callable[[Sequence[InstrumentId], date], pl.DataFrame]

# 快照 schema:instrument_id + 行业分类代码(sector_id)。
_EMPTY_SCHEMA: dict[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,
    "sector_id": pl.Utf8,
}

_SCHEMA_OVERRIDES: dict[str, type[pl.DataType]] = {
    "instrument_id": pl.Int64,
    "sector_id": pl.Utf8,
}


class ClassificationReadFacade(Protocol):
    """
    回测路径所需的行业分类读取能力(InstrumentService 满足此 Protocol).

    定义在 application processes 层,使 builders(service_factory)能依赖此 Protocol
    而不直接依赖 data 层 InstrumentService(解耦,规避 builders→storage 直连)。
    """

    def get_stock_industry(
        self,
        instrument_id: int,
        asof: str | None = None,
    ) -> dict[str, Any] | None:
        """
        查询个股行业分类(PIT,asof=ISO date 字符串,None=当前).

        返回 industry_mapping 行(含 industry_id 等);不存在返回 None。
        """
        ...


def build_classification_snapshot_fn(
    facade: ClassificationReadFacade,
) -> ClassificationSnapshotFn:
    """
    构造分类快照闭包.

    Args:
        facade: 分类读取 facade(InstrumentService 满足 Protocol)。

    Returns:
        ``ClassificationSnapshotFn`` 闭包:接收 (instrument_ids, as_of_date),
        返回含 ``instrument_id / sector_id`` 列的截面 DataFrame。
        PIT as_of 由调用方传 ``knowledge_date``;缺数据返回 null sector_id。

    """

    def _snapshot(
        instrument_ids: Sequence[InstrumentId],
        as_of_date: date,
    ) -> pl.DataFrame:
        if not instrument_ids:
            return pl.DataFrame(schema=_EMPTY_SCHEMA)

        asof = as_of_date.isoformat()
        rows: list[dict[str, str | int | None]] = []
        for iid in instrument_ids:
            iid_int = int(iid)
            industry = facade.get_stock_industry(iid_int, asof=asof)
            # industry_mapping 行含 industry_id(行业分类代码,如申万 "801010")。
            # 用作 sector_id,供 stock_sector_rotation 结构列与中性化 group 使用。
            sector_id = industry.get("industry_id") if industry else None
            rows.append(
                {
                    "instrument_id": iid_int,
                    "sector_id": str(sector_id) if sector_id is not None else None,
                },
            )

        return pl.DataFrame(rows, schema_overrides=_SCHEMA_OVERRIDES)

    return _snapshot
