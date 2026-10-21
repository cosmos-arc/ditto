"""Fetch-boundary guards shared by Tushare adapters."""

from __future__ import annotations

import polars as pl

from ditto_data.sources.base import SourceFetchError

__all__ = ["assert_single_trade_date"]


def assert_single_trade_date(
    response: pl.DataFrame,
    *,
    expected: str,
    dataset: str,
    column: str = "trade_date",
) -> None:
    """
    日期车道响应守卫：非空响应每一行的交易日必须等于请求日。

    服务端会静默忽略未知的查询参数（#585 实测 suspend_d 传
    ``suspend_date`` 被忽略，按日期升序返回 1999 年起的全表第一页，
    以固定 818 只毒化了全部历史停牌标志）。守卫让这类过滤失效在
    摄取边界立即显形，而不是以假数据入库。空响应合法（#583 空观察
    语义）；守卫列缺失说明响应形态漂移，同样 fail closed。
    """
    if response.is_empty():
        return
    if column not in response.columns:
        raise SourceFetchError(
            message=(
                f"{dataset} response lacks the {column} column required by "
                "the single-date guard"
            ),
            source="tushare",
            details={"dataset": dataset, "expected_trade_date": expected},
        )
    # cast 吸收数值/预解析日期形态的列漂移；ne_missing 让 null 守卫列值
    # 计为失配（pl.col != expected 对 null 谓词返回 null 被过滤掉）。
    observed = pl.col(column).cast(pl.String)
    mismatched = response.filter(observed.ne_missing(str(expected)))
    if not mismatched.is_empty():
        foreign = sorted(
            {
                value
                for value in mismatched[column].cast(pl.String).to_list()
                if value is not None
            }
        )
        raise SourceFetchError(
            message=(
                f"{dataset} response rows fall outside the requested trade "
                f"date {expected}: date filter silently ignored or provider "
                "drift (#585)"
            ),
            source="tushare",
            details={
                "dataset": dataset,
                "expected_trade_date": str(expected),
                "foreign_trade_dates": foreign[:5],
                "foreign_row_count": mismatched.height,
            },
        )
