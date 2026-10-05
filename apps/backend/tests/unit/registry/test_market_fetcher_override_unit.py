"""#439：组合根 MarketFetcher 覆盖 registry — 仅替换显式绑定的源."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_apps.registry.contexts.ingestion import _MarketFetcherOverrideRegistry
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
