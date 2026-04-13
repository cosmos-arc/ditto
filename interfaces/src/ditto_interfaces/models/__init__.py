"""
Models 包。

公共 API 仅导出 Pydantic 响应/请求模型。
to_* 转换函数请直接从叶子模块导入，如:
    from ditto_interfaces.models.market import to_bar, to_bar_list
"""

from __future__ import annotations

from ditto_interfaces.models.backtest import (
    AuditRecordResponse,
    BenchmarkNavResponse,
    RunResponse,
    RunsQueryParams,
    TradeResponse,
)
from ditto_interfaces.models.capital import (
    Margin,
    MarginQuery,
    Valuation,
    ValuationQuery,
)
from ditto_interfaces.models.common import (
    APIResponse,
    ErrorResponse,
    PaginationRequest,
    PaginationResponse,
)
from ditto_interfaces.models.market import (
    Adjustment,
    Bar,
    BarsQuery,
)
from ditto_interfaces.models.metadata import (
    Instrument,
    InstrumentQuery,
)
from ditto_interfaces.models.strategy import (
    CreateStrategyRequest,
    PublishStrategyRequest,
    StrategyResponse,
    UpdateStrategyRequest,
)
from ditto_interfaces.models.trade import (
    ComparisonMetricsResponse,
    FillResponse,
    PnlSummaryResponse,
    PositionSnapshotResponse,
    RecordFillRequest,
    TradeIntentResponse,
    UpdateIntentStatusRequest,
)

__all__ = [
    "APIResponse",
    "Adjustment",
    "AuditRecordResponse",
    "Bar",
    "BarsQuery",
    "BenchmarkNavResponse",
    "ComparisonMetricsResponse",
    "CreateStrategyRequest",
    "ErrorResponse",
    "FillResponse",
    "Instrument",
    "InstrumentQuery",
    "Margin",
    "MarginQuery",
    "PaginationRequest",
    "PaginationResponse",
    "PnlSummaryResponse",
    "PositionSnapshotResponse",
    "PublishStrategyRequest",
    "RecordFillRequest",
    "RunResponse",
    "RunsQueryParams",
    "StrategyResponse",
    "TradeIntentResponse",
    "TradeResponse",
    "UpdateIntentStatusRequest",
    "UpdateStrategyRequest",
    "Valuation",
    "ValuationQuery",
]
