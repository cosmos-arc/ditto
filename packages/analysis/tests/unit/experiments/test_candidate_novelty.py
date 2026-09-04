"""Candidate novelty is host-computed from code structure, output, and lineage."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.candidate_novelty import (
    CandidateNoveltyEvidence,
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


@pytest.mark.parametrize("source", [cast("str", None), "", "   ", "def broken("])
def test_candidate_ast_hash_rejects_empty_untyped_or_invalid_source(
    source: str,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        canonical_candidate_ast_hash(source)
    assert exc_info.value.details["reason_code"] == "invalid_candidate_novelty_source"


def test_candidate_ast_hash_normalizes_async_and_all_argument_kinds() -> None:
    first = '''
async def score(seed, /, value, *extras, flag=True, **options):
    """inert documentation"""
    result = seed + value + sum(extras)
    return result if flag else options.get("fallback", result)
'''
    renamed = '''
async def score(left, /, right, *items, enabled=True, **settings):
    """different inert documentation"""
    output = left + right + sum(items)
    return output if enabled else settings.get("fallback", output)
'''
    assert canonical_candidate_ast_hash(first) == canonical_candidate_ast_hash(renamed)


def test_candidate_ast_hash_preserves_module_names_and_non_string_expressions() -> None:
    first = "external = 1\nprint(external)"
    second = "renamed = 1\nprint(renamed)"
    assert canonical_candidate_ast_hash(first) != canonical_candidate_ast_hash(second)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("candidate_hash", "hash"),
        ("canonical_ast_hash", "hash"),
        ("validation_protocol_hash", "hash"),
        ("lineage_root", "hash"),
        ("observation_grid_hash", "hash"),
    ],
)
def test_candidate_profile_requires_typed_content_hashes(
    field: str, value: object
) -> None:
    values: dict[str, object] = {
        "candidate_hash": _hash("a"),
        "canonical_ast_hash": _hash("b"),
        "validation_protocol_hash": _hash("c"),
        "lineage_root": _hash("d"),
        "observation_grid_hash": _hash("e"),
    }
    values[field] = value
    with pytest.raises(ExperimentSpecError):
        CandidateOutputProfile(
            candidate_hash=cast("ContentHash", values["candidate_hash"]),
            canonical_ast_hash=cast("ContentHash", values["canonical_ast_hash"]),
            validation_protocol_hash=cast(
                "ContentHash", values["validation_protocol_hash"]
            ),
            lineage_root=cast("ContentHash", values["lineage_root"]),
            observation_grid_hash=cast("ContentHash", values["observation_grid_hash"]),
            outputs=(1.0, 2.0, 3.0),
        )


@pytest.mark.parametrize(
    "outputs",
    [
        cast("object", "outputs"),
        cast("object", b"outputs"),
        cast("object", 1),
        (),
        (1.0, 2.0),
        (1.0, True, 3.0),
        (1.0, float("nan"), 3.0),
        (1.0, 1.0, 1.0),
    ],
)
def test_candidate_profile_rejects_invalid_outputs(outputs: object) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        CandidateOutputProfile(
            candidate_hash=_hash("a"),
            canonical_ast_hash=_hash("b"),
            validation_protocol_hash=_hash("c"),
            lineage_root=_hash("d"),
            observation_grid_hash=_hash("e"),
            outputs=cast("tuple[float, ...]", outputs),
        )
    assert exc_info.value.details["reason_code"] == "invalid_candidate_output_profile"


def test_candidate_profile_freezes_mutable_outputs_and_hashes_all_context() -> None:
    outputs = [1, 2.5, 3]
    profile = CandidateOutputProfile(
        candidate_hash=_hash("a"),
        canonical_ast_hash=_hash("b"),
        validation_protocol_hash=_hash("c"),
        lineage_root=_hash("d"),
        observation_grid_hash=_hash("e"),
        outputs=outputs,
    )
    outputs.append(4)
    assert profile.outputs == (1.0, 2.5, 3.0)
    assert (
        profile.profile_hash
        != replace(profile, observation_grid_hash=_hash("f")).profile_hash
    )


@pytest.mark.parametrize(
    ("threshold", "minimum"),
    [
        (cast("float", 1), 3),
        (float("nan"), 3),
        (0.0, 3),
        (-0.1, 3),
        (1.01, 3),
        (0.9, cast("int", True)),
        (0.9, 2),
    ],
)
def test_novelty_policy_rejects_invalid_thresholds_and_counts(
    threshold: float,
    minimum: int,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        CandidateNoveltyPolicy(threshold, minimum)
    assert exc_info.value.details["reason_code"] == "invalid_candidate_novelty_policy"


def test_novelty_policy_hash_binds_both_predeclared_limits() -> None:
    assert (
        CandidateNoveltyPolicy().policy_hash
        != CandidateNoveltyPolicy(
            max_abs_output_correlation=0.9,
            minimum_observations=4,
        ).policy_hash
    )


def _evidence() -> CandidateNoveltyEvidence:
    return evaluate_candidate_novelty(
        _profile(),
        references=(),
        policy=CandidateNoveltyPolicy(),
    )


def test_novelty_evidence_rejects_untrusted_construction() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        replace(_evidence(), _factory_token=object())
    assert (
        exc_info.value.details["reason_code"] == "untrusted_candidate_novelty_evidence"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("candidate_hash", "hash"),
        ("evidence_hash", "hash"),
        ("compared_candidate_hashes", ("hash",)),
        ("duplicate_ast_candidate_hashes", ("hash",)),
        ("correlated_candidate_hashes", ("hash",)),
        ("max_abs_output_correlation", 1),
        ("max_abs_output_correlation", float("nan")),
        ("max_abs_output_correlation", -0.1),
        ("max_abs_output_correlation", 1.1),
        ("accepted", 1),
        ("reason", 1),
    ],
)
def test_factory_evidence_rejects_forged_decision_fields(
    field: str, value: object
) -> None:
    with pytest.raises(ExperimentSpecError):
        replace(_evidence(), **{field: value})


def test_factory_evidence_sorts_candidate_hash_sets() -> None:
    first = _profile(candidate_hash=_hash("f"), validation_protocol_hash=_hash("1"))
    second = _profile(candidate_hash=_hash("0"), validation_protocol_hash=_hash("1"))
    evidence = evaluate_candidate_novelty(
        _profile(validation_protocol_hash=_hash("2")),
        references=(first, second),
        policy=CandidateNoveltyPolicy(),
    )
    assert evidence.compared_candidate_hashes == ()
    assert evidence.canonical_body()["candidate_hash"] == str(_hash("a"))


@pytest.mark.parametrize(
    "references", [None, "profiles", b"profiles", 1, (_profile(), object())]
)
def test_evaluator_rejects_invalid_reference_collections(references: object) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        evaluate_candidate_novelty(
            _profile(candidate_hash=_hash("1")),
            references=cast("tuple[CandidateOutputProfile, ...]", references),
            policy=CandidateNoveltyPolicy(),
        )
    assert (
        exc_info.value.details["reason_code"] == "invalid_candidate_novelty_references"
    )


def test_evaluator_rejects_duplicate_reference_candidate_hashes() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        evaluate_candidate_novelty(
            _profile(candidate_hash=_hash("1")),
            references=(_profile(), replace(_profile(), canonical_ast_hash=_hash("f"))),
            policy=CandidateNoveltyPolicy(),
        )
    assert (
        exc_info.value.details["reason_code"] == "invalid_candidate_novelty_references"
    )


def test_evaluator_rejects_untyped_profile_policy_and_insufficient_observations() -> (
    None
):
    with pytest.raises(ExperimentSpecError):
        evaluate_candidate_novelty(
            cast("CandidateOutputProfile", "profile"),
            references=(),
            policy=CandidateNoveltyPolicy(),
        )
    with pytest.raises(ExperimentSpecError):
        evaluate_candidate_novelty(
            _profile(),
            references=(),
            policy=cast("CandidateNoveltyPolicy", "policy"),
        )
    with pytest.raises(ExperimentSpecError) as exc_info:
        evaluate_candidate_novelty(
            _profile(),
            references=(),
            policy=CandidateNoveltyPolicy(minimum_observations=5),
        )
    assert (
        exc_info.value.details["reason_code"]
        == "candidate_novelty_observations_insufficient"
    )


def test_evaluator_fails_closed_if_a_profile_is_forged_constant_after_validation() -> (
    None
):
    reference = _profile()
    object.__setattr__(reference, "outputs", (1.0, 1.0, 1.0, 1.0))
    with pytest.raises(ExperimentSpecError) as exc_info:
        evaluate_candidate_novelty(
            _profile(candidate_hash=_hash("1"), canonical_ast_hash=_hash("2")),
            references=(reference,),
            policy=CandidateNoveltyPolicy(),
        )
    assert exc_info.value.details["reason_code"] == "invalid_candidate_output_profile"
