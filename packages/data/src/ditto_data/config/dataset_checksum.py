"""
数据集校验和排序键配置.

提供 Dataset 名称到 DataFrame 排序键的映射，用于 ChecksumCompute 确定性校验。
"""

from __future__ import annotations

from collections.abc import Sequence

__all__ = ["dataset_sort_keys"]


def dataset_sort_keys(dataset: str) -> Sequence[str]:
    """
    获取数据集的排序键列表.

    Args:
        dataset: 数据集名称（如 "stock_daily", "calendar"）

    Returns:
        排序字段列表。未知数据集返回空列表。

    """
    return _SORT_KEYS.get(dataset, ())


_SORT_KEYS: dict[str, Sequence[str]] = {
    "stock_daily": ("trade_date", "instrument_id"),
    "etf_daily": ("trade_date", "instrument_id"),
    "global_index_daily": ("source_ticker", "trade_date", "knowledge_date"),
    "adj_factor": ("trade_date", "instrument_id"),
    "fund_adj": ("trade_date", "instrument_id"),
    "calendar": ("trade_date",),
    "stock_basic": ("ts_code",),
    "etf_basic": ("ts_code",),
    "industry_classification": (
        "source",
        "classification_version",
        "industry_id",
        "knowledge_date",
    ),
    "industry_mapping": (
        "source",
        "classification_version",
        "instrument_id",
        "industry_id",
        "industry_date",
        "knowledge_date",
    ),
}
