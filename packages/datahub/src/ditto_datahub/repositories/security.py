"""Security Accessor for securities master data access."""

from __future__ import annotations

from typing import Any, Literal

import polars as pl
from ditto_datahub.runtime.sid_allocator import SidAllocator
from ditto_datahub.stores.security_store import SecurityRegistration, SecurityStore
from ditto_foundation import M, logger, traced
from ditto_foundation.util.checksum import ChecksumCompute


class SecuritiesAccessor:
    """
    Securities master data accessor.

    Provides domain-level interface for security data operations,
    coordinating SecurityStore and SidAllocator.
    """

    def __init__(
        self,
        security_store: SecurityStore,
        sid_allocator: SidAllocator,
    ) -> None:
        """
        Initialize SecuritiesAccessor.

        Args:
            security_store: Security store for data access.
            sid_allocator: SID allocator for new securities.

        """
        self._security_store = security_store
        self._sid_allocator = sid_allocator

    @traced("accessor.security.get")
    def get(
        self,
        sids: list[int] | None = None,
        src_codes: list[str] | None = None,
        source: str = "tushare",
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool | None = True,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """
        Query securities data.

        Args:
            sids: Filter by SIDs.
            src_codes: Filter by source codes.
            source: Data source identifier.
            asset_class: Filter by asset class.
            exchange: Filter by exchange.
            is_active: Filter by active status.
            asof: Point-in-time query date.

        Returns:
            Securities data DataFrame.

        """
        logger.debug(
            "Fetching securities",
            event="security_get_start",
            sids_count=len(sids) if sids else None,
            src_codes_count=len(src_codes) if src_codes else None,
            source=source,
            asset_class=asset_class,
        )

        result: pl.DataFrame = self._security_store.find_securities(
            sids=sids,
            src_codes=src_codes,
            source=source,
            asset_class=asset_class,
            exchange=exchange,
            is_active=is_active,
            asof=asof,
        )

        logger.debug(
            "Securities fetched",
            event="security_get_complete",
            row_count=len(result),
        )

        # Record metrics
        M.data_records.add(len(result), {"dataset": "security", "operation": "get"})

        return result

    def get_by_sid(self, sid: int) -> dict[str, Any] | None:
        """
        Get security by SID.

        Args:
            sid: Security ID.

        Returns:
            Security data dict, or None if not found.

        """
        return self._security_store.get_by_sid(sid)

    def resolve_identifier(
        self,
        identifier: str,
        source: str = "tushare",
        asof: str | None = None,
    ) -> int | None:
        """
        Resolve identifier to SID.

        Tries src_code first, then symbol.

        Args:
            identifier: Source code or symbol.
            source: Data source identifier.
            asof: Point-in-time query date.

        Returns:
            SID, or None if not found.

        """
        # Try as src_code first
        sid = self._security_store.resolve_sid(identifier, source, asof)
        if sid:
            return sid

        # Try as symbol
        sids = self._security_store.resolve_by_symbol(identifier, source)
        if sids:
            # Return first match (should be unique for active mappings)
            return sids[0]

        return None

    def resolve_identifiers_batch(
        self,
        identifiers: list[str],
        source: str = "tushare",
        asof: str | None = None,
    ) -> dict[str, int]:
        """
        Batch resolve identifiers to SIDs.

        Args:
            identifiers: List of identifiers.
            source: Data source identifier.
            asof: Point-in-time query date.

        Returns:
            Dictionary mapping identifier to SID (only for found identifiers).

        """
        return self._security_store.resolve_sids_batch(identifiers, source, asof)

    def list_all(
        self,
        asset_class: str | None = None,
        exchange: str | None = None,
        is_active: bool = True,
    ) -> list[int]:
        """
        List all security SIDs.

        Args:
            asset_class: Filter by asset class.
            exchange: Filter by exchange.
            is_active: Filter by active status.

        Returns:
            List of SIDs.

        """
        return self._security_store.list_sids(asset_class, exchange, is_active)

    def get_symbol(self, sid: int) -> str | None:
        """
        Get symbol by SID.

        Args:
            sid: Security ID.

        Returns:
            Symbol, or None if not found.

        """
        return self._security_store.get_symbol(sid)

    def get_src_code(
        self,
        sid: int,
        source: str = "tushare",
        asof: str | None = None,
    ) -> str | None:
        """
        Get source code by SID.

        Args:
            sid: Security ID.
            source: Data source identifier.
            asof: Point-in-time query date.

        Returns:
            Source code, or None if not found.

        """
        return self._security_store.get_src_code(sid, source, asof)

    @traced("accessor.security.register")
    def register(self, registration: SecurityRegistration) -> int:
        """
        Register a new security and allocate SID.

        Args:
            registration: Security registration configuration.

        Returns:
            Allocated SID.

        """
        logger.info(
            "Registering new security",
            event="security_register_start",
            symbol=registration.symbol,
            src_code=registration.src_code,
            asset_class=registration.asset_class,
        )

        # Allocate SID
        sid = self._sid_allocator.allocate(registration.asset_class)

        # Register to security store
        registered_sid = self._security_store.register(
            sid=sid, registration=registration
        )

        logger.info(
            "Security registered successfully",
            event="security_register_complete",
            sid=registered_sid,
            symbol=registration.symbol,
        )

        # Record metrics
        M.data_records.add(1, {"dataset": "security", "operation": "register"})

        return registered_sid

    def register_batch(
        self,
        df: pl.DataFrame,
        source: str,
        asset_class: str,
        src_code_col: str,
    ) -> tuple[str, str]:
        """
        Batch register securities from DataFrame.

        Skips securities that already exist (based on src_code resolution).

        Args:
            df: DataFrame with securities data. Must contain columns:
                - src_code_col: Source code column name
                - symbol: Display symbol
                - name: Security name
                - exchange: Exchange code
                - list_date: Listing date
            source: Data source identifier.
            asset_class: Asset class (stock/etf/index).
            src_code_col: Name of the source code column in df.

        Returns:
            Tuple of (file_path, checksum) for tracking purposes.

        """
        logger.info(
            "Starting batch security registration",
            event="security_batch_register_start",
            source=source,
            asset_class=asset_class,
            row_count=len(df),
        )

        registered_count = 0
        skipped_count = 0

        for row in df.to_dicts():
            src_code = row[src_code_col]

            # Check if already exists
            existing_sid = self._security_store.resolve_sid(src_code, source, None)
            if existing_sid is not None:
                skipped_count += 1
                continue

            # Register new security
            self.register(
                SecurityRegistration(
                    src_code=src_code,
                    symbol=row["symbol"],
                    name=row["name"],
                    exchange=row["exchange"],
                    asset_class=asset_class,
                    list_date=row["list_date"],
                    source=source,
                    board=row.get("board"),
                )
            )
            registered_count += 1

        # 修复：使用统一的 ChecksumCompute 计算 checksum
        # 添加 source 列以确保 checksum 包含 source 信息
        dataset_name = f"{asset_class}_basic"
        df_with_source = df.with_columns(pl.lit(source).alias("source"))
        checksum = ChecksumCompute.from_dataframe(df_with_source, dataset_name)

        # File path for tracking (not a real file for SQLite storage)
        file_path = f"security_store:{asset_class}_basic"

        logger.info(
            "Batch security registration completed",
            event="security_batch_register_complete",
            registered=registered_count,
            skipped=skipped_count,
            checksum=checksum,
        )

        # Record metrics
        M.data_records.add(
            registered_count,
            {"dataset": "security", "operation": "register_batch"},
        )

        return file_path, checksum

    def resolve_or_create_batch(
        self,
        df: pl.DataFrame,
        source: str,
        asset_class: Literal["stock", "etf"],
        src_code_col: str = "ts_code",
    ) -> dict[str, int]:
        """
        批量解析 src_code，不存在则自动创建证券。

        Args:
            df: 包含证券元数据的 DataFrame。必须包含以下列：
                - src_code_col: 源代码列名
                - symbol: 显示符号
                - name: 证券名称
                - exchange: 交易所代码
                - list_date: 上市日期
            source: 数据源标识符（如 "tushare"）
            asset_class: 资产类别（"stock" 或 "etf"）
            src_code_col: DataFrame 中源代码的列名，默认 "ts_code"

        Returns:
            {src_code: sid} 映射字典

        """
        logger.debug(
            "Resolving or creating securities in batch",
            event="security_resolve_or_create_start",
            source=source,
            asset_class=asset_class,
            row_count=len(df),
        )

        result: dict[str, int] = {}
        created_count = 0

        # 处理空 DataFrame
        if len(df) == 0:
            return result

        # 验证必需列
        required_cols = [src_code_col, "symbol", "name", "exchange", "list_date"]
        for col in required_cols:
            if col not in df.columns:
                raise KeyError(f"DataFrame 缺少必需列: {col}")

        # 批量查询已存在的证券
        src_codes = df[src_code_col].to_list()
        existing_mappings = self._security_store.resolve_sids_batch(
            src_codes, source, None
        )

        # 处理每一行
        for row in df.to_dicts():
            src_code = row[src_code_col]

            # 如果已存在，使用已有的 SID
            if src_code in existing_mappings:
                result[src_code] = existing_mappings[src_code]
                continue

            # 不存在则创建新证券
            sid = self.register(
                SecurityRegistration(
                    src_code=src_code,
                    symbol=row["symbol"],
                    name=row["name"],
                    exchange=row["exchange"],
                    asset_class=asset_class,
                    list_date=row["list_date"],
                    source=source,
                )
            )
            result[src_code] = sid
            created_count += 1

        logger.debug(
            "Batch resolve or create completed",
            event="security_resolve_or_create_complete",
            total_count=len(result),
            created_count=created_count,
        )

        # 记录指标
        M.data_records.add(
            created_count,
            {"dataset": "security", "operation": "resolve_or_create_batch"},
        )

        return result

    def enrich_dataframe_with_sid(
        self,
        df: pl.DataFrame,
        source: str,
        asset_class: Literal["stock", "etf"],
        src_code_col: str = "ts_code",
    ) -> pl.DataFrame:
        """
        为 DataFrame 添加 sid 和 source 列。

        不存在的证券会自动创建。

        Args:
            df: 输入 DataFrame，必须包含 src_code_col 指定的列
            source: 数据源标识符（如 "tushare"）
            asset_class: 资产类别（"stock" 或 "etf"）
            src_code_col: 源代码列名，默认 "ts_code"

        Returns:
            添加了 sid 和 source 列的 DataFrame

        """
        logger.debug(
            "Enriching DataFrame with SID",
            event="security_enrich_start",
            source=source,
            asset_class=asset_class,
            row_count=len(df),
        )

        # 处理空 DataFrame
        if len(df) == 0:
            return df.with_columns(
                pl.lit(None, dtype=pl.Int32).alias("sid"),
                pl.lit(source).alias("source"),
            )

        # 批量解析或创建证券
        src_code_to_sid = self.resolve_or_create_batch(
            df=df,
            source=source,
            asset_class=asset_class,
            src_code_col=src_code_col,
        )

        # 创建映射表达式
        src_codes = df[src_code_col].to_list()
        sids = [src_code_to_sid.get(code) for code in src_codes]

        # 添加列
        result = df.with_columns(
            pl.Series(sids, dtype=pl.Int32).alias("sid"),
            pl.lit(source).alias("source"),
        )

        logger.debug(
            "DataFrame enrichment completed",
            event="security_enrich_complete",
            row_count=len(result),
        )

        return result
