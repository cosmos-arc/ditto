"""查询上下文组合包."""

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

from ditto_application.query.capital import CapitalQueryFacade
from ditto_application.query.fundamental import FundamentalQueryFacade
from ditto_application.query.macro import MacroQueryFacade
from ditto_application.query.market import MarketQueryFacade
from ditto_application.query.metadata import MetadataQueryFacade
from ditto_data.services.capital_service import CapitalService
from ditto_data.services.fundamental_service import FundamentalService
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
def create_query_context() -> Generator[QueryContext, None, None]:
    """创建查询上下文（轻量级，不创建协调器等 process 组件）."""
    container = make_app_container()
    try:
        metadata_service = container.get(MetadataService)
        market_service = container.get(MarketService)
        capital_service = container.get(CapitalService)
        fundamental_service = container.get(FundamentalService)
        macro_service = container.get(MacroService)

        yield QueryContext(
            metadata=MetadataQueryFacade(metadata_service=metadata_service),
            market=MarketQueryFacade(market_service=market_service),
            capital=CapitalQueryFacade(capital_service=capital_service),
            fundamental=FundamentalQueryFacade(fundamental_service=fundamental_service),
            macro=MacroQueryFacade(macro_service=macro_service),
        )
    finally:
        container.close()
