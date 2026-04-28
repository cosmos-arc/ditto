"""摄取状态 API 模型."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DatasetStatusResponse(BaseModel):
    """单个数据集的摄取状态."""

    dataset: str = Field(description="数据集名称")
    latest_date: str | None = Field(default=None, description="最新成功摄取日期")
    latest_status: str | None = Field(
        default=None, description="最新摄取状态 (success/failed)"
    )
    record_count: int = Field(default=0, description="最新成功摄取的记录数")
    last_attempt: str | None = Field(default=None, description="最近一次尝试时间")

    model_config = ConfigDict(strict=True, extra="ignore")


class IngestionStatusResponse(BaseModel):
    """摄取状态汇总响应."""

    datasets: list[DatasetStatusResponse] = Field(description="各数据集状态")

    model_config = ConfigDict(strict=True, extra="ignore")


class IngestionHistoryItem(BaseModel):
    """单条摄取历史记录."""

    dataset: str = Field(description="数据集名称")
    trade_date: str = Field(description="交易日期")
    status: str = Field(description="摄取状态")
    rows: int | None = Field(default=None, description="记录数")
    error_message: str | None = Field(default=None, description="错误信息")
    attempts: int = Field(default=1, description="尝试次数")
    last_attempt_at: str | None = Field(default=None, description="最后尝试时间")

    model_config = ConfigDict(strict=True, extra="ignore")


class DQDatasetSummary(BaseModel):
    """单个数据集的 DQ 检查摘要."""

    dataset: str = Field(description="数据集名称")
    total_checks: int = Field(default=0, description="总检查数")
    passed: int = Field(default=0, description="通过数")
    warnings: int = Field(default=0, description="警告数")
    errors: int = Field(default=0, description="错误数")

    model_config = ConfigDict(strict=True, extra="ignore")


class DQSummaryResponse(BaseModel):
    """DQ 检查摘要响应."""

    datasets: list[DQDatasetSummary] = Field(description="各数据集 DQ 摘要")

    model_config = ConfigDict(strict=True, extra="ignore")
