"""DataHub 层 - Market Domain Provider。"""

from __future__ import annotations

from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.services.market_service import MarketService
from ditto_data.services.ports import MarketReadPorts, MarketWritePorts
from ditto_data.stores.market.commodity.bars import (
    CommodityBarsReader,
    CommodityBarsWriter,
)
from ditto_data.stores.market.etf.adj.adj_factor_reader import (
    EtfAdjFactorReader,
)
from ditto_data.stores.market.etf.adj.adj_factor_writer import (
    EtfAdjFactorWriter,
)
from ditto_data.stores.market.etf.bars import EtfBarsReader, EtfBarsWriter
from ditto_data.stores.market.etf.nav.nav_reader import EtfNavReader
from ditto_data.stores.market.etf.nav.nav_writer import EtfNavWriter
from ditto_data.stores.market.etf.status import EtfStatusReader, EtfStatusWriter
from ditto_data.stores.market.fx.bars import FxBarsReader, FxBarsWriter
from ditto_data.stores.market.index.bars.bars_reader import IndexBarsReader
from ditto_data.stores.market.index.bars.bars_writer import IndexBarsWriter
from ditto_data.stores.market.index.constituent.constituent_reader import (
    IndexConstituentReader,
)
from ditto_data.stores.market.index.constituent.constituent_writer import (
    IndexConstituentWriter,
)
from ditto_data.stores.market.stock.adj import (
    StockAdjFactorReader,
    StockAdjFactorWriter,
)
from ditto_data.stores.market.stock.bars import StockBarsReader, StockBarsWriter
from ditto_data.stores.market.stock.status import (
    StockStatusReader,
    StockStatusWriter,
)
from ditto_data.stores.metadata.instrument import InstrumentReader
from ditto_infra.foundation.concurrency import FileLockManager

__all__ = ["MarketProvider"]


class MarketProvider(Provider):
    """Market Domain Provider - 股票/ETF/指数行情、状态、复权因子."""

    scope = Scope.APP

    # ========================================================================
    # Stock Stores
    # ========================================================================

    @provide
    def stock_bars_reader(self, settings: DataStoreSettings) -> StockBarsReader:
        """股票 K线读取器."""
        return StockBarsReader(settings.data_root)

    @provide
    def stock_bars_writer(self, settings: DataStoreSettings) -> StockBarsWriter:
        """股票 K线写入器."""
        return StockBarsWriter(settings.data_root)

    @provide
    def stock_status_reader(self, settings: DataStoreSettings) -> StockStatusReader:
        """股票状态读取器."""
        return StockStatusReader(settings.data_root)

    @provide
    def stock_status_writer(self, settings: DataStoreSettings) -> StockStatusWriter:
        """股票状态写入器."""
        return StockStatusWriter(settings.data_root)

    @provide
    def stock_adj_reader(self, settings: DataStoreSettings) -> StockAdjFactorReader:
        """股票复权因子读取器."""
        return StockAdjFactorReader(settings.data_root)

    @provide
    def stock_adj_writer(self, settings: DataStoreSettings) -> StockAdjFactorWriter:
        """股票复权因子写入器."""
        return StockAdjFactorWriter(settings.data_root)

    # ========================================================================
    # ETF Stores
    # ========================================================================

    @provide
    def etf_bars_reader(self, settings: DataStoreSettings) -> EtfBarsReader:
        """ETF K线读取器."""
        return EtfBarsReader(settings.data_root)

    @provide
    def etf_bars_writer(self, settings: DataStoreSettings) -> EtfBarsWriter:
        """ETF K线写入器."""
        return EtfBarsWriter(settings.data_root)

    @provide
    def etf_status_reader(self, settings: DataStoreSettings) -> EtfStatusReader:
        """ETF 状态读取器."""
        return EtfStatusReader(settings.data_root)

    @provide
    def etf_status_writer(self, settings: DataStoreSettings) -> EtfStatusWriter:
        """ETF 状态写入器."""
        return EtfStatusWriter(settings.data_root)

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

    # ========================================================================
    # Index Stores
    # ========================================================================

    @provide
    def index_bars_reader(self, settings: DataStoreSettings) -> IndexBarsReader:
        """指数 K线读取器."""
        return IndexBarsReader(data_root=settings.data_root)

    @provide
    def index_bars_writer(self, settings: DataStoreSettings) -> IndexBarsWriter:
        """指数 K线写入器."""
        return IndexBarsWriter(data_root=settings.data_root)

    @provide
    def index_constituent_reader(self, data_root: Path) -> IndexConstituentReader:
        """指数成分股读取器."""
        return IndexConstituentReader(data_root=data_root)

    @provide
    def index_constituent_writer(self, data_root: Path) -> IndexConstituentWriter:
        """指数成分股写入器."""
        return IndexConstituentWriter(data_root=data_root)

    # ========================================================================
    # FX Stores
    # ========================================================================

    @provide
    def fx_bars_reader(self, settings: DataStoreSettings) -> FxBarsReader:
        """外汇 K线读取器."""
        return FxBarsReader(settings.data_root)

    @provide
    def fx_bars_writer(self, settings: DataStoreSettings) -> FxBarsWriter:
        """外汇 K线写入器."""
        return FxBarsWriter(settings.data_root)

    # ========================================================================
    # Commodity Stores
    # ========================================================================

    @provide
    def commodity_bars_reader(self, settings: DataStoreSettings) -> CommodityBarsReader:
        """大宗商品 K线读取器."""
        return CommodityBarsReader(settings.data_root)

    @provide
    def commodity_bars_writer(self, settings: DataStoreSettings) -> CommodityBarsWriter:
        """大宗商品 K线写入器."""
        return CommodityBarsWriter(settings.data_root)

    # ========================================================================
    # Market Ports
    # ========================================================================

    @provide
    def market_read_ports(  # noqa: PLR0913
        self,
        stock_bars_reader: StockBarsReader,
        stock_status_reader: StockStatusReader,
        stock_adj_reader: StockAdjFactorReader,
        etf_bars_reader: EtfBarsReader,
        etf_status_reader: EtfStatusReader,
        instrument_reader: InstrumentReader,
        etf_adj_reader: EtfAdjFactorReader,
        index_bars_reader: IndexBarsReader,
        index_constituent_reader: IndexConstituentReader,
        fx_bars_reader: FxBarsReader,
        commodity_bars_reader: CommodityBarsReader,
    ) -> MarketReadPorts:
        """Market 域读取端口."""
        return MarketReadPorts(
            stock_bars=stock_bars_reader,
            stock_status=stock_status_reader,
            stock_adj=stock_adj_reader,
            etf_bars=etf_bars_reader,
            etf_status=etf_status_reader,
            instrument=instrument_reader,
            etf_adj=etf_adj_reader,
            index_bars=index_bars_reader,
            index_constituent=index_constituent_reader,
            fx_bars=fx_bars_reader,
            commodity_bars=commodity_bars_reader,
        )

    @provide
    def market_write_ports(  # noqa: PLR0913
        self,
        stock_bars_writer: StockBarsWriter,
        stock_status_writer: StockStatusWriter,
        stock_adj_writer: StockAdjFactorWriter,
        etf_bars_writer: EtfBarsWriter,
        etf_status_writer: EtfStatusWriter,
        etf_adj_writer: EtfAdjFactorWriter,
        index_bars_writer: IndexBarsWriter,
        index_constituent_writer: IndexConstituentWriter,
        fx_bars_writer: FxBarsWriter,
        commodity_bars_writer: CommodityBarsWriter,
    ) -> MarketWritePorts:
        """Market 域写入端口."""
        return MarketWritePorts(
            stock_bars=stock_bars_writer,
            stock_status=stock_status_writer,
            stock_adj=stock_adj_writer,
            etf_bars=etf_bars_writer,
            etf_status=etf_status_writer,
            etf_adj=etf_adj_writer,
            index_bars=index_bars_writer,
            index_constituent=index_constituent_writer,
            fx_bars=fx_bars_writer,
            commodity_bars=commodity_bars_writer,
        )

    # ========================================================================
    # Market Service
    # ========================================================================

    @provide
    def market_service(
        self,
        read_ports: MarketReadPorts,
        write_ports: MarketWritePorts,
        file_lock_manager: FileLockManager,
    ) -> MarketService:
        """Market 查询服务（支持读写）。"""
        return MarketService(
            read_ports=read_ports,
            write_ports=write_ports,
            file_lock=file_lock_manager,
        )
