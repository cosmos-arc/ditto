"""
交易闭环 API 路由（facade）.

聚合子模块路由，对外暴露统一的 router 对象。
端点详情见 trade_command_routes / trade_query_routes。

maturity: initial-focus
"""

from __future__ import annotations

from fastapi import APIRouter

from ditto_apps.api.routes.trade_command_routes import (
    to_fill_response,
)
from ditto_apps.api.routes.trade_query_routes import (
    to_comparison_response,
    to_intent_response,
    to_pnl_response,
    to_position_response,
)

router = APIRouter(prefix="/trade", tags=["trade"])

# 导入子路由
from ditto_apps.api.routes.trade_command_routes import (  # noqa: E402
    router as _command_router,
)
from ditto_apps.api.routes.trade_query_routes import (  # noqa: E402
    router as _query_router,
)

router.include_router(_command_router)
router.include_router(_query_router)

__all__ = [
    "router",
    "to_comparison_response",
    "to_fill_response",
    # 保留原有导出名称
    "to_intent_response",
    "to_pnl_response",
    "to_position_response",
]
