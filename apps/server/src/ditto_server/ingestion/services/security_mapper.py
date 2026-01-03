"""
Security Mapper 服务。

本模块提供 src_code 到 sid 的映射管理功能,为新证券自动分配 SID。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import polars as pl
from ditto_datahub.stores.security_store import SecurityStore
from ditto_foundation import logger


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

    注意: 当前实现非线程安全,多进程环境下应使用单实例。
    并发场景建议在调用层协调或使用分布式锁。

    SID 分配规则:
    - stock: 1_000_000 - 1_999_999
    - etf: 2_000_000 - 2_999_999
    """

    # SID 范围配置
    STOCK_SID_START = 1_000_000
    ETF_SID_START = 2_000_000

    def __init__(
        self,
        security_store: SecurityStore,
    ) -> None:
        """
        初始化 SecurityMapper。

        Args:
            security_store: SecurityStore 实例,用于查询和注册证券。

        """
        self._store = security_store
        self._cache: dict[str, int] = {}  # {src_code: sid}
        self._stock_sid_counter = self.STOCK_SID_START
        self._etf_sid_counter = self.ETF_SID_START

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
                (
                    pl.col("symbol").alias("symbol")
                    if "symbol" in df.columns
                    else pl.lit("").alias("symbol")
                ),
                (
                    pl.col("name").alias("name")
                    if "name" in df.columns
                    else pl.lit("").alias("name")
                ),
                (
                    pl.col("exchange").alias("exchange")
                    if "exchange" in df.columns
                    else pl.lit("").alias("exchange")
                ),
                (
                    pl.col("list_date").alias("list_date")
                    if "list_date" in df.columns
                    else pl.lit("").alias("list_date")
                ),
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
        分配新的 SID。

        Args:
            asset_class: 资产类别。

        Returns:
            新分配的 SID。

        """
        if asset_class == "stock":
            sid = self._stock_sid_counter
            self._stock_sid_counter += 1
        elif asset_class == "etf":
            sid = self._etf_sid_counter
            self._etf_sid_counter += 1
        else:
            raise ValueError(f"不支持的资产类别: {asset_class}")

        return sid

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
            list_date = str(row.get("list_date", "19900101"))

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
