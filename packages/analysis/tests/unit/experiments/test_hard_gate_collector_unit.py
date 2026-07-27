"""Unit tests for projecting typed observed facts onto hard-correctness gates."""

from __future__ import annotations

from dataclasses import replace

import pytest
from ditto_analysis.experiments import (
    ContentHash,
    GateFact,
    HardGateEvidence,
    HardGateEvidenceView,
    collect_hard_gate_evidence,
)


def _hash(seed: str) -> ContentHash:
    """Build a valid lowercase SHA-256 ContentHash from a single-char seed."""

    return ContentHash(seed * 64)


def _all_satisfied_view() -> HardGateEvidenceView:
    """View where every gate's facts lead to satisfaction (except r2_live_gate)."""

    return HardGateEvidenceView(
        certified_snapshot=True,
        snapshot_id="snap-001",
        oos_month_count=96,
        pit_policy="sample_time",
        purge_embargo_configured=True,
        reproduction_fingerprints=(_hash("a"), _hash("b")),
        cost_config_hash=_hash("c"),
        baseline_candidate_id="candidate-baseline",
        trial_count=5,
        expected_trial_count=5,
        holdout_claim_id="claim-001",
        artifact_complete=True,
        artifact_missing=(),
    )


def test_collect_returns_hard_gate_evidence_instance() -> None:
    evidence = collect_hard_gate_evidence(_all_satisfied_view())

    assert isinstance(evidence, HardGateEvidence)


def test_all_satisfied_view_passes_ten_gates_except_r2_live() -> None:
    evidence = collect_hard_gate_evidence(_all_satisfied_view())

    assert evidence.certified_snapshot.satisfied is True
    assert evidence.ninety_six_month.satisfied is True
    assert evidence.pit_known_at.satisfied is True
    assert evidence.split_purge_embargo.satisfied is True
    assert evidence.reproduction.satisfied is True
    assert evidence.cost_assumptions.satisfied is True
    assert evidence.baseline_declared.satisfied is True
    assert evidence.trial_declaration.satisfied is True
    assert evidence.holdout_claim.satisfied is True
    assert evidence.artifact_completeness.satisfied is True
    # r2_live_gate is always NOT_EVALUATED (deferred to G2 live acceptance)
    assert evidence.r2_live_gate.satisfied is None


def test_collect_is_pure_for_equal_inputs() -> None:
    """Referential transparency: equal views project to equal evidence."""

    first = collect_hard_gate_evidence(_all_satisfied_view())
    second = collect_hard_gate_evidence(_all_satisfied_view())

    assert first == second


def test_certified_snapshot_passes_when_flag_true() -> None:
    evidence = collect_hard_gate_evidence(_all_satisfied_view())

    assert evidence.certified_snapshot.satisfied is True
    assert evidence.certified_snapshot.detail == {"snapshot_id": "snap-001"}


def test_certified_snapshot_fails_when_flag_false() -> None:
    view = replace(_all_satisfied_view(), certified_snapshot=False)

    evidence = collect_hard_gate_evidence(view)

    assert evidence.certified_snapshot.satisfied is False
    assert evidence.certified_snapshot.detail == {"snapshot_id": "snap-001"}


def test_ninety_six_month_passes_at_threshold() -> None:
    view = replace(_all_satisfied_view(), oos_month_count=96)

    evidence = collect_hard_gate_evidence(view)

    assert evidence.ninety_six_month.satisfied is True
    assert evidence.ninety_six_month.detail == {"oos_months": 96, "required": 96}


def test_ninety_six_month_passes_above_threshold() -> None:
    view = replace(_all_satisfied_view(), oos_month_count=120)

    evidence = collect_hard_gate_evidence(view)

    assert evidence.ninety_six_month.satisfied is True
    assert evidence.ninety_six_month.detail == {"oos_months": 120, "required": 96}


def test_ninety_six_month_fails_below_threshold() -> None:
    view = replace(_all_satisfied_view(), oos_month_count=95)

    evidence = collect_hard_gate_evidence(view)

    assert evidence.ninety_six_month.satisfied is False
    assert evidence.ninety_six_month.detail == {"oos_months": 95, "required": 96}


def test_pit_known_at_passes_with_sample_time_policy() -> None:
    view = replace(_all_satisfied_view(), pit_policy="sample_time")

    evidence = collect_hard_gate_evidence(view)

    assert evidence.pit_known_at.satisfied is True
    assert evidence.pit_known_at.detail == {"pit_policy": "sample_time"}


def test_pit_known_at_fails_with_other_policy() -> None:
    view = replace(_all_satisfied_view(), pit_policy="event_time")

    evidence = collect_hard_gate_evidence(view)

    assert evidence.pit_known_at.satisfied is False
    assert evidence.pit_known_at.detail == {"pit_policy": "event_time"}


def test_split_purge_embargo_passes_when_configured() -> None:
    view = replace(_all_satisfied_view(), purge_embargo_configured=True)

    evidence = collect_hard_gate_evidence(view)

    assert evidence.split_purge_embargo.satisfied is True
    assert evidence.split_purge_embargo.detail is None


def test_split_purge_embargo_fails_when_not_configured() -> None:
    view = replace(_all_satisfied_view(), purge_embargo_configured=False)

    evidence = collect_hard_gate_evidence(view)

    assert evidence.split_purge_embargo.satisfied is False


def test_reproduction_fails_with_empty_fingerprints() -> None:
    view = replace(_all_satisfied_view(), reproduction_fingerprints=())

    evidence = collect_hard_gate_evidence(view)

    assert evidence.reproduction.satisfied is False


def test_reproduction_passes_with_one_fingerprint() -> None:
    view = replace(_all_satisfied_view(), reproduction_fingerprints=(_hash("a"),))

    evidence = collect_hard_gate_evidence(view)

    assert evidence.reproduction.satisfied is True


def test_cost_assumptions_passes_when_hash_present() -> None:
    """V1 semantics: a present cost config hash satisfies the gate."""

    view = replace(_all_satisfied_view(), cost_config_hash=_hash("d"))

    evidence = collect_hard_gate_evidence(view)

    assert evidence.cost_assumptions.satisfied is True
    assert evidence.cost_assumptions.detail == {
        "cost_config_hash": "d" * 64,
    }


def test_baseline_declared_passes_when_non_empty() -> None:
    view = replace(_all_satisfied_view(), baseline_candidate_id="candidate-baseline")

    evidence = collect_hard_gate_evidence(view)

    assert evidence.baseline_declared.satisfied is True
    assert evidence.baseline_declared.detail == {
        "baseline_candidate_id": "candidate-baseline",
    }


def test_baseline_declared_fails_when_empty() -> None:
    view = replace(_all_satisfied_view(), baseline_candidate_id="")

    evidence = collect_hard_gate_evidence(view)

    assert evidence.baseline_declared.satisfied is False
    assert evidence.baseline_declared.detail == {"baseline_candidate_id": ""}


def test_trial_declaration_passes_when_counts_match() -> None:
    view = replace(
        _all_satisfied_view(),
        trial_count=5,
        expected_trial_count=5,
    )

    evidence = collect_hard_gate_evidence(view)

    assert evidence.trial_declaration.satisfied is True
    assert evidence.trial_declaration.detail == {"trial_count": 5, "expected": 5}


def test_trial_declaration_fails_when_mismatch() -> None:
    view = replace(
        _all_satisfied_view(),
        trial_count=3,
        expected_trial_count=5,
    )

    evidence = collect_hard_gate_evidence(view)

    assert evidence.trial_declaration.satisfied is False
    assert evidence.trial_declaration.detail == {"trial_count": 3, "expected": 5}


def test_holdout_claim_not_evaluated_when_absent() -> None:
    view = replace(_all_satisfied_view(), holdout_claim_id=None)

    evidence = collect_hard_gate_evidence(view)

    assert evidence.holdout_claim.satisfied is None
    assert evidence.holdout_claim.detail == {"claim_id": None}


def test_holdout_claim_passes_when_present() -> None:
    view = replace(_all_satisfied_view(), holdout_claim_id="claim-999")

    evidence = collect_hard_gate_evidence(view)

    assert evidence.holdout_claim.satisfied is True
    assert evidence.holdout_claim.detail == {"claim_id": "claim-999"}


def test_artifact_completeness_passes_when_complete() -> None:
    view = replace(_all_satisfied_view(), artifact_complete=True, artifact_missing=())

    evidence = collect_hard_gate_evidence(view)

    assert evidence.artifact_completeness.satisfied is True
    assert evidence.artifact_completeness.detail == {"missing": ()}


def test_artifact_completeness_fails_when_incomplete_with_missing() -> None:
    view = replace(
        _all_satisfied_view(),
        artifact_complete=False,
        artifact_missing=("report.md", "metrics.json"),
    )

    evidence = collect_hard_gate_evidence(view)

    assert evidence.artifact_completeness.satisfied is False
    assert evidence.artifact_completeness.detail == {
        "missing": ("report.md", "metrics.json"),
    }


def test_r2_live_gate_always_not_evaluated() -> None:
    """Beta stage: r2_live_gate stays NOT_EVALUATED regardless of view state."""

    evidence = collect_hard_gate_evidence(_all_satisfied_view())

    assert evidence.r2_live_gate.satisfied is None
    assert evidence.r2_live_gate.detail is None


def test_view_is_frozen() -> None:
    """HardGateEvidenceView must be immutable to keep observed facts stable."""

    view = _all_satisfied_view()

    with pytest.raises(Exception):  # noqa: B017 - frozen-assignment raises vary
        view.certified_snapshot = False  # type: ignore[misc]


def test_gate_fact_default_detail_is_none() -> None:
    """GateFact remains a thin satisfied+detail record."""

    fact = GateFact(True)

    assert fact.detail is None
    assert fact.satisfied is True
