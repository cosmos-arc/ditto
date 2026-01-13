"""
Security Mapper 服务。

本模块提供 src_code 到 sid 的映射管理功能,为新证券自动分配 SID。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Literal

import polars as pl
from ditto_datahub.stores.security_store import SecurityStore
from ditto_foundation import logger

if TYPE_CHECKING:
    from ditto_datahub.runtime.sid_allocator import SidAllocator


def _optional_col(df: pl.DataFrame, col_name: str, default: str = "") -> pl.Expr:
    """
    创建可选列的表达式，如果列不存在则使用默认值。

    Args:
        df: DataFrame 对象
        col_name: 列名
        default: 默认值（默认为空字符串）

    Returns:
        Polars 表达式

    Examples:
        >>> df = pl.DataFrame({"a": [1, 2]})
        >>> _optional_col(df, "b", "N/A")
        ... # 返回一个表达式，如果列 b 不存在则使用 "N/A"

    """
    if col_name in df.columns:
        return pl.col(col_name).alias(col_name)
    return pl.lit(default).alias(col_name)


def _format_date_for_sqlite(d: date | str | None) -> str:
    """
    转换日期为 SQLite 可绑定的字符串.

    Args:
        d: 日期对象、字符串或 None

    Returns:
        可绑定的日期字符串 (YYYYMMDD 或 YYYY-MM-DD)

    Examples:
        >>> _format_date_for_sqlite(date(2024, 1, 2))
        '20240102'
        >>> _format_date_for_sqlite("2024-01-02")
        '20240102'
        >>> _format_date_for_sqlite("19900101")
        '19900101'

    """
    if d is None:
        return "19900101"
    if isinstance(d, date):
        return d.strftime("%Y%m%d")
    # 处理 "YYYY-MM-DD" 格式
    if isinstance(d, str) and "-" in d:
        return d.replace("-", "")
    return str(d)


@dataclass(frozen=True)
class SecurityRegistrationParams:
    """证券注册参数。"""

    src_code: str
    sid: int
    source: str
    asset_class: Literal["stock", "etf"]
    metadata: pl.DataFrame
    src_code_col: str = "ts_code"


class SecurityMapper:
    """
    管理 src_code → sid 映射,为新证券自动分配 SID。

    使用线程安全的 SidAllocator 进行 SID 分配，支持多进程/多线程并发场景。

    SID 分配规则:
    - stock: 1_000_000 - 1_999_999
    - etf: 2_000_000 - 2_999_999
    """

    def __init__(
        self,
        security_store: SecurityStore,
        sid_allocator: SidAllocator,
    ) -> None:
        """
        初始化 SecurityMapper。

        Args:
            security_store: SecurityStore 实例,用于查询和注册证券。
            sid_allocator: 线程安全的 SID 分配器。

        """
        self._store = security_store
        self._sid_allocator = sid_allocator
        self._cache: dict[str, int] = {}  # {src_code: sid}

    def map_or_create(
        self,
        src_codes: list[str],
        source: str,
        asset_class: Literal["stock", "etf"],
        metadata: pl.DataFrame,
        src_code_col: str = "ts_code",
    ) -> dict[str, int]:
        """
        映射 src_code 到 sid,不存在则创建并分配 SID。

        Args:
            src_codes: 源代码列表,如 ["000001.SZ", "000002.SZ"]。
            source: 数据源标识符。
            asset_class: 资产类别,可选 "stock" 或 "etf"。
            metadata: 证券元数据 DataFrame,必须包含以下列:
                - {src_code_col}: 源代码（默认 "ts_code"）
                - symbol: 显示符号
                - name: 证券名称
                - exchange: 交易所代码
                - list_date: 上市日期
            src_code_col: metadata 中源代码的字段名,默认 "ts_code"。

        Returns:
            字典,映射 src_code 到 sid。

        """
        logger.info(
            "开始映射证券代码",
            event="security_map_start",
            source=source,
            asset_class=asset_class,
            input_count=len(src_codes),
        )

        result: dict[str, int] = {}
        found_count = 0
        created_count = 0

        for src_code in src_codes:
            # 先从缓存获取
            cache_key = f"{source}:{src_code}"
            if cache_key in self._cache:
                result[src_code] = self._cache[cache_key]
                found_count += 1
                continue

            # 查询是否已存在
            existing_sid = self._store.resolve_sid(src_code, source, None)

            if existing_sid is not None:
                # 已存在,使用已有 SID
                result[src_code] = existing_sid
                self._cache[cache_key] = existing_sid
                found_count += 1
                logger.debug(
                    "找到已有证券",
                    event="security_found",
                    src_code=src_code,
                    sid=existing_sid,
                )
            else:
                # 不存在,分配新 SID
                new_sid = self._allocate_sid(asset_class)
                params = SecurityRegistrationParams(
                    src_code=src_code,
                    sid=new_sid,
                    source=source,
                    asset_class=asset_class,
                    metadata=metadata,
                    src_code_col=src_code_col,
                )
                self._register_security(params)
                result[src_code] = new_sid
                self._cache[cache_key] = new_sid
                created_count += 1
                logger.debug(
                    "创建新证券",
                    event="security_created",
                    src_code=src_code,
                    sid=new_sid,
                )

        logger.info(
            "证券映射完成",
            event="security_map_complete",
            source=source,
            asset_class=asset_class,
            total_count=len(src_codes),
            found_count=found_count,
            created_count=created_count,
        )

        return result

    def enrich_dataframe(
        self,
        df: pl.DataFrame,
        src_code_col: str = "ts_code",
        asset_class: Literal["stock", "etf"] = "stock",
        source: str = "tushare",
    ) -> pl.DataFrame:
        """
        为 DataFrame 添加 sid 和 source 列。

        Args:
            df: 输入 DataFrame。
            src_code_col: 源代码列名,默认为 "ts_code"。
            asset_class: 资产类别,默认为 "stock"。
            source: 数据源标识符,默认为 "tushare"。

        Returns:
            添加了 sid 和 source 列的 DataFrame。

        """
        if df.is_empty():
            return df.with_columns(
                pl.lit(None, dtype=pl.Int64).alias("sid"),
                pl.lit(source).alias("source"),
            )

        src_codes = df[src_code_col].unique().to_list()

        # 获取元数据 (从 DataFrame 中提取)
        metadata = df.select(
            [
                pl.col(src_code_col).alias("ts_code"),
                _optional_col(df, "symbol"),
                _optional_col(df, "name"),
                _optional_col(df, "exchange"),
                _optional_col(df, "list_date"),
            ]
        )

        # 映射或创建 SID
        sid_map = self.map_or_create(src_codes, source, asset_class, metadata)

        # 为 DataFrame 添加 sid 列
        # 使用 join 而不是 map_dict
        sid_df = pl.DataFrame(
            {
                src_code_col: list(sid_map.keys()),
                "sid": list(sid_map.values()),
            }
        )

        result = df.join(sid_df, on=src_code_col, how="left").with_columns(
            pl.lit(source).alias("source"),
        )

        return result

    def _allocate_sid(self, asset_class: Literal["stock", "etf"]) -> int:
        """
        分配新的 SID（线程安全）。

        委托给 SidAllocator 进行原子分配，确保并发安全。

        Args:
            asset_class: 资产类别。

        Returns:
            新分配的 SID。

        """
        return self._sid_allocator.allocate(asset_class)

    def _register_security(self, params: SecurityRegistrationParams) -> None:
        """
        注册新证券到 SecurityStore。

        Args:
            params: 证券注册参数。

        """
        # 检查是否已注册（防止并发竞态）
        existing = self._store.resolve_sid(params.src_code, params.source, None)
        if existing is not None:
            logger.debug(
                "证券已在并发中注册,跳过",
                event="security_already_registered",
                source=params.source,
                src_code=params.src_code,
                sid=existing,
            )
            return

        # 从 metadata 中提取该证券的信息
        security_meta = params.metadata.filter(
            pl.col(params.src_code_col) == params.src_code
        )

        if security_meta.is_empty():
            logger.warning(
                "未找到证券元数据",
                event="security_metadata_not_found",
                src_code=params.src_code,
            )
            # 使用默认值
            symbol = params.src_code
            name = params.src_code
            exchange = "UNKNOWN"
            list_date = "19900101"
        else:
            row = security_meta.row(0, named=True)
            symbol = str(row.get("symbol", params.src_code))
            name = str(row.get("name", params.src_code))
            exchange = str(row.get("exchange", "UNKNOWN"))
            list_date = _format_date_for_sqlite(row.get("list_date"))

        self._store.register(
            sid=params.sid,
            source=params.source,
            src_code=params.src_code,
            symbol=symbol,
            name=name,
            exchange=exchange,
            asset_class=params.asset_class,
            list_date=list_date,
            board=None,
        )
