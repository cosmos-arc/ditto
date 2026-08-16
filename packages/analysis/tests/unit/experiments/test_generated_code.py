"""R5 generated-code artifact and sandbox-manifest contract tests."""

from __future__ import annotations

import hashlib

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.generated_code import (
    ResearchCodeArtifact,
    SandboxExecutionManifest,
    SandboxExitStatus,
    SandboxResourceLimits,
    canonical_research_ast_hash,
    validate_research_code_contract,
)
from ditto_analysis.experiments.models import ContentHash

SOURCE = "def fit(training_stream):\n    return {'mean': 0.0}\n"


def _hash(character: str) -> ContentHash:
    return ContentHash(character * 64)


def _source_hash(source: str = SOURCE) -> ContentHash:
    return ContentHash(hashlib.sha256(source.encode("utf-8")).hexdigest())


def _artifact() -> ResearchCodeArtifact:
    return ResearchCodeArtifact(
        source_code=SOURCE,
        source_hash=_source_hash(),
        canonical_ast_hash=canonical_research_ast_hash(SOURCE),
        dependency_lock_hash=_hash("b"),
        dependencies=("numpy==2.3.2", "polars==1.32.2"),
        image_digest=_hash("c"),
        input_schema_hash=_hash("d"),
        output_schema_hash=_hash("e"),
    )


def test_code_artifact_is_content_addressed_and_dependency_locked() -> None:
    artifact = _artifact()

    assert artifact.source_hash == _source_hash()
    assert artifact.dependencies == ("numpy==2.3.2", "polars==1.32.2")
    assert not hasattr(artifact, "performance_metrics")


def test_code_artifact_rejects_source_hash_tamper() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        ResearchCodeArtifact(
            source_code=SOURCE,
            source_hash=_hash("f"),
            canonical_ast_hash=_hash("a"),
            dependency_lock_hash=_hash("b"),
            dependencies=("numpy==2.3.2",),
            image_digest=_hash("c"),
            input_schema_hash=_hash("d"),
            output_schema_hash=_hash("e"),
        )

    assert exc_info.value.details["reason_code"] == "research_code_hash_mismatch"


def test_sandbox_manifest_requires_attested_output_only_on_success() -> None:
    manifest = SandboxExecutionManifest(
        code_artifact_hash=_artifact().artifact_hash,
        runtime_digest=_hash("f"),
        resource_limits=SandboxResourceLimits(
            cpu_count=2,
            memory_bytes=4 * 1024**3,
            process_limit=64,
            temporary_storage_bytes=1024**3,
            wall_time_seconds=600,
            output_bytes=10 * 1024**2,
        ),
        input_hash=_hash("1"),
        output_hash=_hash("2"),
        seed=42,
        exit_status=SandboxExitStatus.SUCCEEDED,
        exit_code=0,
        attestation_hash=_hash("3"),
    )

    assert manifest.output_hash == _hash("2")
    assert not hasattr(manifest, "sharpe_ratio")


def test_sandbox_manifest_rejects_unattested_success() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        SandboxExecutionManifest(
            code_artifact_hash=_artifact().artifact_hash,
            runtime_digest=_hash("f"),
            resource_limits=SandboxResourceLimits(),
            input_hash=_hash("1"),
            output_hash=None,
            seed=42,
            exit_status=SandboxExitStatus.SUCCEEDED,
            exit_code=0,
            attestation_hash=_hash("3"),
        )

    assert exc_info.value.details["reason_code"] == "invalid_sandbox_success_manifest"


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        (
            "def fit(frame):\n    return {}\n"
            "def score(visible_window, immutable_model_state):\n    return []\n",
            "invalid_generated_code_signature",
        ),
        (
            "state = {}\n"
            "def fit(training_stream):\n    return {}\n"
            "def score(visible_window, immutable_model_state):\n    return []\n",
            "mutable_generated_code_state",
        ),
        (
            "async def fit(training_stream):\n    return {}\n"
            "def score(visible_window, immutable_model_state):\n    return []\n",
            "invalid_generated_code_signature",
        ),
    ],
)
def test_generated_code_contract_rejects_invalid_signature_or_mutable_state(
    source: str,
    reason: str,
) -> None:
    artifact = ResearchCodeArtifact(
        source_code=source,
        source_hash=_source_hash(source),
        canonical_ast_hash=canonical_research_ast_hash(source),
        dependency_lock_hash=_hash("b"),
        dependencies=("numpy==2.3.2",),
        image_digest=_hash("c"),
        input_schema_hash=_hash("d"),
        output_schema_hash=_hash("e"),
    )

    with pytest.raises(ExperimentSpecError) as exc_info:
        validate_research_code_contract(artifact)

    assert exc_info.value.details["reason_code"] == reason


def test_generated_code_contract_accepts_exact_fit_and_score_protocol() -> None:
    source = (
        "import math\n"
        "SCALE = 2.0\n"
        "def fit(training_stream):\n    return {'scale': SCALE}\n"
        "def score(visible_window, immutable_model_state):\n"
        "    return [math.tanh(row['value']) for row in visible_window]\n"
    )
    artifact = ResearchCodeArtifact(
        source_code=source,
        source_hash=_source_hash(source),
        canonical_ast_hash=canonical_research_ast_hash(source),
        dependency_lock_hash=_hash("b"),
        dependencies=("numpy==2.3.2",),
        image_digest=_hash("c"),
        input_schema_hash=_hash("d"),
        output_schema_hash=_hash("e"),
    )

    validate_research_code_contract(artifact)
