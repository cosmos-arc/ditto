"""Maturity governance API response models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ditto_apps.models.ingestion import (
    DatasetMaturitySummaryResponse,
    MaturityPromotionRevocationReason,
    PromotionCriterionCountResponse,
    PromotionStatusCountResponse,
)


class MaturityGovernanceDatasetResponse(BaseModel):
    """Unified dataset maturity governance report item."""

    dataset_id: str = Field(description="数据集 ID")
    current_maturity: str | None = Field(
        default=None,
        description="当前有效成熟度",
    )
    catalog_freshness_status: str | None = Field(
        default=None,
        description="Catalog freshness 状态",
    )
    promotion_status: str = Field(description="晋级评估状态")
    active_maturity_promotion: bool = Field(
        description="当前是否存在 active maturity promotion override",
    )
    has_maturity_warning: bool = Field(description="当前状态是否有 maturity 警告")
    required_criteria: list[str] = Field(
        default_factory=list,
        description="晋级所需条件",
    )
    satisfied_criteria: list[str] = Field(
        default_factory=list,
        description="已满足条件",
    )
    latest_revocation_reason: MaturityPromotionRevocationReason | None = Field(
        default=None,
        description="最近一次晋级撤销原因分类",
    )
    latest_revoked_by: str | None = Field(
        default=None,
        description="最近一次晋级撤销人或撤销主体",
    )
    latest_revoked_at: str | None = Field(
        default=None,
        description="最近一次晋级撤销时间",
    )
    missing_criteria: list[str] = Field(
        default_factory=list,
        description="当前缺失的晋级条件",
    )
    rejected_criteria: list[str] = Field(
        default_factory=list,
        description="已审核但未通过的晋级条件",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class MaturityGovernanceAttentionItemResponse(BaseModel):
    """Maturity governance item requiring operator attention."""

    dataset_id: str = Field(description="数据集 ID")
    attention_reasons: list[str] = Field(
        default_factory=list,
        description="需要后端消费者关注该数据集的结构化原因代码",
    )
    attention_severity: str = Field(
        description="maturity governance attention severity (critical/warning/info)",
    )
    dataset: MaturityGovernanceDatasetResponse = Field(
        description="对应的数据集成熟度治理明细",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class MaturityGovernanceAttentionReasonCountResponse(BaseModel):
    """Maturity governance attention reason count response."""

    reason: str = Field(description="maturity governance attention reason code")
    count: int = Field(description="该 reason 覆盖的数据集数量")

    model_config = ConfigDict(strict=True, extra="ignore")


class MaturityGovernanceAttentionSeverityCountResponse(BaseModel):
    """Maturity governance attention severity count response."""

    severity: str = Field(description="maturity governance attention severity")
    count: int = Field(description="该 severity 覆盖的数据集数量")

    model_config = ConfigDict(strict=True, extra="ignore")


class MaturityGovernanceSourceFallbackPolicyEffectCountResponse(BaseModel):
    """Maturity governance count by source fallback policy effect."""

    policy_id: str = Field(description="触发 source fallback effect 的 policy ID")
    policy_status: str = Field(description="触发 effect 的 policy lifecycle 状态")
    catalog_selected_source: str = Field(
        description="Catalog freshness 策略原本选择的来源",
    )
    effective_selected_source: str = Field(
        description="应用 active fallback policy 后的最终来源",
    )
    count: int = Field(description="该 policy effect 影响的 source decision 数量")

    model_config = ConfigDict(strict=True, extra="ignore")


class MaturityGovernanceReportResponse(BaseModel):
    """Unified maturity governance backend report."""

    dataset_count: int = Field(description="报告覆盖的数据集数量")
    warning_count: int = Field(description="带 maturity warning 的数据集数量")
    promotable_count: int = Field(description="晋级评估 ready 的数据集数量")
    active_promotion_count: int = Field(
        description="当前存在 maturity promotion override 的数据集数量",
    )
    revoked_promotion_count: int = Field(
        description="存在最近晋级撤销上下文的数据集数量",
    )
    maturity_summary: list[DatasetMaturitySummaryResponse] = Field(
        description="按当前 maturity 聚合的状态摘要",
    )
    promotion_status_counts: list[PromotionStatusCountResponse] = Field(
        description="按晋级评估状态聚合的数据集数量",
    )
    missing_criteria_counts: list[PromotionCriterionCountResponse] = Field(
        default_factory=list,
        description="按缺失晋级条件聚合的数据集数量",
    )
    rejected_criteria_counts: list[PromotionCriterionCountResponse] = Field(
        default_factory=list,
        description="按 rejected 晋级条件聚合的数据集数量",
    )
    datasets: list[MaturityGovernanceDatasetResponse] = Field(
        description="各数据集成熟度治理明细",
    )
    attention_reason_counts: list[MaturityGovernanceAttentionReasonCountResponse] = (
        Field(
            default_factory=list,
            description="按 maturity governance attention reason 聚合的数据集数量",
        )
    )
    attention_severity_counts: list[
        MaturityGovernanceAttentionSeverityCountResponse
    ] = Field(
        default_factory=list,
        description="按 maturity governance attention severity 聚合的数据集数量",
    )
    source_fallback_policy_effect_counts: list[
        MaturityGovernanceSourceFallbackPolicyEffectCountResponse
    ] = Field(
        default_factory=list,
        description=(
            "按 active source fallback policy effect 聚合的 source decision 数量"
        ),
    )
    attention_required: list[MaturityGovernanceAttentionItemResponse] = Field(
        default_factory=list,
        description="带有结构化 attention reason 的数据集治理明细",
    )

    model_config = ConfigDict(strict=True, extra="ignore")
