"""API 响应通用模型."""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from ditto_application.queries.dataset_coverage import DatasetCoverageView
from pydantic import BaseModel, ConfigDict, Field, computed_field

T = TypeVar("T")

# 读取时间语义词汇表（#628 P4）：
# - latest_available: 返回库内现存行，无 PIT 过滤——受限研究，不得包装为严格 PIT
# - pit_asof: 返回 as_of 可见版本（日粒度 as_of = 上海日终，date 精度知识当日
#   全天不视为部分可见；修订多版本收敛到最新可见 knowledge 版本）
# - frozen_snapshot: 快照重放，逐字段稳定，绑定 snapshot 身份
ReadSemantics = Literal["latest_available", "pit_asof", "frozen_snapshot"]


class DataCoverageInfo(BaseModel):
    """数据集覆盖限制快照（#622 测量证据投影，测量时点非实时；#628 限制传播）."""

    model_config = ConfigDict(strict=True, extra="ignore")

    dataset: str = Field(description="数据集 ID")
    domain: str = Field(description="数据域")
    status: Literal["ready", "partial", "empty"] = Field(
        description=(
            "ready=预期范围完整且当前 / partial=起点末端味道品种有缺 / empty=本地零行"
        )
    )
    measured_start: str | None = Field(
        default=None, description="实测覆盖起点（ISO 日期）"
    )
    measured_end: str | None = Field(
        default=None, description="实测覆盖终点（ISO 日期）"
    )
    gaps: tuple[str, ...] = Field(
        default=(), description="缺口与限制说明（源端权限、末端滞后、制度分段等）"
    )
    notes: str | None = Field(default=None, description="测量备注")
    measured_at: str = Field(description="测量时点（ISO 日期；非实时）")
    knowledge_axis: (
        Literal["provider_anchor", "derived_t1", "same_day", "observation"] | None
    ) = Field(
        default=None,
        description=(
            "知识轴分类：provider_anchor=公告锚(日终语义) / derived_t1=T+1 推导 / "
            "same_day=即日 / observation=观察日(不宣称公告可知性)；None=未分类"
        ),
    )

    @classmethod
    def from_view(cls, view: DatasetCoverageView) -> DataCoverageInfo:
        """从 application 覆盖限制 View 构建（状态词表已由 facade 收敛为 Literal）."""
        return cls(
            dataset=view.dataset,
            domain=view.domain,
            status=view.status,
            measured_start=view.measured_start,
            measured_end=view.measured_end,
            gaps=view.gaps,
            notes=view.notes,
            measured_at=view.measured_at.isoformat(),
            knowledge_axis=view.knowledge_axis,
        )


class PaginationRequest(BaseModel):
    """
    分页请求模型.

    Attributes:
        limit: 每页数量, 默认 100, 范围 1-1000.
        offset: 偏移量, 默认 0, 非负整数.

    """

    limit: int = Field(default=20, ge=1, le=100, description="每页数量, 范围 1-100")
    offset: int = Field(default=0, ge=0, description="偏移量, 非负整数")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class PaginationResponse(BaseModel):
    """
    分页响应模型.

    Attributes:
        total: 总记录数.
        limit: 每页数量.
        offset: 当前偏移量.
        has_more: 是否有更多数据(计算字段).

    """

    total: int = Field(ge=0, description="总记录数")
    limit: int = Field(ge=1, description="每页数量")
    offset: int = Field(ge=0, description="当前偏移量")

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )

    @computed_field
    @property
    def has_more(self) -> bool:
        """判断是否还有更多数据."""
        return self.offset + self.limit < self.total


class APIResponse(BaseModel, Generic[T]):  # noqa: UP046  # Pydantic requires Generic[T]
    """
    统一 API 响应模型.

    泛型模型, 用于包装任意类型的数据响应.

    Attributes:
        data: 响应数据.
        pagination: 分页信息(可选).

    """

    data: T = Field(description="响应数据")
    pagination: PaginationResponse | None = Field(
        default=None, description="分页信息(可选)"
    )
    read_semantics: ReadSemantics | None = Field(
        default=None,
        description=(
            "读取时间语义（#628）：latest_available=现存行无 PIT 过滤(受限研究) / "
            "pit_asof=as_of 可见版本(日粒度=上海日终) / frozen_snapshot=快照重放"
        ),
    )

    model_config = ConfigDict(
        strict=True,
        extra="ignore",
    )


class ErrorResponse(BaseModel):
    """
    Standard error response model for API errors.

    Used for external API responses, so using Pydantic BaseModel (not frozen dataclass).
    """

    success: Literal[False] = False
    status_code: int
    error: str
    detail: str | None = None
    error_code: str | None = None
    request_id: str | None = None
    timestamp: float | None = None

    model_config = ConfigDict(
        # API 响应模型: 必须 strict=True 防止类型强制转换
        strict=True,
        # 忽略额外字段, 确保向后兼容
        extra="ignore",
    )
