"""Fail-closed edges for generated research code and sandbox attestations."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from typing import cast

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments import generated_code
from ditto_analysis.experiments.generated_code import (
    ResearchCodeArtifact,
    SandboxExecutionManifest,
    SandboxExitStatus,
    SandboxResourceLimits,
    canonical_research_ast_hash,
    validate_research_code_contract,
)
from ditto_analysis.experiments.models import ContentHash

VALID_SOURCE = (
    "def fit(training_stream):\n"
    "    return {'rows': tuple(training_stream)}\n"
    "def score(visible_window, immutable_model_state):\n"
    "    return tuple(visible_window)\n"
)


def _hash(character: str) -> ContentHash:
    return ContentHash(character * 64)


def _source_hash(source: str) -> ContentHash:
    return ContentHash(hashlib.sha256(source.encode("utf-8")).hexdigest())


def _artifact(
    *,
    source: str = VALID_SOURCE,
    canonical_hash: ContentHash | None = None,
    dependencies: Sequence[str] = ("polars==1.32.2",),
) -> ResearchCodeArtifact:
    return ResearchCodeArtifact(
        source_code=source,
        source_hash=_source_hash(source),
        canonical_ast_hash=(
            canonical_research_ast_hash(source)
            if canonical_hash is None
            else canonical_hash
        ),
        dependency_lock_hash=_hash("b"),
        dependencies=dependencies,
        image_digest=_hash("c"),
        input_schema_hash=_hash("d"),
        output_schema_hash=_hash("e"),
    )


def _reason(exc_info: pytest.ExceptionInfo[ExperimentSpecError]) -> object:
    return exc_info.value.details["reason_code"]


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "1"])
def test_resource_limits_require_positive_exact_integers(value: object) -> None:
    constructor = cast("Callable[..., SandboxResourceLimits]", SandboxResourceLimits)
    with pytest.raises(ExperimentSpecError) as exc_info:
        constructor(cpu_count=value)
    assert _reason(exc_info) == "invalid_sandbox_resource_limit"


@pytest.mark.parametrize(
    "dependencies",
    [
        cast("Sequence[str]", "polars==1.32.2"),
        (),
        ("",),
        (" polars==1.32.2",),
        cast("Sequence[str]", (1,)),
        ("polars==1.32.2", "polars==1.32.2"),
    ],
)
def test_code_artifact_rejects_ambiguous_dependency_manifests(
    dependencies: Sequence[str],
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _artifact(dependencies=dependencies)
    assert _reason(exc_info) == "invalid_research_code_dependencies"


def test_code_artifact_sorts_dependency_identity() -> None:
    artifact = _artifact(dependencies=("zlib==1.0", "polars==1.32.2"))
    assert artifact.dependencies == ("polars==1.32.2", "zlib==1.0")


def test_canonical_ast_hash_rejects_invalid_python() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        canonical_research_ast_hash("def broken(:\n")
    assert _reason(exc_info) == "invalid_generated_code_syntax"


@pytest.mark.parametrize(
    ("declaration", "expected_reason"),
    [
        ("A = B = 1", "mutable_generated_code_state"),
        ("state = 1", "mutable_generated_code_state"),
        ("VALUE: int", "mutable_generated_code_state"),
        ("VALUE = []", "mutable_generated_code_state"),
        ("VALUE = object()", "mutable_generated_code_state"),
        ("async def helper():\n    return None", "invalid_generated_code_signature"),
        ("class Mutable:\n    pass", "mutable_generated_code_state"),
    ],
)
def test_generated_module_rejects_mutable_or_unsupported_top_level_state(
    declaration: str,
    expected_reason: str,
) -> None:
    source = f"{declaration}\n{VALID_SOURCE}"
    artifact = _artifact(source=source)

    with pytest.raises(ExperimentSpecError) as exc_info:
        validate_research_code_contract(artifact)
    assert _reason(exc_info) == expected_reason


def test_generated_module_accepts_recursive_immutable_constants() -> None:
    source = "SETTINGS = (None, True, 1, 1.5, 1j, 'x', b'x', (2,))\n" + VALID_SOURCE
    validate_research_code_contract(_artifact(source=source))


def test_generated_module_rejects_duplicate_contract_functions() -> None:
    source = (
        "def fit(training_stream):\n    return {}\n"
        "def fit(training_stream):\n    return {}\n"
        "def score(visible_window, immutable_model_state):\n    return []\n"
    )
    with pytest.raises(ExperimentSpecError) as exc_info:
        validate_research_code_contract(_artifact(source=source))
    assert _reason(exc_info) == "invalid_generated_code_signature"


@pytest.mark.parametrize(
    "fit_signature",
    [
        "training_stream, *, option=False",
        "training_stream, *args",
        "training_stream, **kwargs",
        "training_stream=None",
    ],
)
def test_generated_module_rejects_signature_extensions(fit_signature: str) -> None:
    source = (
        f"def fit({fit_signature}):\n    return {{}}\n"
        "def score(visible_window, immutable_model_state):\n    return []\n"
    )
    with pytest.raises(ExperimentSpecError) as exc_info:
        validate_research_code_contract(_artifact(source=source))
    assert _reason(exc_info) == "invalid_generated_code_signature"


def test_generated_module_rejects_decorated_contract_function() -> None:
    source = (
        "def decorator(function):\n    return function\n"
        "@decorator\n"
        "def fit(training_stream):\n    return {}\n"
        "def score(visible_window, immutable_model_state):\n    return []\n"
    )
    with pytest.raises(ExperimentSpecError) as exc_info:
        validate_research_code_contract(_artifact(source=source))
    assert _reason(exc_info) == "invalid_generated_code_signature"


@pytest.mark.parametrize("scope_statement", ["global STATE", "nonlocal state"])
def test_generated_module_rejects_outer_state_mutation(scope_statement: str) -> None:
    if scope_statement.startswith("nonlocal"):
        source = (
            "def fit(training_stream):\n"
            "    state = 1\n"
            "    def mutate():\n"
            f"        {scope_statement}\n"
            "        state = 2\n"
            "    return {}\n"
            "def score(visible_window, immutable_model_state):\n    return []\n"
        )
    else:
        source = (
            "def fit(training_stream):\n"
            f"    {scope_statement}\n"
            "    STATE = 1\n"
            "    return {}\n"
            "def score(visible_window, immutable_model_state):\n    return []\n"
        )
    with pytest.raises(ExperimentSpecError) as exc_info:
        validate_research_code_contract(_artifact(source=source))
    assert _reason(exc_info) == "mutable_generated_code_state"


def test_generated_module_rejects_ast_hash_drift() -> None:
    artifact = _artifact(canonical_hash=_hash("f"))
    with pytest.raises(ExperimentSpecError) as exc_info:
        validate_research_code_contract(artifact)
    assert _reason(exc_info) == "generated_code_ast_hash_mismatch"


def test_contract_validator_requires_exact_artifact_type() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        validate_research_code_contract(cast("ResearchCodeArtifact", object()))
    assert _reason(exc_info) == "invalid_generated_code_contract"


def test_code_artifact_requires_nonempty_source_and_typed_hashes() -> None:
    constructor = cast("Callable[..., ResearchCodeArtifact]", ResearchCodeArtifact)
    with pytest.raises(ExperimentSpecError) as exc_info:
        constructor(
            source_code=" ",
            source_hash=_hash("a"),
            canonical_ast_hash=_hash("b"),
            dependency_lock_hash=_hash("c"),
            dependencies=("polars==1.32.2",),
            image_digest=_hash("d"),
            input_schema_hash=_hash("e"),
            output_schema_hash=_hash("f"),
        )
    assert _reason(exc_info) == "invalid_research_code_source"

    values: dict[str, object] = {
        "source_code": VALID_SOURCE,
        "source_hash": _source_hash(VALID_SOURCE),
        "canonical_ast_hash": canonical_research_ast_hash(VALID_SOURCE),
        "dependency_lock_hash": _hash("c"),
        "dependencies": ("polars==1.32.2",),
        "image_digest": _hash("d"),
        "input_schema_hash": _hash("e"),
        "output_schema_hash": _hash("f"),
    }
    for field in (
        "source_hash",
        "canonical_ast_hash",
        "dependency_lock_hash",
        "image_digest",
        "input_schema_hash",
        "output_schema_hash",
    ):
        malformed = {**values, field: "a" * 64}
        with pytest.raises(ExperimentSpecError) as exc_info:
            constructor(**malformed)
        assert _reason(exc_info) == "invalid_research_code_artifact"
        assert exc_info.value.details["field"] == field


def _manifest(**overrides: object) -> SandboxExecutionManifest:
    values: dict[str, object] = {
        "code_artifact_hash": _hash("a"),
        "runtime_digest": _hash("b"),
        "resource_limits": SandboxResourceLimits(),
        "input_hash": _hash("c"),
        "output_hash": _hash("d"),
        "seed": 42,
        "exit_status": SandboxExitStatus.SUCCEEDED,
        "exit_code": 0,
        "attestation_hash": _hash("e"),
    }
    values.update(overrides)
    constructor = cast(
        "Callable[..., SandboxExecutionManifest]", SandboxExecutionManifest
    )
    return constructor(**values)


@pytest.mark.parametrize(
    "field",
    [
        "code_artifact_hash",
        "runtime_digest",
        "resource_limits",
        "input_hash",
        "exit_status",
        "attestation_hash",
    ],
)
def test_sandbox_manifest_requires_exact_identity_types(field: str) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _manifest(**{field: object()})
    assert _reason(exc_info) == "invalid_sandbox_execution_manifest"
    assert exc_info.value.details["field"] == field


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"output_hash": "a" * 64}, "invalid_sandbox_execution_manifest"),
        ({"seed": True}, "invalid_sandbox_execution_manifest"),
        ({"seed": -1}, "invalid_sandbox_execution_manifest"),
        ({"exit_code": True}, "invalid_sandbox_execution_manifest"),
        ({"output_hash": None}, "invalid_sandbox_success_manifest"),
        ({"exit_code": 1}, "invalid_sandbox_success_manifest"),
        (
            {"exit_status": SandboxExitStatus.FAILED, "exit_code": 0},
            "invalid_sandbox_execution_manifest",
        ),
    ],
)
def test_sandbox_manifest_rejects_inconsistent_outcomes(
    overrides: dict[str, object],
    reason: str,
) -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        _manifest(**overrides)
    assert _reason(exc_info) == reason


def test_sandbox_manifest_accepts_nonzero_failure_without_output() -> None:
    manifest = _manifest(
        exit_status=SandboxExitStatus.FAILED,
        exit_code=2,
        output_hash=None,
    )
    assert manifest.exit_status is SandboxExitStatus.FAILED
    assert manifest.output_hash is None


def test_private_positive_limit_helper_reports_the_exact_field() -> None:
    with pytest.raises(ExperimentSpecError) as exc_info:
        generated_code._positive_int(0, "process_limit")
    assert exc_info.value.details == {
        "reason_code": "invalid_sandbox_resource_limit",
        "field": "process_limit",
    }
