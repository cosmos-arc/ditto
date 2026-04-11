"""回测 API 模型."""

from __future__ import annotations

from typing import Any, cast

import orjson
from ditto_app.query.backtest_trade import TradeRecord
from pydantic import BaseModel, ConfigDict, Field

from ditto_interfaces.models._date_helpers import DateField


class RunResponse(BaseModel):
    """运行记录响应."""

    run_id: str
    strategy_id: str
    strategy_version: str = ""
    mode: str = "backtest"
    status: str
    started_at: str = ""
    completed_at: str = ""
    error_message: str = ""
    parent_run_id: str = ""
    benchmark_return: float | None = None

    model_config = ConfigDict(strict=True, extra="ignore")


class RunsQueryParams(BaseModel):
    """运行列表查询参数."""

    strategy_id: str | None = Field(default=None, description="策略 ID")
    status: str | None = Field(default=None, description="运行状态")
    start_date: DateField = Field(default=None, description="开始日期")
    end_date: DateField = Field(default=None, description="结束日期")
    limit: int = Field(default=100, ge=1, le=1000, description="每页数量")
    offset: int = Field(default=0, ge=0, description="偏移量")

    model_config = ConfigDict(strict=True, extra="ignore")


class TradeResponse(BaseModel):
    """成交记录响应."""

    trade_date: str = ""
    instrument_id: int = 0
    direction: str = ""
    entry_date: str = ""
    exit_date: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: float = 0.0
    pnl: float = 0.0

    model_config = ConfigDict(strict=True, extra="ignore")


class AuditRecordResponse(BaseModel):
    """审计记录响应."""

    id: int = 0
    run_id: str = ""
    trade_date: str = ""
    record_type: str = ""
    instrument_id: int | None = None
    payload: dict[str, Any] = {}
    created_at: str = ""

    model_config = ConfigDict(strict=True, extra="ignore")


def to_run_response(record: Any) -> RunResponse:  # noqa: ANN401
    """将 StrategyRunRecord 转为 API 响应."""
    return RunResponse(
        run_id=record.run_id,
        strategy_id=record.strategy_id,
        strategy_version=record.strategy_version,
        mode=record.mode,
        status=record.status,
        started_at=record.started_at,
        completed_at=record.completed_at,
        error_message=record.error_message,
        parent_run_id=getattr(record, "parent_run_id", ""),
    )


def to_trade_response(record: TradeRecord) -> TradeResponse:
    """将 TradeRecord 转为 API 响应."""
    return TradeResponse(
        trade_date=record.trade_date,
        instrument_id=record.instrument_id,
        direction=record.direction,
        entry_date=record.entry_date,
        exit_date=record.exit_date,
        entry_price=record.entry_price,
        exit_price=record.exit_price,
        quantity=record.quantity,
        pnl=record.pnl,
    )


def _parse_payload(raw: Any) -> dict[str, Any]:  # noqa: ANN401
    """解析审计 payload 字段."""
    if isinstance(raw, str):
        return orjson.loads(raw)
    if isinstance(raw, dict):
        return cast(dict[str, Any], raw)
    return {}


def to_audit_record_response(row: dict[str, Any]) -> AuditRecordResponse:
    """将审计行 dict 转为 API 响应."""
    return AuditRecordResponse(
        id=int(row.get("id", 0)),
        run_id=str(row.get("run_id", "")),
        trade_date=str(row.get("trade_date", "")),
        record_type=str(row.get("record_type", "")),
        instrument_id=row.get("instrument_id"),
        payload=_parse_payload(row.get("payload", "{}")),
        created_at=str(row.get("created_at", "")),
    )


class BenchmarkNavResponse(BaseModel):
    """基准 NAV 序列响应."""

    run_id: str
    dates: list[str] = []
    navs: list[float] = []
    benchmark_return: float | None = None

    model_config = ConfigDict(strict=True, extra="ignore")


__all__ = [
    "AuditRecordResponse",
    "BenchmarkNavResponse",
    "RunResponse",
    "RunsQueryParams",
    "TradeResponse",
    "to_audit_record_response",
    "to_run_response",
    "to_trade_response",
]
