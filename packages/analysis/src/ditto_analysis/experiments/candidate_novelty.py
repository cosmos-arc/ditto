"""Deterministic candidate novelty from canonical code, outputs, and lineage."""

from __future__ import annotations

import ast
import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TypedDict, cast

from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments.models import ContentHash
from ditto_analysis.experiments.persistence import canonical_payload

__all__ = [
    "CandidateNoveltyEvidence",
    "CandidateNoveltyPolicy",
    "CandidateOutputProfile",
    "canonical_candidate_ast_hash",
    "evaluate_candidate_novelty",
]

_NOVELTY_FACTORY_TOKEN = object()
_MINIMUM_NOVELTY_OBSERVATIONS = 3


def _error(
    message: str,
    reason_code: str,
    **details: object,
) -> ExperimentSpecError:
    return ExperimentSpecError(
        message,
        details={"reason_code": reason_code, **details},
    )


def _content_hash(value: object, field_name: str) -> ContentHash:
    if type(value) is not ContentHash:
        raise _error(
            f"{field_name} must be ContentHash",
            "invalid_candidate_novelty_profile",
            field=field_name,
        )
    return value


class _AlphaNormalizer(ast.NodeTransformer):
    """Normalize function-local bindings while preserving external names."""

    def __init__(self) -> None:
        self._scopes: list[Mapping[str, str]] = []

    @staticmethod
    def _bound_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
        ordered: dict[str, None] = {}
        arguments = (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        )
        if node.args.vararg is not None:
            arguments = (*arguments, node.args.vararg)
        if node.args.kwarg is not None:
            arguments = (*arguments, node.args.kwarg)
        for argument in arguments:
            ordered.setdefault(argument.arg, None)
        for statement in node.body:
            for child in ast.walk(statement):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    ordered.setdefault(child.id, None)
        return tuple(ordered)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        """Normalize one synchronous function scope."""
        names = self._bound_names(node)
        self._scopes.append(
            {name: f"local_{index}" for index, name in enumerate(names, start=1)}
        )
        transformed = self.generic_visit(node)
        self._scopes.pop()
        return transformed

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        """Normalize one asynchronous function scope."""
        names = self._bound_names(node)
        self._scopes.append(
            {name: f"local_{index}" for index, name in enumerate(names, start=1)}
        )
        transformed = self.generic_visit(node)
        self._scopes.pop()
        return transformed

    def visit_arg(self, node: ast.arg) -> ast.AST:
        """Rename a bound argument inside the active scope."""
        if self._scopes and node.arg in self._scopes[-1]:
            node.arg = self._scopes[-1][node.arg]
        return self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> ast.AST:
        """Rename local reads and writes consistently."""
        if self._scopes and node.id in self._scopes[-1]:
            node.id = self._scopes[-1][node.id]
        return self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> ast.AST | None:
        """Discard docstrings and other inert standalone string literals."""
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return None
        return self.generic_visit(node)


def canonical_candidate_ast_hash(source_code: str) -> ContentHash:
    """Hash candidate semantics without formatting or local variable spelling."""
    if type(source_code) is not str or not source_code.strip():
        raise _error(
            "candidate source must be non-empty",
            "invalid_candidate_novelty_source",
        )
    try:
        tree = ast.parse(source_code, mode="exec")
    except (SyntaxError, ValueError, TypeError) as exc:
        raise _error(
            "candidate source is not valid Python",
            "invalid_candidate_novelty_source",
            parser_error=type(exc).__name__,
        ) from exc
    normalized = _AlphaNormalizer().visit(tree)
    canonical = ast.dump(normalized, annotate_fields=True, include_attributes=False)
    return ContentHash(hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _freeze_outputs(value: object) -> tuple[float, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _error(
            "candidate outputs must be an ordered sequence",
            "invalid_candidate_output_profile",
        )
    raw = tuple(cast("Sequence[object]", value))
    if len(raw) < _MINIMUM_NOVELTY_OBSERVATIONS or any(
        type(item) not in {int, float} or not math.isfinite(cast("float", item))
        for item in raw
    ):
        raise _error(
            "candidate outputs require at least three finite observations",
            "invalid_candidate_output_profile",
        )
    outputs = tuple(float(cast("int | float", item)) for item in raw)
    if max(outputs) == min(outputs):
        raise _error(
            "candidate outputs cannot be constant",
            "invalid_candidate_output_profile",
        )
    return outputs


@dataclass(frozen=True, slots=True)
class CandidateOutputProfile:
    """Trusted-host candidate output aligned to one protocol and observation grid."""

    candidate_hash: ContentHash
    canonical_ast_hash: ContentHash
    validation_protocol_hash: ContentHash
    lineage_root: ContentHash
    observation_grid_hash: ContentHash
    outputs: Sequence[float]

    def __post_init__(self) -> None:
        """Freeze the exact content and correlation context."""
        for field_name in (
            "candidate_hash",
            "canonical_ast_hash",
            "validation_protocol_hash",
            "lineage_root",
            "observation_grid_hash",
        ):
            _content_hash(getattr(self, field_name), field_name)
        object.__setattr__(self, "outputs", _freeze_outputs(self.outputs))

    @property
    def profile_hash(self) -> ContentHash:
        """Bind the candidate, temporal grid, protocol, and exact output values."""
        return canonical_payload(
            {
                "schema_id": "r5-candidate-output-profile",
                "schema_version": 1,
                "candidate_hash": str(self.candidate_hash),
                "canonical_ast_hash": str(self.canonical_ast_hash),
                "validation_protocol_hash": str(self.validation_protocol_hash),
                "lineage_root": str(self.lineage_root),
                "observation_grid_hash": str(self.observation_grid_hash),
                "outputs": list(self.outputs),
            }
        ).content_hash


@dataclass(frozen=True, slots=True)
class CandidateNoveltyPolicy:
    """Predeclared threshold for semantic-output candidate deduplication."""

    max_abs_output_correlation: float = 0.995
    minimum_observations: int = 3

    def __post_init__(self) -> None:
        """Require a finite bounded threshold and usable observation count."""
        if (
            type(self.max_abs_output_correlation) is not float
            or not math.isfinite(self.max_abs_output_correlation)
            or not 0.0 < self.max_abs_output_correlation <= 1.0
        ):
            raise _error(
                "output correlation threshold must be in (0, 1]",
                "invalid_candidate_novelty_policy",
            )
        if (
            type(self.minimum_observations) is not int
            or self.minimum_observations < _MINIMUM_NOVELTY_OBSERVATIONS
        ):
            raise _error(
                "minimum observations must be an integer of at least three",
                "invalid_candidate_novelty_policy",
            )

    @property
    def policy_hash(self) -> ContentHash:
        """Return the immutable policy identity included in novelty evidence."""
        return canonical_payload(
            {
                "schema_id": "r5-candidate-novelty-policy",
                "schema_version": 1,
                "max_abs_output_correlation": self.max_abs_output_correlation,
                "minimum_observations": self.minimum_observations,
            }
        ).content_hash


def _hashes(values: Sequence[ContentHash]) -> tuple[ContentHash, ...]:
    return tuple(sorted(values, key=str))


class _NoveltyEvidenceValues(TypedDict):
    candidate_hash: ContentHash
    candidate_profile_hash: ContentHash
    canonical_ast_hash: ContentHash
    validation_protocol_hash: ContentHash
    lineage_root: ContentHash
    observation_grid_hash: ContentHash
    policy_hash: ContentHash
    compared_candidate_hashes: tuple[ContentHash, ...]
    duplicate_ast_candidate_hashes: tuple[ContentHash, ...]
    correlated_candidate_hashes: tuple[ContentHash, ...]
    max_abs_output_correlation: float | None
    accepted: bool
    reason: str


@dataclass(frozen=True, slots=True)
class CandidateNoveltyEvidence:
    """Content-addressed trusted decision without exposing candidate outputs."""

    candidate_hash: ContentHash
    candidate_profile_hash: ContentHash
    canonical_ast_hash: ContentHash
    validation_protocol_hash: ContentHash
    lineage_root: ContentHash
    observation_grid_hash: ContentHash
    policy_hash: ContentHash
    compared_candidate_hashes: Sequence[ContentHash]
    duplicate_ast_candidate_hashes: Sequence[ContentHash]
    correlated_candidate_hashes: Sequence[ContentHash]
    max_abs_output_correlation: float | None
    accepted: bool
    reason: str
    evidence_hash: ContentHash
    _factory_token: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        """Allow decisions only from the trusted deterministic evaluator."""
        if self._factory_token is not _NOVELTY_FACTORY_TOKEN:
            raise _error(
                "candidate novelty evidence must be factory-produced",
                "untrusted_candidate_novelty_evidence",
            )
        for field_name in (
            "candidate_hash",
            "candidate_profile_hash",
            "canonical_ast_hash",
            "validation_protocol_hash",
            "lineage_root",
            "observation_grid_hash",
            "policy_hash",
            "evidence_hash",
        ):
            _content_hash(getattr(self, field_name), field_name)
        for field_name in (
            "compared_candidate_hashes",
            "duplicate_ast_candidate_hashes",
            "correlated_candidate_hashes",
        ):
            values = tuple(getattr(self, field_name))
            if any(type(item) is not ContentHash for item in values):
                raise _error(
                    "novelty evidence contains invalid candidate hashes",
                    "invalid_candidate_novelty_evidence",
                    field=field_name,
                )
            object.__setattr__(self, field_name, _hashes(values))
        if self.max_abs_output_correlation is not None and (
            type(self.max_abs_output_correlation) is not float
            or not math.isfinite(self.max_abs_output_correlation)
            or not 0.0 <= self.max_abs_output_correlation <= 1.0
        ):
            raise _error(
                "novelty correlation evidence is invalid",
                "invalid_candidate_novelty_evidence",
            )
        if type(self.accepted) is not bool or type(self.reason) is not str:
            raise _error(
                "candidate novelty decision is invalid",
                "invalid_candidate_novelty_evidence",
            )

    def canonical_body(self) -> dict[str, object]:
        """Return the safe, versioned body bound by ``evidence_hash``."""
        return {
            "schema_id": "r5-candidate-novelty-evidence",
            "schema_version": 1,
            "candidate_hash": str(self.candidate_hash),
            "candidate_profile_hash": str(self.candidate_profile_hash),
            "canonical_ast_hash": str(self.canonical_ast_hash),
            "validation_protocol_hash": str(self.validation_protocol_hash),
            "lineage_root": str(self.lineage_root),
            "observation_grid_hash": str(self.observation_grid_hash),
            "policy_hash": str(self.policy_hash),
            "compared_candidate_hashes": [
                str(item) for item in self.compared_candidate_hashes
            ],
            "duplicate_ast_candidate_hashes": [
                str(item) for item in self.duplicate_ast_candidate_hashes
            ],
            "correlated_candidate_hashes": [
                str(item) for item in self.correlated_candidate_hashes
            ],
            "max_abs_output_correlation": self.max_abs_output_correlation,
            "accepted": self.accepted,
            "reason": self.reason,
        }

    def verify_integrity(self) -> bool:
        """Verify all decision fields against the factory content hash."""
        return canonical_payload(self.canonical_body()).content_hash == (
            self.evidence_hash
        )


def _correlation(left: Sequence[float], right: Sequence[float]) -> float:
    count = len(left)
    left_mean = math.fsum(left) / count
    right_mean = math.fsum(right) / count
    left_deviations = tuple(item - left_mean for item in left)
    right_deviations = tuple(item - right_mean for item in right)
    covariance = math.fsum(
        left_item * right_item
        for left_item, right_item in zip(left_deviations, right_deviations, strict=True)
    )
    left_scale = math.sqrt(math.fsum(item * item for item in left_deviations))
    right_scale = math.sqrt(math.fsum(item * item for item in right_deviations))
    if left_scale == 0.0 or right_scale == 0.0:
        raise _error(
            "candidate correlation requires non-constant outputs",
            "invalid_candidate_output_profile",
        )
    return max(-1.0, min(1.0, covariance / (left_scale * right_scale)))


def _freeze_reference_profiles(
    value: object,
) -> tuple[CandidateOutputProfile, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise _error(
            "references must be an ordered profile sequence",
            "invalid_candidate_novelty_references",
        )
    raw = tuple(cast("Sequence[object]", value))
    if any(type(item) is not CandidateOutputProfile for item in raw):
        raise _error(
            "references must contain CandidateOutputProfile values",
            "invalid_candidate_novelty_references",
        )
    typed = cast("tuple[CandidateOutputProfile, ...]", raw)
    if len({item.candidate_hash for item in typed}) != len(typed):
        raise _error(
            "candidate novelty references must be unique",
            "invalid_candidate_novelty_references",
        )
    return typed


def _novelty_correlations(
    proposed: CandidateOutputProfile,
    references: tuple[CandidateOutputProfile, ...],
    policy: CandidateNoveltyPolicy,
) -> tuple[tuple[CandidateOutputProfile, ...], tuple[tuple[ContentHash, float], ...]]:
    if len(proposed.outputs) < policy.minimum_observations:
        raise _error(
            "proposed output profile is shorter than the novelty policy",
            "candidate_novelty_observations_insufficient",
        )
    if any(item.lineage_root != proposed.lineage_root for item in references):
        raise _error(
            "candidate novelty cannot cross lineage roots",
            "novelty_lineage_mismatch",
        )
    comparable = tuple(
        item
        for item in references
        if item.validation_protocol_hash == proposed.validation_protocol_hash
    )
    correlations: list[tuple[ContentHash, float]] = []
    for item in comparable:
        if item.observation_grid_hash != proposed.observation_grid_hash or len(
            item.outputs
        ) != len(proposed.outputs):
            raise _error(
                "same-protocol novelty outputs must share one observation grid",
                "novelty_observation_grid_mismatch",
            )
        if len(item.outputs) < policy.minimum_observations:
            raise _error(
                "reference output profile is shorter than the novelty policy",
                "candidate_novelty_observations_insufficient",
            )
        correlations.append(
            (item.candidate_hash, abs(_correlation(proposed.outputs, item.outputs)))
        )
    return comparable, tuple(correlations)


def evaluate_candidate_novelty(
    proposed: CandidateOutputProfile,
    *,
    references: Sequence[CandidateOutputProfile],
    policy: CandidateNoveltyPolicy,
) -> CandidateNoveltyEvidence:
    """Evaluate structural and output novelty within one immutable lineage."""
    if type(proposed) is not CandidateOutputProfile:
        raise _error(
            "proposed profile must be CandidateOutputProfile",
            "invalid_candidate_novelty_profile",
        )
    if type(policy) is not CandidateNoveltyPolicy:
        raise _error(
            "policy must be CandidateNoveltyPolicy",
            "invalid_candidate_novelty_policy",
        )
    typed = _freeze_reference_profiles(references)

    duplicate_ast = _hashes(
        tuple(
            item.candidate_hash
            for item in typed
            if item.canonical_ast_hash == proposed.canonical_ast_hash
        )
    )
    comparable, correlations = _novelty_correlations(proposed, typed, policy)
    correlated = _hashes(
        tuple(
            candidate_hash
            for candidate_hash, value in correlations
            if value >= policy.max_abs_output_correlation
        )
    )
    maximum = max((value for _, value in correlations), default=None)
    if duplicate_ast:
        reason = "duplicate_canonical_ast"
    elif correlated:
        reason = "output_correlation_exceeds_limit"
    else:
        reason = "candidate_novel"
    accepted = reason == "candidate_novel"
    values: _NoveltyEvidenceValues = {
        "candidate_hash": proposed.candidate_hash,
        "candidate_profile_hash": proposed.profile_hash,
        "canonical_ast_hash": proposed.canonical_ast_hash,
        "validation_protocol_hash": proposed.validation_protocol_hash,
        "lineage_root": proposed.lineage_root,
        "observation_grid_hash": proposed.observation_grid_hash,
        "policy_hash": policy.policy_hash,
        "compared_candidate_hashes": _hashes(
            tuple(item.candidate_hash for item in comparable)
        ),
        "duplicate_ast_candidate_hashes": duplicate_ast,
        "correlated_candidate_hashes": correlated,
        "max_abs_output_correlation": maximum,
        "accepted": accepted,
        "reason": reason,
    }
    provisional = CandidateNoveltyEvidence(
        **values,
        evidence_hash=ContentHash("0" * 64),
        _factory_token=_NOVELTY_FACTORY_TOKEN,
    )
    return CandidateNoveltyEvidence(
        **values,
        evidence_hash=canonical_payload(provisional.canonical_body()).content_hash,
        _factory_token=_NOVELTY_FACTORY_TOKEN,
    )
