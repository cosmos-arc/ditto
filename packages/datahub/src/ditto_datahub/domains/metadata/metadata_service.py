"""
MetadataService - Metadata 域统一查询服务.

整合 Metadata 域所有 Store 的查询功能，提供统一的访问入口.

替代: SecuritiesAccessor + CalendarAccessor 的部分功能
"""

from __future__ import annotations

from typing import Any, Literal

import polars as pl
from ditto_foundation import logger, traced
from ditto_foundation.util.checksum import ChecksumCompute

from ditto_datahub.domains.metadata.calendar.calendar_store import CalendarStore
from ditto_datahub.domains.metadata.identity.identity_store import IdentityStore
from ditto_datahub.domains.metadata.industry.industry_basic_store import (
    IndustryBasicStore,
)
from ditto_datahub.domains.metadata.industry.industry_mapping_store import (
    IndustryMappingStore,
)
from ditto_datahub.domains.metadata.instrument import InstrumentStore
from ditto_datahub.domains.metadata.instrument.models import InstrumentRegistration
from ditto_datahub.domains.metadata.universe.universe_store import UniverseStore
from ditto_datahub.runtime.sid_allocator import InstrumentIdAllocator


class MetadataService:
    """
    Metadata 域统一查询服务.

    整合 Metadata 域所有 Store 的查询功能，提供统一的访问入口.

    替代: SecuritiesAccessor + CalendarAccessor 的部分功能
    """

    def __init__(
        self,
        instrument_store: InstrumentStore,
        identity_store: IdentityStore,
        calendar_store: CalendarStore,
        industry_basic_store: IndustryBasicStore,
        industry_mapping_store: IndustryMappingStore,
        universe_store: UniverseStore,
        instrument_id_allocator: InstrumentIdAllocator,
    ) -> None:
        """
        初始化 MetadataService.

        Args:
            instrument_store: 证券主数据存储.
            identity_store: Identity 映射存储.
            calendar_store: 交易日历存储.
            industry_basic_store: 行业主数据存储.
            industry_mapping_store: 行业映射存储.
            universe_store: 标的池存储.
            instrument_id_allocator: SID 分配器.

        """
        self._instrument_store = instrument_store
        self._identity_store = identity_store
        self._calendar_store = calendar_store
        self._industry_basic_store = industry_basic_store
        self._industry_mapping_store = industry_mapping_store
        self._universe_store = universe_store
        self._instrument_id_allocator = instrument_id_allocator

        logger.debug(
            "MetadataService initialized",
            event="metadata_query_service_init_complete",
        )

    # ============ Identity 解析 ============

    @traced("metadata.identity.resolve_sid")
    def resolve_sid(
        self,
        identifier: str,
        source: str,
        asof: str | None,
    ) -> int | None:
        """
        解析标识符到 SID.

        Args:
            identifier: 数据源代码 (src_code).
            source: 数据源标识.
            asof: 时间点日期.

        Returns:
            SID 或 None.

        """
        return self._identity_store.resolve_sid(identifier, source, asof)

    @traced("metadata.identity.resolve_sids_batch")
    def resolve_sids_batch(
        self,
        identifiers: list[str],
        source: str,
        asof: str | None,
    ) -> dict[str, int]:
        """
        批量解析标识符到 SID.

        Args:
            identifiers: 数据源代码列表.
            source: 数据源标识.
            asof: 时间点日期.

        Returns:
            {identifier: sid} 映射字典.

        """
        return self._identity_store.resolve_sids_batch(identifiers, source, asof)

    # ============ 证券查询 ============

    @traced("metadata.security.get_securities")
    def get_securities(
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
        查询证券数据.

        Args:
            sids: 过滤 SID 列表.
            src_codes: 过滤源代码列表.
            source: 数据源标识.
            asset_class: 过滤资产类别.
            exchange: 过滤交易所.
            is_active: 过滤活跃状态.
            asof: 时间点日期.

        Returns:
            证券数据 DataFrame.

        """
        return self._instrument_store.find_securities(
            sids=sids,
            src_codes=src_codes,
            source=source,
            asset_class=asset_class,
            exchange=exchange,
            is_active=is_active,
            asof=asof,
        )

    @traced("metadata.security.get_symbol")
    def get_symbol(self, sid: int) -> str | None:
        """
        根据 SID 获取交易代码.

        Args:
            sid: 证券 ID.

        Returns:
            交易代码 或 None.

        """
        return self._instrument_store.get_symbol(sid)

    @traced("metadata.security.get_src_code")
    def get_src_code(
        self,
        sid: int,
        source: str = "tushare",
        asof: str | None = None,
    ) -> str | None:
        """
        根据 SID 获取源代码.

        Args:
            sid: 证券 ID.
            source: 数据源标识.
            asof: 时间点日期.

        Returns:
            源代码 或 None.

        """
        return self._identity_store.get_src_code(sid, source, asof)

    # ============ 行业查询 ============

    @traced("metadata.industry.get_industries")
    def get_industries(
        self,
        is_active: bool = True,
        industry_level: str | None = None,
    ) -> pl.DataFrame:
        """
        查询行业数据.

        Args:
            is_active: 是否只返回活跃行业.
            industry_level: 行业级别过滤.

        Returns:
            行业数据 DataFrame.

        """
        return self._industry_basic_store.get_all(is_active, industry_level)

    @traced("metadata.industry.get_stock_industry")
    def get_stock_industry(
        self,
        sid: int,
        asof: str | None = None,
    ) -> dict[str, Any] | None:
        """
        查询股票所属行业.

        Args:
            sid: 证券 ID.
            asof: 时间点日期.

        Returns:
            行业映射信息 或 None.

        """
        return self._industry_mapping_store.get_stock_industry(sid, asof)

    @traced("metadata.industry.get_industry_stocks")
    def get_industry_stocks(
        self,
        industry_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        查询行业成分股.

        Args:
            industry_id: 行业 ID.
            asof: 时间点日期.

        Returns:
            SID 列表.

        """
        return self._industry_mapping_store.get_stocks(industry_id, asof)

    # ============ 交易日历查询 ============

    @traced("metadata.calendar.get_range_df")
    def get_range_df(
        self,
        start: str,
        end: str,
        only_open: bool = True,
    ) -> pl.DataFrame:
        """
        查询日历数据（DataFrame 格式）.

        Args:
            start: 开始日期.
            end: 结束日期.
            only_open: 是否只返回交易日.

        Returns:
            日历数据 DataFrame，包含 trade_date, is_open, prev_trade_date 等列.

        """
        return self._calendar_store.get_range_df(start, end, only_open)

    @traced("metadata.calendar.get_trading_days")
    def get_trading_days(
        self,
        start: str,
        end: str,
        only_open: bool = True,
    ) -> list[str]:
        """
        查询交易日列表.

        Args:
            start: 开始日期.
            end: 结束日期.
            only_open: 是否只返回交易日.

        Returns:
            交易日列表.

        """
        return self._calendar_store.get_range(start, end)

    @traced("metadata.calendar.is_trading_day")
    def is_trading_day(self, date: str) -> bool:
        """
        判断是否为交易日.

        Args:
            date: 日期字符串.

        Returns:
            是否为交易日.

        """
        return self._calendar_store.is_trading_day(date)

    @traced("metadata.calendar.upsert")
    def upsert(self, records: list[dict[str, Any]]) -> int:
        """
        插入或更新日历记录.

        Args:
            records: 日历记录列表.

        Returns:
            插入的记录数.

        """
        self._calendar_store.upsert(records)
        return len(records)

    @traced("metadata.calendar.get_last_trading_day")
    def get_last_trading_day(self) -> str | None:
        """
        获取最后一个交易日.

        Returns:
            最后一个交易日日期字符串，如果没有数据则返回 None.

        """
        return self._calendar_store.get_last_trading_day()

    @traced("metadata.calendar.get_first_trading_day")
    def get_first_trading_day(self) -> str | None:
        """
        获取第一个交易日.

        Returns:
            第一个交易日日期字符串，如果没有数据则返回 None.

        """
        return self._calendar_store.get_first_trading_day()

    @traced("metadata.calendar.list_trading_days")
    def list_trading_days(self, start: str, end: str) -> list[str]:
        """
        获取交易日列表（别名方法，与 get_trading_days 相同）.

        Args:
            start: 开始日期.
            end: 结束日期.

        Returns:
            交易日列表.

        """
        return self.get_trading_days(start, end, only_open=True)

    # ============ 标的池查询 ============

    @traced("metadata.universe.get_universe")
    def get_universe(
        self,
        universe_id: str,
        asof: str | None = None,
    ) -> list[int]:
        """
        查询标的池成分股.

        Args:
            universe_id: 标的池 ID.
            asof: 时间点日期.

        Returns:
            SID 列表.

        """
        return self._universe_store.get_constituents_sids(universe_id, asof)

    # ============ 证券注册 ============

    @traced("metadata.security.register_security")
    def register_security(self, registration: InstrumentRegistration) -> int:
        """
        注册新证券.

        Args:
            registration: 证券注册信息.

        Returns:
            分配的 instrument_id.

        """
        # 分配 instrument_id
        instrument_id = self._instrument_id_allocator.allocate(registration.asset_class)

        # 注册到 security_store
        registered_id = self._instrument_store.register(instrument_id, registration)

        logger.info(
            "Security registered via MetadataService",
            event="metadata_security_registered",
            instrument_id=registered_id,
            symbol=registration.symbol,
            source_ticker=registration.source_ticker,
        )

        return registered_id

    @traced("metadata.security.register_securities_batch")
    def register_securities_batch(
        self,
        df: pl.DataFrame,
        source: str,
        asset_class: Literal["stock", "etf"],
        src_code_col: str = "ts_code",
    ) -> tuple[str, str]:
        """
        批量注册证券（跳过已存在的）。

        Args:
            df: 包含证券元数据的 DataFrame。必须包含以下列：
                - src_code_col: 源代码列名
                - symbol: 显示符号
                - name: 证券名称
                - exchange: 交易所代码
                - list_date: 上市日期
            source: 数据源标识符
            asset_class: 资产类别
            src_code_col: DataFrame 中源代码的列名

        Returns:
            (file_path, checksum) 元组

        """
        logger.info(
            "Starting batch instrument registration",
            event="instrument_batch_register_start",
            source=source,
            asset_class=asset_class,
            row_count=len(df),
        )

        registered_count = 0
        skipped_count = 0

        for row in df.to_dicts():
            src_code = row[src_code_col]

            # 检查是否已存在
            existing_sid = self._instrument_store.resolve_sid(src_code, source, None)
            if existing_sid is not None:
                skipped_count += 1
                continue

            # 注册新证券
            self.register_security(
                InstrumentRegistration(
                    source_ticker=src_code,
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

        # 计算 checksum
        dataset_name = f"{asset_class}_basic"
        df_with_source = df.with_columns(pl.lit(source).alias("source"))
        checksum = ChecksumCompute.from_dataframe(df_with_source, dataset_name)

        file_path = f"instrument_store:{asset_class}_basic"

        logger.info(
            "Batch instrument registration completed",
            event="instrument_batch_register_complete",
            registered=registered_count,
            skipped=skipped_count,
            checksum=checksum,
        )

        return file_path, checksum

    @traced("metadata.security.resolve_or_create_batch")
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
            source: 数据源标识符
            asset_class: 资产类别
            src_code_col: DataFrame 中源代码的列名

        Returns:
            {src_code: sid} 映射字典

        """
        logger.debug(
            "Resolving or creating instruments in batch",
            event="instrument_resolve_or_create_start",
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
                msg = f"DataFrame 缺少必需列: {col}"
                raise KeyError(msg)

        # 批量查询已存在的证券
        src_codes = df[src_code_col].to_list()
        existing_mappings = self._instrument_store.resolve_sids_batch(
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
            sid = self.register_security(
                InstrumentRegistration(
                    source_ticker=src_code,
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

        return result
