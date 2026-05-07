"""统一的 Checksum 计算工具."""

from __future__ import annotations

from collections.abc import Sequence

import orjson
import polars as pl
import xxhash

from ditto_platform.foundation import logger


def _json_serializable(obj: object) -> object:
    """将对象转换为 JSON 可序列化的格式."""
    if isinstance(obj, pl.DataFrame):
        return obj.to_dict(as_series=False)
    return str(obj)


class ChecksumCompute:
    """
    统一的 Checksum 计算工具（纯工具，无领域知识）.

    特性:
    - 算法统一: XXH3_128 (超快哈希，非安全场景)
    - 排序由调用方提供: 通过 sort_keys 参数控制确定性排序
    """

    @staticmethod
    def from_dataframe(
        df: pl.DataFrame,
        sort_keys: Sequence[str] = (),
    ) -> str:
        """
        计算 DataFrame 的确定性 checksum.

        Args:
            df: 输入 DataFrame
            sort_keys: 排序字段列表（用于确定性排序，为空则不排序）

        Returns:
            XXH3_128 hex string (32 字符)

        """
        if df.is_empty():
            return xxhash.xxh3_128_hexdigest(b"")

        # 确定性排序
        if sort_keys:
            missing_keys = [k for k in sort_keys if k not in df.columns]
            if missing_keys:
                logger.warning(
                    "Sort keys not found in DataFrame",
                    event="checksum_sort_keys_missing",
                    missing_keys=missing_keys,
                    available_columns=df.columns,
                )
            else:
                df = df.sort(sort_keys)

        # 转换为字典（保持顺序）
        data_dict = df.to_dict(as_series=False)

        # 序列化为 JSON（orjson + OPT_SORT_KEYS 确保确定性）
        json_bytes = orjson.dumps(
            data_dict,
            option=orjson.OPT_SORT_KEYS | orjson.OPT_NON_STR_KEYS,
            default=_json_serializable,
        )

        # 计算 XXH3_128 checksum
        checksum = xxhash.xxh3_128_hexdigest(json_bytes)

        logger.debug(
            "Checksum computed from DataFrame",
            event="checksum_computed",
            row_count=len(df),
            checksum_prefix=checksum[:8] + "...",
        )

        return checksum
