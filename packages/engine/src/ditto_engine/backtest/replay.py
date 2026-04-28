"""
ReplayValidator — 回测运行复现性验证.

Phase 3.1 — Run Lineage / Replayability.

- ManifestDiff: 分类 manifest 差异（数据/配置/版本/种子）
- NavComparison: NAV 序列对比指标
- ReplayValidationResult: 完整复现性验证结果
- ReplayValidator: 纯函数验证器（无 I/O，无副作用）
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ditto_kernel.math import pearson_correlation

from ditto_engine.backtest.manifest import (
    InputRef,
    RunManifest,
)

__all__ = [
    "ManifestDiff",
    "NavComparison",
    "ReplayValidationResult",
    "ReplayValidator",
]


# ---------------------------------------------------------------------------
# ManifestDiff
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ManifestDiff:
    """
    分类 manifest 差异报告.

    Attributes:
        config_diffs: 配置差异
            (config_hash / strategy_id / parameter_overrides / spec_hash / rule_refs)
        data_diffs: 数据差异 (input_refs / input_ref_details / data_hash)
        version_diffs: 版本差异 (engine_version / dependency_versions)
        seed_diffs: 种子差异 (random_seed)

    """

    config_diffs: tuple[str, ...] = ()
    data_diffs: tuple[str, ...] = ()
    version_diffs: tuple[str, ...] = ()
    seed_diffs: tuple[str, ...] = ()

    @property
    def has_diff(self) -> bool:
        """是否存在任何差异。"""
        return bool(
            self.config_diffs
            or self.data_diffs
            or self.version_diffs
            or self.seed_diffs,
        )


# ---------------------------------------------------------------------------
# NavComparison
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NavComparison:
    """
    NAV 序列对比指标.

    Attributes:
        correlation: Pearson 相关系数（-1.0 ~ 1.0）
        max_diff_bps: 最大差异（基点）
        mean_diff_bps: 平均差异（基点）
        identical: 是否完全一致
        point_count: 数据点数

    """

    correlation: float
    max_diff_bps: float
    mean_diff_bps: float
    identical: bool
    point_count: int


# ---------------------------------------------------------------------------
# ReplayValidationResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayValidationResult:
    """
    完整复现性验证结果.

    Attributes:
        is_reproducible: 是否可复现（manifest 一致 + NAV 一致）
        nav_correlation: NAV 相关系数
        max_nav_diff_bps: 最大 NAV 差异（基点）
        manifest_diff: 分类 manifest 差异
        input_data_match: 输入数据是否匹配

    """

    is_reproducible: bool
    nav_correlation: float
    max_nav_diff_bps: float
    manifest_diff: ManifestDiff
    input_data_match: bool


# ---------------------------------------------------------------------------
# ReplayValidator
# ---------------------------------------------------------------------------


class ReplayValidator:
    """回测运行复现性验证器 — 纯函数，无 I/O。"""

    @staticmethod
    def compare_manifests(
        original: RunManifest,
        replay: RunManifest,
    ) -> ManifestDiff:
        """
        对比两个 RunManifest，返回分类差异报告.

        跳过 run_id / created_at（这些在重放时必然不同）。
        """
        config_diffs: list[str] = []
        data_diffs: list[str] = []
        version_diffs: list[str] = []
        seed_diffs: list[str] = []

        # -- config 类 --
        if original.config_hash != replay.config_hash:
            config_diffs.append(
                f"config_hash: {original.config_hash} vs {replay.config_hash}",
            )
        if original.strategy_id != replay.strategy_id:
            config_diffs.append(
                f"strategy_id: {original.strategy_id} vs {replay.strategy_id}",
            )
        if original.parameter_overrides != replay.parameter_overrides:
            a_str = original.parameter_overrides
            b_str = replay.parameter_overrides
            config_diffs.append(
                f"parameter_overrides: {a_str} vs {b_str}",
            )
        if original.spec_hash != replay.spec_hash:
            config_diffs.append(
                f"spec_hash: {original.spec_hash} vs {replay.spec_hash}",
            )
        if original.rule_refs != replay.rule_refs:
            config_diffs.append("rule_refs: mismatch")

        # -- data 类 --
        if original.input_refs != replay.input_refs:
            data_diffs.append(
                f"input_refs: {original.input_refs} vs {replay.input_refs}",
            )
        data_diffs.extend(
            _compare_input_ref_details(
                original.input_ref_details,
                replay.input_ref_details,
            ),
        )

        # -- version 类 --
        if original.engine_version != replay.engine_version:
            version_diffs.append(
                f"engine_version: {original.engine_version} vs {replay.engine_version}",
            )
        if original.dependency_versions != replay.dependency_versions:
            a_ver = original.dependency_versions
            b_ver = replay.dependency_versions
            version_diffs.append(
                f"dependency_versions: {a_ver} vs {b_ver}",
            )

        # -- seed 类 --
        if original.random_seed != replay.random_seed:
            seed_diffs.append(
                f"random_seed: {original.random_seed} vs {replay.random_seed}",
            )

        return ManifestDiff(
            config_diffs=tuple(config_diffs),
            data_diffs=tuple(data_diffs),
            version_diffs=tuple(version_diffs),
            seed_diffs=tuple(seed_diffs),
        )

    @staticmethod
    def compare_nav_series(
        original: Sequence[float],
        replay: Sequence[float],
    ) -> NavComparison:
        """
        对比两个 NAV 序列，返回对比指标.

        Raises:
            ValueError: 序列长度不一致

        """
        n = len(original)
        if n != len(replay):
            msg = f"NAV series length mismatch: {n} vs {len(replay)}"
            raise ValueError(msg)

        if n == 0:
            return NavComparison(
                correlation=1.0,
                max_diff_bps=0.0,
                mean_diff_bps=0.0,
                identical=True,
                point_count=0,
            )

        # 检查是否完全一致（浮点精确比较 — 回测确定性要求）
        identical = all(a == b for a, b in zip(original, replay, strict=False))

        # 基点差异计算：|a - b| / max(|a|, epsilon) * 10000
        bps_values: list[float] = []
        for a, b in zip(original, replay, strict=False):
            denom = max(abs(a), 1e-10)
            bps_values.append(abs(a - b) / denom * 10_000)

        max_diff_bps = max(bps_values)
        mean_diff_bps = sum(bps_values) / n

        # Pearson 相关系数
        correlation = pearson_correlation(list(original), list(replay))

        return NavComparison(
            correlation=correlation,
            max_diff_bps=max_diff_bps,
            mean_diff_bps=mean_diff_bps,
            identical=identical,
            point_count=n,
        )

    @staticmethod
    def validate(
        original_manifest: RunManifest,
        replay_manifest: RunManifest,
        original_nav: Sequence[float],
        replay_nav: Sequence[float],
    ) -> ReplayValidationResult:
        """
        端到端复现性验证.

        判定可复现条件：
        1. manifest 无差异（忽略 run_id / created_at）
        2. NAV 序列完全一致

        """
        manifest_diff = ReplayValidator.compare_manifests(
            original_manifest,
            replay_manifest,
        )
        nav_comp = ReplayValidator.compare_nav_series(original_nav, replay_nav)

        input_data_match = len(manifest_diff.data_diffs) == 0
        is_reproducible = not manifest_diff.has_diff and nav_comp.identical

        return ReplayValidationResult(
            is_reproducible=is_reproducible,
            nav_correlation=nav_comp.correlation,
            max_nav_diff_bps=nav_comp.max_diff_bps,
            manifest_diff=manifest_diff,
            input_data_match=input_data_match,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compare_input_ref_details(
    a: tuple[InputRef, ...],
    b: tuple[InputRef, ...],
) -> list[str]:
    """对比 input_ref_details，返回差异描述列表。"""
    if a == b:
        return []

    diffs: list[str] = []

    # 按 instrument_id 建立映射
    a_map = {ref.instrument_id: ref for ref in a}
    b_map = {ref.instrument_id: ref for ref in b}

    all_ids = sorted(set(a_map) | set(b_map))
    for iid in all_ids:
        a_ref = a_map.get(iid)
        b_ref = b_map.get(iid)
        if a_ref is None:
            diffs.append(f"input_ref_details: {iid} only in replay")
            continue
        if b_ref is None:
            diffs.append(f"input_ref_details: {iid} only in original")
            continue
        if a_ref.data_hash != b_ref.data_hash:
            diffs.append(
                f"data_hash mismatch for {iid}: {a_ref.data_hash} vs {b_ref.data_hash}",
            )

    # 如果只是数量不同但没有具体映射差异（空 input_ref_details 对比场景）
    if not diffs and len(a) != len(b):
        diffs.append("input_ref_details: count mismatch")

    return diffs
