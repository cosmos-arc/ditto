"""查询上下文组合包."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from ditto_application.queries.capital import CapitalQueryFacade
from ditto_application.queries.fundamental import FundamentalQueryFacade
from ditto_application.queries.macro import MacroQueryFacade
from ditto_application.queries.market import MarketQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_data.services.capital_store import CapitalStore
from ditto_data.services.fundamental_store import FundamentalStore
from ditto_data.services.macro_service import MacroService
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService

from ditto_apps.registry.container import make_app_container


@dataclass(frozen=True)
class QueryContext:
    """只读查询上下文 — 封装 app 层 query facades."""

    metadata: MetadataQueryFacade
    market: MarketQueryFacade
    capital: CapitalQueryFacade
    fundamental: FundamentalQueryFacade
    macro: MacroQueryFacade


@contextmanager
def create_query_context() -> Generator[QueryContext]:
    """创建查询上下文（轻量级，不创建协调器等 process 组件）."""
    container = make_app_container()
    try:
        metadata_service = container.get(MetadataService)
        market_service = container.get(MarketService)
        capital_store = container.get(CapitalStore)
        fundamental_store = container.get(FundamentalStore)
        macro_service = container.get(MacroService)

        yield QueryContext(
            metadata=MetadataQueryFacade(metadata_service=metadata_service),
            market=MarketQueryFacade(
                market_service=market_service,
                capital_store=capital_store,
            ),
            capital=CapitalQueryFacade(capital_store=capital_store),
            fundamental=FundamentalQueryFacade(fundamental_store=fundamental_store),
            macro=MacroQueryFacade(macro_service=macro_service),
        )
    finally:
        container.close()
