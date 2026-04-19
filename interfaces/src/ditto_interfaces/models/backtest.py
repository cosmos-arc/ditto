"""回测 API 模型."""

from __future__ import annotations

from typing import Any, cast

import orjson
from ditto_app.config import DEFAULT_INITIAL_CASH
from ditto_kernel.strategy import ImpactModel
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ditto_interfaces.models._date_helpers import DateField

# Re-export for internal use — avoids repeated literal magic numbers.
# Commission defaults mirror ditto_engine.execution.reality.constants.
# Stamp duty / slippage are A-share standard rates not yet centralized there.
_DEFAULT_COMMISSION_RATE: float = 0.0003
_DEFAULT_COMMISSION_MIN: float = 5.0
_DEFAULT_STAMP_DUTY_RATE: float = 0.001
_DEFAULT_SLIPPAGE_BPS: float = 1.0


class RunResponse(BaseModel):
    """运行记录响应."""

    run_id: str = Field(description="运行唯一标识")
    strategy_id: str = Field(description="策略 ID")
    strategy_version: str = Field(default="", description="策略版本号")
    mode: str = Field(default="backtest", description="运行模式")
    status: str = Field(description="运行状态")
    started_at: str = Field(default="", description="开始时间 (ISO 8601)")
    completed_at: str = Field(default="", description="完成时间 (ISO 8601)")
    error_message: str = Field(default="", description="错误信息")
    parent_run_id: str = Field(default="", description="父运行 ID (重试场景)")
    benchmark_return: float | None = Field(default=None, description="基准收益率 (%)")
    progress_pct: float = Field(default=0.0, description="运行进度百分比")
    current_step: str = Field(default="", description="当前步骤描述")
    completed_days: int = Field(default=0, description="已完成交易日数")
    total_days: int = Field(default=0, description="总交易日数")

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

    trade_date: str = Field(default="", description="成交日期 (YYYY-MM-DD)")
    instrument_id: int = Field(default=0, description="标的 ID")
    direction: str = Field(default="", description="交易方向 (buy/sell)")
    entry_date: str = Field(default="", description="建仓日期 (YYYY-MM-DD)")
    exit_date: str = Field(default="", description="平仓日期 (YYYY-MM-DD)")
    entry_price: float = Field(default=0.0, description="建仓价格")
    exit_price: float = Field(default=0.0, description="平仓价格")
    quantity: float = Field(default=0.0, description="成交数量")
    pnl: float = Field(default=0.0, description="盈亏金额")

    model_config = ConfigDict(strict=True, extra="ignore")


class AuditRecordResponse(BaseModel):
    """审计记录响应."""

    id: int = Field(default=0, description="记录 ID")
    run_id: str = Field(default="", description="运行 ID")
    trade_date: str = Field(default="", description="交易日期 (YYYY-MM-DD)")
    record_type: str = Field(default="", description="审计记录类型")
    instrument_id: int | None = Field(default=None, description="标的 ID")
    payload: dict[str, Any] = Field(default_factory=dict, description="审计载荷内容")
    created_at: str = Field(default="", description="创建时间 (ISO 8601)")

    model_config = ConfigDict(strict=True, extra="ignore")


def _parse_payload(raw: object) -> dict[str, Any]:
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

    run_id: str = Field(description="运行 ID")
    dates: list[str] = Field(default_factory=list, description="日期序列 (YYYY-MM-DD)")
    navs: list[float] = Field(default_factory=list, description="净值序列")
    benchmark_return: float | None = Field(default=None, description="基准收益率(%)")

    model_config = ConfigDict(strict=True, extra="ignore")


def _coerce_impact_model(v: object) -> ImpactModel:
    """Coerce string or ImpactModel to ImpactModel (for Pydantic strict mode)."""
    if isinstance(v, ImpactModel):
        return v
    if isinstance(v, str):
        try:
            return ImpactModel(v)
        except ValueError:
            valid = [m.value for m in ImpactModel]
            msg = f"非法 impact_model 值: {v!r}, 合法值: {valid}"
            raise ValueError(msg) from None
    msg = f"impact_model must be str or ImpactModel, got {type(v).__name__}"
    raise TypeError(msg)


class CostConfigRequest(BaseModel):
    """成本模型配置请求 — A 股标准费率默认值."""

    commission_rate: float = Field(
        default=_DEFAULT_COMMISSION_RATE,
        ge=0,
        description="佣金费率",
    )
    commission_min: float = Field(
        default=_DEFAULT_COMMISSION_MIN,
        ge=0,
        description="最低佣金(元)",
    )
    stamp_duty_rate: float = Field(
        default=_DEFAULT_STAMP_DUTY_RATE,
        ge=0,
        description="印花税税率(卖出)",
    )
    slippage_bps: float = Field(
        default=_DEFAULT_SLIPPAGE_BPS,
        ge=0,
        description="滑点(bps)",
    )
    impact_model: ImpactModel = Field(
        default=ImpactModel.NONE,
        description="冲击成本模型",
    )

    model_config = ConfigDict(strict=True, extra="ignore")

    @field_validator("impact_model", mode="before")
    @classmethod
    def _validate_impact_model(cls, v: object) -> ImpactModel:
        return _coerce_impact_model(v)


class CreateBacktestRunRequest(BaseModel):
    """创建回测运行请求."""

    strategy_id: str = Field(..., min_length=1, description="策略 ID")
    start_date: str = Field(..., min_length=1, description="起始日期 (YYYY-MM-DD)")
    end_date: str = Field(..., min_length=1, description="结束日期 (YYYY-MM-DD)")
    initial_cash: float = Field(
        default=DEFAULT_INITIAL_CASH,
        gt=0,
        description="初始资金",
    )
    parameter_overrides: list[str] = Field(default_factory=list, description="参数覆盖")
    cost_config: CostConfigRequest | None = Field(
        default=None,
        description="成本模型配置",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class BacktestRunTriggerResponse(BaseModel):
    """回测触发响应."""

    run_id: str
    strategy_id: str
    status: str = "pending"

    model_config = ConfigDict(strict=True, extra="ignore")


class CancelRunResponse(BaseModel):
    """取消运行响应."""

    run_id: str
    status: str = "cancelled"

    model_config = ConfigDict(strict=True, extra="ignore")


class RetryRunResponse(BaseModel):
    """重试运行响应."""

    run_id: str
    parent_run_id: str
    status: str = "pending"

    model_config = ConfigDict(strict=True, extra="ignore")


__all__ = [
    "AuditRecordResponse",
    "BacktestRunTriggerResponse",
    "BenchmarkNavResponse",
    "CancelRunResponse",
    "CostConfigRequest",
    "CreateBacktestRunRequest",
    "RetryRunResponse",
    "RunResponse",
    "RunsQueryParams",
    "TradeResponse",
    "to_audit_record_response",
]
