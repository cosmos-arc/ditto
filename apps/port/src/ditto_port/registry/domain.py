"""
Domain Store Provider - 封装所有 Store 的导入和创建.

将所有 DataHub Store 类的导入和创建逻辑封装在此 Provider 中，
避免 DataHubProvider 直接依赖具体的 Store 类。

架构分层：
    Port 层 (apps/port) → DomainServiceProvider → DataHub Store 层
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dishka import Provider, Scope, provide
from ditto_datahub.config.data_root import DataRootConfig
from ditto_datahub.runtime.freeze_manager import FreezeManager
from ditto_datahub.runtime.ingestion.ingestion_log_store import (
    IngestionLogStore,
)
from ditto_datahub.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_datahub.runtime.quality.quarantine_store import QuarantineStore
from ditto_datahub.services.fundamental.fundamental_service import (
    FundamentalService,
)

# Fundamental domain CQRS Readers and Writers
from ditto_datahub.stores.fundamental.corporate.corporate_actions_reader import (
    CorporateActionsReader,
)
from ditto_datahub.stores.fundamental.corporate.corporate_actions_writer import (
    CorporateActionsWriter,
)
from ditto_datahub.stores.fundamental.corporate.dividend_reader import (
    DividendReader,
)
from ditto_datahub.stores.fundamental.corporate.dividend_writer import (
    DividendWriter,
)
from ditto_datahub.stores.fundamental.financial.balance_sheet_reader import (
    BalanceSheetReader,
)
from ditto_datahub.stores.fundamental.financial.balance_sheet_writer import (
    BalanceSheetWriter,
)
from ditto_datahub.stores.fundamental.financial.cash_flow_reader import (
    CashFlowReader,
)
from ditto_datahub.stores.fundamental.financial.cash_flow_writer import (
    CashFlowWriter,
)
from ditto_datahub.stores.fundamental.financial.income_statement_reader import (
    IncomeStatementReader,
)
from ditto_datahub.stores.fundamental.financial.income_statement_writer import (
    IncomeStatementWriter,
)
from ditto_datahub.stores.fundamental.forecast.express_reader import (
    ExpressReader,
)
from ditto_datahub.stores.fundamental.forecast.express_writer import (
    ExpressWriter,
)
from ditto_datahub.stores.fundamental.forecast.forecast_reader import (
    ForecastReader,
)
from ditto_datahub.stores.fundamental.forecast.forecast_writer import (
    ForecastWriter,
)

# Market domain CQRS Readers and Writers
from ditto_datahub.stores.market.etf.bars import EtfBarsReader, EtfBarsWriter
from ditto_datahub.stores.market.etf.status import EtfStatusReader, EtfStatusWriter
from ditto_datahub.stores.market.stock.adj import (
    StockAdjFactorReader,
    StockAdjFactorWriter,
)
from ditto_datahub.stores.market.stock.bars import StockBarsReader, StockBarsWriter
from ditto_datahub.stores.market.stock.status import (
    StockStatusReader,
    StockStatusWriter,
)

# Metadata domain CQRS Readers and Writers
from ditto_datahub.stores.metadata.calendar import CalendarReader, CalendarWriter
from ditto_datahub.stores.metadata.industry import (
    IndustryMappingReader,
    IndustryMappingWriter,
    IndustryReader,
    IndustryWriter,
)
from ditto_datahub.stores.metadata.instrument import (
    InstrumentReader,
    InstrumentWriter,
)
from ditto_datahub.stores.metadata.universe import UniverseReader, UniverseWriter
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool

__all__ = ["DomainServiceProvider"]


class DomainServiceProvider(Provider):
    """
    Domain Store Provider - 封装所有 Store 的创建.

    职责：
    - 导入所有 DataHub Store 类（封装在此文件中）
    - 提供 Store 实例的创建方法
    - 通过 dishka 容器管理依赖注入
    """

    scope = Scope.APP

    # ========================================================================
    # Runtime Layer
    # ========================================================================

    @provide
    def sqlite_client(self, sqlite_pool: SQLitePool) -> SQLiteClient:
        """SQLite 客户端（基于全局连接池）."""
        return SQLiteClient(sqlite_pool)

    @provide
    def instrument_id_allocator(self, sqlite_pool: SQLitePool) -> InstrumentIdAllocator:
        """Instrument ID 分配器."""
        return InstrumentIdAllocator(sqlite_pool)

    @provide
    def freeze_manager(self, data_root: Path) -> FreezeManager:
        """数据版本管理."""
        return FreezeManager(data_root=str(data_root))

    # ========================================================================
    # Metadata Domain Stores
    # ========================================================================

    @provide
    def instrument_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> InstrumentReader:
        """证券数据读取器."""
        return InstrumentReader(sqlite_client)

    @provide
    def calendar_reader(self, sqlite_client: SQLiteClient) -> CalendarReader:
        """交易日历读取器."""
        return CalendarReader(sqlite_client)

    @provide
    def calendar_writer(
        self,
        sqlite_client: SQLiteClient,
        data_cache: Any,
        calendar_reader: CalendarReader,
    ) -> CalendarWriter:
        """交易日历写入器."""
        return CalendarWriter(
            sqlite_client=sqlite_client,
            data_cache=data_cache,
            reader=calendar_reader,
        )

    @provide
    def instrument_writer(
        self,
        sqlite_client: SQLiteClient,
        data_cache: Any,
    ) -> InstrumentWriter:
        """证券主数据写入器."""
        return InstrumentWriter(client=sqlite_client, cache=data_cache)

    @provide
    def industry_reader(
        self,
        sqlite_client: SQLiteClient,
        data_cache: Any,
    ) -> IndustryReader:
        """行业主数据读取器."""
        return IndustryReader(client=sqlite_client, cache=data_cache)

    @provide
    def industry_writer(
        self,
        sqlite_client: SQLiteClient,
        data_cache: Any,
    ) -> IndustryWriter:
        """行业主数据写入器."""
        return IndustryWriter(client=sqlite_client, cache=data_cache)

    @provide
    def industry_mapping_reader(
        self,
        sqlite_client: SQLiteClient,
        data_cache: Any,
    ) -> IndustryMappingReader:
        """行业映射读取器."""
        return IndustryMappingReader(client=sqlite_client, cache=data_cache)

    @provide
    def industry_mapping_writer(
        self,
        sqlite_client: SQLiteClient,
        data_cache: Any,
    ) -> IndustryMappingWriter:
        """行业映射写入器."""
        return IndustryMappingWriter(client=sqlite_client, cache=data_cache)

    @provide
    def universe_reader(
        self,
        sqlite_client: SQLiteClient,
        data_cache: Any,
    ) -> UniverseReader:
        """标的池读取器."""
        return UniverseReader(client=sqlite_client, cache=data_cache)

    @provide
    def universe_writer(
        self,
        sqlite_client: SQLiteClient,
        data_cache: Any,
    ) -> UniverseWriter:
        """标的池写入器."""
        return UniverseWriter(client=sqlite_client, cache=data_cache)

    @provide
    def ingestion_log_store(self, sqlite_client: SQLiteClient) -> IngestionLogStore:
        """摄取日志存储."""
        return IngestionLogStore(sqlite_client)

    @provide
    def quarantine_store(self, sqlite_client: SQLiteClient) -> QuarantineStore:
        """隔离区存储（使用主数据库）."""
        return QuarantineStore(sqlite_client)

    # ========================================================================
    # Market Domain Stores
    # ========================================================================

    # ========================================================================
    # Market Domain CQRS Readers and Writers
    # ========================================================================

    @provide
    def stock_bars_reader(self, config: DataRootConfig) -> StockBarsReader:
        """股票 K线读取器."""
        return StockBarsReader(config.data_root)

    @provide
    def stock_bars_writer(self, config: DataRootConfig) -> StockBarsWriter:
        """股票 K线写入器."""
        return StockBarsWriter(config.data_root)

    @provide
    def stock_status_reader(self, config: DataRootConfig) -> StockStatusReader:
        """股票状态读取器."""
        return StockStatusReader(config.data_root)

    @provide
    def stock_status_writer(self, config: DataRootConfig) -> StockStatusWriter:
        """股票状态写入器."""
        return StockStatusWriter(config.data_root)

    @provide
    def stock_adj_reader(self, config: DataRootConfig) -> StockAdjFactorReader:
        """股票复权因子读取器."""
        return StockAdjFactorReader(config.data_root)

    @provide
    def stock_adj_writer(self, config: DataRootConfig) -> StockAdjFactorWriter:
        """股票复权因子写入器."""
        return StockAdjFactorWriter(config.data_root)

    @provide
    def etf_bars_reader(self, config: DataRootConfig) -> EtfBarsReader:
        """ETF K线读取器."""
        return EtfBarsReader(config.data_root)

    @provide
    def etf_bars_writer(self, config: DataRootConfig) -> EtfBarsWriter:
        """ETF K线写入器."""
        return EtfBarsWriter(config.data_root)

    @provide
    def etf_status_reader(self, config: DataRootConfig) -> EtfStatusReader:
        """ETF 状态读取器."""
        return EtfStatusReader(config.data_root)

    @provide
    def etf_status_writer(self, config: DataRootConfig) -> EtfStatusWriter:
        """ETF 状态写入器."""
        return EtfStatusWriter(config.data_root)

    # ========================================================================
    # Fundamental & Capital Domain Stores
    # ========================================================================

    # Fundamental domain Readers
    @provide
    def balance_sheet_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> BalanceSheetReader:
        """BalanceSheet reader."""
        return BalanceSheetReader(sqlite_client)

    @provide
    def balance_sheet_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> BalanceSheetWriter:
        """BalanceSheet writer."""
        return BalanceSheetWriter(sqlite_client)

    @provide
    def income_statement_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> IncomeStatementReader:
        """IncomeStatement reader."""
        return IncomeStatementReader(sqlite_client)

    @provide
    def income_statement_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> IncomeStatementWriter:
        """IncomeStatement writer."""
        return IncomeStatementWriter(sqlite_client)

    @provide
    def cash_flow_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> CashFlowReader:
        """CashFlow reader."""
        return CashFlowReader(sqlite_client)

    @provide
    def cash_flow_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> CashFlowWriter:
        """CashFlow writer."""
        return CashFlowWriter(sqlite_client)

    @provide
    def dividend_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> DividendReader:
        """Dividend reader."""
        return DividendReader(sqlite_client)

    @provide
    def dividend_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> DividendWriter:
        """Dividend writer."""
        return DividendWriter(sqlite_client)

    @provide
    def corporate_actions_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> CorporateActionsReader:
        """CorporateActions reader."""
        return CorporateActionsReader(sqlite_client)

    @provide
    def corporate_actions_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> CorporateActionsWriter:
        """CorporateActions writer."""
        return CorporateActionsWriter(sqlite_client)

    @provide
    def forecast_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> ForecastReader:
        """Forecast reader."""
        return ForecastReader(sqlite_client)

    @provide
    def forecast_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> ForecastWriter:
        """Forecast writer."""
        return ForecastWriter(sqlite_client)

    @provide
    def express_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> ExpressReader:
        """Express reader."""
        return ExpressReader(sqlite_client)

    @provide
    def express_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> ExpressWriter:
        """Express writer."""
        return ExpressWriter(sqlite_client)

    @provide
    def fundamental_service(  # noqa: PLR0913
        self,
        balance_sheet_reader: BalanceSheetReader,
        balance_sheet_writer: BalanceSheetWriter,
        income_statement_reader: IncomeStatementReader,
        income_statement_writer: IncomeStatementWriter,
        cash_flow_reader: CashFlowReader,
        cash_flow_writer: CashFlowWriter,
        dividend_reader: DividendReader,
        dividend_writer: DividendWriter,
        corporate_actions_reader: CorporateActionsReader,
        corporate_actions_writer: CorporateActionsWriter,
        forecast_reader: ForecastReader,
        forecast_writer: ForecastWriter,
        express_reader: ExpressReader,
        express_writer: ExpressWriter,
    ) -> FundamentalService:
        """Fundamental domain unified service."""
        return FundamentalService(
            balance_sheet_reader=balance_sheet_reader,
            balance_sheet_writer=balance_sheet_writer,
            income_statement_reader=income_statement_reader,
            income_statement_writer=income_statement_writer,
            cash_flow_reader=cash_flow_reader,
            cash_flow_writer=cash_flow_writer,
            dividend_reader=dividend_reader,
            dividend_writer=dividend_writer,
            corporate_actions_reader=corporate_actions_reader,
            corporate_actions_writer=corporate_actions_writer,
            forecast_reader=forecast_reader,
            forecast_writer=forecast_writer,
            express_reader=express_reader,
            express_writer=express_writer,
        )

    # ========================================================================
    # Macro Domain Stores
    # ========================================================================

    # ========================================================================
    # Features Domain Stores
    # ========================================================================

    # ========================================================================
    # Factors Domain Stores
    # ========================================================================
