"""统一的 Checksum 计算工具."""

from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

import orjson
import polars as pl
import xxhash

from ditto_foundation import logger


def _json_serializable(obj: object) -> object:
    """将对象转换为 JSON 可序列化的格式."""
    if isinstance(obj, pl.DataFrame):
        return obj.to_dict(as_series=False)
    return str(obj)


class ChecksumCompute:
    """
    统一的 Checksum 计算工具。

    特性:
    - 算法统一: XXH3_128 (超快哈希，非安全场景)
    - 排序统一: 按数据集类型确定性行排序
    - 字段统一: 包含 DataFrame 的所有字段（包括 instrument_id、source）
    """

    # 数据集排序键配置
    # 键: 数据集名称
    # 值: 排序字段列表（按优先级排序）
    SORT_KEYS: ClassVar[dict[str, Sequence[str]]] = {
        # 日线数据: 按日期 + 证券ID 排序
        "stock_daily": ("trade_date", "instrument_id"),
        "etf_daily": ("trade_date", "instrument_id"),
        # 复权因子: 按日期 + 证券ID 排序
        "adj_factor": ("trade_date", "instrument_id"),
        "fund_adj": ("trade_date", "instrument_id"),
        # 日历: 按日期排序
        "calendar": ("trade_date",),
        # 基础信息: 按源代码排序
        "stock_basic": ("ts_code",),
        "etf_basic": ("ts_code",),
    }

    @staticmethod
    def from_dataframe(
        df: pl.DataFrame,
        dataset: str,
        fallback_sort_keys: Sequence[str] | None = None,
    ) -> str:
        """
        计算 DataFrame 的确定性 checksum。

        Args:
            df: 输入 DataFrame
            dataset: 数据集名称（用于确定排序键）
            fallback_sort_keys: 备用排序键（如果 dataset 不在预定义列表中）

        Returns:
            XXH3_128 hex string (32 字符)

        """
        if df.is_empty():
            # 空数据的固定 checksum
            return xxhash.xxh3_128_hexdigest(b"")

        # 1. 获取排序键
        sort_keys = ChecksumCompute.SORT_KEYS.get(dataset, fallback_sort_keys or [])

        # 2. 确定性排序（如果指定了排序键）
        if sort_keys:
            # 验证排序键存在
            missing_keys = [k for k in sort_keys if k not in df.columns]
            if missing_keys:
                logger.warning(
                    "Sort keys not found in DataFrame",
                    event="checksum_sort_keys_missing",
                    dataset=dataset,
                    missing_keys=missing_keys,
                    available_columns=df.columns,
                )
                sorted_df = df
            else:
                sorted_df = df.sort(sort_keys)
        else:
            sorted_df = df

        # 3. 转换为字典（保持顺序）
        data_dict = sorted_df.to_dict(as_series=False)

        # 4. 序列化为 JSON（orjson + OPT_SORT_KEYS 确保确定性）
        json_bytes = orjson.dumps(
            data_dict,
            option=orjson.OPT_SORT_KEYS | orjson.OPT_NON_STR_KEYS,
            default=_json_serializable,
        )

        # 5. 计算 XXH3_128 checksum
        checksum = xxhash.xxh3_128_hexdigest(json_bytes)

        logger.debug(
            "Checksum computed from DataFrame",
            event="checksum_computed",
            dataset=dataset,
            row_count=len(df),
            checksum_prefix=checksum[:8] + "...",
        )

        return checksum

    @staticmethod
    def get_sort_keys(dataset: str) -> Sequence[str]:
        """获取数据集的排序键配置."""
        return list(ChecksumCompute.SORT_KEYS.get(dataset, []))
