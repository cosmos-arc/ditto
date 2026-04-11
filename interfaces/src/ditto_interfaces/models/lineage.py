"""Lineage / Replay API 模型."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ditto_interfaces.models.backtest import RunResponse


class LineageResponse(BaseModel):
    """运行血统链响应."""

    runs: list[RunResponse]
    depth: int

    model_config = ConfigDict(strict=True, extra="ignore")


class ManifestDiffResponse(BaseModel):
    """Manifest 差异报告."""

    config_diffs: list[str] = []
    data_diffs: list[str] = []
    version_diffs: list[str] = []
    seed_diffs: list[str] = []
    has_diff: bool = False

    model_config = ConfigDict(strict=True, extra="ignore")


class ReplayResponse(BaseModel):
    """重放结果响应."""

    new_run_id: str
    is_reproducible: bool
    nav_correlation: float
    max_nav_diff_bps: float
    manifest_diff: ManifestDiffResponse
    input_data_match: bool

    model_config = ConfigDict(strict=True, extra="ignore")


__all__ = [
    "LineageResponse",
    "ManifestDiffResponse",
    "ReplayResponse",
]
