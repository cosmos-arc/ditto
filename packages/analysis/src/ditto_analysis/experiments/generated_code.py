"""Pure generated research-code and sandbox attestation contracts."""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.models import ContentHash
from ditto_analysis.experiments.persistence import canonical_payload

__all__ = [
    "ResearchCodeArtifact",
    "SandboxExecutionManifest",
    "SandboxExitStatus",
    "SandboxResourceLimits",
    "canonical_research_ast_hash",
    "validate_research_code_contract",
]


def _code_error(
    message: str,
    reason_code: str,
    **details: object,
) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _positive_int(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise _code_error(
            f"{field} must be a positive integer",
            "invalid_sandbox_resource_limit",
            field=field,
        )
    return value


def _freeze_dependencies(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _code_error(
            "dependencies must be an ordered sequence",
            "invalid_research_code_dependencies",
        )
    raw = tuple(cast("Sequence[object]", value))
    if not raw or any(
        type(item) is not str or not item.strip() or item != item.strip()
        for item in raw
    ):
        raise _code_error(
            "dependencies must contain pinned non-empty declarations",
            "invalid_research_code_dependencies",
        )
    typed = cast("tuple[str, ...]", raw)
    if len(set(typed)) != len(typed):
        raise _code_error(
            "dependencies cannot contain duplicates",
            "invalid_research_code_dependencies",
        )
    return tuple(sorted(typed))


def canonical_research_ast_hash(source_code: str) -> ContentHash:
    """Return a location-independent hash of one parsed research module."""
    try:
        tree = ast.parse(source_code, mode="exec")
    except (SyntaxError, ValueError, TypeError) as exc:
        raise _code_error(
            "generated research code is not valid Python",
            "invalid_generated_code_syntax",
            parser_error=type(exc).__name__,
        ) from exc
    canonical = ast.dump(tree, annotate_fields=True, include_attributes=False)
    return ContentHash(hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _immutable_module_constant(node: ast.Assign | ast.AnnAssign) -> bool:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    if len(targets) != 1 or not isinstance(targets[0], ast.Name):
        return False
    if not targets[0].id.isupper():
        return False
    value = node.value
    if value is None:
        return False
    try:
        literal = ast.literal_eval(value)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False

    def _immutable(item: object) -> bool:
        if item is None or type(item) in (bool, int, float, complex, str, bytes):
            return True
        if not isinstance(item, tuple):
            return False
        parts = cast("tuple[object, ...]", item)
        return all(_immutable(part) for part in parts)

    return _immutable(literal)


def _exact_signature(function: ast.FunctionDef, names: tuple[str, ...]) -> bool:
    arguments = function.args
    return (
        tuple(argument.arg for argument in arguments.posonlyargs + arguments.args)
        == names
        and not arguments.kwonlyargs
        and arguments.vararg is None
        and arguments.kwarg is None
        and not arguments.defaults
        and not arguments.kw_defaults
        and not function.decorator_list
    )


def _collect_contract_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    functions: dict[str, ast.FunctionDef] = {}
    for statement in tree.body:
        if isinstance(statement, ast.FunctionDef):
            if statement.name in functions:
                raise _code_error(
                    "generated research function names must be unique",
                    "invalid_generated_code_signature",
                    function=statement.name,
                )
            functions[statement.name] = statement
        elif isinstance(statement, (ast.Import, ast.ImportFrom)) or (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            continue
        elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
            if not _immutable_module_constant(statement):
                raise _code_error(
                    "generated research modules cannot own mutable state",
                    "mutable_generated_code_state",
                )
        elif isinstance(statement, ast.AsyncFunctionDef):
            raise _code_error(
                "generated research entry points must be synchronous",
                "invalid_generated_code_signature",
                function=statement.name,
            )
        else:
            raise _code_error(
                "generated research modules contain an unsupported top-level statement",
                "mutable_generated_code_state",
                statement_type=type(statement).__name__,
            )
    return functions


def validate_research_code_contract(artifact: ResearchCodeArtifact) -> None:
    """Validate the fixed, stateless fit/score research-code surface."""
    if type(artifact) is not ResearchCodeArtifact:
        raise _code_error(
            "artifact must be ResearchCodeArtifact",
            "invalid_generated_code_contract",
        )
    try:
        tree = ast.parse(artifact.source_code, mode="exec")
    except (SyntaxError, ValueError, TypeError) as exc:
        raise _code_error(
            "generated research code is not valid Python",
            "invalid_generated_code_syntax",
            parser_error=type(exc).__name__,
        ) from exc
    functions = _collect_contract_functions(tree)
    expected = {
        "fit": ("training_stream",),
        "score": ("visible_window", "immutable_model_state"),
    }
    for name, arguments in expected.items():
        function = functions.get(name)
        if function is None or not _exact_signature(function, arguments):
            raise _code_error(
                f"{name} must use the fixed generated-code signature",
                "invalid_generated_code_signature",
                function=name,
            )
    if any(isinstance(node, (ast.Global, ast.Nonlocal)) for node in ast.walk(tree)):
        raise _code_error(
            "generated research functions cannot mutate outer state",
            "mutable_generated_code_state",
        )
    if artifact.canonical_ast_hash != canonical_research_ast_hash(artifact.source_code):
        raise _code_error(
            "canonical_ast_hash does not match source_code",
            "generated_code_ast_hash_mismatch",
        )


@dataclass(frozen=True, slots=True)
class ResearchCodeArtifact:
    """Content-addressed generated code without trusted evaluation fields."""

    source_code: str
    source_hash: ContentHash
    canonical_ast_hash: ContentHash
    dependency_lock_hash: ContentHash
    dependencies: Sequence[str]
    image_digest: ContentHash
    input_schema_hash: ContentHash
    output_schema_hash: ContentHash

    def __post_init__(self) -> None:
        """Verify source content and freeze the dependency declaration."""
        if type(self.source_code) is not str or not self.source_code.strip():
            raise _code_error(
                "source_code must be non-empty",
                "invalid_research_code_source",
            )
        for value, field in (
            (self.source_hash, "source_hash"),
            (self.canonical_ast_hash, "canonical_ast_hash"),
            (self.dependency_lock_hash, "dependency_lock_hash"),
            (self.image_digest, "image_digest"),
            (self.input_schema_hash, "input_schema_hash"),
            (self.output_schema_hash, "output_schema_hash"),
        ):
            if type(value) is not ContentHash:
                raise _code_error(
                    f"{field} must be ContentHash",
                    "invalid_research_code_artifact",
                    field=field,
                )
        actual_source_hash = ContentHash(
            hashlib.sha256(self.source_code.encode("utf-8")).hexdigest()
        )
        if actual_source_hash != self.source_hash:
            raise _code_error(
                "source_hash does not match source_code",
                "research_code_hash_mismatch",
            )
        object.__setattr__(
            self, "dependencies", _freeze_dependencies(self.dependencies)
        )

    @property
    def artifact_hash(self) -> ContentHash:
        """Return the stable identity of code, schemas, image, and dependencies."""
        return canonical_payload(
            {
                "schema_id": "r5-research-code-artifact",
                "schema_version": 1,
                "source_hash": str(self.source_hash),
                "canonical_ast_hash": str(self.canonical_ast_hash),
                "dependency_lock_hash": str(self.dependency_lock_hash),
                "dependencies": list(self.dependencies),
                "image_digest": str(self.image_digest),
                "input_schema_hash": str(self.input_schema_hash),
                "output_schema_hash": str(self.output_schema_hash),
            }
        ).content_hash


class SandboxExitStatus(StrEnum):
    """Stable untrusted-code execution outcome."""

    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    RESOURCE_EXHAUSTED = "resource_exhausted"


@dataclass(frozen=True, slots=True)
class SandboxResourceLimits:
    """Immutable upper bounds for one isolated execution."""

    cpu_count: int = 2
    memory_bytes: int = 4 * 1024**3
    process_limit: int = 64
    temporary_storage_bytes: int = 1024**3
    wall_time_seconds: int = 600
    output_bytes: int = 10 * 1024**2

    def __post_init__(self) -> None:
        """Reject absent or non-positive resource limits."""
        for field in (
            "cpu_count",
            "memory_bytes",
            "process_limit",
            "temporary_storage_bytes",
            "wall_time_seconds",
            "output_bytes",
        ):
            _positive_int(getattr(self, field), field)


@dataclass(frozen=True, slots=True)
class SandboxExecutionManifest:
    """Attested I/O and outcome of one sandbox execution."""

    code_artifact_hash: ContentHash
    runtime_digest: ContentHash
    resource_limits: SandboxResourceLimits
    input_hash: ContentHash
    output_hash: ContentHash | None
    seed: int
    exit_status: SandboxExitStatus
    exit_code: int | None
    attestation_hash: ContentHash

    def __post_init__(self) -> None:
        """Require typed, internally consistent execution evidence."""
        for value, expected, field in (
            (self.code_artifact_hash, ContentHash, "code_artifact_hash"),
            (self.runtime_digest, ContentHash, "runtime_digest"),
            (self.resource_limits, SandboxResourceLimits, "resource_limits"),
            (self.input_hash, ContentHash, "input_hash"),
            (self.exit_status, SandboxExitStatus, "exit_status"),
            (self.attestation_hash, ContentHash, "attestation_hash"),
        ):
            if type(value) is not expected:
                raise _code_error(
                    f"{field} must be {expected.__name__}",
                    "invalid_sandbox_execution_manifest",
                    field=field,
                )
        if self.output_hash is not None and type(self.output_hash) is not ContentHash:
            raise _code_error(
                "output_hash must be ContentHash when present",
                "invalid_sandbox_execution_manifest",
                field="output_hash",
            )
        if type(self.seed) is not int or self.seed < 0:
            raise _code_error(
                "seed must be a non-negative integer",
                "invalid_sandbox_execution_manifest",
                field="seed",
            )
        if self.exit_code is not None and type(self.exit_code) is not int:
            raise _code_error(
                "exit_code must be int when present",
                "invalid_sandbox_execution_manifest",
                field="exit_code",
            )
        if self.exit_status is SandboxExitStatus.SUCCEEDED and (
            self.output_hash is None or self.exit_code != 0
        ):
            raise _code_error(
                "successful execution requires output_hash and zero exit_code",
                "invalid_sandbox_success_manifest",
            )
        if self.exit_status is not SandboxExitStatus.SUCCEEDED and self.exit_code == 0:
            raise _code_error(
                "non-success execution cannot have a zero exit_code",
                "invalid_sandbox_execution_manifest",
                field="exit_code",
            )
