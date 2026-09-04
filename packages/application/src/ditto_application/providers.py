"""
App 层 DI Provider — 应用编排服务注册。

十一个 Provider 按职责分离：
- AppAccountLedgerProvider: 账户账本命令与精确查询
- AppPaperProvider: Paper 账户、会话、撮合、恢复与对账用例
- AppCommandProvider: Command Handler 注册（providers_command 模块）
- AppMarketQueryProvider: 市场数据查询服务（providers_market 模块）
- AppStrategyQueryProvider: 策略/回测查询服务（providers_strategy 模块）
- AppPortfolioQueryProvider: 组合/交易查询服务（providers_portfolio 模块）
- AppProcessProvider: 编排/物化/质量服务（providers_process 模块）
- AppSelectionProvider: 行业轮动与个股/ETF 选择工作台（providers_selection 模块）
- AppBuilderFactory: 策略运行时装配服务（providers_builder 模块）
- AppResearchExecutionProvider: R3 研究执行 bundle wiring
  （providers_research_execution 模块）
"""

from __future__ import annotations

from dishka import Provider

from ditto_application.providers_account_ledger import AppAccountLedgerProvider
from ditto_application.providers_builder import (
    AppBuilderFactory,
    get_trading_calendar_range,
)
from ditto_application.providers_command import AppCommandProvider
from ditto_application.providers_market import AppMarketQueryProvider
from ditto_application.providers_paper import AppPaperProvider
from ditto_application.providers_portfolio import AppPortfolioQueryProvider
from ditto_application.providers_process import AppProcessProvider
from ditto_application.providers_research_execution import (
    AppResearchExecutionProvider,
)
from ditto_application.providers_research_memory import AppResearchMemoryProvider
from ditto_application.providers_selection import AppSelectionProvider
from ditto_application.providers_strategy import AppStrategyQueryProvider

__all__ = [
    "AppAccountLedgerProvider",
    "AppBuilderFactory",
    "AppCommandProvider",
    "AppMarketQueryProvider",
    "AppPaperProvider",
    "AppPortfolioQueryProvider",
    "AppProcessProvider",
    "AppResearchExecutionProvider",
    "AppResearchMemoryProvider",
    "AppSelectionProvider",
    "AppStrategyQueryProvider",
    "get_app_providers",
    "get_trading_calendar_range",
]


def get_app_providers() -> list[Provider]:
    """返回 App 层所有 Provider。"""
    return [
        AppAccountLedgerProvider(),
        AppPaperProvider(),
        AppCommandProvider(),
        AppMarketQueryProvider(),
        AppStrategyQueryProvider(),
        AppPortfolioQueryProvider(),
        AppSelectionProvider(),
        AppProcessProvider(),
        AppBuilderFactory(),
        AppResearchExecutionProvider(),
        AppResearchMemoryProvider(),
    ]
