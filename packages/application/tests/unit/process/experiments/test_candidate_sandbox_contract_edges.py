"""Adversarial tests for the generated-candidate sandbox boundary contracts."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import cast

import pytest
from ditto_analysis.experiments.generated_code import (
    ResearchCodeArtifact,
    SandboxExecutionManifest,
    SandboxResourceLimits,
    canonical_research_ast_hash,
)
from ditto_analysis.experiments.models import ContentHash, SnapshotId
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.candidate_sandbox_port import (
    FrozenSandboxArtifact,
    FrozenSandboxWindow,
    SandboxArtifactFormat,
    SandboxExecutionResult,
    SandboxFitRequest,
    SandboxScoreKey,
    SandboxScoreRequest,
    build_successful_sandbox_result,
    freeze_sandbox_artifact,
)

pytestmark = [pytest.mark.unit, pytest.mark.pit]

_SOURCE = (
    "def fit(training_stream):\n"
    "    return {}\n"
    "def score(visible_window, immutable_model_state):\n"
    "    return []\n"
)
_SCHEMA_HASH = ContentHash("1" * 64)


def _hash(value: bytes | str) -> ContentHash:
    raw = value.encode() if isinstance(value, str) else value
    return ContentHash(hashlib.sha256(raw).hexdigest())


def _code() -> ResearchCodeArtifact:
    return ResearchCodeArtifact(
        source_code=_SOURCE,
        source_hash=_hash(_SOURCE),
        canonical_ast_hash=canonical_research_ast_hash(_SOURCE),
        dependency_lock_hash=ContentHash("2" * 64),
        dependencies=("numpy==2.3.2",),
        image_digest=ContentHash("3" * 64),
        input_schema_hash=_SCHEMA_HASH,
        output_schema_hash=ContentHash("4" * 64),
    )


def _artifact(
    *,
    payload: bytes = b"{}",
    row_count: int = 1,
) -> FrozenSandboxArtifact:
    return freeze_sandbox_artifact(
        payload,
        serialization=SandboxArtifactFormat.JSON,
        schema_hash=_SCHEMA_HASH,
        row_count=row_count,
    )


def _score_key() -> SandboxScoreKey:
    return SandboxScoreKey(
        entity_id="510300.SH",
        event_time_epoch_us=10,
        known_at_epoch_us=9,
        publication_time_epoch_us=8,
        execution_eligible_at_epoch_us=11,
    )


def _window() -> FrozenSandboxWindow:
    return FrozenSandboxWindow(
        artifact=_artifact(),
        snapshot_id=SnapshotId("snapshot:sandbox-contract"),
        decision_time_epoch_us=10,
        knowledge_cutoff_epoch_us=9,
        publication_cutoff_epoch_us=8,
        score_keys=(_score_key(),),
    )


def _fit_request() -> SandboxFitRequest:
    return SandboxFitRequest(
        code_artifact=_code(),
        training_stream=_window(),
        resource_limits=SandboxResourceLimits(),
        seed=7,
    )


def _reason(exc_info: pytest.ExceptionInfo[AppProcessError]) -> object:
    return exc_info.value.details["reason"]


def _expect_invalid(reason: str, factory: Callable[[], object]) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        factory()
    assert _reason(exc_info) == reason


def test_artifact_rejects_empty_mutable_untyped_and_forged_bytes() -> None:
    valid_hash = _hash(b"payload")
    cases: tuple[tuple[str, Callable[[], object]], ...] = (
        (
            "sandbox_artifact_payload_invalid",
            lambda: FrozenSandboxArtifact(
                b"",
                SandboxArtifactFormat.JSON,
                _hash(b""),
                _SCHEMA_HASH,
                0,
            ),
        ),
        (
            "sandbox_artifact_payload_invalid",
            lambda: freeze_sandbox_artifact(
                cast("bytes", bytearray(b"payload")),
                serialization=SandboxArtifactFormat.JSON,
                schema_hash=_SCHEMA_HASH,
                row_count=1,
            ),
        ),
        (
            "sandbox_artifact_serialization_invalid",
            lambda: FrozenSandboxArtifact(
                b"payload",
                cast("SandboxArtifactFormat", "application/json"),
                valid_hash,
                _SCHEMA_HASH,
                1,
            ),
        ),
        (
            "sandbox_artifact_identity_invalid",
            lambda: FrozenSandboxArtifact(
                b"payload",
                SandboxArtifactFormat.JSON,
                cast("ContentHash", valid_hash.value),
                _SCHEMA_HASH,
                1,
            ),
        ),
        (
            "sandbox_artifact_row_count_invalid",
            lambda: FrozenSandboxArtifact(
                b"payload",
                SandboxArtifactFormat.JSON,
                valid_hash,
                _SCHEMA_HASH,
                -1,
            ),
        ),
        (
            "sandbox_artifact_hash_mismatch",
            lambda: FrozenSandboxArtifact(
                b"payload",
                SandboxArtifactFormat.JSON,
                ContentHash("f" * 64),
                _SCHEMA_HASH,
                1,
            ),
        ),
    )

    for reason, factory in cases:
        _expect_invalid(reason, factory)


def test_score_key_rejects_ambiguous_identity_and_time_semantics() -> None:
    key = _score_key()
    cases: tuple[tuple[str, Callable[[], object]], ...] = (
        (
            "sandbox_score_identity_invalid",
            lambda: replace(key, entity_id=" 510300.SH"),
        ),
        (
            "sandbox_score_time_invalid",
            lambda: replace(key, known_at_epoch_us=-1),
        ),
        (
            "sandbox_score_publication_after_knowledge",
            lambda: replace(key, publication_time_epoch_us=10),
        ),
        (
            "same_close_execution_forbidden",
            lambda: replace(key, execution_eligible_at_epoch_us=10),
        ),
    )

    for reason, factory in cases:
        _expect_invalid(reason, factory)


def test_window_rejects_untyped_nodes_and_invalid_cutoffs() -> None:
    valid = _window()
    cases: tuple[tuple[str, Callable[[], object]], ...] = (
        (
            "sandbox_window_artifact_invalid",
            lambda: replace(valid, artifact=cast("FrozenSandboxArtifact", object())),
        ),
        (
            "sandbox_window_snapshot_invalid",
            lambda: replace(valid, snapshot_id=cast("SnapshotId", "snapshot")),
        ),
        (
            "sandbox_window_cutoff_invalid",
            lambda: replace(valid, decision_time_epoch_us=-1),
        ),
        (
            "sandbox_window_temporal_order_invalid",
            lambda: replace(valid, publication_cutoff_epoch_us=10),
        ),
        (
            "sandbox_window_keys_invalid",
            lambda: replace(
                valid,
                score_keys=cast("Sequence[SandboxScoreKey]", "not-keys"),
            ),
        ),
        (
            "sandbox_window_keys_invalid",
            lambda: replace(
                valid,
                score_keys=(cast("SandboxScoreKey", object()),),
            ),
        ),
    )

    for reason, factory in cases:
        _expect_invalid(reason, factory)


def test_window_rejects_row_identity_and_publication_boundary_drift() -> None:
    valid = _window()
    _expect_invalid(
        "sandbox_window_row_count_mismatch",
        lambda: replace(valid, artifact=_artifact(row_count=2)),
    )
    _expect_invalid(
        "sandbox_window_duplicate_identity",
        lambda: FrozenSandboxWindow(
            artifact=_artifact(row_count=2),
            snapshot_id=valid.snapshot_id,
            decision_time_epoch_us=valid.decision_time_epoch_us,
            knowledge_cutoff_epoch_us=valid.knowledge_cutoff_epoch_us,
            publication_cutoff_epoch_us=valid.publication_cutoff_epoch_us,
            score_keys=(_score_key(), _score_key()),
        ),
    )
    future_publication = SandboxScoreKey(
        entity_id="510300.SH",
        event_time_epoch_us=10,
        known_at_epoch_us=12,
        publication_time_epoch_us=11,
        execution_eligible_at_epoch_us=13,
    )
    _expect_invalid(
        "sandbox_window_future_publication",
        lambda: FrozenSandboxWindow(
            artifact=_artifact(),
            snapshot_id=valid.snapshot_id,
            decision_time_epoch_us=12,
            knowledge_cutoff_epoch_us=12,
            publication_cutoff_epoch_us=10,
            score_keys=(future_publication,),
        ),
    )


def test_invocations_reject_untyped_code_window_limits_state_and_seed() -> None:
    valid = _fit_request()
    cases: tuple[tuple[str, Callable[[], object]], ...] = (
        (
            "sandbox_code_artifact_invalid",
            lambda: replace(
                valid,
                code_artifact=cast("ResearchCodeArtifact", object()),
            ),
        ),
        (
            "sandbox_window_invalid",
            lambda: replace(
                valid,
                training_stream=cast("FrozenSandboxWindow", object()),
            ),
        ),
        (
            "sandbox_resource_limits_invalid",
            lambda: replace(
                valid,
                resource_limits=cast("SandboxResourceLimits", object()),
            ),
        ),
        ("sandbox_seed_invalid", lambda: replace(valid, seed=-1)),
        (
            "sandbox_model_state_invalid",
            lambda: SandboxScoreRequest(
                code_artifact=valid.code_artifact,
                visible_window=valid.training_stream,
                immutable_model_state=cast("FrozenSandboxArtifact", object()),
                resource_limits=valid.resource_limits,
                seed=valid.seed,
            ),
        ),
    )

    for reason, factory in cases:
        _expect_invalid(reason, factory)


def test_execution_result_requires_exact_output_and_manifest_nodes() -> None:
    request = _fit_request()
    output = _artifact(payload=b'{"model": 1}')
    valid = build_successful_sandbox_result(request, output)

    _expect_invalid(
        "sandbox_execution_result_invalid",
        lambda: SandboxExecutionResult(
            output=cast("FrozenSandboxArtifact", object()),
            manifest=valid.manifest,
        ),
    )
    _expect_invalid(
        "sandbox_execution_result_invalid",
        lambda: SandboxExecutionResult(
            output=valid.output,
            manifest=cast("SandboxExecutionManifest", object()),
        ),
    )
    assert valid.manifest.input_hash == request.input_hash
    assert valid.manifest.output_hash == output.content_hash
