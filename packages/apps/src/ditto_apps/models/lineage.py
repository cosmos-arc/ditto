"""Lineage / Replay API 模型."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ditto_apps.models.backtest import RunResponse


class DataLineageAssetResponse(BaseModel):
    """数据资产身份响应."""

    dataset_id: str = Field(description="数据集 ID")
    namespace: str = Field(description="资产命名空间")
    partition_keys: list[str] = Field(
        default_factory=list,
        description="资产分区键",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class DataLineageRefResponse(BaseModel):
    """数据血缘输入/输出引用响应."""

    asset: DataLineageAssetResponse = Field(description="资产引用")
    role: str = Field(description="资产在 lineage 事件中的角色")

    model_config = ConfigDict(strict=True, extra="ignore")


class DataLineageEventResponse(BaseModel):
    """数据血缘事件响应."""

    run_id: str = Field(description="产生该 lineage 事件的运行 ID")
    operation: str = Field(description="lineage 操作类型")
    timestamp: str = Field(description="lineage 事件时间戳")
    inputs: list[DataLineageRefResponse] = Field(description="输入资产")
    outputs: list[DataLineageRefResponse] = Field(description="输出资产")

    model_config = ConfigDict(strict=True, extra="ignore")


class DataLineageRunResponse(BaseModel):
    """运行级数据血缘摘要响应."""

    run_id: str = Field(description="运行 ID")
    events: list[DataLineageEventResponse] = Field(description="该运行的 lineage 事件")
    input_assets: list[DataLineageAssetResponse] = Field(description="去重输入资产")
    output_assets: list[DataLineageAssetResponse] = Field(description="去重输出资产")

    model_config = ConfigDict(strict=True, extra="ignore")


class DataLineageCatalogAssetResponse(BaseModel):
    """运行级 lineage 资产的 DataCatalog 证据响应."""

    asset: DataLineageAssetResponse = Field(description="lineage 资产身份")
    catalog_status: str = Field(
        description="DataCatalog 精确资产匹配状态 (found/missing/not_configured)",
    )
    storage_uri: str | None = Field(default=None, description="Catalog 存储 URI")
    source: str | None = Field(default=None, description="Catalog 数据源")
    schema_hash: str | None = Field(default=None, description="Catalog schema 指纹")
    row_count: int | None = Field(default=None, description="Catalog 记录数")
    schema_created_at: str | None = Field(
        default=None,
        description="Catalog schema 观测时间",
    )
    freshness_at: str | None = Field(
        default=None,
        description="Catalog freshness 时间",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class DataLineageCatalogRunReportResponse(BaseModel):
    """运行级数据血缘 + Catalog 证据报告响应."""

    run_id: str = Field(description="运行 ID")
    events: list[DataLineageEventResponse] = Field(description="该运行的 lineage 事件")
    input_assets: list[DataLineageCatalogAssetResponse] = Field(
        description="去重输入资产及其 Catalog 证据",
    )
    output_assets: list[DataLineageCatalogAssetResponse] = Field(
        description="去重输出资产及其 Catalog 证据",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class DataLineageGraphEdgeResponse(BaseModel):
    """数据血缘图有向边响应."""

    source: DataLineageAssetResponse = Field(description="来源资产")
    target: DataLineageAssetResponse = Field(description="目标资产")
    event: DataLineageEventResponse = Field(description="产生该边的 lineage 事件")

    model_config = ConfigDict(strict=True, extra="ignore")


class DataLineageGraphResponse(BaseModel):
    """资产级数据血缘图响应."""

    root: DataLineageAssetResponse = Field(description="查询根资产")
    direction: str = Field(description="遍历方向")
    max_depth: int = Field(description="最大遍历深度")
    assets: list[DataLineageAssetResponse] = Field(description="图中去重资产")
    events: list[DataLineageEventResponse] = Field(description="图中 lineage 事件")
    edges: list[DataLineageGraphEdgeResponse] = Field(description="图中有向边")

    model_config = ConfigDict(strict=True, extra="ignore")


class LineageResponse(BaseModel):
    """运行血统链响应."""

    runs: list[RunResponse] = Field(description="血统链运行记录")
    depth: int = Field(description="血统链深度")

    model_config = ConfigDict(strict=True, extra="ignore")


class ManifestDiffResponse(BaseModel):
    """Manifest 差异报告."""

    config_diffs: list[str] = Field(default_factory=list, description="配置差异列表")
    data_diffs: list[str] = Field(default_factory=list, description="数据差异列表")
    version_diffs: list[str] = Field(default_factory=list, description="版本差异列表")
    seed_diffs: list[str] = Field(default_factory=list, description="随机种子差异列表")
    has_diff: bool = Field(default=False, description="是否存在差异")

    model_config = ConfigDict(strict=True, extra="ignore")


class ReplayResponse(BaseModel):
    """重放结果响应."""

    new_run_id: str = Field(description="重放生成的运行 ID")
    is_reproducible: bool = Field(description="是否可复现")
    nav_correlation: float = Field(description="重放与原始净值序列相关系数")
    max_nav_diff_bps: float = Field(description="重放与原始净值序列最大偏差 (bps)")
    manifest_diff: ManifestDiffResponse = Field(description="Manifest 差异详情")
    input_data_match: bool = Field(description="输入数据是否匹配")

    model_config = ConfigDict(strict=True, extra="ignore")


class FillComparisonResponse(BaseModel):
    """Replay fill 序列对比响应."""

    identical: bool = Field(description="Fill 序列是否完全一致")
    mismatch_count: int = Field(description="逐点不一致数量")
    length_mismatch: bool = Field(description="Fill 序列长度是否不一致")
    point_count: int = Field(description="原始 Fill 序列点数")

    model_config = ConfigDict(strict=True, extra="ignore")


class AccountStateComparisonResponse(BaseModel):
    """Replay 账户状态对比响应."""

    identical: bool = Field(description="账户状态是否完全一致")
    nav_diff: float = Field(description="NAV 绝对差异")
    available_cash_diff: float = Field(description="可用现金绝对差异")
    settled_cash_diff: float = Field(description="已结算现金绝对差异")
    frozen_cash_diff: float = Field(description="冻结现金绝对差异")
    position_count_diff: int = Field(description="持仓数量差异")

    model_config = ConfigDict(strict=True, extra="ignore")


class ReplayProofResponse(BaseModel):
    """重放 proof 证据响应."""

    proof_version: int = Field(description="Proof 格式版本")
    created_at: str = Field(default="", description="Proof 创建时间")
    original_run_id: str = Field(description="原始运行 ID")
    replay_run_id: str = Field(description="重放运行 ID")
    is_reproducible: bool = Field(description="是否可复现")
    nav_correlation: float = Field(description="NAV 序列相关系数")
    max_nav_diff_bps: float = Field(description="NAV 最大偏差 bps")
    input_data_match: bool = Field(description="输入数据是否匹配")
    manifest_diff: ManifestDiffResponse = Field(description="Manifest 差异")
    fill_match: bool | None = Field(default=None, description="Fill 序列是否匹配")
    account_state_match: bool | None = Field(
        default=None,
        description="账户状态是否匹配",
    )
    fill_comparison: FillComparisonResponse | None = Field(
        default=None,
        description="Fill 序列对比详情",
    )
    account_state_comparison: AccountStateComparisonResponse | None = Field(
        default=None,
        description="账户状态对比详情",
    )
    original_resume_provenance: dict[str, object] | None = Field(
        default=None,
        description="原始运行若来自 checkpoint 恢复, 则记录其恢复来源证据",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


class ReplayEvidenceSummaryResponse(BaseModel):
    """恢复运行重放证据摘要响应."""

    run_id: str = Field(description="当前查询的运行 ID")
    original_run_id: str = Field(description="Replay proof 指向的原始运行 ID")
    replay_run_id: str = Field(description="Replay proof 记录的重放运行 ID")
    is_reproducible: bool = Field(description="是否可复现")
    input_data_match: bool = Field(description="输入数据是否匹配")
    fill_match: bool | None = Field(default=None, description="Fill 序列是否匹配")
    account_state_match: bool | None = Field(
        default=None,
        description="账户状态是否匹配",
    )
    report_resume_provenance: dict[str, object] | None = Field(
        default=None,
        description="原始 restored-run report 中记录的恢复来源证据",
    )
    proof_resume_provenance: dict[str, object] | None = Field(
        default=None,
        description="Replay proof 中记录的原始恢复来源证据",
    )
    resume_provenance_match: bool = Field(
        description="report 与 proof 中的恢复来源证据是否一致",
    )
    missing_sections: list[str] = Field(
        default_factory=list,
        description="缺失的证据段落",
    )

    model_config = ConfigDict(strict=True, extra="ignore")


__all__ = [
    "AccountStateComparisonResponse",
    "DataLineageAssetResponse",
    "DataLineageCatalogAssetResponse",
    "DataLineageCatalogRunReportResponse",
    "DataLineageEventResponse",
    "DataLineageGraphEdgeResponse",
    "DataLineageGraphResponse",
    "DataLineageRefResponse",
    "DataLineageRunResponse",
    "FillComparisonResponse",
    "LineageResponse",
    "ManifestDiffResponse",
    "ReplayEvidenceSummaryResponse",
    "ReplayProofResponse",
    "ReplayResponse",
]
