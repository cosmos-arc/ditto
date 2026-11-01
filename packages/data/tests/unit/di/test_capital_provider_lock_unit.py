"""#627 correctness F2 回归：CapitalStore 必须真实注入 FileLockManager.

死锁分支（save_* 的同年分区互斥）从未接线时是死代码——并行回补的
丢失更新防护形同虚设。FundamentalStore 自 #517-523 起正确注入，
本测试钉住 CapitalStore 同一接线不再回退。
"""

from __future__ import annotations

from pathlib import Path

from dishka import Provider, Scope, make_container, provide
from ditto_data.config.data_source import DataSourceSettings
from ditto_data.config.data_store import DataStoreSettings
from ditto_data.di.capital import CapitalProvider
from ditto_data.di.runtime import RuntimeProvider
from ditto_data.di.sources import SourcesProvider
from ditto_data.services.capital_store import CapitalStore


def test_capital_store_has_file_lock_wired(tmp_path: Path) -> None:
    settings = DataStoreSettings(data_root=tmp_path)

    class _SettingsProvider(Provider):
        scope = Scope.APP

        @provide
        def data_store_settings(self) -> DataStoreSettings:
            return settings

        @provide
        def data_source_settings(self) -> DataSourceSettings:
            return DataSourceSettings(tushare_token="test-token")

    container = make_container(
        _SettingsProvider(), SourcesProvider(), RuntimeProvider(), CapitalProvider()
    )
    try:
        store = container.get(CapitalStore)
        assert store._file_lock is not None, (
            "CapitalStore 未注入 FileLockManager——parquet 车道并发写防护"
            "是死代码 (#627 correctness F2)"
        )
    finally:
        container.close()
