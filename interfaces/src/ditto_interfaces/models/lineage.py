"""Lineage / Replay API 模型."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ditto_interfaces.models.backtest import RunResponse


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


__all__ = [
    "LineageResponse",
    "ManifestDiffResponse",
    "ReplayResponse",
]
