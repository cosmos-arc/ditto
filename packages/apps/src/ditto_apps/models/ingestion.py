"""摄取状态 API 模型."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type MaturityPromotionRevocationReason = Literal[
    "policy_regression",
    "failed_revalidation",
    "manual_override",
    "evidence_invalidated",
]


class DatasetStatusResponse(BaseModel):
    """单个数据集的摄取状态."""

    dataset: str = Field(description="数据集名称")
    latest_date: str | None = Field(default=None, description="最新成功摄取日期")
    latest_status: str | None = Field(
        default=None, description="最新摄取状态 (success/failed)"
    )
    dataset_maturity: str | None = Field(
        default=None,
        description="数据集能力成熟度 (initial-focus/experimental/reserved)",
    )
    dataset_maturity_warning: str | None = Field(
        default=None,
        description="数据集能力成熟度警告",
    )
    dataset_promotion_criteria: list[str] = Field(
        default_factory=list,
        description="数据集晋级到运行时焦点能力前需满足的条件",
    )
    dataset_promotion_status: str | None = Field(
        default=None,
        description="数据集晋级评估状态 (not_applicable/blocked/ready)",
    )
    dataset_promotion_missing_criteria: list[str] = Field(
        default_factory=list,
        description="当前缺失的晋级证据条件",
    )
    dataset_promotion_satisfied_criteria: list[str] = Field(
        default_factory=list,
        description="已满足的晋级证据条件",
    )
    dataset_promotion_rejected_criteria: list[str] = Field(
        default_factory=list,
        description="已审核但未通过的晋级证据条件",
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
    record_count: int = Field(default=0, description="最新成功摄取的记录数")
    last_attempt: str | None = Field(default=None, description="最近一次尝试时间")
    catalog_freshness_at: str | None = Field(
        default=None,
        description="Catalog 记录的最新鲜度时间",
    )
    catalog_storage_uri: str | None = Field(
        default=None,
        description="Catalog 最新资产存储 URI",
    )
    catalog_schema_hash: str | None = Field(
        default=None,
        description="Catalog 最新资产 schema 指纹",
    )
    catalog_row_count: int | None = Field(
        default=None,
        description="Catalog 最新资产记录数",
    )
    catalog_freshness_status: str | None = Field(
        default=None,
        description="Catalog freshness SLA 状态 (fresh/stale/missing/not_applicable)",
    )
    catalog_freshness_sla_hours: int | None = Field(
        default=None,
        description="Catalog freshness SLA 小时数",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class DatasetMaturitySummaryResponse(BaseModel):
    """Maturity-aware dataset status summary."""

    maturity: str = Field(description="能力成熟度")
    dataset_count: int = Field(default=0, description="数据集数量")
    fresh_count: int = Field(default=0, description="Catalog freshness 为 fresh 的数量")
    stale_count: int = Field(default=0, description="Catalog freshness 为 stale 的数量")
    missing_count: int = Field(
        default=0,
        description="Catalog freshness 为 missing 的数量",
    )
    not_applicable_count: int = Field(
        default=0,
        description="Catalog freshness 不适用的数量",
    )
    failed_count: int = Field(default=0, description="最新摄取状态为 failed 的数量")
    warning_count: int = Field(default=0, description="包含 maturity 警告的数据集数量")
    promotion_ready_count: int = Field(default=0, description="晋级评估 ready 数量")
    promotion_blocked_count: int = Field(default=0, description="晋级评估 blocked 数量")

    model_config = ConfigDict(strict=True, extra="ignore")


class IngestionStatusResponse(BaseModel):
    """摄取状态汇总响应."""

    datasets: list[DatasetStatusResponse] = Field(description="各数据集状态")
    maturity_summary: list[DatasetMaturitySummaryResponse] = Field(
        default_factory=list,
        description="按能力成熟度分组的摄取与 freshness 摘要",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class PromotionEvidenceReviewRequest(BaseModel):
    """Reviewer decision request for one dataset promotion criterion."""

    dataset_id: str = Field(description="数据集 ID")
    criterion: str = Field(description="被审核的晋级条件")
    evidence_uri: str = Field(description="审核证据 URI")
    reviewed_by: str = Field(description="审核人或审核主体")
    passed: bool = Field(default=True, description="该条件是否审核通过")
    notes: str | None = Field(default=None, description="审核备注")

    model_config = ConfigDict(strict=True, extra="ignore")


class PromotionEvidenceReviewResponse(BaseModel):
    """Promotion review result response."""

    dataset_id: str = Field(description="数据集 ID")
    reviewed_criterion: str = Field(description="本次审核的晋级条件")
    evidence_uri: str = Field(description="审核证据 URI")
    reviewed_by: str = Field(description="审核人或审核主体")
    passed: bool = Field(description="该条件是否审核通过")
    reviewed_at: str = Field(description="审核时间")
    promotion_status: str = Field(description="审核后晋级评估状态")
    missing_criteria: list[str] = Field(default_factory=list, description="缺失条件")
    satisfied_criteria: list[str] = Field(default_factory=list, description="通过条件")
    rejected_criteria: list[str] = Field(
        default_factory=list,
        description="已审核但未通过条件",
    )
    metadata_promoted: bool = Field(description="本次审核是否触发 metadata 晋级")
    dataset_maturity_before: str = Field(description="审核前数据集成熟度")
    dataset_maturity_after: str = Field(description="审核后数据集成熟度")

    model_config = ConfigDict(strict=True, extra="ignore")


class PromotionStatusCountResponse(BaseModel):
    """Promotion readiness status count."""

    status: str = Field(description="晋级评估状态")
    count: int = Field(description="该状态的数据集数量")

    model_config = ConfigDict(strict=True, extra="ignore")


class PromotionCriterionCountResponse(BaseModel):
    """Promotion criterion occurrence count."""

    criterion: str = Field(description="晋级条件")
    count: int = Field(description="该条件出现次数")

    model_config = ConfigDict(strict=True, extra="ignore")


class PromotionReadinessSourceFallbackPolicyEffectCountResponse(BaseModel):
    """Promotion readiness count by source fallback policy effect."""

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


class PromotionReadinessItemResponse(BaseModel):
    """Dataset-level promotion readiness report item."""

    dataset_id: str = Field(description="数据集 ID")
    metadata_maturity: str | None = Field(
        default=None,
        description="DatasetMetadata 声明的原始 maturity",
    )
    current_maturity: str | None = Field(
        default=None,
        description="应用当前 maturity promotion override 后的 maturity",
    )
    promotion_status: str = Field(description="晋级评估状态")
    active_maturity_promotion: bool = Field(
        description="当前是否存在 active maturity promotion override",
    )
    required_criteria: list[str] = Field(
        default_factory=list,
        description="晋级所需条件",
    )
    satisfied_criteria: list[str] = Field(
        default_factory=list,
        description="已满足条件",
    )
    missing_criteria: list[str] = Field(
        default_factory=list,
        description="缺失条件",
    )
    rejected_criteria: list[str] = Field(
        default_factory=list,
        description="已审核但未通过条件",
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

    model_config = ConfigDict(strict=True, extra="ignore")


class PromotionReadinessReportResponse(BaseModel):
    """Aggregated dataset promotion readiness report."""

    dataset_count: int = Field(description="报告覆盖的数据集数量")
    promotable_count: int = Field(description="晋级评估 ready 的数据集数量")
    active_promotion_count: int = Field(
        description="当前存在 maturity promotion override 的数据集数量",
    )
    status_counts: list[PromotionStatusCountResponse] = Field(
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
    source_fallback_policy_effect_counts: list[
        PromotionReadinessSourceFallbackPolicyEffectCountResponse
    ] = Field(
        default_factory=list,
        description=(
            "按 active source fallback policy effect 聚合的 source decision 数量"
        ),
    )
    datasets: list[PromotionReadinessItemResponse] = Field(
        description="各数据集晋级评估明细",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class MaturityPromotionHistoryItem(BaseModel):
    """Dataset maturity promotion governance history item."""

    dataset_id: str = Field(description="数据集 ID")
    action: str = Field(description="治理动作 (promoted/revoked)")
    previous_maturity: str = Field(description="动作前成熟度")
    next_maturity: str = Field(description="动作后成熟度")
    actor: str = Field(description="操作人或操作主体")
    action_at: str | None = Field(default=None, description="操作时间")
    evidence_uri: str | None = Field(default=None, description="关联证据 URI")
    revocation_reason: MaturityPromotionRevocationReason | None = Field(
        default=None,
        description="撤销原因分类",
    )
    notes: str | None = Field(default=None, description="备注")

    model_config = ConfigDict(strict=True, extra="ignore")


class MaturityPromotionRevokeRequest(BaseModel):
    """Operator request to revoke a current maturity promotion override."""

    dataset_id: str = Field(description="数据集 ID")
    revoked_by: str = Field(description="撤销人或撤销主体")
    revocation_reason: MaturityPromotionRevocationReason = Field(
        description="撤销原因分类",
    )
    notes: str | None = Field(default=None, description="撤销备注")

    model_config = ConfigDict(strict=True, extra="ignore")


class MaturityPromotionRevokeResponse(BaseModel):
    """Result of revoking a dataset maturity promotion override."""

    dataset_id: str = Field(description="数据集 ID")
    revoked_by: str = Field(description="撤销人或撤销主体")
    revoked_at: str = Field(description="撤销时间")
    dataset_maturity_before: str = Field(description="撤销前数据集成熟度")
    dataset_maturity_after: str = Field(description="撤销后数据集成熟度")
    evidence_uri: str | None = Field(default=None, description="原晋级证据 URI")
    revocation_reason: MaturityPromotionRevocationReason | None = Field(
        default=None,
        description="撤销原因分类",
    )
    notes: str | None = Field(default=None, description="撤销备注")

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


class CatalogAssetRefResponse(BaseModel):
    """DataCatalog 资产身份响应."""

    dataset_id: str = Field(description="数据集 ID")
    namespace: str = Field(description="资产命名空间")
    partition_keys: list[str] = Field(
        default_factory=list,
        description="资产分区键",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSchemaResponse(BaseModel):
    """DataCatalog schema 指纹响应."""

    schema_hash: str = Field(description="Schema 指纹")
    row_count: int | None = Field(default=None, description="记录数")
    created_at: str | None = Field(default=None, description="Schema 观测时间")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogAssetResponse(BaseModel):
    """DataCatalog 资产元数据响应."""

    asset: CatalogAssetRefResponse = Field(description="资产身份")
    storage_uri: str = Field(description="存储 URI")
    schema_fingerprint: CatalogSchemaResponse = Field(description="Schema 指纹")
    source: str = Field(description="来源")
    freshness_at: str = Field(description="最新鲜度时间")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceHealthResponse(BaseModel):
    """DataCatalog source-level freshness evidence."""

    source: str = Field(description="来源名称")
    supported: bool = Field(description="该来源是否被数据集 metadata 支持")
    freshness_status: str = Field(
        description="该来源在指定交易日的 freshness 状态",
    )
    freshness_sla_hours: int | None = Field(
        default=None,
        description="该数据集 freshness SLA 小时数",
    )
    freshness_at: str | None = Field(
        default=None,
        description="Catalog freshness 时间",
    )
    storage_uri: str | None = Field(
        default=None,
        description="Catalog asset storage URI",
    )
    schema_hash: str | None = Field(
        default=None,
        description="Catalog asset schema hash",
    )
    row_count: int | None = Field(
        default=None,
        description="Catalog asset row count",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceFallbackPolicyEffectResponse(BaseModel):
    """Active source fallback policy effect evidence."""

    policy_id: str = Field(description="触发 source fallback effect 的 policy ID")
    policy_status: str = Field(description="触发 effect 的 policy lifecycle 状态")
    catalog_selected_source: str = Field(
        description="Catalog freshness 策略原本选择的来源",
    )
    effective_selected_source: str = Field(
        description="应用 active fallback policy 后的最终来源",
    )
    reason_codes: list[str] = Field(
        default_factory=list,
        description="policy 持久化的结构化原因代码",
    )
    recommended_actions: list[str] = Field(
        default_factory=list,
        description="policy 持久化的建议动作代码",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceHealthReportResponse(BaseModel):
    """DataCatalog source-selection health report response."""

    dataset_id: str = Field(description="数据集 ID")
    namespace: str = Field(description="Catalog namespace")
    trade_date: str = Field(description="交易日期")
    default_source: str = Field(description="DatasetMetadata 默认来源")
    selected_source: str = Field(description="source=auto 当前会选择的来源")
    selected_freshness_status: str = Field(
        description="selected_source 在指定交易日的 freshness 状态",
    )
    selected_source_health: CatalogSourceHealthResponse = Field(
        description="source=auto 选中来源的完整 freshness 证据",
    )
    source_fallback_policy_effect: CatalogSourceFallbackPolicyEffectResponse | None = (
        Field(
            default=None,
            description="active fallback policy 对 source=auto 选择产生的只读证据",
        )
    )
    source_selection_status: str = Field(
        description="source=auto 选中来源是否可用于后端编排",
    )
    source_selection_blockers: list[str] = Field(
        default_factory=list,
        description="阻塞 source=auto 编排的结构化原因代码",
    )
    attention_reasons: list[str] = Field(
        default_factory=list,
        description="需要后端消费者关注该 report 的结构化原因代码",
    )
    sources: list[CatalogSourceHealthResponse] = Field(
        description="候选来源 freshness 证据",
    )
    unsupported_sources: list[str] = Field(
        default_factory=list,
        description="本次可用来源中不被该数据集 metadata 支持的来源",
    )
    failover_from_default: bool = Field(
        default=False,
        description="source=auto 是否选择了非默认来源",
    )
    fallback_sources: list[str] = Field(
        default_factory=list,
        description="该数据集支持的非默认候选来源",
    )
    latest_revocation_reason: MaturityPromotionRevocationReason | None = Field(
        default=None,
        description="最近一次数据集晋级撤销原因分类",
    )
    latest_revoked_by: str | None = Field(
        default=None,
        description="最近一次数据集晋级撤销人或撤销主体",
    )
    latest_revoked_at: str | None = Field(
        default=None,
        description="最近一次数据集晋级撤销时间",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceHealthStatusCountResponse(BaseModel):
    """Aggregated freshness status count response."""

    status: str = Field(description="freshness 状态")
    count: int = Field(description="该状态出现次数")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceSelectionCountResponse(BaseModel):
    """Aggregated selected-source count response."""

    source: str = Field(description="被 source=auto 选中的来源")
    count: int = Field(description="该来源被选中次数")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceSelectionStatusCountResponse(BaseModel):
    """Aggregated source-selection readiness count response."""

    status: str = Field(description="source=auto 选中来源是否可用于后端编排")
    count: int = Field(description="该 source-selection 状态出现次数")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceHealthAttentionReasonCountResponse(BaseModel):
    """Aggregated source-health attention reason count response."""

    reason: str = Field(description="需要关注的结构化原因代码")
    count: int = Field(description="该原因出现次数")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceHealthAttentionSeverityCountResponse(BaseModel):
    """Aggregated source-health attention severity count response."""

    severity: str = Field(description="source-health attention severity")
    count: int = Field(description="该严重程度覆盖的 attention item 数量")

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceHealthAttentionItemResponse(BaseModel):
    """Source-health summary item requiring operator attention."""

    dataset_id: str = Field(description="数据集 ID")
    namespace: str = Field(description="Catalog namespace")
    trade_date: str = Field(description="交易日期")
    default_source: str = Field(description="DatasetMetadata 默认来源")
    selected_source: str = Field(description="source=auto 当前会选择的来源")
    selected_freshness_status: str = Field(description="selected source freshness 状态")
    selected_source_health: CatalogSourceHealthResponse = Field(
        description="selected source 的 freshness/storage/schema 证据",
    )
    source_fallback_policy_effect: CatalogSourceFallbackPolicyEffectResponse | None = (
        Field(
            default=None,
            description="active fallback policy 对 source=auto 选择产生的只读证据",
        )
    )
    source_selection_status: str = Field(
        description="source=auto 选中来源是否可用于后端编排",
    )
    source_selection_blockers: list[str] = Field(
        default_factory=list,
        description="阻塞 source=auto 编排的结构化原因代码",
    )
    attention_reasons: list[str] = Field(
        default_factory=list,
        description="需要后端消费者关注该 report 的结构化原因代码",
    )
    attention_severity: str = Field(
        description="source-health attention severity (critical/warning/info)",
    )
    unsupported_sources: list[str] = Field(
        default_factory=list,
        description="本次可用来源中不被该数据集 metadata 支持的来源",
    )
    failover_from_default: bool = Field(
        default=False,
        description="source=auto 是否选择了非默认来源",
    )
    fallback_sources: list[str] = Field(
        default_factory=list,
        description="该数据集支持的非默认候选来源",
    )
    latest_revocation_reason: MaturityPromotionRevocationReason | None = Field(
        default=None,
        description="最近一次数据集晋级撤销原因分类",
    )
    latest_revoked_by: str | None = Field(
        default=None,
        description="最近一次数据集晋级撤销人或撤销主体",
    )
    latest_revoked_at: str | None = Field(
        default=None,
        description="最近一次数据集晋级撤销时间",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class CatalogSourceHealthSummaryReportResponse(BaseModel):
    """Aggregated DataCatalog source-health report response."""

    dataset_ids: list[str] = Field(description="聚合的数据集 ID")
    trade_dates: list[str] = Field(description="聚合的交易日期")
    available_sources: list[str] = Field(description="参与 source=auto 判断的来源")
    total_reports: int = Field(description="单项 source-health report 数量")
    failover_count: int = Field(
        default=0,
        description="selected source 与默认来源不同的 report 数量",
    )
    no_fallback_source_count: int = Field(
        default=0,
        description="没有非默认候选来源的 report 数量",
    )
    revoked_promotion_count: int = Field(
        default=0,
        description="存在最近晋级撤销上下文的 report 数量",
    )
    status_counts: list[CatalogSourceHealthStatusCountResponse] = Field(
        description="按 freshness 状态聚合的 source health 数量",
    )
    selected_source_counts: list[CatalogSourceSelectionCountResponse] = Field(
        description="按 selected source 聚合的 report 数量",
    )
    source_selection_status_counts: list[CatalogSourceSelectionStatusCountResponse] = (
        Field(
            default_factory=list,
            description="按 source=auto 选中来源可编排状态聚合的 report 数量",
        )
    )
    fallback_source_counts: list[CatalogSourceSelectionCountResponse] = Field(
        default_factory=list,
        description="按非默认候选来源聚合的 report 覆盖数量",
    )
    attention_reason_counts: list[CatalogSourceHealthAttentionReasonCountResponse] = (
        Field(
            default_factory=list,
            description="按 source-health attention reason 聚合的 report 数量",
        )
    )
    attention_severity_counts: list[
        CatalogSourceHealthAttentionSeverityCountResponse
    ] = Field(
        default_factory=list,
        description="按 source-health attention severity 聚合的 attention item 数量",
    )
    attention_required: list[CatalogSourceHealthAttentionItemResponse] = Field(
        description="带有结构化 attention reason 的数据集/日期",
    )
    reports: list[CatalogSourceHealthReportResponse] = Field(
        description="明细 source-health reports",
    )

    model_config = ConfigDict(strict=True, extra="ignore")
