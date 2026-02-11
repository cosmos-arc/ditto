"""
DataHub 组件注册.

Root 注入模式：在 Provider 中集中注册所有 DataHub 组件。
所有依赖通过 Provider 管理，DataHub 不再使用 @cached_property.

架构说明：
- Store 的导入和创建已移至 DomainServiceProvider
- DataHubProvider 只负责组合 Domain Services
- Port 层不再直接依赖 Store 类
"""

# 延迟类型注解评估，避免前向引用问题
from __future__ import annotations

from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_datahub.config.data_root import DataRootConfig
from ditto_datahub.runtime.instrument_id_allocator import InstrumentIdAllocator
from ditto_datahub.runtime.sql_engine import SqlEngine
from ditto_datahub.services import IngestionLogService
from ditto_datahub.services.capital_service import CapitalService
from ditto_datahub.services.factor_service import FactorService
from ditto_datahub.services.feature_service import FeatureService
from ditto_datahub.services.fundamental_service import FundamentalService
from ditto_datahub.services.macro_service import MacroService
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.services.source_service import SourceService
from ditto_datahub.sources.source import DataSources
from ditto_datahub.sources.tushare.tushare_source import TushareSource
from ditto_datahub.stores.capital.futures.futures_reader import (
    FuturesReader,
)
from ditto_datahub.stores.capital.futures.futures_writer import (
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

# Market Stores (CQRS Reader/Writer)
from ditto_datahub.stores.market.etf.adj.adj_factor_reader import (
    EtfAdjFactorReader,
)
from ditto_datahub.stores.market.etf.adj.adj_factor_writer import (
    EtfAdjFactorWriter,
)
from ditto_datahub.stores.market.etf.bars import (
    EtfBarsReader,
    EtfBarsWriter,
)
from ditto_datahub.stores.market.etf.nav.nav_reader import (
    EtfNavReader,
)
from ditto_datahub.stores.market.etf.nav.nav_writer import (
    EtfNavWriter,
)
from ditto_datahub.stores.market.etf.status import (
    EtfStatusReader,
    EtfStatusWriter,
)
from ditto_datahub.stores.market.index.bars.bars_reader import (
    IndexBarsReader,
)
from ditto_datahub.stores.market.index.bars.bars_writer import (
    IndexBarsWriter,
)
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
from ditto_datahub.stores.market.stock.bars import (
    StockBarsReader,
    StockBarsWriter,
)
from ditto_datahub.stores.market.stock.status import (
    StockStatusReader,
    StockStatusWriter,
)

# Metadata Stores (CQRS Reader/Writer)
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
from ditto_datahub.stores.runtime.ingestion import IngestionLogStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool
from ditto_foundation.concurrency import FileLockManager

__all__ = ["DataHubProvider"]


class DataHubProvider(Provider):
    """
    DataHub 组件 Provider.

    架构说明：
    - Store 的创建由 DomainServiceProvider 负责
    - 此 Provider 只负责组合 Domain Services
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
    def file_lock(self, data_root: Path) -> FileLockManager:
        """文件锁管理器."""
        lock_dir = data_root / "locks"
        return FileLockManager(lock_dir)

    # ========================================================================
    # Fundamental & Capital Query Services
    # ========================================================================

    @provide
    def fundamental_query_service(
        self,
        sqlite_client: SQLiteClient,
    ) -> FundamentalService:
        """Fundamental 查询服务."""
        balance_sheet_reader = BalanceSheetReader(client=sqlite_client)
        balance_sheet_writer = BalanceSheetWriter(client=sqlite_client)
        income_statement_reader = IncomeStatementReader(client=sqlite_client)
        income_statement_writer = IncomeStatementWriter(client=sqlite_client)
        cash_flow_reader = CashFlowReader(client=sqlite_client)
        cash_flow_writer = CashFlowWriter(client=sqlite_client)
        dividend_reader = DividendReader(client=sqlite_client)
        dividend_writer = DividendWriter(client=sqlite_client)
        corporate_actions_reader = CorporateActionsReader(client=sqlite_client)
        corporate_actions_writer = CorporateActionsWriter(client=sqlite_client)
        forecast_reader = ForecastReader(client=sqlite_client)
        forecast_writer = ForecastWriter(client=sqlite_client)
        express_reader = ExpressReader(client=sqlite_client)
        express_writer = ExpressWriter(client=sqlite_client)
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
    def capital_query_service(
        self,
        sqlite_client: SQLiteClient,
    ) -> CapitalService:
        """Capital 查询服务."""
        margin_trading_reader = MarginTradingReader(client=sqlite_client)
        margin_trading_writer = MarginTradingWriter(client=sqlite_client)
        pledge_ratio_reader = PledgeRatioReader(client=sqlite_client)
        pledge_ratio_writer = PledgeRatioWriter(client=sqlite_client)
        valuation_metrics_reader = ValuationMetricsReader(client=sqlite_client)
        valuation_metrics_writer = ValuationMetricsWriter(client=sqlite_client)
        futures_reader = FuturesReader(client=sqlite_client)
        futures_writer = FuturesWriter(client=sqlite_client)
        index_composition_reader = IndexCompositionReader(client=sqlite_client)
        index_composition_writer = IndexCompositionWriter(client=sqlite_client)
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

    # ========================================================================
    # Macro Query Service
    # ========================================================================

    @provide
    def macro_query_service(
        self,
        sqlite_client: SQLiteClient,
    ) -> MacroService:
        """Macro 查询服务（CQRS Reader/Writer）."""
        indicator_reader = MacroIndicatorReader(client=sqlite_client)
        indicator_writer = MacroIndicatorWriter(client=sqlite_client)
        metadata_reader = MacroIndicatorMetadataReader(client=sqlite_client)
        metadata_writer = MacroIndicatorMetadataWriter(client=sqlite_client)
        return MacroService(
            indicator_reader=indicator_reader,
            indicator_writer=indicator_writer,
            metadata_reader=metadata_reader,
            metadata_writer=metadata_writer,
        )

    # ========================================================================
    # Features Domain Stores & Services
    # ========================================================================

    @provide
    def features_query_service(
        self,
        data_root_config: DataRootConfig,
        sqlite_client: SQLiteClient,
    ) -> FeatureService:
        """Features 查询服务（CQRS Reader/Writer）."""
        indicator_reader = TechnicalIndicatorReader(
            data_root_config.features_technical_indicators_narrow_path
        )
        indicator_writer = TechnicalIndicatorWriter(
            data_root_config.features_technical_indicators_narrow_path
        )
        metadata_reader = TechnicalIndicatorMetadataReader(client=sqlite_client)
        metadata_writer = TechnicalIndicatorMetadataWriter(client=sqlite_client)
        return FeatureService(
            indicator_reader=indicator_reader,
            indicator_writer=indicator_writer,
            metadata_reader=metadata_reader,
            metadata_writer=metadata_writer,
        )

    # ========================================================================
    # Factors Domain Stores & Services
    # ========================================================================

    @provide
    def factors_query_service(
        self,
        data_root_config: DataRootConfig,
        sqlite_client: SQLiteClient,
    ) -> FactorService:
        """Factors 查询服务（CQRS Reader/Writer）."""
        factor_reader = FactorReader(data_root_config.factors_narrow_path)
        factor_writer = FactorWriter(data_root_config.factors_narrow_path)
        metadata_reader = FactorMetadataReader(client=sqlite_client)
        metadata_writer = FactorMetadataWriter(client=sqlite_client)
        return FactorService(
            factor_reader=factor_reader,
            factor_writer=factor_writer,
            metadata_reader=metadata_reader,
            metadata_writer=metadata_writer,
        )

    # ========================================================================
    # Metadata Query Service
    # ========================================================================

    @provide
    def metadata_query_service(  # noqa: PLR0913
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

    # ========================================================================
    # Market Domain Stores (CQRS Reader/Writer)
    # ========================================================================

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
    # Market Query Service
    # ========================================================================

    @provide
    def market_query_service(  # noqa: PLR0913
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
    # Sources Layer
    # ========================================================================

    @provide
    def sources(self, tushare_source: TushareSource) -> DataSources:
        """
        外部数据源组合器.

        Args:
            tushare_source: Tushare 数据源实例

        """
        return DataSources(tushare=tushare_source)

    # ========================================================================
    # Runtime Services
    # ========================================================================

    @provide
    def ingestion_log_service(
        self,
        ingestion_log_store: IngestionLogStore,
    ) -> IngestionLogService:
        """数据摄入日志服务."""
        return IngestionLogService(ingestion_log_store)

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
