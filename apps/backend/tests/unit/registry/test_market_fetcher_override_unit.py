"""#439：组合根 MarketFetcher 覆盖 registry — 仅替换显式绑定的源."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from ditto_apps.registry.contexts.ingestion import _MarketFetcherOverrideRegistry
from ditto_apps.registry.infra.protocol_adapters import FuyaoDailyKDumpFetcher
from ditto_data.sources.protocols import MarketFetcher
from ditto_data.sources.registry import SourceRegistry


@pytest.mark.unit
class TestMarketFetcherOverrideRegistry:
    def test_overrides_only_bound_source_protocol(self) -> None:
        base = SourceRegistry()
        original = MagicMock(name="fuyao_default")
        tushare = MagicMock(name="tushare")
        base.register("fuyao", MarketFetcher, original)
        base.register("tushare", MarketFetcher, tushare)

        replacement = MagicMock(name="dump_fetcher")
        override = _MarketFetcherOverrideRegistry(base, "fuyao", replacement)

        assert override.get("fuyao", MarketFetcher) is replacement
        # 其它源/协议透传底座
        assert override.get("tushare", MarketFetcher) is tushare
        with pytest.raises(ValueError, match="No source registered"):
            override.get("fred", MarketFetcher)


@pytest.mark.unit
def test_override_bundle_assembles_with_real_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """真实容器装配冒烟：override 经 registry 进协调器工厂（不执行摄取）."""
    from datetime import date

    import polars as pl
    from ditto_apps.registry.contexts.ingestion import create_ingestion_bundle
    from ditto_data.sources.fuyao.client import date_to_ms

    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DITTO_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("DITTO_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("TUSHARE_TOKEN", "offline-container-test")
    dump = tmp_path / "daily-k.parquet"
    pl.DataFrame(
        {
            "thscode": ["600519.SH"],
            "currency": ["CNY"],
            "interval": ["1d"],
            "adjusted": ["none"],
            "date_ms": [date_to_ms(date(2025, 8, 18))],
            "open_price": [10.0],
            "high_price": [11.0],
            "low_price": [9.5],
            "close_price": [10.5],
            "volume": [100.0],
            "turnover": [1050.0],
        }
    ).write_parquet(dump)
    fetcher = FuyaoDailyKDumpFetcher(dump)

    with create_ingestion_bundle("fuyao", market_fetcher_override=fetcher) as bundle:
        assert bundle.coordinator is not None
