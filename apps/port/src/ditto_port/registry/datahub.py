"""
DataHub 组件注册。

Root 注入模式：在 Provider 中集中注册所有 DataHub 组件。
所有依赖通过 Provider 管理，DataHub 不再使用 @cached_property.

架构说明：
- DataHubProvider 负责提供所有 Store 和 Service
- Store 的创建采用依赖注入模式
- Port 层不再直接依赖 Store 类
"""

# 延迟类型注解评估，避免前向引用问题
from __future__ import annotations

from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path
from typing import Any

from dishka import Provider, Scope, provide
from ditto_datahub.config.data_root import DataRootConfig
from ditto_datahub.runtime.freeze_manager import FreezeManager
from ditto_datahub.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_datahub.runtime.sql_engine import SqlEngine
from ditto_datahub.services import IngestionLogService, QualityRecordService
from ditto_datahub.services.capital_service import CapitalService
from ditto_datahub.services.factor_service import FactorService
from ditto_datahub.services.feature_service import FeatureService
from ditto_datahub.services.fundamental_service import FundamentalService
from ditto_datahub.services.macro_service import MacroService
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.services.source_service import SourceService
from ditto_datahub.sources.source import DataSources

# Capital Stores (CQRS Reader/Writer)
from ditto_datahub.stores.capital.futures_position.futures_reader import (
    FuturesReader,
)
from ditto_datahub.stores.capital.futures_position.futures_writer import (
    FuturesWriter,
)
from ditto_datahub.stores.capital.index_composition.index_composition_reader import (
    IndexCompositionReader,
)
from ditto_datahub.stores.capital.index_composition.index_composition_writer import (
    IndexCompositionWriter,
)
from ditto_datahub.stores.capital.margin.margin_trading_reader import (
    MarginTradingReader,
)
from ditto_datahub.stores.capital.margin.margin_trading_writer import (
    MarginTradingWriter,
)
from ditto_datahub.stores.capital.pledge.pledge_ratio_reader import (
    PledgeRatioReader,
)
from ditto_datahub.stores.capital.pledge.pledge_ratio_writer import (
    PledgeRatioWriter,
)
from ditto_datahub.stores.capital.valuation.valuation_metrics_reader import (
    ValuationMetricsReader,
)
from ditto_datahub.stores.capital.valuation.valuation_metrics_writer import (
    ValuationMetricsWriter,
)

# Factors Stores (CQRS Reader/Writer)
from ditto_datahub.stores.factors.factor_metadata_reader import (
    FactorMetadataReader,
)
from ditto_datahub.stores.factors.factor_metadata_writer import (
    FactorMetadataWriter,
)
from ditto_datahub.stores.factors.factor_reader import FactorReader
from ditto_datahub.stores.factors.factor_writer import FactorWriter

# Features Stores (CQRS Reader/Writer)
from ditto_datahub.stores.features.technical.technical_indicator_metadata_reader import (  # noqa: E501
    TechnicalIndicatorMetadataReader,
)
from ditto_datahub.stores.features.technical.technical_indicator_metadata_writer import (  # noqa: E501
    TechnicalIndicatorMetadataWriter,
)
from ditto_datahub.stores.features.technical.technical_indicator_reader import (
    TechnicalIndicatorReader,
)
from ditto_datahub.stores.features.technical.technical_indicator_writer import (
    TechnicalIndicatorWriter,
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

# Macro Stores (CQRS Reader/Writer)
from ditto_datahub.stores.macro.indicator.indicator_reader import (
    IndicatorReader as MacroIndicatorReader,
)
from ditto_datahub.stores.macro.indicator.indicator_writer import (
    IndicatorWriter as MacroIndicatorWriter,
)
from ditto_datahub.stores.macro.indicator.metadata_reader import (
    IndicatorMetadataReader as MacroIndicatorMetadataReader,
)
from ditto_datahub.stores.macro.indicator.metadata_writer import (
    IndicatorMetadataWriter as MacroIndicatorMetadataWriter,
)

# Market domain CQRS Readers and Writers
from ditto_datahub.stores.market.etf.adj.adj_factor_reader import (
    EtfAdjFactorReader,
)
from ditto_datahub.stores.market.etf.adj.adj_factor_writer import (
    EtfAdjFactorWriter,
)
from ditto_datahub.stores.market.etf.bars import EtfBarsReader, EtfBarsWriter
from ditto_datahub.stores.market.etf.nav.nav_reader import EtfNavReader
from ditto_datahub.stores.market.etf.nav.nav_writer import EtfNavWriter
from ditto_datahub.stores.market.etf.status import EtfStatusReader, EtfStatusWriter
from ditto_datahub.stores.market.index.bars.bars_reader import IndexBarsReader
from ditto_datahub.stores.market.index.bars.bars_writer import IndexBarsWriter
from ditto_datahub.stores.market.index.constituent.constituent_reader import (
    IndexConstituentReader,
)
from ditto_datahub.stores.market.index.constituent.constituent_writer import (
    IndexConstituentWriter,
)
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

# Runtime domain CQRS Readers and Writers
from ditto_datahub.stores.runtime.ingestion import (
    IngestionLogReader,
    IngestionLogWriter,
)
from ditto_datahub.stores.runtime.quality import (
    ComparisonReader,
    ComparisonWriter,
    QuarantineReader,
    QuarantineWriter,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_infra.foundation import SQLitePool
from ditto_infra.foundation.cache import DataCache
from ditto_infra.foundation.concurrency import FileLockManager

__all__ = ["DataHubProvider"]


class DataHubProvider(Provider):
    """
    DataHub 组件 Provider.

    架构说明：
    - 此 Provider 负责提供所有 Store 和 Service
    - Store 依赖通过 dishka 容器自动注入
    - DataHub Facade 已被移除，Port 层不再依赖 DataHub 类
    """

    scope = Scope.APP

    @provide
    def data_root(self, config: DataRootConfig) -> Path:
        """数据根目录."""
        return config.data_root

    # ========================================================================
    # Runtime Layer
    # ========================================================================

    @provide
    def sqlite_pool(
        self,
        config: DataRootConfig,
    ) -> Iterator[SQLitePool]:
        """SQLite 连接池（应用级单例）."""
        db_path = config.metadata_db_path
        # 确保父目录存在
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # 获取 schema.sql 路径
        # 将 Traversable 转换为 Path（importlib.resources.files 返回 Traversable）
        schema_traversable = files("ditto_datahub.scripts") / "schema.sql"
        schema_path = Path(str(schema_traversable))
        pool = SQLitePool(str(db_path), schema_path=schema_path)
        pool.init_schema()
        yield pool
        pool.close()

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

    @provide
    def file_lock(self, data_root: Path) -> FileLockManager:
        """文件锁管理器."""
        lock_dir = data_root / "locks"
        return FileLockManager(lock_dir)

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
        data_cache: DataCache[Any],
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
        data_cache: DataCache[Any],
    ) -> InstrumentWriter:
        """证券主数据写入器."""
        return InstrumentWriter(client=sqlite_client, cache=data_cache)

    @provide
    def industry_reader(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> IndustryReader:
        """行业主数据读取器."""
        return IndustryReader(client=sqlite_client, cache=data_cache)

    @provide
    def industry_writer(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> IndustryWriter:
        """行业主数据写入器."""
        return IndustryWriter(client=sqlite_client, cache=data_cache)

    @provide
    def industry_mapping_reader(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> IndustryMappingReader:
        """行业映射读取器."""
        return IndustryMappingReader(client=sqlite_client, cache=data_cache)

    @provide
    def industry_mapping_writer(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> IndustryMappingWriter:
        """行业映射写入器."""
        return IndustryMappingWriter(client=sqlite_client, cache=data_cache)

    @provide
    def universe_reader(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> UniverseReader:
        """标的池读取器."""
        return UniverseReader(client=sqlite_client, cache=data_cache)

    @provide
    def universe_writer(
        self,
        sqlite_client: SQLiteClient,
        data_cache: DataCache[Any],
    ) -> UniverseWriter:
        """标的池写入器."""
        return UniverseWriter(client=sqlite_client, cache=data_cache)

    # ========================================================================
    # Runtime Domain CQRS Readers and Writers
    # ========================================================================

    @provide
    def ingestion_log_reader(self, sqlite_client: SQLiteClient) -> IngestionLogReader:
        """摄取日志读取器."""
        return IngestionLogReader(sqlite_client)

    @provide
    def ingestion_log_writer(self, sqlite_client: SQLiteClient) -> IngestionLogWriter:
        """摄取日志写入器."""
        return IngestionLogWriter(sqlite_client)

    @provide
    def comparison_reader(self, config: DataRootConfig) -> ComparisonReader:
        """质量对比数据读取器."""
        return ComparisonReader(base_path=config.data_root)

    @provide
    def comparison_writer(self, config: DataRootConfig) -> ComparisonWriter:
        """质量对比数据写入器."""
        return ComparisonWriter(base_path=config.data_root)

    @provide
    def quarantine_reader(self, sqlite_client: SQLiteClient) -> QuarantineReader:
        """隔离区数据读取器."""
        return QuarantineReader(sqlite_client)

    @provide
    def quarantine_writer(self, sqlite_client: SQLiteClient) -> QuarantineWriter:
        """隔离区数据写入器."""
        return QuarantineWriter(sqlite_client)

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

    @provide
    def etf_nav_reader(self, data_root: Path) -> EtfNavReader:
        """ETF NAV 数据读取器."""
        return EtfNavReader(data_root=data_root / "market" / "etf" / "nav")

    @provide
    def etf_nav_writer(self, data_root: Path) -> EtfNavWriter:
        """ETF NAV 数据写入器."""
        return EtfNavWriter(data_root=data_root / "market" / "etf" / "nav")

    @provide
    def etf_adj_factor_reader(self, data_root: Path) -> EtfAdjFactorReader:
        """ETF 复权因子读取器."""
        return EtfAdjFactorReader(data_root=data_root / "market" / "etf" / "adj")

    @provide
    def etf_adj_factor_writer(self, data_root: Path) -> EtfAdjFactorWriter:
        """ETF 复权因子写入器."""
        return EtfAdjFactorWriter(data_root=data_root / "market" / "etf" / "adj")

    @provide
    def index_bars_reader(self, data_root: Path) -> IndexBarsReader:
        """指数 K线读取器."""
        return IndexBarsReader(data_root=data_root / "market" / "index" / "bars")

    @provide
    def index_bars_writer(self, data_root: Path) -> IndexBarsWriter:
        """指数 K线写入器."""
        return IndexBarsWriter(data_root=data_root / "market" / "index" / "bars")

    @provide
    def index_constituent_reader(self, data_root: Path) -> IndexConstituentReader:
        """指数成分股读取器."""
        return IndexConstituentReader(data_root=data_root)

    @provide
    def index_constituent_writer(self, data_root: Path) -> IndexConstituentWriter:
        """指数成分股写入器."""
        return IndexConstituentWriter(data_root=data_root)

    # ========================================================================
    # Fundamental Domain CQRS Readers and Writers
    # ========================================================================

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

    # ========================================================================
    # Capital Domain CQRS Readers and Writers
    # ========================================================================

    @provide
    def margin_trading_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> MarginTradingReader:
        """MarginTrading reader."""
        return MarginTradingReader(client=sqlite_client)

    @provide
    def margin_trading_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> MarginTradingWriter:
        """MarginTrading writer."""
        return MarginTradingWriter(client=sqlite_client)

    @provide
    def pledge_ratio_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> PledgeRatioReader:
        """PledgeRatio reader."""
        return PledgeRatioReader(client=sqlite_client)

    @provide
    def pledge_ratio_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> PledgeRatioWriter:
        """PledgeRatio writer."""
        return PledgeRatioWriter(client=sqlite_client)

    @provide
    def valuation_metrics_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> ValuationMetricsReader:
        """ValuationMetrics reader."""
        return ValuationMetricsReader(client=sqlite_client)

    @provide
    def valuation_metrics_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> ValuationMetricsWriter:
        """ValuationMetrics writer."""
        return ValuationMetricsWriter(client=sqlite_client)

    @provide
    def futures_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> FuturesReader:
        """Futures reader."""
        return FuturesReader(client=sqlite_client)

    @provide
    def futures_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> FuturesWriter:
        """Futures writer."""
        return FuturesWriter(client=sqlite_client)

    @provide
    def index_composition_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> IndexCompositionReader:
        """IndexComposition reader."""
        return IndexCompositionReader(client=sqlite_client)

    @provide
    def index_composition_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> IndexCompositionWriter:
        """IndexComposition writer."""
        return IndexCompositionWriter(client=sqlite_client)

    # ========================================================================
    # Macro Domain CQRS Readers and Writers
    # ========================================================================

    @provide
    def macro_indicator_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> MacroIndicatorReader:
        """Macro indicator reader."""
        return MacroIndicatorReader(client=sqlite_client)

    @provide
    def macro_indicator_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> MacroIndicatorWriter:
        """Macro indicator writer."""
        return MacroIndicatorWriter(client=sqlite_client)

    @provide
    def macro_indicator_metadata_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> MacroIndicatorMetadataReader:
        """Macro indicator metadata reader."""
        return MacroIndicatorMetadataReader(client=sqlite_client)

    @provide
    def macro_indicator_metadata_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> MacroIndicatorMetadataWriter:
        """Macro indicator metadata writer."""
        return MacroIndicatorMetadataWriter(client=sqlite_client)

    # ========================================================================
    # Features Domain CQRS Readers and Writers
    # ========================================================================

    @provide
    def technical_indicator_reader(
        self,
        data_root_config: DataRootConfig,
    ) -> TechnicalIndicatorReader:
        """TechnicalIndicator reader."""
        return TechnicalIndicatorReader(
            data_root_config.features_technical_indicators_narrow_path
        )

    @provide
    def technical_indicator_writer(
        self,
        data_root_config: DataRootConfig,
    ) -> TechnicalIndicatorWriter:
        """TechnicalIndicator writer."""
        return TechnicalIndicatorWriter(
            data_root_config.features_technical_indicators_narrow_path
        )

    @provide
    def technical_indicator_metadata_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> TechnicalIndicatorMetadataReader:
        """TechnicalIndicator metadata reader."""
        return TechnicalIndicatorMetadataReader(client=sqlite_client)

    @provide
    def technical_indicator_metadata_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> TechnicalIndicatorMetadataWriter:
        """TechnicalIndicator metadata writer."""
        return TechnicalIndicatorMetadataWriter(client=sqlite_client)

    # ========================================================================
    # Factors Domain CQRS Readers and Writers
    # ========================================================================

    @provide
    def factor_reader(
        self,
        data_root_config: DataRootConfig,
    ) -> FactorReader:
        """Factor reader."""
        return FactorReader(data_root_config.factors_narrow_path)

    @provide
    def factor_writer(
        self,
        data_root_config: DataRootConfig,
    ) -> FactorWriter:
        """Factor writer."""
        return FactorWriter(data_root_config.factors_narrow_path)

    @provide
    def factor_metadata_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> FactorMetadataReader:
        """Factor metadata reader."""
        return FactorMetadataReader(client=sqlite_client)

    @provide
    def factor_metadata_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> FactorMetadataWriter:
        """Factor metadata writer."""
        return FactorMetadataWriter(client=sqlite_client)

    # ========================================================================
    # Domain Services (依赖注入模式)
    # ========================================================================

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

    @provide
    def capital_service(  # noqa: PLR0913
        self,
        margin_trading_reader: MarginTradingReader,
        margin_trading_writer: MarginTradingWriter,
        pledge_ratio_reader: PledgeRatioReader,
        pledge_ratio_writer: PledgeRatioWriter,
        valuation_metrics_reader: ValuationMetricsReader,
        valuation_metrics_writer: ValuationMetricsWriter,
        futures_reader: FuturesReader,
        futures_writer: FuturesWriter,
        index_composition_reader: IndexCompositionReader,
        index_composition_writer: IndexCompositionWriter,
    ) -> CapitalService:
        """Capital domain unified service."""
        return CapitalService(
            margin_trading_reader=margin_trading_reader,
            margin_trading_writer=margin_trading_writer,
            pledge_ratio_reader=pledge_ratio_reader,
            pledge_ratio_writer=pledge_ratio_writer,
            valuation_metrics_reader=valuation_metrics_reader,
            valuation_metrics_writer=valuation_metrics_writer,
            futures_reader=futures_reader,
            futures_writer=futures_writer,
            index_composition_reader=index_composition_reader,
            index_composition_writer=index_composition_writer,
        )

    @provide
    def macro_service(
        self,
        indicator_reader: MacroIndicatorReader,
        indicator_writer: MacroIndicatorWriter,
        metadata_reader: MacroIndicatorMetadataReader,
        metadata_writer: MacroIndicatorMetadataWriter,
    ) -> MacroService:
        """Macro domain unified service."""
        return MacroService(
            indicator_reader=indicator_reader,
            indicator_writer=indicator_writer,
            metadata_reader=metadata_reader,
            metadata_writer=metadata_writer,
        )

    @provide
    def feature_service(
        self,
        indicator_reader: TechnicalIndicatorReader,
        indicator_writer: TechnicalIndicatorWriter,
        metadata_reader: TechnicalIndicatorMetadataReader,
        metadata_writer: TechnicalIndicatorMetadataWriter,
    ) -> FeatureService:
        """Features domain unified service."""
        return FeatureService(
            indicator_reader=indicator_reader,
            indicator_writer=indicator_writer,
            metadata_reader=metadata_reader,
            metadata_writer=metadata_writer,
        )

    @provide
    def factor_service(
        self,
        factor_reader: FactorReader,
        factor_writer: FactorWriter,
        metadata_reader: FactorMetadataReader,
        metadata_writer: FactorMetadataWriter,
    ) -> FactorService:
        """Factors domain unified service."""
        return FactorService(
            factor_reader=factor_reader,
            factor_writer=factor_writer,
            metadata_reader=metadata_reader,
            metadata_writer=metadata_writer,
        )

    @provide
    def metadata_service(  # noqa: PLR0913
        self,
        instrument_reader: InstrumentReader,
        instrument_writer: InstrumentWriter,
        calendar_reader: CalendarReader,
        calendar_writer: CalendarWriter,
        industry_reader: IndustryReader,
        industry_writer: IndustryWriter,
        industry_mapping_reader: IndustryMappingReader,
        industry_mapping_writer: IndustryMappingWriter,
        universe_reader: UniverseReader,
        universe_writer: UniverseWriter,
        instrument_id_allocator: InstrumentIdAllocator,
    ) -> MetadataService:
        """Metadata 查询服务（CQRS Reader/Writer）。"""
        return MetadataService(
            instrument_reader=instrument_reader,
            instrument_writer=instrument_writer,
            calendar_reader=calendar_reader,
            calendar_writer=calendar_writer,
            industry_reader=industry_reader,
            industry_writer=industry_writer,
            industry_mapping_reader=industry_mapping_reader,
            industry_mapping_writer=industry_mapping_writer,
            universe_reader=universe_reader,
            universe_writer=universe_writer,
            instrument_id_allocator=instrument_id_allocator,
        )

    @provide
    def market_service(  # noqa: PLR0913
        self,
        stock_bars_reader: StockBarsReader,
        stock_bars_writer: StockBarsWriter,
        stock_status_reader: StockStatusReader,
        stock_status_writer: StockStatusWriter,
        stock_adj_reader: StockAdjFactorReader,
        stock_adj_writer: StockAdjFactorWriter,
        etf_bars_reader: EtfBarsReader,
        etf_bars_writer: EtfBarsWriter,
        etf_status_reader: EtfStatusReader,
        etf_status_writer: EtfStatusWriter,
        instrument_reader: InstrumentReader,
        file_lock_manager: FileLockManager,
        etf_adj_reader: EtfAdjFactorReader,
        etf_adj_writer: EtfAdjFactorWriter,
        index_bars_reader: IndexBarsReader,
        index_bars_writer: IndexBarsWriter,
        index_constituent_reader: IndexConstituentReader,
        index_constituent_writer: IndexConstituentWriter,
    ) -> MarketService:
        """Market 查询服务（支持读写）。"""
        return MarketService(
            stock_bars_reader=stock_bars_reader,
            stock_bars_writer=stock_bars_writer,
            stock_status_reader=stock_status_reader,
            stock_status_writer=stock_status_writer,
            stock_adj_reader=stock_adj_reader,
            stock_adj_writer=stock_adj_writer,
            etf_bars_reader=etf_bars_reader,
            etf_bars_writer=etf_bars_writer,
            etf_status_reader=etf_status_reader,
            etf_status_writer=etf_status_writer,
            instrument_reader=instrument_reader,
            file_lock=file_lock_manager,
            etf_adj_reader=etf_adj_reader,
            etf_adj_writer=etf_adj_writer,
            index_bars_reader=index_bars_reader,
            index_bars_writer=index_bars_writer,
            index_constituent_reader=index_constituent_reader,
            index_constituent_writer=index_constituent_writer,
        )

    # ========================================================================
    # Runtime Services
    # ========================================================================

    @provide
    def ingestion_log_service(
        self,
        ingestion_log_reader: IngestionLogReader,
        ingestion_log_writer: IngestionLogWriter,
    ) -> IngestionLogService:
        """数据摄入日志服务."""
        return IngestionLogService(ingestion_log_reader, ingestion_log_writer)

    @provide
    def quality_record_service(
        self,
        comparison_reader: ComparisonReader,
        comparison_writer: ComparisonWriter,
        quarantine_reader: QuarantineReader,
        quarantine_writer: QuarantineWriter,
    ) -> QualityRecordService:
        """质量记录服务."""
        return QualityRecordService(
            comparison_reader,
            comparison_writer,
            quarantine_reader,
            quarantine_writer,
        )

    @provide
    def source_service(self, sources: DataSources) -> SourceService:
        """外部数据源访问服务."""
        return SourceService(sources)

    # ========================================================================
    # SQL Engine
    # ========================================================================

    @provide
    def sql_engine(
        self,
        data_root: Path,
    ) -> SqlEngine:
        """DuckDB SQL 引擎."""
        return SqlEngine(data_root=data_root)
