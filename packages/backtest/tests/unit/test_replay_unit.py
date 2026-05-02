"""ReplayValidator / ManifestDiff / NavComparison unit tests.

Phase 3.1 — Run Lineage / Replayability.
"""

from __future__ import annotations

import pytest
from ditto_backtest.manifest import (
    InputRef,
    RuleRef,
    RunManifest,
    RunMode,
)
from ditto_backtest.replay import (
    ManifestDiff,
    NavComparison,
    ReplayValidationResult,
    ReplayValidator,
)
from ditto_kernel.identity import InstrumentId

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
    parameter_overrides: tuple[str, ...] = (),
    rule_refs: tuple[RuleRef, ...] = (),
    spec_hash: str = "",
    random_seed: int | None = None,
    dependency_versions: tuple[str, ...] = (),
    input_ref_details: tuple[InputRef, ...] = (),
) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        mode=RunMode.BACKTEST,
        created_at="2026-04-11T00:00:00Z",
        input_refs=input_refs,
        input_ref_details=input_ref_details,
        parameter_overrides=parameter_overrides,
        rule_refs=rule_refs,
        config_hash=config_hash,
        engine_version=engine_version,
        spec_hash=spec_hash,
        random_seed=random_seed,
        dependency_versions=dependency_versions,
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

    def test_parameter_overrides_mismatch(self) -> None:
        a = _make_manifest(parameter_overrides=("key1=val1",))
        b = _make_manifest(parameter_overrides=("key1=val2",))
        diff = ReplayValidator.compare_manifests(a, b)
        assert diff.has_diff is True
        assert any("parameter_overrides" in d for d in diff.config_diffs)

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
        a = _make_manifest(spec_hash="spec_aaa")
        b = _make_manifest(spec_hash="spec_bbb")
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
        with pytest.raises(ValueError, match="length"):
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
