"""共享 K 线查询处理器 — fx/commodity 复用."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date
from typing import Any, Protocol

import polars as pl

from ditto_apps.api.errors import BadRequestError
from ditto_apps.models.common import APIResponse


class _BarFacade(Protocol):
    """InstrumentCodeQueryFacade 所需的最小接口."""

    def get_valid_codes(self) -> set[str]: ...
    def code_to_instrument_id(self, code: str) -> int: ...
    def instrument_id_to_code(self, instrument_id: int) -> str | None: ...
    def get_all_instrument_ids(self) -> list[int]: ...
    def list_bars(
        self,
        *,
        instrument_ids: list[int],
        start: str | None = None,
        end: str | None = None,
        limit: int | None = None,
    ) -> pl.DataFrame: ...


async def handle_bars_post(
    *,
    facade: _BarFacade,
    codes: list[str] | None,
    start_date: date | None,
    end_date: date | None,
    limit: int,
    alias: str,
    converter: Callable[[pl.DataFrame], list[Any]],
) -> APIResponse[list[Any]]:
    """
    共享 K 线 POST 处理器.

    Args:
        facade: InstrumentCodeQueryFacade 实例.
        codes: 用户传入的代码列表（None 表示查询全部）.
        start_date: 开始日期.
        end_date: 结束日期.
        limit: 返回数量限制.
        alias: 从 instrument_id 映射回来的列名.
        converter: DataFrame → 模型列表的转换函数.

    Returns:
        APIResponse 包含模型列表.

    """
    # 1. 校验非法代码
    valid_codes = facade.get_valid_codes()
    if codes:
        invalid = [c for c in codes if c not in valid_codes]
        if invalid:
            msg = f"Invalid codes: {invalid}. Valid codes: {sorted(valid_codes)}"
            raise BadRequestError(msg)
        instrument_ids = [facade.code_to_instrument_id(c) for c in codes]
    else:
        instrument_ids = facade.get_all_instrument_ids()

    # 2. 构建查询参数
    start_str = start_date.isoformat() if start_date else None
    end_str = end_date.isoformat() if end_date else None

    # 3. 查询数据（线程池执行，避免阻塞事件循环）
    df = await asyncio.to_thread(
        facade.list_bars,
        instrument_ids=instrument_ids,
        start=start_str,
        end=end_str,
        limit=limit,
    )

    # 4. 空数据直接返回
    if df.is_empty():
        return APIResponse(data=[])

    # 5. 添加别名列（instrument_id → 代码）
    id_to_code_map = {
        iid: facade.instrument_id_to_code(iid) or ""
        for iid in df["instrument_id"].unique().to_list()
    }
    df = df.with_columns(
        pl.col("instrument_id").cast(pl.Utf8).replace(id_to_code_map).alias(alias)
    )

    # 6. 选择列 + 转换
    df = df.select(
        alias,
        pl.col("trade_date_utc"),
        "open",
        "high",
        "low",
        "close",
    )

    bars = converter(df)
    return APIResponse(data=bars)
