"""#627 correctness F2 回归：parquet 写入车道必须真实注入 FileLockManager.

死锁分支（同年分区互斥）从未接线时是死代码——并行回补的丢失更新防护
形同虚设。审计 #684 批B #7 起锁下沉 ParquetDatasetWriter（经 store 携带
FileLockManager），本测试钉住各域 writer 的 store 接线不再回退。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from dishka import Container, Provider, Scope, make_container, provide
from ditto_data.config.data_source import DataSourceSettings
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.di.capital import CapitalProvider
from ditto_data.di.fundamental import FundamentalProvider
from ditto_data.di.market import MarketProvider
from ditto_data.di.runtime import RuntimeProvider
from ditto_data.di.sources import SourcesProvider
from ditto_data.services.deps import CapitalWriters, FundamentalWriters, MarketWriters
from ditto_data.storage.metadata.instrument import InstrumentReader


def _container(tmp_path: Path, *providers: Provider) -> Container:
    settings = DataStoreSettings(data_root=tmp_path)

    class _SettingsProvider(Provider):
        scope = Scope.APP

        @provide
        def data_store_settings(self) -> DataStoreSettings:
            return settings

        @provide
        def data_source_settings(self) -> DataSourceSettings:
            return DataSourceSettings(tushare_token="test-token")

        # MarketProvider.market_readers 的图依赖（本测试不触读路径）
        @provide
        def instrument_reader(self) -> InstrumentReader:
            return MagicMock(spec=InstrumentReader)

    return make_container(
        _SettingsProvider(), SourcesProvider(), RuntimeProvider(), *providers
    )


def test_capital_writers_have_file_lock_wired(tmp_path: Path) -> None:
    container = _container(tmp_path, CapitalProvider())
    try:
        writers = container.get(CapitalWriters)
        for writer in (
            writers.moneyflow,
            writers.hk_hold,
            writers.top10_holders,
            writers.index_valuation,
        ):
            assert writer is not None
            assert writer._store.file_lock is not None, (
                f"{type(writer).__name__} 的 store 未携带 FileLockManager——"
                "同年分区写入锁是死代码 (#627 correctness F2 / #684 批B #7)"
            )
    finally:
        container.close()


def test_market_and_fundamental_writers_have_file_lock_wired(tmp_path: Path) -> None:
    container = _container(tmp_path, MarketProvider(), FundamentalProvider())
    try:
        market = container.get(MarketWriters)
        assert market.stock_bars._store.file_lock is not None
        assert market.etf_nav is not None
        assert market.etf_nav._store.file_lock is not None

        fundamental = container.get(FundamentalWriters)
        assert fundamental.fina_indicator is not None
        assert fundamental.fina_indicator._store.file_lock is not None
        assert fundamental.earnings_forecast is not None
        assert fundamental.earnings_forecast._store.file_lock is not None
    finally:
        container.close()
