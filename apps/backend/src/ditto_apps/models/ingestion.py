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
    dataset_maturity: str | None = Field(
        default=None,
        description="数据集能力成熟度 (initial-focus/experimental/reserved)",
    )
    dataset_maturity_warning: str | None = Field(
        default=None,
        description="数据集能力成熟度警告",
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

    model_config = ConfigDict(strict=True, extra="ignore")


class IngestionStatusResponse(BaseModel):
    """摄取状态汇总响应."""

    datasets: list[DatasetStatusResponse] = Field(description="各数据集状态")
    maturity_summary: list[DatasetMaturitySummaryResponse] = Field(
        default_factory=list,
        description="按能力成熟度分组的摄取与 freshness 摘要",
    )

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
