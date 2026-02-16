"""DataHub 层 - Market Domain Provider。"""

from __future__ import annotations

from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_datahub.config.data_store import DataStoreSettings
from ditto_datahub.services.market_service import MarketService
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
from ditto_datahub.stores.metadata.instrument import InstrumentReader
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
    # Market Service
    # ========================================================================

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
