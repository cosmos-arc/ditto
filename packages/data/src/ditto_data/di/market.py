"""Data 层 - Market Domain Provider。"""

from dishka import Provider, Scope, provide
from ditto_platform.foundation.concurrency import FileLockManager

from ditto_data.config.data_store import DataStoreSettings
from ditto_data.services.deps import MarketReaders, MarketWriters
from ditto_data.services.market_service import MarketService
from ditto_data.services.market_write_service import MarketWriteService
from ditto_data.storage.base.parquet_store import ParquetStore
from ditto_data.storage.market.commodity.bars import (
    CommodityBarsReader,
    CommodityBarsWriter,
)
from ditto_data.storage.market.etf.adj.adj_factor_reader import EtfAdjFactorReader
from ditto_data.storage.market.etf.adj.adj_factor_writer import EtfAdjFactorWriter
from ditto_data.storage.market.etf.bars import EtfBarsReader, EtfBarsWriter
from ditto_data.storage.market.etf.nav.nav_reader import EtfNavReader
from ditto_data.storage.market.etf.nav.nav_writer import EtfNavWriter
from ditto_data.storage.market.etf.status import EtfStatusReader, EtfStatusWriter
from ditto_data.storage.market.fx.bars import FxBarsReader, FxBarsWriter
from ditto_data.storage.market.index.bars.bars_reader import IndexBarsReader
from ditto_data.storage.market.index.bars.bars_writer import IndexBarsWriter
from ditto_data.storage.market.index.constituent.constituent_reader import (
    IndexConstituentReader,
)
from ditto_data.storage.market.index.constituent.constituent_writer import (
    IndexConstituentWriter,
)
from ditto_data.storage.market.stock.adj import (
    StockAdjFactorReader,
    StockAdjFactorWriter,
)
from ditto_data.storage.market.stock.bars import StockBarsReader, StockBarsWriter
from ditto_data.storage.market.stock.status import (
    StockStatusReader,
    StockStatusWriter,
)
from ditto_data.storage.metadata.instrument import InstrumentReader

__all__ = ["MarketProvider"]


class MarketProvider(Provider):
    """Market Domain Provider - 股票/ETF/指数行情、状态、复权因子."""

    scope = Scope.APP

    @provide
    def market_readers(
        self,
        settings: DataStoreSettings,
        instrument_reader: InstrumentReader,
    ) -> MarketReaders:
        """Market 域读取依赖聚合。"""
        store = ParquetStore(settings.data_root)
        return MarketReaders(
            stock_bars=StockBarsReader(store),
            stock_status=StockStatusReader(store),
            stock_adj=StockAdjFactorReader(store),
            etf_bars=EtfBarsReader(store),
            etf_status=EtfStatusReader(store),
            instrument=instrument_reader,
            etf_adj=EtfAdjFactorReader(store),
            etf_nav=EtfNavReader(store),
            index_bars=IndexBarsReader(store),
            index_constituent=IndexConstituentReader(data_root=settings.data_root),
            fx_bars=FxBarsReader(store),
            commodity_bars=CommodityBarsReader(store),
        )

    @provide
    def market_writers(
        self,
        settings: DataStoreSettings,
    ) -> MarketWriters:
        """Market 域写入依赖聚合。"""
        store = ParquetStore(settings.data_root)
        return MarketWriters(
            stock_bars=StockBarsWriter(store),
            stock_status=StockStatusWriter(store),
            stock_adj=StockAdjFactorWriter(store),
            etf_bars=EtfBarsWriter(store),
            etf_status=EtfStatusWriter(store),
            etf_adj=EtfAdjFactorWriter(store),
            etf_nav=EtfNavWriter(store),
            index_bars=IndexBarsWriter(store),
            index_constituent=IndexConstituentWriter(data_root=settings.data_root),
            fx_bars=FxBarsWriter(store),
            commodity_bars=CommodityBarsWriter(store),
        )

    @provide
    def market_service(self, read_ports: MarketReaders) -> MarketService:
        """Market 查询服务（只读）。"""
        return MarketService(read_ports=read_ports)

    @provide
    def market_write_service(
        self,
        write_ports: MarketWriters,
        file_lock_manager: FileLockManager,
    ) -> MarketWriteService:
        """Market 写入服务。"""
        return MarketWriteService(write_ports=write_ports, file_lock=file_lock_manager)
