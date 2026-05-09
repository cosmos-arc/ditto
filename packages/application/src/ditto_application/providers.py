"""
App 层 DI Provider — 应用编排服务注册。

六个 Provider 按职责分离：
- AppCommandProvider: Command Handler 注册（providers_command 模块）
- AppMarketQueryProvider: 市场数据查询服务（providers_market 模块）
- AppStrategyQueryProvider: 策略/回测查询服务（providers_strategy 模块）
- AppPortfolioQueryProvider: 组合/交易查询服务（providers_portfolio 模块）
- AppProcessProvider: 编排/物化/质量服务（providers_process 模块）
- AppBuilderFactory: 策略运行时装配服务（providers_builder 模块）
"""

from __future__ import annotations

from dishka import Provider

from ditto_application.providers_builder import AppBuilderFactory
from ditto_application.providers_command import (
    AppCommandProvider,
    get_trading_calendar_range,
)
from ditto_application.providers_market import AppMarketQueryProvider
from ditto_application.providers_portfolio import AppPortfolioQueryProvider
from ditto_application.providers_process import AppProcessProvider
from ditto_application.providers_strategy import AppStrategyQueryProvider

__all__ = [
    "AppBuilderFactory",
    "AppCommandProvider",
    "AppMarketQueryProvider",
    "AppPortfolioQueryProvider",
    "AppProcessProvider",
    "AppStrategyQueryProvider",
    "get_app_providers",
    "get_trading_calendar_range",
]


def get_app_providers() -> list[Provider]:
    """返回 App 层所有 Provider。"""
    return [
        AppCommandProvider(),
        AppMarketQueryProvider(),
        AppStrategyQueryProvider(),
        AppPortfolioQueryProvider(),
        AppProcessProvider(),
        AppBuilderFactory(),
    ]
