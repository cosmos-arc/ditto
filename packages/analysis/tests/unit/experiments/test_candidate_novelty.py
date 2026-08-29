"""Candidate novelty is host-computed from code structure, output, and lineage."""

from __future__ import annotations

from dataclasses import replace

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.candidate_novelty import (
    CandidateNoveltyPolicy,
    CandidateOutputProfile,
    canonical_candidate_ast_hash,
    evaluate_candidate_novelty,
)
from ditto_analysis.experiments.models import ContentHash


def _hash(character: str) -> ContentHash:
    return ContentHash(character * 64)


def _profile(
    *,
    candidate_hash: ContentHash = ContentHash("a" * 64),
    canonical_ast_hash: ContentHash = ContentHash("b" * 64),
    validation_protocol_hash: ContentHash = ContentHash("c" * 64),
    lineage_root: ContentHash = ContentHash("d" * 64),
    observation_grid_hash: ContentHash = ContentHash("e" * 64),
    outputs: tuple[float, ...] = (1.0, -1.0, 1.0, -1.0),
) -> CandidateOutputProfile:
    return CandidateOutputProfile(
        candidate_hash=candidate_hash,
        canonical_ast_hash=canonical_ast_hash,
        validation_protocol_hash=validation_protocol_hash,
        lineage_root=lineage_root,
        observation_grid_hash=observation_grid_hash,
        outputs=outputs,
    )


def test_alpha_renamed_equivalent_code_has_one_canonical_ast_hash() -> None:
    first = """
def fit(training_stream):
    values = tuple(training_stream)
    return values

def score(visible_window, immutable_model_state):
    result = tuple(visible_window)
    return result
"""
    renamed = """
def fit(training_stream):
    observations = tuple(training_stream)
    return observations

def score(visible_window, immutable_model_state):
    predictions = tuple(visible_window)
    return predictions
"""

    assert canonical_candidate_ast_hash(first) == canonical_candidate_ast_hash(renamed)


@pytest.mark.parametrize(
    "outputs",
    [
        (2.0, 4.0, 6.0, 8.0),
        (-2.0, -4.0, -6.0, -8.0),
    ],
)
def test_absolute_output_correlation_rejects_semantic_duplicate(
    outputs: tuple[float, ...],
) -> None:
    reference = _profile(outputs=(1.0, 2.0, 3.0, 4.0))
    proposed = _profile(
        candidate_hash=_hash("f"),
        canonical_ast_hash=_hash("1"),
        outputs=outputs,
    )

    evidence = evaluate_candidate_novelty(
        proposed,
        references=(reference,),
        policy=CandidateNoveltyPolicy(max_abs_output_correlation=0.99),
    )

    assert evidence.accepted is False
    assert evidence.reason == "output_correlation_exceeds_limit"
    assert evidence.max_abs_output_correlation == pytest.approx(1.0)
    assert evidence.compared_candidate_hashes == (reference.candidate_hash,)
    assert evidence.verify_integrity()


def test_exact_canonical_ast_is_rejected_even_when_outputs_differ() -> None:
    reference = _profile()
    proposed = _profile(
        candidate_hash=_hash("f"),
        outputs=(1.0, 0.0, -1.0, 0.0),
    )

    evidence = evaluate_candidate_novelty(
        proposed,
        references=(reference,),
        policy=CandidateNoveltyPolicy(),
    )

    assert evidence.accepted is False
    assert evidence.reason == "duplicate_canonical_ast"
    assert evidence.duplicate_ast_candidate_hashes == (reference.candidate_hash,)


def test_low_correlation_distinct_ast_is_novel() -> None:
    reference = _profile(outputs=(1.0, 1.0, -1.0, -1.0))
    proposed = _profile(
        candidate_hash=_hash("f"),
        canonical_ast_hash=_hash("1"),
        outputs=(1.0, -1.0, -1.0, 1.0),
    )

    evidence = evaluate_candidate_novelty(
        proposed,
        references=(reference,),
        policy=CandidateNoveltyPolicy(max_abs_output_correlation=0.99),
    )

    assert evidence.accepted is True
    assert evidence.reason == "candidate_novel"
    assert evidence.max_abs_output_correlation == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("reference", "reason"),
    [
        (replace(_profile(), lineage_root=_hash("f")), "novelty_lineage_mismatch"),
        (
            replace(_profile(), observation_grid_hash=_hash("f")),
            "novelty_observation_grid_mismatch",
        ),
    ],
)
def test_lineage_or_same_protocol_grid_drift_fails_closed(
    reference: CandidateOutputProfile,
    reason: str,
) -> None:
    proposed = _profile(candidate_hash=_hash("1"), canonical_ast_hash=_hash("2"))

    with pytest.raises(ExperimentSpecError) as exc_info:
        evaluate_candidate_novelty(
            proposed,
            references=(reference,),
            policy=CandidateNoveltyPolicy(),
        )

    assert exc_info.value.details["reason_code"] == reason


def test_changed_protocol_does_not_compare_unaligned_outputs() -> None:
    reference = _profile()
    proposed = _profile(
        candidate_hash=_hash("f"),
        canonical_ast_hash=_hash("1"),
        validation_protocol_hash=_hash("2"),
        observation_grid_hash=_hash("3"),
    )

    evidence = evaluate_candidate_novelty(
        proposed,
        references=(reference,),
        policy=CandidateNoveltyPolicy(),
    )

    assert evidence.accepted is True
    assert evidence.compared_candidate_hashes == ()
    assert evidence.max_abs_output_correlation is None


def test_modified_factory_evidence_fails_integrity_verification() -> None:
    evidence = evaluate_candidate_novelty(
        _profile(),
        references=(),
        policy=CandidateNoveltyPolicy(),
    )

    tampered = replace(evidence, accepted=False)

    assert tampered.verify_integrity() is False
