"""ReplayValidator / ManifestDiff / NavComparison unit tests.

Phase 3.1 — Run Lineage / Replayability.
"""

from __future__ import annotations

import pytest
from ditto_backtest.errors import ReplayError
from ditto_backtest.manifest import (
    InputRef,
    RuleRef,
    RunManifest,
    RunMode,
)
from ditto_backtest.manifest_types import (
    ReplayArtifactRef,
    ResearchReplayEvidence,
)
from ditto_backtest.replay import (
    ManifestDiff,
    NavComparison,
    ReplayValidationResult,
    ReplayValidator,
)
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.parameters import (
    EffectiveParameter,
    canonical_parameter_hash,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IID_510300 = InstrumentId(510300)
_IID_510500 = InstrumentId(510500)


def _make_manifest(
    run_id: str = "run-001",
    strategy_id: str = "strat-a",
    strategy_version: str = "1",
    config_hash: str = "abc123",
    engine_version: str = "0.1.0",
    input_refs: tuple[InstrumentId, ...] = (_IID_510300, _IID_510500),
    rule_refs: tuple[RuleRef, ...] = (),
    spec_hash: str = "a" * 64,
    base_spec_hash: str = "b" * 64,
    effective_parameters: tuple[EffectiveParameter, ...] = (),
    research_snapshot_id: str | None = None,
    research_snapshot_manifest_hash: str | None = None,
    random_seed: int | None = None,
    dependency_versions: tuple[str, ...] = (),
    input_ref_details: tuple[InputRef, ...] = (),
    replay_evidence: ResearchReplayEvidence | None = None,
    **overrides: object,
) -> RunManifest:
    values: dict[str, object] = {
        "run_id": run_id,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "mode": RunMode.BACKTEST,
        "created_at": "2026-04-11T00:00:00Z",
        "input_refs": input_refs,
        "input_ref_details": input_ref_details,
        "parameter_overrides": (),
        "rule_refs": rule_refs,
        "config_hash": config_hash,
        "engine_version": engine_version,
        "spec_hash": spec_hash,
        "base_spec_hash": base_spec_hash,
        "parameter_hash": canonical_parameter_hash(effective_parameters),
        "effective_parameters": effective_parameters,
        "research_snapshot_id": research_snapshot_id,
        "research_snapshot_manifest_hash": research_snapshot_manifest_hash,
        "random_seed": random_seed,
        "dependency_versions": dependency_versions,
        "replay_evidence": replay_evidence,
    }
    values.update(overrides)
    return RunManifest(**values)  # type: ignore[arg-type]


def _artifact_ref(
    artifact_id: str,
    *,
    artifact_kind: str,
    content_hash: str,
) -> ReplayArtifactRef:
    return ReplayArtifactRef(
        artifact_id=artifact_id,
        artifact_kind=artifact_kind,
        artifact_format="json" if artifact_kind == "summary" else "parquet",
        content_hash=content_hash,
        schema_hash="e" * 64,
        row_count=1,
        byte_size=128,
    )


def _research_replay_evidence(
    *,
    reproduction_fingerprint: str = "f" * 64,
    summary_hash: str = "1" * 64,
    nav_hash: str = "2" * 64,
    include_nav: bool = True,
    artifact_id_suffix: str = "",
) -> ResearchReplayEvidence:
    summary_id = f"artifact-summary{artifact_id_suffix}"
    nav_id = f"artifact-nav{artifact_id_suffix}"
    artifacts = [
        _artifact_ref(
            summary_id,
            artifact_kind="summary",
            content_hash=summary_hash,
        )
    ]
    if include_nav:
        artifacts.append(
            _artifact_ref(
                nav_id,
                artifact_kind="nav",
                content_hash=nav_hash,
            )
        )
    return ResearchReplayEvidence(
        reproduction_fingerprint=reproduction_fingerprint,
        key_result_summary_artifact_id=summary_id,
        required_artifacts=tuple(sorted(artifacts, key=lambda item: item.identity)),
    )


# ---------------------------------------------------------------------------
# Test ManifestDiff
# ---------------------------------------------------------------------------


class TestManifestDiff:
    """ManifestDiff frozen dataclass + has_diff property."""

    def test_frozen(self) -> None:
        diff = ManifestDiff(
            config_diffs=("config_hash mismatch",),
            data_diffs=(),
            version_diffs=(),
            seed_diffs=(),
        )
        with pytest.raises(AttributeError):
            diff.config_diffs = ()  # type: ignore[misc]

    def test_has_diff_true_when_config_mismatch(self) -> None:
        diff = ManifestDiff(
            config_diffs=("config_hash mismatch",),
            data_diffs=(),
            version_diffs=(),
            seed_diffs=(),
        )
        assert diff.has_diff is True

    def test_has_diff_false_when_all_empty(self) -> None:
        diff = ManifestDiff(
            config_diffs=(),
            data_diffs=(),
            version_diffs=(),
            seed_diffs=(),
        )
        assert diff.has_diff is False

    def test_has_diff_true_when_data_mismatch(self) -> None:
        diff = ManifestDiff(
            config_diffs=(),
            data_diffs=("input_ref mismatch: 510300",),
            version_diffs=(),
            seed_diffs=(),
        )
        assert diff.has_diff is True

    def test_has_diff_true_when_version_mismatch(self) -> None:
        diff = ManifestDiff(
            config_diffs=(),
            data_diffs=(),
            version_diffs=("engine_version: 0.1.0 vs 0.2.0",),
            seed_diffs=(),
        )
        assert diff.has_diff is True

    def test_has_diff_true_when_seed_mismatch(self) -> None:
        diff = ManifestDiff(
            config_diffs=(),
            data_diffs=(),
            version_diffs=(),
            seed_diffs=("random_seed: 42 vs None",),
        )
        assert diff.has_diff is True

    def test_has_diff_true_when_research_evidence_mismatch(self) -> None:
        diff = ManifestDiff(evidence_diffs=("reproduction_fingerprint: mismatch",))

        assert diff.has_diff is True


class TestResearchReplayEvidence:
    """R3 replay evidence is complete, canonical, and content addressed."""

    def test_complete_evidence_accepts_full_hashes_and_sorted_artifacts(self) -> None:
        evidence = _research_replay_evidence()

        assert evidence.schema_version == 1
        assert evidence.key_result_summary.content_hash == "1" * 64
        assert tuple(item.artifact_id for item in evidence.required_artifacts) == (
            "artifact-nav",
            "artifact-summary",
        )

    @pytest.mark.parametrize(
        ("field_name", "value"),
        [
            ("content_hash", "a" * 16),
            ("schema_hash", "A" * 64),
            ("content_hash", "z" * 64),
        ],
    )
    def test_artifact_ref_rejects_noncanonical_hash(
        self,
        field_name: str,
        value: str,
    ) -> None:
        kwargs: dict[str, object] = {
            "artifact_id": "artifact-summary",
            "artifact_kind": "summary",
            "artifact_format": "json",
            "content_hash": "a" * 64,
            "schema_hash": "b" * 64,
            "row_count": 1,
            "byte_size": 10,
        }
        kwargs[field_name] = value

        with pytest.raises(ValueError, match="SHA-256"):
            ReplayArtifactRef(**kwargs)  # type: ignore[arg-type]

    @pytest.mark.parametrize("artifact_format", ["", "csv", "JSON"])
    def test_artifact_ref_rejects_unknown_format(self, artifact_format: str) -> None:
        with pytest.raises(ValueError, match="artifact_format"):
            ReplayArtifactRef(
                artifact_id="artifact-summary",
                artifact_kind="summary",
                artifact_format=artifact_format,
                content_hash="a" * 64,
                schema_hash="b" * 64,
                row_count=1,
                byte_size=10,
            )

    def test_evidence_rejects_unknown_schema_version(self) -> None:
        with pytest.raises(ValueError, match="schema_version"):
            ResearchReplayEvidence(
                schema_version=2,
                reproduction_fingerprint="f" * 64,
                key_result_summary_artifact_id="artifact-summary",
                required_artifacts=(
                    _artifact_ref(
                        "artifact-summary",
                        artifact_kind="summary",
                        content_hash="1" * 64,
                    ),
                ),
            )

    def test_evidence_rejects_missing_key_result_summary(self) -> None:
        with pytest.raises(ValueError, match="key result summary"):
            ResearchReplayEvidence(
                reproduction_fingerprint="f" * 64,
                key_result_summary_artifact_id="artifact-summary",
                required_artifacts=(
                    _artifact_ref(
                        "artifact-nav",
                        artifact_kind="nav",
                        content_hash="2" * 64,
                    ),
                ),
            )

    def test_evidence_rejects_duplicate_artifact_identity(self) -> None:
        artifact = _artifact_ref(
            "artifact-summary",
            artifact_kind="summary",
            content_hash="1" * 64,
        )
        with pytest.raises(ValueError, match="unique"):
            ResearchReplayEvidence(
                reproduction_fingerprint="f" * 64,
                key_result_summary_artifact_id="artifact-summary",
                required_artifacts=(artifact, artifact),
            )

    def test_evidence_rejects_ambiguous_duplicate_semantic_kind(self) -> None:
        summary = _artifact_ref(
            "artifact-summary",
            artifact_kind="summary",
            content_hash="1" * 64,
        )
        nav_a = _artifact_ref(
            "artifact-nav-a",
            artifact_kind="nav",
            content_hash="2" * 64,
        )
        nav_b = _artifact_ref(
            "artifact-nav-b",
            artifact_kind="nav",
            content_hash="3" * 64,
        )

        with pytest.raises(ValueError, match=r"kinds.*unique"):
            ResearchReplayEvidence(
                reproduction_fingerprint="f" * 64,
                key_result_summary_artifact_id="artifact-summary",
                required_artifacts=(nav_a, nav_b, summary),
            )

    def test_evidence_rejects_noncanonical_artifact_order(self) -> None:
        summary = _artifact_ref(
            "artifact-summary",
            artifact_kind="summary",
            content_hash="1" * 64,
        )
        nav = _artifact_ref(
            "artifact-nav",
            artifact_kind="nav",
            content_hash="2" * 64,
        )
        with pytest.raises(ValueError, match="sorted"):
            ResearchReplayEvidence(
                reproduction_fingerprint="f" * 64,
                key_result_summary_artifact_id="artifact-summary",
                required_artifacts=(summary, nav),
            )


# ---------------------------------------------------------------------------
# Test NavComparison
# ---------------------------------------------------------------------------


class TestNavComparison:
    """NavComparison frozen dataclass."""

    def test_frozen(self) -> None:
        comp = NavComparison(
            correlation=1.0,
            max_diff_bps=0.0,
            mean_diff_bps=0.0,
            identical=True,
            point_count=10,
        )
        with pytest.raises(AttributeError):
            comp.correlation = 0.5  # type: ignore[misc]

    def test_identical(self) -> None:
        comp = NavComparison(
            correlation=1.0,
            max_diff_bps=0.0,
            mean_diff_bps=0.0,
            identical=True,
            point_count=10,
        )
        assert comp.identical is True
        assert comp.correlation == 1.0

    def test_different(self) -> None:
        comp = NavComparison(
            correlation=0.99,
            max_diff_bps=15.5,
            mean_diff_bps=3.2,
            identical=False,
            point_count=20,
        )
        assert comp.identical is False
        assert comp.max_diff_bps == pytest.approx(15.5)


# ---------------------------------------------------------------------------
# Test ReplayValidationResult
# ---------------------------------------------------------------------------


class TestReplayValidationResult:
    """ReplayValidationResult frozen dataclass."""

    def test_frozen(self) -> None:
        result = ReplayValidationResult(
            is_reproducible=True,
            nav_correlation=1.0,
            max_nav_diff_bps=0.0,
            manifest_diff=ManifestDiff(
                config_diffs=(),
                data_diffs=(),
                version_diffs=(),
                seed_diffs=(),
            ),
            input_data_match=True,
        )
        with pytest.raises(AttributeError):
            result.is_reproducible = False  # type: ignore[misc]

    def test_reproducible(self) -> None:
        result = ReplayValidationResult(
            is_reproducible=True,
            nav_correlation=1.0,
            max_nav_diff_bps=0.0,
            manifest_diff=ManifestDiff(
                config_diffs=(),
                data_diffs=(),
                version_diffs=(),
                seed_diffs=(),
            ),
            input_data_match=True,
        )
        assert result.is_reproducible is True
        assert result.input_data_match is True

    def test_not_reproducible(self) -> None:
        diff = ManifestDiff(
            config_diffs=("config_hash mismatch",),
            data_diffs=(),
            version_diffs=(),
            seed_diffs=(),
        )
        result = ReplayValidationResult(
            is_reproducible=False,
            nav_correlation=0.95,
            max_nav_diff_bps=50.0,
            manifest_diff=diff,
            input_data_match=False,
        )
        assert result.is_reproducible is False
        assert result.manifest_diff.has_diff is True


# ---------------------------------------------------------------------------
# Test ReplayValidator.compare_manifests
# ---------------------------------------------------------------------------


class TestCompareManifests:
    """ReplayValidator.compare_manifests — categorize manifest differences."""

    def test_identical_manifests_no_diff(self) -> None:
        a = _make_manifest()
        b = _make_manifest(run_id="run-002")
        diff = ReplayValidator.compare_manifests(a, b)
        assert diff.has_diff is False

    def test_config_hash_mismatch(self) -> None:
        a = _make_manifest(config_hash="abc123")
        b = _make_manifest(config_hash="def456")
        diff = ReplayValidator.compare_manifests(a, b)
        assert diff.has_diff is True
        assert len(diff.config_diffs) == 1
        assert "config_hash" in diff.config_diffs[0]

    def test_strategy_id_mismatch(self) -> None:
        a = _make_manifest(strategy_id="strat-a")
        b = _make_manifest(strategy_id="strat-b")
        diff = ReplayValidator.compare_manifests(a, b)
        assert diff.has_diff is True
        assert any("strategy_id" in d for d in diff.config_diffs)

    def test_base_spec_hash_mismatch(self) -> None:
        a = _make_manifest(base_spec_hash="a" * 64)
        b = _make_manifest(base_spec_hash="b" * 64)

        diff = ReplayValidator.compare_manifests(a, b)

        assert any("base_spec_hash" in item for item in diff.config_diffs)

    def test_strategy_version_mismatch(self) -> None:
        a = _make_manifest(strategy_version="1")
        b = _make_manifest(strategy_version="2")

        diff = ReplayValidator.compare_manifests(a, b)

        assert any("strategy_version" in item for item in diff.version_diffs)

    def test_research_snapshot_identity_mismatch(self) -> None:
        a = _make_manifest(
            research_snapshot_id="snapshot-a",
            research_snapshot_manifest_hash="c" * 64,
        )
        b = _make_manifest(
            research_snapshot_id="snapshot-b",
            research_snapshot_manifest_hash="d" * 64,
        )

        diff = ReplayValidator.compare_manifests(a, b)

        assert any("research_snapshot_id" in item for item in diff.data_diffs)
        assert any(
            "research_snapshot_manifest_hash" in item for item in diff.data_diffs
        )

    def test_effective_parameters_mismatch(self) -> None:
        path = "/pipeline/nodes/legacy_factor_set/config/params/key1"
        a = _make_manifest(
            effective_parameters=(EffectiveParameter(path=path, value="val1"),),
        )
        b = _make_manifest(
            effective_parameters=(EffectiveParameter(path=path, value="val2"),),
        )
        diff = ReplayValidator.compare_manifests(a, b)
        assert diff.has_diff is True
        assert any("effective_parameters" in d for d in diff.config_diffs)
        assert any("parameter_hash" in d for d in diff.config_diffs)

    def test_input_refs_mismatch(self) -> None:
        a = _make_manifest(input_refs=(_IID_510300, _IID_510500))
        b = _make_manifest(input_refs=(_IID_510300,))
        diff = ReplayValidator.compare_manifests(a, b)
        assert diff.has_diff is True
        assert any("input_refs" in d for d in diff.data_diffs)

    def test_input_ref_details_data_hash_mismatch(self) -> None:
        a = _make_manifest(
            input_ref_details=(
                InputRef(
                    instrument_id=_IID_510300,
                    data_hash="sha256:aaa",
                    date_range=("2025-01-01", "2025-03-01"),
                    source="tushare",
                ),
            ),
        )
        b = _make_manifest(
            input_ref_details=(
                InputRef(
                    instrument_id=_IID_510300,
                    data_hash="sha256:bbb",
                    date_range=("2025-01-01", "2025-03-01"),
                    source="tushare",
                ),
            ),
        )
        diff = ReplayValidator.compare_manifests(a, b)
        assert diff.has_diff is True
        assert any("data_hash" in d for d in diff.data_diffs)

    def test_input_ref_details_source_snapshot_mismatch(self) -> None:
        """Replay validation must catch source snapshot drift."""
        a = _make_manifest(
            input_ref_details=(
                InputRef(
                    instrument_id=_IID_510300,
                    data_hash="sha256:aaa",
                    date_range=("2025-01-01", "2025-03-01"),
                    source="tushare",
                    source_snapshot_id="snapshot-v1",
                ),
            ),
        )
        b = _make_manifest(
            input_ref_details=(
                InputRef(
                    instrument_id=_IID_510300,
                    data_hash="sha256:aaa",
                    date_range=("2025-01-01", "2025-03-01"),
                    source="tushare",
                    source_snapshot_id="snapshot-v2",
                ),
            ),
        )

        diff = ReplayValidator.compare_manifests(a, b)

        assert diff.has_diff is True
        assert any("source_snapshot_id" in d for d in diff.data_diffs)

    def test_manifest_rejects_duplicate_input_ref_identity(self) -> None:
        first = InputRef(
            instrument_id=_IID_510300,
            data_hash="sha256:aaa",
            date_range=("2025-01-01", "2025-03-01"),
            source="tushare",
        )
        second = InputRef(
            instrument_id=_IID_510300,
            data_hash="sha256:bbb",
            date_range=("2025-01-01", "2025-03-01"),
            source="wind",
        )

        with pytest.raises(ValueError, match=r"input_ref_details.*unique"):
            _make_manifest(input_ref_details=(first, second))

    @pytest.mark.parametrize(
        ("field_name", "replay_value"),
        [
            ("source", "wind"),
            ("date_range", ("2025-01-02", "2025-03-01")),
        ],
    )
    def test_input_ref_details_compares_complete_identity(
        self,
        field_name: str,
        replay_value: object,
    ) -> None:
        values: dict[str, object] = {
            "instrument_id": _IID_510300,
            "data_hash": "sha256:aaa",
            "date_range": ("2025-01-01", "2025-03-01"),
            "source": "tushare",
            "source_snapshot_id": "snapshot-v1",
        }
        replay_values = dict(values)
        replay_values[field_name] = replay_value
        a = _make_manifest(input_ref_details=(InputRef(**values),))  # type: ignore[arg-type]
        b = _make_manifest(
            input_ref_details=(InputRef(**replay_values),),  # type: ignore[arg-type]
        )

        diff = ReplayValidator.compare_manifests(a, b)

        assert any(field_name in item for item in diff.data_diffs)

    @pytest.mark.parametrize(
        ("field_name", "replay_value"),
        [
            ("mode", RunMode.RESEARCH),
            ("artifacts", ("manifest.json",)),
            ("rule_resolution_policy", "latest"),
            ("universe_hash", "changed"),
            ("pit_time_column", "trade_date"),
            ("pit_policy", "unsafe"),
            ("unsafe_time_policy", "allow_future"),
            ("knowledge_lag_days", 2),
        ],
    )
    def test_complete_deterministic_manifest_identity_is_compared(
        self,
        field_name: str,
        replay_value: object,
    ) -> None:
        a = _make_manifest()
        b = _make_manifest(**{field_name: replay_value})

        diff = ReplayValidator.compare_manifests(a, b)

        assert diff.has_diff is True
        assert any(
            field_name in item
            for item in (
                *diff.config_diffs,
                *diff.data_diffs,
                *diff.version_diffs,
                *diff.seed_diffs,
                *diff.evidence_diffs,
            )
        )

    def test_audit_identity_can_change_when_r3_evidence_is_exact(self) -> None:
        evidence = _research_replay_evidence()
        a = _make_manifest(
            run_id="run-original",
            replay_evidence=evidence,
        )
        b = _make_manifest(
            run_id="run-replay",
            replay_evidence=evidence,
            created_at="2026-04-12T00:00:00Z",
        )

        diff = ReplayValidator.compare_manifests(a, b)

        assert diff.has_diff is False

    def test_attempt_specific_artifact_ids_can_change_when_hashes_are_exact(
        self,
    ) -> None:
        a = _make_manifest(
            run_id="run-original",
            replay_evidence=_research_replay_evidence(artifact_id_suffix="-attempt-1"),
        )
        b = _make_manifest(
            run_id="run-replay",
            replay_evidence=_research_replay_evidence(artifact_id_suffix="-attempt-2"),
            created_at="2026-04-12T00:00:00Z",
        )

        diff = ReplayValidator.compare_manifests(a, b)

        assert diff.has_diff is False

    def test_reproduction_fingerprint_mismatch_is_explicit(self) -> None:
        a = _make_manifest(replay_evidence=_research_replay_evidence())
        b = _make_manifest(
            replay_evidence=_research_replay_evidence(
                reproduction_fingerprint="0" * 64,
            )
        )

        diff = ReplayValidator.compare_manifests(a, b)

        assert any("reproduction_fingerprint" in item for item in diff.evidence_diffs)

    def test_key_result_summary_hash_mismatch_is_explicit(self) -> None:
        a = _make_manifest(replay_evidence=_research_replay_evidence())
        b = _make_manifest(
            replay_evidence=_research_replay_evidence(summary_hash="3" * 64)
        )

        diff = ReplayValidator.compare_manifests(a, b)

        assert any("key_result_summary" in item for item in diff.evidence_diffs)

    def test_missing_required_artifact_is_fail_closed(self) -> None:
        a = _make_manifest(replay_evidence=_research_replay_evidence())
        b = _make_manifest(replay_evidence=_research_replay_evidence(include_nav=False))

        diff = ReplayValidator.compare_manifests(a, b)

        assert any("required_artifacts" in item for item in diff.evidence_diffs)

    def test_required_parquet_content_hash_mismatch_is_fail_closed(self) -> None:
        a = _make_manifest(replay_evidence=_research_replay_evidence())
        b = _make_manifest(replay_evidence=_research_replay_evidence(nav_hash="4" * 64))

        diff = ReplayValidator.compare_manifests(a, b)

        assert any("artifact-nav" in item for item in diff.evidence_diffs)

    def test_one_sided_r3_evidence_is_fail_closed(self) -> None:
        a = _make_manifest(replay_evidence=_research_replay_evidence())
        b = _make_manifest(replay_evidence=None)

        diff = ReplayValidator.compare_manifests(a, b)

        assert any("missing" in item for item in diff.evidence_diffs)

    def test_engine_version_mismatch(self) -> None:
        a = _make_manifest(engine_version="0.1.0")
        b = _make_manifest(engine_version="0.2.0")
        diff = ReplayValidator.compare_manifests(a, b)
        assert diff.has_diff is True
        assert any("engine_version" in d for d in diff.version_diffs)

    def test_dependency_versions_mismatch(self) -> None:
        a = _make_manifest(dependency_versions=("polars==0.20.0",))
        b = _make_manifest(dependency_versions=("polars==0.21.0",))
        diff = ReplayValidator.compare_manifests(a, b)
        assert diff.has_diff is True
        assert any("dependency_versions" in d for d in diff.version_diffs)

    def test_random_seed_mismatch(self) -> None:
        a = _make_manifest(random_seed=42)
        b = _make_manifest(random_seed=99)
        diff = ReplayValidator.compare_manifests(a, b)
        assert diff.has_diff is True
        assert any("random_seed" in d for d in diff.seed_diffs)

    def test_random_seed_vs_none(self) -> None:
        a = _make_manifest(random_seed=42)
        b = _make_manifest(random_seed=None)
        diff = ReplayValidator.compare_manifests(a, b)
        assert diff.has_diff is True
        assert len(diff.seed_diffs) == 1

    def test_spec_hash_mismatch(self) -> None:
        a = _make_manifest(spec_hash="a" * 64)
        b = _make_manifest(spec_hash="b" * 64)
        diff = ReplayValidator.compare_manifests(a, b)
        assert diff.has_diff is True
        assert any("spec_hash" in d for d in diff.config_diffs)

    def test_rule_refs_mismatch(self) -> None:
        rule_a = RuleRef(
            instrument_id=_IID_510300,
            definition_version="abc",
            trading_rule_as_of="2025-01-01",
            fee_schedule_as_of="2025-01-01",
        )
        rule_b = RuleRef(
            instrument_id=_IID_510300,
            definition_version="def",
            trading_rule_as_of="2025-01-01",
            fee_schedule_as_of="2025-01-01",
        )
        a = _make_manifest(rule_refs=(rule_a,))
        b = _make_manifest(rule_refs=(rule_b,))
        diff = ReplayValidator.compare_manifests(a, b)
        assert diff.has_diff is True
        assert any("rule_refs" in d for d in diff.config_diffs)

    def test_multiple_diffs_categorized(self) -> None:
        a = _make_manifest(
            config_hash="aaa",
            engine_version="0.1.0",
            random_seed=42,
        )
        b = _make_manifest(
            config_hash="bbb",
            engine_version="0.2.0",
            random_seed=None,
        )
        diff = ReplayValidator.compare_manifests(a, b)
        assert len(diff.config_diffs) >= 1
        assert len(diff.version_diffs) >= 1
        assert len(diff.seed_diffs) >= 1


# ---------------------------------------------------------------------------
# Test ReplayValidator.compare_nav_series
# ---------------------------------------------------------------------------


class TestCompareNavSeries:
    """ReplayValidator.compare_nav_series — NAV comparison metrics."""

    def test_identical_series(self) -> None:
        nav = [100.0, 101.0, 102.0, 103.0, 104.0]
        comp = ReplayValidator.compare_nav_series(nav, nav)
        assert comp.identical is True
        assert comp.correlation == pytest.approx(1.0)
        assert comp.max_diff_bps == pytest.approx(0.0)
        assert comp.point_count == 5

    def test_different_series(self) -> None:
        a = [100.0, 101.0, 102.0, 103.0, 104.0]
        b = [100.0, 101.5, 102.5, 103.5, 104.5]
        comp = ReplayValidator.compare_nav_series(a, b)
        assert comp.identical is False
        assert comp.correlation > 0.99
        assert comp.max_diff_bps > 0.0
        assert comp.point_count == 5

    def test_single_point(self) -> None:
        comp = ReplayValidator.compare_nav_series([100.0], [100.0])
        assert comp.identical is True
        assert comp.point_count == 1

    def test_empty_series_returns_zero(self) -> None:
        comp = ReplayValidator.compare_nav_series([], [])
        assert comp.identical is True
        assert comp.point_count == 0

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ReplayError, match="length"):
            ReplayValidator.compare_nav_series([100.0], [100.0, 101.0])

    def test_bps_calculation(self) -> None:
        a = [100.0, 200.0]
        b = [100.0, 200.1]
        comp = ReplayValidator.compare_nav_series(a, b)
        # diff = 0.1, bps = 0.1 / 200.0 * 10000 = 5.0
        assert comp.max_diff_bps == pytest.approx(5.0)

    def test_high_correlation_similar_series(self) -> None:
        a = [100.0, 110.0, 120.0, 130.0, 140.0]
        b = [100.0, 110.5, 119.5, 130.5, 139.5]
        comp = ReplayValidator.compare_nav_series(a, b)
        assert comp.correlation > 0.99

    def test_zero_variance_constant_series(self) -> None:
        a = [100.0, 100.0, 100.0]
        b = [100.0, 100.0, 100.0]
        comp = ReplayValidator.compare_nav_series(a, b)
        assert comp.identical is True
        assert comp.correlation == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test ReplayValidator.validate
# ---------------------------------------------------------------------------


class TestValidate:
    """ReplayValidator.validate — end-to-end validation."""

    def test_perfect_replay(self) -> None:
        manifest = _make_manifest()
        nav = [100.0, 101.0, 102.0, 103.0, 104.0]
        result = ReplayValidator.validate(manifest, manifest, nav, nav)
        assert result.is_reproducible is True
        assert result.nav_correlation == pytest.approx(1.0)
        assert result.max_nav_diff_bps == pytest.approx(0.0)
        assert result.manifest_diff.has_diff is False
        assert result.input_data_match is True

    def test_r3_replay_requires_complete_evidence_on_both_sides(self) -> None:
        manifest = _make_manifest()

        result = ReplayValidator.validate(
            manifest,
            manifest,
            [100.0],
            [100.0],
            require_research_evidence=True,
        )

        assert result.is_reproducible is False
        assert result.reproduction_fingerprint_match is False
        assert result.key_result_summary_match is False
        assert result.required_artifact_hashes_match is False
        assert any("required" in item for item in result.manifest_diff.evidence_diffs)

    def test_r3_replay_passes_with_exact_semantics_summary_and_artifacts(self) -> None:
        evidence = _research_replay_evidence()
        original = _make_manifest(
            run_id="run-original",
            replay_evidence=evidence,
        )
        replay = _make_manifest(
            run_id="run-replay",
            replay_evidence=evidence,
            created_at="2026-04-12T00:00:00Z",
        )

        result = ReplayValidator.validate(
            original,
            replay,
            [100.0, 101.0],
            [100.0, 101.0],
            require_research_evidence=True,
        )

        assert result.is_reproducible is True
        assert result.reproduction_fingerprint_match is True
        assert result.key_result_summary_match is True
        assert result.required_artifact_hashes_match is True

    def test_failed_replay_config_diff(self) -> None:
        a = _make_manifest(config_hash="aaa")
        b = _make_manifest(config_hash="bbb")
        nav = [100.0, 101.0, 102.0]
        result = ReplayValidator.validate(a, b, nav, nav)
        assert result.is_reproducible is False
        assert result.manifest_diff.has_diff is True
        assert result.input_data_match is True  # NAV identical despite config diff

    def test_failed_replay_nav_diff(self) -> None:
        manifest = _make_manifest()
        nav_a = [100.0, 101.0, 102.0]
        nav_b = [100.0, 101.5, 103.0]
        result = ReplayValidator.validate(manifest, manifest, nav_a, nav_b)
        assert result.is_reproducible is False
        assert result.max_nav_diff_bps > 0.0

    def test_reproducible_with_different_run_id(self) -> None:
        a = _make_manifest(run_id="run-001")
        b = _make_manifest(run_id="run-002")
        nav = [100.0, 101.0, 102.0]
        result = ReplayValidator.validate(a, b, nav, nav)
        assert result.is_reproducible is True
        assert result.manifest_diff.has_diff is False

    def test_reproducible_with_different_created_at(self) -> None:
        a = _make_manifest()
        b = RunManifest(
            **{k: v for k, v in _make_manifest().__dict__.items() if k != "created_at"},
            created_at="2026-04-12T00:00:00Z",
        )
        nav = [100.0, 101.0, 102.0]
        result = ReplayValidator.validate(a, b, nav, nav)
        assert result.is_reproducible is True

    def test_input_data_mismatch_detected(self) -> None:
        a = _make_manifest(
            input_ref_details=(
                InputRef(
                    instrument_id=_IID_510300,
                    data_hash="sha256:aaa",
                    date_range=("2025-01-01", "2025-03-01"),
                    source="tushare",
                ),
            ),
        )
        b = _make_manifest(
            input_ref_details=(
                InputRef(
                    instrument_id=_IID_510300,
                    data_hash="sha256:bbb",
                    date_range=("2025-01-01", "2025-03-01"),
                    source="tushare",
                ),
            ),
        )
        nav = [100.0, 101.0, 102.0]
        result = ReplayValidator.validate(a, b, nav, nav)
        assert result.input_data_match is False
        assert result.is_reproducible is False
