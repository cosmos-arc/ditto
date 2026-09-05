"""
回测 API 路由（facade）.

聚合子模块路由，对外暴露统一的 router 对象。
端点详情见 backtest_run_routes / backtest_query_routes。
"""

from __future__ import annotations

from fastapi import APIRouter

from ditto_apps.api.routes.backtest_query_routes import (
    to_run_response,
    to_trade_response,
)
from ditto_apps.api.routes.backtest_run_routes import (
    build_flow_params,
    make_failure_callback,
    restore_flow_params_from_config,
    run_backtest_flow_sync,
    to_cost_config,
)

router = APIRouter(prefix="/backtests", tags=["backtests"])

# 导入子路由
from ditto_apps.api.routes.backtest_query_routes import (  # noqa: E402
    router as _query_router,
)
from ditto_apps.api.routes.backtest_run_routes import (  # noqa: E402
    router as _run_router,
)

router.include_router(_run_router)
router.include_router(_query_router)

__all__ = [
    "build_flow_params",
    "make_failure_callback",
    "restore_flow_params_from_config",
    "router",
    "run_backtest_flow_sync",
    "to_cost_config",
    "to_run_response",
    "to_trade_response",
]
