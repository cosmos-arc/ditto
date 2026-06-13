"""Catalog remediation API models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ditto_apps.models.ingestion import CatalogSourceFallbackPolicyEffectResponse


class CatalogRemediationSeverityCountResponse(BaseModel):
    """Catalog remediation backlog count by severity."""

    severity: str = Field(description="remediation severity")
    count: int = Field(description="该 severity 的 backlog item 数量")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogRemediationSourceCountResponse(BaseModel):
    """Catalog remediation backlog count by source report."""

    source: str = Field(description="backlog item 来源报告")
    count: int = Field(description="该来源报告产生的 backlog item 数量")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogRemediationReasonCountResponse(BaseModel):
    """Catalog remediation backlog count by source and reason."""

    source: str = Field(description="backlog item 来源报告")
    reason: str = Field(description="结构化 reason code")
    count: int = Field(description="该 reason 的 backlog item 数量")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogRemediationSourceFallbackPolicyEffectCountResponse(BaseModel):
    """Catalog remediation backlog count by source fallback policy effect."""

    policy_id: str = Field(description="触发 source fallback effect 的 policy ID")
    policy_status: str = Field(description="触发 effect 的 policy lifecycle 状态")
    catalog_selected_source: str = Field(
        description="Catalog freshness 策略原本选择的来源",
    )
    effective_selected_source: str = Field(
        description="应用 active fallback policy 后的最终来源",
    )
    count: int = Field(description="该 policy effect 影响的 backlog item 数量")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogRemediationEvidenceRequirementResponse(BaseModel):
    """Evidence requirement for one remediation item."""

    requirement_id: str = Field(description="稳定 evidence requirement ID")
    source: str = Field(description="requirement 来源")
    status: str = Field(description="requirement 当前状态")
    description: str = Field(description="requirement 描述")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogRemediationApprovalIntentResponse(BaseModel):
    """Backend next-step intent for one remediation action."""

    action: str = Field(description="稳定 remediation action code")
    intent_type: str = Field(description="intent 类型: read/write/manual")
    method: str | None = Field(default=None, description="HTTP method")
    path: str | None = Field(default=None, description="后端 API path")
    request_template: dict[str, object] = Field(
        default_factory=dict,
        description="调用后端 API 所需 request template",
    )
    required_operator_inputs: list[str] = Field(
        default_factory=list,
        description="执行该 intent 前需要 operator 填写的字段",
    )
    notes: str | None = Field(default=None, description="intent 说明")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogRemediationApprovalRequest(BaseModel):
    """Request persistent approval state for one remediation intent."""

    item_id: str = Field(description="remediation backlog item ID")
    action: str = Field(description="remediation action code")
    requested_by: str = Field(description="requesting operator or system")
    intent_type: str = Field(description="intent type: read/write/manual")
    method: str | None = Field(default=None, description="target backend method")
    path: str | None = Field(default=None, description="target backend path")
    request_payload: dict[str, object] = Field(
        default_factory=dict,
        description="target backend request payload snapshot",
    )
    notes: str | None = Field(default=None, description="approval request notes")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogRemediationApprovalDecisionRequest(BaseModel):
    """Approve or reject a pending remediation approval request."""

    decision: Literal["approved", "rejected"] = Field(
        description="approved or rejected"
    )
    decided_by: str = Field(description="decision operator or system")
    notes: str | None = Field(default=None, description="decision notes")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogRemediationApprovalExecutionRequest(BaseModel):
    """Execute an approved remediation action."""

    executed_by: str = Field(description="execution operator or backend actor")
    notes: str | None = Field(default=None, description="execution notes")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogRemediationApprovalResponse(BaseModel):
    """Current remediation approval state response."""

    approval_id: str = Field(description="stable remediation approval ID")
    item_id: str = Field(description="remediation backlog item ID")
    action: str = Field(description="remediation action code")
    status: str = Field(description="current approval status")
    requested_by: str = Field(description="requesting operator or system")
    requested_at: str = Field(description="approval request time")
    intent_type: str = Field(description="intent type: read/write/manual")
    method: str | None = Field(default=None, description="target backend method")
    path: str | None = Field(default=None, description="target backend path")
    request_payload: dict[str, object] = Field(
        default_factory=dict,
        description="target backend request payload snapshot",
    )
    notes: str | None = Field(default=None, description="approval request notes")
    decided_by: str | None = Field(default=None, description="decision actor")
    decided_at: str | None = Field(default=None, description="decision time")
    decision_notes: str | None = Field(default=None, description="decision notes")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogRemediationApprovalEventResponse(BaseModel):
    """Append-only remediation approval audit event response."""

    approval_id: str = Field(description="stable remediation approval ID")
    action: str = Field(description="audit event action")
    actor: str = Field(description="operator or backend actor that wrote the event")
    action_at: str = Field(description="audit event time")
    status: str = Field(description="approval status after the event")
    notes: str | None = Field(default=None, description="audit event notes")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogRemediationActionExecutionResponse(BaseModel):
    """Approved remediation action execution response."""

    approval_id: str = Field(description="stable remediation approval ID")
    action: str = Field(description="remediation action code")
    status: str = Field(description="execution status: success/skipped/failed")
    executed_by: str = Field(description="execution operator or backend actor")
    executed_at: str = Field(description="execution time")
    result_payload: dict[str, object] = Field(
        default_factory=dict,
        description="backend action result payload",
    )
    notes: str | None = Field(default=None, description="execution notes")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogRemediationApprovalExecutionResponse(BaseModel):
    """Completed remediation approval state plus execution evidence."""

    approval: CatalogRemediationApprovalResponse = Field(
        description="current approval state after execution",
    )
    execution: CatalogRemediationActionExecutionResponse = Field(
        description="backend execution evidence",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogRemediationItemResponse(BaseModel):
    """One backend-owned remediation backlog item."""

    item_id: str = Field(description="稳定 backlog item ID")
    source: str = Field(description="backlog item 来源报告")
    dataset_id: str = Field(description="数据集 ID")
    namespace: str = Field(description="Catalog namespace")
    severity: str = Field(description="remediation severity")
    reasons: list[str] = Field(
        default_factory=list,
        description="触发该 backlog item 的结构化 reason codes",
    )
    suggested_actions: list[str] = Field(
        default_factory=list,
        description="后端建议的稳定修复动作代码",
    )
    trade_date: str | None = Field(default=None, description="交易日期")
    run_id: str | None = Field(default=None, description="关联 backtest run ID")
    side: str | None = Field(default=None, description="lineage asset side")
    partition_keys: list[str] = Field(
        default_factory=list,
        description="Catalog/lineage asset partition keys",
    )
    default_source: str | None = Field(default=None, description="默认数据源")
    selected_source: str | None = Field(
        default=None,
        description="source=auto 当前选择的数据源",
    )
    fallback_sources: list[str] = Field(
        default_factory=list,
        description="source-health 当前候选 fallback 数据源",
    )
    source_fallback_policy_effect: CatalogSourceFallbackPolicyEffectResponse | None = (
        Field(
            default=None,
            description=(
                "active source fallback policy 对该 remediation item 的影响证据"
            ),
        )
    )
    source_selection_status: str | None = Field(
        default=None,
        description="source=auto 选源 readiness 状态",
    )
    source_selection_blockers: list[str] = Field(
        default_factory=list,
        description="阻塞 source=auto 选源执行的稳定 blocker codes",
    )
    current_maturity: str | None = Field(default=None, description="当前 maturity")
    promotion_status: str | None = Field(default=None, description="晋级评估状态")
    catalog_status: str | None = Field(default=None, description="lineage catalog 状态")
    freshness_status: str | None = Field(default=None, description="freshness 状态")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogRemediationItemDetailResponse(BaseModel):
    """Detailed backend-owned remediation item response."""

    generated_at: str = Field(description="detail 生成时间")
    item: CatalogRemediationItemResponse = Field(description="backlog item")
    summary: str = Field(description="后端生成的 remediation 摘要")
    evidence_requirements: list[CatalogRemediationEvidenceRequirementResponse] = Field(
        default_factory=list,
        description="推进该 remediation 前需要补齐或复核的证据",
    )
    approval_intents: list[CatalogRemediationApprovalIntentResponse] = Field(
        default_factory=list,
        description="可由后端消费者发起的下一步审批/证据 intent",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogRemediationBacklogResponse(BaseModel):
    """Action-oriented catalog remediation backlog response."""

    generated_at: str = Field(description="backlog 生成时间")
    dataset_ids: list[str] = Field(description="报告覆盖的数据集 ID")
    trade_dates: list[str] = Field(description="报告覆盖的交易日期")
    available_sources: list[str] = Field(description="参与 source=auto 判断的来源")
    run_id: str | None = Field(default=None, description="可选 backtest run ID")
    total_items: int = Field(description="backlog item 总数")
    severity_counts: list[CatalogRemediationSeverityCountResponse] = Field(
        description="按 severity 聚合的 backlog item 数量",
    )
    source_counts: list[CatalogRemediationSourceCountResponse] = Field(
        default_factory=list,
        description="按来源报告聚合的 backlog item 数量",
    )
    reason_counts: list[CatalogRemediationReasonCountResponse] = Field(
        default_factory=list,
        description="按来源报告和 reason 聚合的 backlog item 数量",
    )
    source_fallback_policy_effect_counts: list[
        CatalogRemediationSourceFallbackPolicyEffectCountResponse
    ] = Field(
        default_factory=list,
        description="按 active source fallback policy effect 聚合的 backlog item 数量",
    )
    items: list[CatalogRemediationItemResponse] = Field(
        description="按 severity 排序的 remediation backlog items",
    )

    model_config = ConfigDict(strict=True, extra="ignore")
