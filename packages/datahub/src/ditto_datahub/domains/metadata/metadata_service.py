"""
MetadataService - Metadata 域统一查询服务.

整合 Metadata 域所有 Store 的查询功能，提供统一的访问入口.

替代: SecuritiesAccessor + CalendarAccessor 的部分功能
"""

from __future__ import annotations

from typing import Any

import polars as pl
from ditto_foundation import logger, traced

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
from ditto_datahub.runtime.sid_allocator import SidAllocator
from ditto_datahub.stores.universe_store import UniverseStore


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
        sid_allocator: SidAllocator,
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
            sid_allocator: SID 分配器.

        """
        self._instrument_store = instrument_store
        self._identity_store = identity_store
        self._calendar_store = calendar_store
        self._industry_basic_store = industry_basic_store
        self._industry_mapping_store = industry_mapping_store
        self._universe_store = universe_store
        self._sid_allocator = sid_allocator

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
            分配的 SID.

        """
        # 分配 SID
        sid = self._sid_allocator.allocate(registration.asset_class)

        # 注册到 security_store
        registered_sid = self._instrument_store.register(sid, registration)

        logger.info(
            "Security registered via MetadataService",
            event="metadata_security_registered",
            sid=registered_sid,
            symbol=registration.symbol,
            src_code=registration.source_ticker,
        )

        return registered_sid
