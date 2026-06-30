"""Catalog source fallback policy API models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CatalogSourceFallbackPolicyPreviewResponse(BaseModel):
    """Read-only source fallback policy preview response."""

    dataset_id: str = Field(description="数据集 ID")
    namespace: str = Field(description="Catalog namespace")
    trade_date: str = Field(description="交易日期")
    default_source: str = Field(description="DatasetMetadata 默认来源")
    selected_source: str = Field(description="source=auto 当前会选择的来源")
    recommended_source: str | None = Field(
        default=None,
        description="后端建议使用的来源; blocked 时为空",
    )
    selected_freshness_status: str = Field(description="selected source freshness 状态")
    policy_status: str = Field(description="fallback policy preview 状态")
    recommended_actions: list[str] = Field(
        default_factory=list,
        description="后端建议的下一步 action codes",
    )
    approval_required: bool = Field(description="是否需要人工审批或复核")
    execution_allowed: bool = Field(
        description="当前 source=auto 结果是否可进入后端执行编排",
    )
    reason_codes: list[str] = Field(
        default_factory=list,
        description="支撑该 preview 决策的 reason/blocker codes",
    )
    fallback_sources: list[str] = Field(
        default_factory=list,
        description="该数据集支持的非默认候选来源",
    )
    unsupported_sources: list[str] = Field(
        default_factory=list,
        description="本次可用来源中不被该数据集 metadata 支持的来源",
    )
    source_selection_status: str = Field(
        description="source=auto 选中来源是否可用于后端编排",
    )
    source_selection_blockers: list[str] = Field(
        default_factory=list,
        description="阻塞 source=auto 编排的结构化原因代码",
    )
    latest_revocation_reason: str | None = Field(
        default=None,
        description="最近一次数据集晋级撤销原因分类",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceFallbackPolicyStatusCountResponse(BaseModel):
    """Aggregated fallback-policy preview count by status."""

    status: str = Field(description="fallback policy preview 状态")
    count: int = Field(description="该状态覆盖的 preview 数量")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceFallbackPolicyActionCountResponse(BaseModel):
    """Aggregated fallback-policy preview count by recommended action."""

    action: str = Field(description="后端建议的下一步 action code")
    count: int = Field(description="该 action 覆盖的 preview 数量")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceFallbackPolicySummaryResponse(BaseModel):
    """Aggregated source fallback policy preview response."""

    dataset_ids: list[str] = Field(description="聚合的数据集 ID")
    trade_dates: list[str] = Field(description="聚合的交易日期")
    available_sources: list[str] = Field(description="参与 source=auto 判断的来源")
    total_previews: int = Field(description="单项 fallback policy preview 数量")
    approval_required_count: int = Field(
        description="需要审批或人工复核的 preview 数量"
    )
    execution_allowed_count: int = Field(
        description="允许进入后端执行编排的 preview 数量"
    )
    policy_status_counts: list[CatalogSourceFallbackPolicyStatusCountResponse] = Field(
        description="按 fallback policy preview 状态聚合的数量",
    )
    recommended_action_counts: list[CatalogSourceFallbackPolicyActionCountResponse] = (
        Field(
            default_factory=list,
            description="按 recommended action 聚合的数量",
        )
    )
    previews: list[CatalogSourceFallbackPolicyPreviewResponse] = Field(
        description="明细 fallback policy previews",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceFallbackPolicyDraftRequest(BaseModel):
    """Request durable draft state for one source fallback policy decision."""

    dataset_id: str = Field(description="数据集 ID")
    namespace: str = Field(description="Catalog namespace")
    trade_date: str = Field(description="交易日期")
    default_source: str = Field(description="DatasetMetadata 默认来源")
    selected_source: str = Field(description="source=auto 当前选择的来源")
    recommended_source: str | None = Field(
        default=None,
        description="后端建议持久化的 fallback 来源",
    )
    created_by: str = Field(description="创建 draft policy 的 operator/backend actor")
    recommended_actions: list[str] = Field(
        default_factory=list,
        description="后端建议的下一步 action codes",
    )
    reason_codes: list[str] = Field(
        default_factory=list,
        description="支撑该 policy draft 的 reason/blocker codes",
    )
    fallback_sources: list[str] = Field(
        default_factory=list,
        description="候选 fallback sources",
    )
    unsupported_sources: list[str] = Field(
        default_factory=list,
        description="当前请求中不被 dataset metadata 支持的来源",
    )
    source_selection_status: str = Field(description="source=auto readiness 状态")
    source_selection_blockers: list[str] = Field(
        default_factory=list,
        description="阻塞 source=auto 编排的结构化原因代码",
    )
    approval_required: bool = Field(description="是否需要人工审批或复核")
    execution_allowed: bool = Field(description="是否允许进入后端执行编排")
    notes: str | None = Field(default=None, description="draft policy 备注")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceFallbackPolicyStateResponse(BaseModel):
    """Current source fallback policy state response."""

    policy_id: str = Field(description="stable source fallback policy ID")
    dataset_id: str = Field(description="数据集 ID")
    namespace: str = Field(description="Catalog namespace")
    trade_date: str = Field(description="交易日期")
    default_source: str = Field(description="DatasetMetadata 默认来源")
    selected_source: str = Field(description="source=auto 当前选择的来源")
    recommended_source: str | None = Field(
        default=None,
        description="后端建议持久化的 fallback 来源",
    )
    status: str = Field(description="current policy lifecycle status")
    created_by: str = Field(description="创建 policy 的 operator/backend actor")
    created_at: str = Field(description="policy 创建时间")
    recommended_actions: list[str] = Field(
        default_factory=list,
        description="后端建议的下一步 action codes",
    )
    reason_codes: list[str] = Field(
        default_factory=list,
        description="支撑该 policy 的 reason/blocker codes",
    )
    fallback_sources: list[str] = Field(
        default_factory=list,
        description="候选 fallback sources",
    )
    unsupported_sources: list[str] = Field(
        default_factory=list,
        description="当前请求中不被 dataset metadata 支持的来源",
    )
    source_selection_status: str = Field(description="source=auto readiness 状态")
    source_selection_blockers: list[str] = Field(
        default_factory=list,
        description="阻塞 source=auto 编排的结构化原因代码",
    )
    approval_required: bool = Field(description="是否需要人工审批或复核")
    execution_allowed: bool = Field(description="是否允许进入后端执行编排")
    notes: str | None = Field(default=None, description="policy 备注")
    decided_by: str | None = Field(default=None, description="decision actor")
    decided_at: str | None = Field(default=None, description="decision time")
    decision_notes: str | None = Field(default=None, description="decision notes")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceFallbackPolicyLifecycleRequest(BaseModel):
    """Request a source fallback policy lifecycle transition."""

    actor: str = Field(description="operator/backend actor performing transition")
    notes: str | None = Field(default=None, description="transition notes")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceFallbackPolicyEventResponse(BaseModel):
    """Append-only source fallback policy audit event response."""

    policy_id: str = Field(description="stable source fallback policy ID")
    action: str = Field(description="audit event action")
    actor: str = Field(description="operator/backend actor that wrote the event")
    action_at: str = Field(description="audit event time")
    status: str = Field(description="policy status after the event")
    notes: str | None = Field(default=None, description="audit event notes")

    model_config = ConfigDict(strict=True, extra="ignore")
