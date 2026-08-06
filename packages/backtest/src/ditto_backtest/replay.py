"""回测运行复现性验证 — manifest 对比、NAV 序列、fill 与 account 状态."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ditto_kernel.math import pearson_correlation
from ditto_portfolio.accounting.account import AccountView
from ditto_portfolio.accounting.fills import FillEvent

from ditto_backtest.errors import ReplayError
from ditto_backtest.manifest import (
    InputRef,
    RunManifest,
)
from ditto_backtest.manifest_types import ReplayArtifactRef, ResearchReplayEvidence

__all__ = [
    "AccountStateComparison",
    "FillComparison",
    "ManifestDiff",
    "NavComparison",
    "ReplayProof",
    "ReplayStateProof",
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
    evidence_diffs: tuple[str, ...] = ()

    @property
    def has_diff(self) -> bool:
        """是否存在任何差异。"""
        return bool(
            self.config_diffs
            or self.data_diffs
            or self.version_diffs
            or self.seed_diffs
            or self.evidence_diffs
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
# ReplayStateProof
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayStateProof:
    """Replay 验证可选状态证据。"""

    original_fills: Sequence[FillEvent] | None = None
    replay_fills: Sequence[FillEvent] | None = None
    original_account: AccountView | None = None
    replay_account: AccountView | None = None


# ---------------------------------------------------------------------------
# ReplayValidationResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayValidationResult:
    """
    完整复现性验证结果.

    Attributes:
        is_reproducible: 是否可复现（manifest 一致 + NAV 一致 + 状态证据一致）
        nav_correlation: NAV 相关系数
        max_nav_diff_bps: 最大 NAV 差异（基点）
        manifest_diff: 分类 manifest 差异
        input_data_match: 输入数据是否匹配
        fill_match: Fill 序列是否匹配；未提供 fill 证据时为 None
        account_state_match: Account 状态是否匹配；未提供状态证据时为 None
        fill_comparison: Fill 序列对比详情
        account_state_comparison: Account 状态对比详情

    """

    is_reproducible: bool
    nav_correlation: float
    max_nav_diff_bps: float
    manifest_diff: ManifestDiff
    input_data_match: bool
    fill_match: bool | None = None
    account_state_match: bool | None = None
    fill_comparison: FillComparison | None = None
    account_state_comparison: AccountStateComparison | None = None
    reproduction_fingerprint_match: bool | None = None
    key_result_summary_match: bool | None = None
    required_artifact_hashes_match: bool | None = None


# ---------------------------------------------------------------------------
# ReplayValidator
# ---------------------------------------------------------------------------


def _manifest_diff_line(
    field_name: str,
    original_value: object,
    replay_value: object,
) -> str:
    return f"{field_name}: {original_value} vs {replay_value}"


def _compare_manifest_config(
    original: RunManifest,
    replay: RunManifest,
) -> tuple[str, ...]:
    diffs: list[str] = []
    scalar_fields = (
        ("mode", original.mode, replay.mode),
        ("config_hash", original.config_hash, replay.config_hash),
        ("strategy_id", original.strategy_id, replay.strategy_id),
        ("base_spec_hash", original.base_spec_hash, replay.base_spec_hash),
        ("spec_hash", original.spec_hash, replay.spec_hash),
        ("parameter_hash", original.parameter_hash, replay.parameter_hash),
        (
            "rule_resolution_policy",
            original.rule_resolution_policy,
            replay.rule_resolution_policy,
        ),
        ("pit_time_column", original.pit_time_column, replay.pit_time_column),
        ("pit_policy", original.pit_policy, replay.pit_policy),
        (
            "unsafe_time_policy",
            original.unsafe_time_policy,
            replay.unsafe_time_policy,
        ),
        (
            "knowledge_lag_days",
            original.knowledge_lag_days,
            replay.knowledge_lag_days,
        ),
    )
    for field_name, original_value, replay_value in scalar_fields:
        if original_value != replay_value:
            diffs.append(_manifest_diff_line(field_name, original_value, replay_value))
    if original.effective_parameters != replay.effective_parameters:
        diffs.append("effective_parameters: mismatch")
    if original.rule_refs != replay.rule_refs:
        diffs.append("rule_refs: mismatch")
    return tuple(diffs)


def _compare_manifest_data(
    original: RunManifest,
    replay: RunManifest,
) -> tuple[str, ...]:
    diffs: list[str] = []
    if original.input_refs != replay.input_refs:
        diffs.append(f"input_refs: {original.input_refs} vs {replay.input_refs}")
    diffs.extend(
        _compare_input_ref_details(
            original.input_ref_details,
            replay.input_ref_details,
        )
    )
    if original.artifacts != replay.artifacts:
        diffs.append(
            _manifest_diff_line("artifacts", original.artifacts, replay.artifacts)
        )
    if original.universe_hash != replay.universe_hash:
        diffs.append(
            _manifest_diff_line(
                "universe_hash",
                original.universe_hash,
                replay.universe_hash,
            )
        )
    if original.research_snapshot_id != replay.research_snapshot_id:
        diffs.append(
            _manifest_diff_line(
                "research_snapshot_id",
                original.research_snapshot_id,
                replay.research_snapshot_id,
            )
        )
    if (
        original.research_snapshot_manifest_hash
        != replay.research_snapshot_manifest_hash
    ):
        diffs.append(
            _manifest_diff_line(
                "research_snapshot_manifest_hash",
                original.research_snapshot_manifest_hash,
                replay.research_snapshot_manifest_hash,
            )
        )
    return tuple(diffs)


def _compare_manifest_versions(
    original: RunManifest,
    replay: RunManifest,
) -> tuple[str, ...]:
    diffs: list[str] = []
    scalar_fields = (
        ("engine_version", original.engine_version, replay.engine_version),
        ("strategy_version", original.strategy_version, replay.strategy_version),
    )
    for field_name, original_value, replay_value in scalar_fields:
        if original_value != replay_value:
            diffs.append(_manifest_diff_line(field_name, original_value, replay_value))
    if original.dependency_versions != replay.dependency_versions:
        diffs.append(
            _manifest_diff_line(
                "dependency_versions",
                original.dependency_versions,
                replay.dependency_versions,
            )
        )
    return tuple(diffs)


def _compare_manifest_seed(
    original: RunManifest,
    replay: RunManifest,
) -> tuple[str, ...]:
    if original.random_seed == replay.random_seed:
        return ()
    return (f"random_seed: {original.random_seed} vs {replay.random_seed}",)


def _compare_research_evidence(
    original: ResearchReplayEvidence | None,
    replay: ResearchReplayEvidence | None,
    *,
    required: bool,
) -> tuple[str, ...]:
    """Compare already-authoritative R3 evidence without deriving a fingerprint."""
    if original is None and replay is None:
        return ("research replay evidence is required but missing",) if required else ()
    if original is None:
        return ("research replay evidence missing in original",)
    if replay is None:
        return ("research replay evidence missing in replay",)

    diffs: list[str] = []
    if original.schema_version != replay.schema_version:
        diffs.append(
            _manifest_diff_line(
                "replay_evidence.schema_version",
                original.schema_version,
                replay.schema_version,
            )
        )
    if original.reproduction_fingerprint != replay.reproduction_fingerprint:
        diffs.append(
            _manifest_diff_line(
                "reproduction_fingerprint",
                original.reproduction_fingerprint,
                replay.reproduction_fingerprint,
            )
        )
    if _artifact_measurement(original.key_result_summary) != _artifact_measurement(
        replay.key_result_summary
    ):
        diffs.append("key_result_summary: verified content mismatch")
    original_by_kind = _artifact_measurements_by_kind(original)
    replay_by_kind = _artifact_measurements_by_kind(replay)
    for artifact_kind in sorted(original_by_kind.keys() | replay_by_kind.keys()):
        if original_by_kind.get(artifact_kind) != replay_by_kind.get(artifact_kind):
            original_ids = ",".join(
                item.artifact_id
                for item in original.required_artifacts
                if item.artifact_kind == artifact_kind
            )
            diffs.append(
                "required_artifacts kind "
                + f"{artifact_kind} ({original_ids}): verified measurements mismatch"
            )
    return tuple(diffs)


def _artifact_measurement(artifact: ReplayArtifactRef) -> tuple[object, ...]:
    ref = artifact
    return (
        ref.artifact_kind,
        ref.artifact_format,
        ref.content_hash,
        ref.schema_hash,
        ref.row_count,
        ref.byte_size,
    )


def _artifact_measurements_by_kind(
    evidence: ResearchReplayEvidence,
) -> dict[str, tuple[tuple[object, ...], ...]]:
    kinds = {item.artifact_kind for item in evidence.required_artifacts}
    return {
        kind: tuple(
            sorted(
                _artifact_measurement(item)
                for item in evidence.required_artifacts
                if item.artifact_kind == kind
            )
        )
        for kind in kinds
    }


def _research_evidence_match_state(
    original: ResearchReplayEvidence | None,
    replay: ResearchReplayEvidence | None,
    *,
    required: bool,
) -> tuple[bool | None, bool | None, bool | None]:
    if original is None and replay is None and not required:
        return None, None, None
    if original is None or replay is None:
        return False, False, False
    return (
        original.reproduction_fingerprint == replay.reproduction_fingerprint,
        _artifact_measurement(original.key_result_summary)
        == _artifact_measurement(replay.key_result_summary),
        _artifact_measurements_by_kind(original)
        == _artifact_measurements_by_kind(replay),
    )


class ReplayValidator:
    """回测运行复现性验证器 — 纯函数，无 I/O。"""

    @staticmethod
    def compare_manifests(
        original: RunManifest,
        replay: RunManifest,
        *,
        require_research_evidence: bool = False,
    ) -> ManifestDiff:
        """
        对比两个 RunManifest，返回分类差异报告.

        跳过 run_id / created_at（这些在重放时必然不同）。
        """
        return ManifestDiff(
            config_diffs=_compare_manifest_config(original, replay),
            data_diffs=_compare_manifest_data(original, replay),
            version_diffs=_compare_manifest_versions(original, replay),
            seed_diffs=_compare_manifest_seed(original, replay),
            evidence_diffs=_compare_research_evidence(
                original.replay_evidence,
                replay.replay_evidence,
                required=require_research_evidence,
            ),
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
            raise ReplayError(msg, point_count=n, replay_point_count=len(replay))

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
        *,
        state_proof: ReplayStateProof | None = None,
        require_research_evidence: bool = False,
    ) -> ReplayValidationResult:
        """
        端到端复现性验证.

        判定可复现条件：
        1. manifest 无差异（忽略 run_id / created_at）
        2. NAV 序列完全一致
        3. 如果提供 fill / account 状态证据，则这些状态也必须一致

        """
        manifest_diff = ReplayValidator.compare_manifests(
            original_manifest,
            replay_manifest,
            require_research_evidence=require_research_evidence,
        )
        nav_comp = ReplayValidator.compare_nav_series(original_nav, replay_nav)

        fill_comparison: FillComparison | None = None
        fill_match: bool | None = None
        if state_proof is not None and (
            state_proof.original_fills is not None
            or state_proof.replay_fills is not None
        ):
            original_fill_seq: Sequence[FillEvent] = (
                state_proof.original_fills
                if state_proof.original_fills is not None
                else ()
            )
            replay_fill_seq: Sequence[FillEvent] = (
                state_proof.replay_fills if state_proof.replay_fills is not None else ()
            )
            fill_comparison = ReplayProof.compare_fills(
                original_fill_seq,
                replay_fill_seq,
            )
            fill_match = fill_comparison.identical

        account_state_comparison: AccountStateComparison | None = None
        account_state_match: bool | None = None
        if state_proof is not None and (
            state_proof.original_account is not None
            or state_proof.replay_account is not None
        ):
            if (
                state_proof.original_account is None
                or state_proof.replay_account is None
            ):
                account_state_match = False
            else:
                account_state_comparison = ReplayProof.compare_account_state(
                    state_proof.original_account,
                    state_proof.replay_account,
                )
                account_state_match = account_state_comparison.identical

        input_data_match = len(manifest_diff.data_diffs) == 0
        state_match = fill_match is not False and account_state_match is not False
        is_reproducible = (
            not manifest_diff.has_diff and nav_comp.identical and state_match
        )
        fingerprint_match, summary_match, artifact_hashes_match = (
            _research_evidence_match_state(
                original_manifest.replay_evidence,
                replay_manifest.replay_evidence,
                required=require_research_evidence,
            )
        )

        return ReplayValidationResult(
            is_reproducible=is_reproducible,
            nav_correlation=nav_comp.correlation,
            max_nav_diff_bps=nav_comp.max_diff_bps,
            manifest_diff=manifest_diff,
            input_data_match=input_data_match,
            fill_match=fill_match,
            account_state_match=account_state_match,
            fill_comparison=fill_comparison,
            account_state_comparison=account_state_comparison,
            reproduction_fingerprint_match=fingerprint_match,
            key_result_summary_match=summary_match,
            required_artifact_hashes_match=artifact_hashes_match,
        )


# ---------------------------------------------------------------------------
# FillComparison
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FillComparison:
    """Fill 序列对比结果。"""

    identical: bool
    mismatch_count: int
    length_mismatch: bool
    point_count: int


# ---------------------------------------------------------------------------
# AccountStateComparison
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccountStateComparison:
    """Account 状态对比结果。"""

    identical: bool
    nav_diff: float
    available_cash_diff: float
    settled_cash_diff: float
    frozen_cash_diff: float
    position_count_diff: int


# ---------------------------------------------------------------------------
# ReplayProof
# ---------------------------------------------------------------------------


class ReplayProof:
    """Fill 与 Account 状态对比 — 回测确定性验证."""

    @staticmethod
    def compare_fills(
        original: Sequence[FillEvent],
        replay: Sequence[FillEvent],
    ) -> FillComparison:
        """对比两条 fill 序列，返回差异报告。"""
        n = len(original)
        length_mismatch = n != len(replay)
        identical = not length_mismatch
        mismatch_count = 0
        for a, b in zip(original, replay, strict=False):
            if a != b:
                identical = False
                mismatch_count += 1
        return FillComparison(
            identical=identical,
            mismatch_count=mismatch_count,
            length_mismatch=length_mismatch,
            point_count=n,
        )

    @staticmethod
    def compare_account_state(
        original: AccountView,
        replay: AccountView,
    ) -> AccountStateComparison:
        """对比两个 AccountView，返回 NAV / 现金 / 持仓差异。"""
        nav_diff = abs(original.nav - replay.nav)
        available_cash_diff = abs(original.cash.available - replay.cash.available)
        settled_cash_diff = abs(original.cash.settled - replay.cash.settled)
        frozen_cash_diff = abs(original.cash.frozen - replay.cash.frozen)
        cash_match = original.cash == replay.cash
        position_count_diff = len(original.positions) - len(replay.positions)
        keys_match = set(original.positions.keys()) == set(replay.positions.keys())
        position_values_match = keys_match and all(
            original.positions[iid] == replay.positions[iid]
            for iid in original.positions
        )
        identical = (
            nav_diff == 0.0
            and cash_match
            and position_count_diff == 0
            and position_values_match
        )
        return AccountStateComparison(
            identical=identical,
            nav_diff=nav_diff,
            available_cash_diff=available_cash_diff,
            settled_cash_diff=settled_cash_diff,
            frozen_cash_diff=frozen_cash_diff,
            position_count_diff=position_count_diff,
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
        if a_ref.date_range != b_ref.date_range:
            diffs.append(
                f"date_range mismatch for {iid}: "
                + f"{a_ref.date_range} vs {b_ref.date_range}",
            )
        if a_ref.source != b_ref.source:
            diffs.append(
                f"source mismatch for {iid}: {a_ref.source} vs {b_ref.source}",
            )
        if a_ref.source_snapshot_id != b_ref.source_snapshot_id:
            diffs.append(
                "source_snapshot_id mismatch for "
                + f"{iid}: {a_ref.source_snapshot_id} vs "
                + b_ref.source_snapshot_id,
            )

    # 如果只是数量不同但没有具体映射差异（空 input_ref_details 对比场景）
    if len(a) != len(b):
        diffs.append("input_ref_details: count mismatch")

    return diffs
