#!/usr/bin/env python3
"""Policy/grader regression over prefilled attempts; not a model benchmark."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

try:
    from .hook import classify_diff, verification_commands
except ImportError:  # Direct script execution.
    from hook import classify_diff, verification_commands


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = Path(__file__).with_name("evals") / "v1" / "cases.json"
REGISTRY_SCHEMA_VERSION = 1
SUITE_ID = "ditto-coding-agent-governance"

Verdict = Literal["pass", "fail"]
RuntimeKind = Literal["none", "live", "mock"]
WriteOrigin = Literal["agent", "generator", "preexisting"]

_UV_PREFIX = ("uv", "run", "--no-sync")

REQUIRED_ADVERSARIAL_CATEGORIES = frozenset(
    {
        "changed_set_completeness",
        "contract_integrity",
        "instruction_hierarchy",
        "live_evidence",
        "pit_future_sentinel",
        "python_import_boundary",
        "test_claim_integrity",
        "verification_scope",
        "web_import_boundary",
    }
)
SUPPORTED_CATEGORIES = REQUIRED_ADVERSARIAL_CATEGORIES | {
    "baseline",
    "boundary",
}
SUPPORTED_VIOLATIONS = frozenset(
    {
        "changed_set_incomplete",
        "contract_codegen_drift",
        "deterministic_gate_failed",
        "generated_file_manual_edit",
        "instruction_hierarchy_incomplete",
        "live_evidence_missing",
        "pit_future_sentinel_failed",
        "pit_future_sentinel_missing",
        "python_import_boundary",
        "unverified_test_claim",
        "verification_scope_too_small",
        "web_import_boundary",
    }
)
_GENERATED_CONTRACT_PATHS = frozenset(
    {
        "apps/web/src/api/generated/schema.d.ts",
        "contracts/openapi/v1.json",
    }
)
_OPENAPI_SNAPSHOT = "contracts/openapi/v1.json"
_WEB_SCHEMA = "apps/web/src/api/generated/schema.d.ts"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_LIVE_ASSERTIONS = frozenset({"production_web", "real_http", "runtime_live"})


@dataclass(frozen=True)
class ChangeEvidence:
    """One path in the authoritative staged/unstaged/untracked changed set."""

    path: str
    tracked: bool
    write_origin: WriteOrigin = "agent"


@dataclass(frozen=True)
class ToolEvidence:
    """Authenticated outcome from one deterministic command invocation."""

    command: tuple[str, ...]
    exit_code: int
    findings: tuple[str, ...] = ()
    runtime: RuntimeKind = "none"
    assertions: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneratedArtifactEvidence:
    """Provenance and zero-diff facts for one generated contract consumer."""

    path: str
    source_path: str
    source_sha256: str
    embedded_source_sha256: str
    zero_diff: bool


@dataclass(frozen=True)
class AgentAttempt:
    """Facts and claims produced by one coding-agent task attempt."""

    changes: tuple[ChangeEvidence, ...]
    reported_paths: tuple[str, ...]
    read_instructions: tuple[str, ...]
    tool_evidence: tuple[ToolEvidence, ...]
    reported_successful_commands: tuple[tuple[str, ...], ...] = ()
    generated_artifacts: tuple[GeneratedArtifactEvidence, ...] = ()
    claims_live_behavior: bool = False


@dataclass(frozen=True)
class Grade:
    verdict: Verdict
    violations: tuple[str, ...]


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    category: str
    description: str
    attempt: AgentAttempt
    expected_verdict: Verdict
    expected_violations: tuple[str, ...]


@dataclass(frozen=True)
class EvalRegistry:
    schema_version: int
    suite_id: str
    suite_version: str
    cases: tuple[EvalCase, ...]


def _mapping(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{context} must be an object")
    return {str(key): item for key, item in value.items()}


def _exact_keys(value: dict[str, object], expected: set[str], context: str) -> None:
    if set(value) != expected:
        raise ValueError(
            f"{context} keys must be {sorted(expected)}, found {sorted(value)}"
        )


def _string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty string")
    return value


def _boolean(value: object, context: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{context} must be a boolean")
    return value


def _integer(value: object, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{context} must be an integer")
    return value


def _sequence(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be an array")
    return value


def _strings(value: object, context: str) -> tuple[str, ...]:
    values = tuple(
        _string(item, f"{context}[{index}]")
        for index, item in enumerate(_sequence(value, context))
    )
    if len(set(values)) != len(values):
        raise ValueError(f"{context} must not contain duplicates")
    return values


def _relative_path(value: object, context: str) -> str:
    path = _string(value, context)
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or path != pure.as_posix():
        raise ValueError(f"{context} must be a normalized repository-relative path")
    return path


def _command(value: object, context: str) -> tuple[str, ...]:
    command = _strings(value, context)
    if not command:
        raise ValueError(f"{context} must not be empty")
    return command


def _parse_change(value: object, context: str) -> ChangeEvidence:
    mapping = _mapping(value, context)
    _exact_keys(mapping, {"path", "tracked", "write_origin"}, context)
    origin_value = _string(mapping["write_origin"], f"{context}.write_origin")
    match origin_value:
        case "agent":
            origin: WriteOrigin = "agent"
        case "generator":
            origin = "generator"
        case "preexisting":
            origin = "preexisting"
        case _:
            raise ValueError(f"{context}.write_origin is invalid")
    return ChangeEvidence(
        path=_relative_path(mapping["path"], f"{context}.path"),
        tracked=_boolean(mapping["tracked"], f"{context}.tracked"),
        write_origin=origin,
    )


def _parse_tool(value: object, context: str) -> ToolEvidence:
    mapping = _mapping(value, context)
    _exact_keys(
        mapping,
        {"assertions", "command", "exit_code", "findings", "runtime"},
        context,
    )
    findings = _strings(mapping["findings"], f"{context}.findings")
    unknown_findings = set(findings) - SUPPORTED_VIOLATIONS
    if unknown_findings:
        raise ValueError(f"{context}.findings contains unsupported codes")
    runtime_value = _string(mapping["runtime"], f"{context}.runtime")
    match runtime_value:
        case "none":
            runtime: RuntimeKind = "none"
        case "live":
            runtime = "live"
        case "mock":
            runtime = "mock"
        case _:
            raise ValueError(f"{context}.runtime is invalid")
    return ToolEvidence(
        command=_command(mapping["command"], f"{context}.command"),
        exit_code=_integer(mapping["exit_code"], f"{context}.exit_code"),
        findings=findings,
        runtime=runtime,
        assertions=_strings(mapping["assertions"], f"{context}.assertions"),
    )


def _parse_artifact(value: object, context: str) -> GeneratedArtifactEvidence:
    mapping = _mapping(value, context)
    _exact_keys(
        mapping,
        {
            "embedded_source_sha256",
            "path",
            "source_path",
            "source_sha256",
            "zero_diff",
        },
        context,
    )
    source_sha256 = _string(mapping["source_sha256"], f"{context}.source_sha256")
    embedded = _string(
        mapping["embedded_source_sha256"],
        f"{context}.embedded_source_sha256",
    )
    if _SHA256.fullmatch(source_sha256) is None or _SHA256.fullmatch(embedded) is None:
        raise ValueError(f"{context} hashes must be lowercase SHA-256 values")
    return GeneratedArtifactEvidence(
        path=_relative_path(mapping["path"], f"{context}.path"),
        source_path=_relative_path(mapping["source_path"], f"{context}.source_path"),
        source_sha256=source_sha256,
        embedded_source_sha256=embedded,
        zero_diff=_boolean(mapping["zero_diff"], f"{context}.zero_diff"),
    )


def _parse_attempt(value: object, context: str) -> AgentAttempt:
    mapping = _mapping(value, context)
    _exact_keys(
        mapping,
        {
            "changes",
            "claims_live_behavior",
            "generated_artifacts",
            "read_instructions",
            "reported_paths",
            "reported_successful_commands",
            "tool_evidence",
        },
        context,
    )
    changes = tuple(
        _parse_change(item, f"{context}.changes[{index}]")
        for index, item in enumerate(
            _sequence(mapping["changes"], f"{context}.changes")
        )
    )
    if not changes or len({change.path for change in changes}) != len(changes):
        raise ValueError(f"{context}.changes must be non-empty with unique paths")
    tools = tuple(
        _parse_tool(item, f"{context}.tool_evidence[{index}]")
        for index, item in enumerate(
            _sequence(mapping["tool_evidence"], f"{context}.tool_evidence")
        )
    )
    if len({tool.command for tool in tools}) != len(tools):
        raise ValueError(f"{context}.tool_evidence commands must be unique")
    reported_commands = tuple(
        _command(item, f"{context}.reported_successful_commands[{index}]")
        for index, item in enumerate(
            _sequence(
                mapping["reported_successful_commands"],
                f"{context}.reported_successful_commands",
            )
        )
    )
    if len(set(reported_commands)) != len(reported_commands):
        raise ValueError(
            f"{context}.reported_successful_commands must not contain duplicates"
        )
    return AgentAttempt(
        changes=changes,
        reported_paths=tuple(
            _relative_path(path, f"{context}.reported_paths[{index}]")
            for index, path in enumerate(
                _sequence(mapping["reported_paths"], f"{context}.reported_paths")
            )
        ),
        read_instructions=tuple(
            _relative_path(path, f"{context}.read_instructions[{index}]")
            for index, path in enumerate(
                _sequence(mapping["read_instructions"], f"{context}.read_instructions")
            )
        ),
        tool_evidence=tools,
        reported_successful_commands=reported_commands,
        generated_artifacts=tuple(
            _parse_artifact(item, f"{context}.generated_artifacts[{index}]")
            for index, item in enumerate(
                _sequence(
                    mapping["generated_artifacts"],
                    f"{context}.generated_artifacts",
                )
            )
        ),
        claims_live_behavior=_boolean(
            mapping["claims_live_behavior"], f"{context}.claims_live_behavior"
        ),
    )


def _parse_case(value: object, context: str) -> EvalCase:
    mapping = _mapping(value, context)
    _exact_keys(
        mapping,
        {"attempt", "category", "description", "expected", "id"},
        context,
    )
    category = _string(mapping["category"], f"{context}.category")
    if category not in SUPPORTED_CATEGORIES:
        raise ValueError(f"{context}.category is unsupported")
    expected = _mapping(mapping["expected"], f"{context}.expected")
    _exact_keys(expected, {"verdict", "violations"}, f"{context}.expected")
    verdict_value = _string(expected["verdict"], f"{context}.expected.verdict")
    match verdict_value:
        case "pass":
            verdict: Verdict = "pass"
        case "fail":
            verdict = "fail"
        case _:
            raise ValueError(f"{context}.expected.verdict is invalid")
    violations = _strings(expected["violations"], f"{context}.expected.violations")
    if tuple(sorted(violations)) != violations:
        raise ValueError(f"{context}.expected.violations must be sorted")
    if set(violations) - SUPPORTED_VIOLATIONS:
        raise ValueError(f"{context}.expected.violations contains unsupported codes")
    if (verdict == "pass") != (not violations):
        raise ValueError(f"{context}.expected verdict and violations disagree")
    return EvalCase(
        case_id=_string(mapping["id"], f"{context}.id"),
        category=category,
        description=_string(mapping["description"], f"{context}.description"),
        attempt=_parse_attempt(mapping["attempt"], f"{context}.attempt"),
        expected_verdict=verdict,
        expected_violations=violations,
    )


def load_registry(path: Path = DEFAULT_REGISTRY) -> EvalRegistry:
    """Load and strictly validate the versioned case registry."""
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid Agent Eval registry {path}: {error}") from error
    mapping = _mapping(raw, "registry")
    _exact_keys(
        mapping,
        {"cases", "schema_version", "suite_id", "suite_version"},
        "registry",
    )
    schema_version = _integer(mapping["schema_version"], "registry.schema_version")
    if schema_version != REGISTRY_SCHEMA_VERSION:
        raise ValueError(f"registry.schema_version must be {REGISTRY_SCHEMA_VERSION}")
    suite_id = _string(mapping["suite_id"], "registry.suite_id")
    if suite_id != SUITE_ID:
        raise ValueError(f"registry.suite_id must be {SUITE_ID}")
    suite_version = _string(mapping["suite_version"], "registry.suite_version")
    if re.fullmatch(r"v[1-9][0-9]*", suite_version) is None:
        raise ValueError("registry.suite_version must be a positive vN identifier")
    cases = tuple(
        _parse_case(item, f"registry.cases[{index}]")
        for index, item in enumerate(_sequence(mapping["cases"], "registry.cases"))
    )
    if not cases or len({case.case_id for case in cases}) != len(cases):
        raise ValueError("registry case IDs must be non-empty and unique")
    missing_categories = REQUIRED_ADVERSARIAL_CATEGORIES - {
        case.category for case in cases
    }
    if missing_categories:
        raise ValueError(
            f"registry is missing adversarial categories: {sorted(missing_categories)}"
        )
    return EvalRegistry(
        schema_version=schema_version,
        suite_id=suite_id,
        suite_version=suite_version,
        cases=cases,
    )


def _instruction_chains(
    root: Path, paths: tuple[str, ...]
) -> tuple[tuple[str, ...], ...]:
    chains: list[tuple[str, ...]] = []
    for relative in paths:
        parts = PurePosixPath(relative).parts[:-1]
        candidates = ["AGENTS.md"]
        for index in range(1, len(parts) + 1):
            candidates.append(PurePosixPath(*parts[:index], "AGENTS.md").as_posix())
        chain = tuple(path for path in candidates if (root / path).is_file())
        chains.append(chain)
    return tuple(chains)


def _has_instruction_hierarchy(
    root: Path, paths: tuple[str, ...], read_instructions: tuple[str, ...]
) -> bool:
    if len(set(read_instructions)) != len(read_instructions):
        return False
    positions = {path: index for index, path in enumerate(read_instructions)}
    for chain in _instruction_chains(root, paths):
        try:
            indices = [positions[path] for path in chain]
        except KeyError:
            return False
        if indices != sorted(indices):
            return False
    return True


def _gate_id(command: tuple[str, ...]) -> str:
    arguments = command
    if arguments[:1] == ("task",):
        arguments = arguments[1:]
    elif arguments[:3] == _UV_PREFIX:
        arguments = arguments[3:]
    if not arguments:
        return "unknown"
    if arguments[0] in {
        "artifact-gate",
        "check",
        "check-backend",
        "check-contract",
        "check-web",
        "ci",
        "harness-check",
        "pit",
        "security-supply-chain",
        "test-system",
    }:
        return arguments[0]
    if arguments[0] == "pytest" and "-m" in arguments:
        marker_index = arguments.index("-m")
        if marker_index + 1 < len(arguments) and arguments[marker_index + 1] == "pit":
            return "pit"
    return " ".join(command)


def _gate_covers(actual: str, required: str) -> bool:
    if actual in {required, "ci"}:
        return True
    return actual == "check" and required in {
        "check-backend",
        "check-contract",
        "check-web",
        "harness-check",
    }


def _required_gates(root: Path, paths: tuple[str, ...]) -> frozenset[str]:
    level = classify_diff(paths)
    commands = verification_commands(level, paths, root=root)
    return frozenset(_gate_id(tuple(command)) for command in commands)


def _contract_violations(attempt: AgentAttempt) -> set[str]:
    violations: set[str] = set()
    changed = {change.path: change for change in attempt.changes}
    artifacts = {artifact.path: artifact for artifact in attempt.generated_artifacts}
    for path in _GENERATED_CONTRACT_PATHS.intersection(changed):
        if changed[path].write_origin != "generator":
            violations.add("generated_file_manual_edit")

    schema = artifacts.get(_WEB_SCHEMA)
    if _OPENAPI_SNAPSHOT in changed and schema is None:
        violations.add("contract_codegen_drift")
    for artifact in attempt.generated_artifacts:
        if (
            artifact.source_sha256 != artifact.embedded_source_sha256
            or not artifact.zero_diff
        ):
            violations.add("contract_codegen_drift")
    return violations


def _tool_violations(evidence_items: tuple[ToolEvidence, ...]) -> set[str]:
    violations: set[str] = set()
    for evidence in evidence_items:
        if evidence.findings:
            violations.update(evidence.findings)
        elif evidence.exit_code != 0:
            violations.add("deterministic_gate_failed")
    return violations


def _has_required_scope(
    root: Path,
    paths: tuple[str, ...],
    evidence_items: tuple[ToolEvidence, ...],
) -> bool:
    required_gates = _required_gates(root, paths)
    attempted_gates = {_gate_id(evidence.command) for evidence in evidence_items}
    return all(
        any(_gate_covers(actual, required) for actual in attempted_gates)
        for required in required_gates
    )


def _pit_sentinel_violation(
    root: Path,
    paths: tuple[str, ...],
    evidence_items: tuple[ToolEvidence, ...],
    violations: set[str],
) -> str | None:
    if "pit" not in _required_gates(root, paths):
        return None
    pit_evidence = tuple(
        evidence
        for evidence in evidence_items
        if _gate_covers(_gate_id(evidence.command), "pit")
    )
    if any(
        evidence.exit_code == 0 and "pit_future_sentinel" in evidence.assertions
        for evidence in pit_evidence
    ):
        return None
    if "pit_future_sentinel_failed" in violations:
        return None
    return "pit_future_sentinel_missing"


def _has_live_proof(evidence_items: tuple[ToolEvidence, ...]) -> bool:
    return any(
        evidence.exit_code == 0
        and evidence.runtime == "live"
        and _gate_covers(_gate_id(evidence.command), "test-system")
        and _LIVE_ASSERTIONS.issubset(evidence.assertions)
        for evidence in evidence_items
    )


def grade_attempt(attempt: AgentAttempt, root: Path = ROOT) -> Grade:
    """Grade one task attempt entirely from deterministic facts and receipts."""
    violations: set[str] = set()
    actual_paths = tuple(sorted(change.path for change in attempt.changes))
    if set(actual_paths) != set(attempt.reported_paths):
        violations.add("changed_set_incomplete")
    if not _has_instruction_hierarchy(root, actual_paths, attempt.read_instructions):
        violations.add("instruction_hierarchy_incomplete")

    violations.update(_tool_violations(attempt.tool_evidence))
    violations.update(_contract_violations(attempt))

    successful_commands = {
        evidence.command
        for evidence in attempt.tool_evidence
        if evidence.exit_code == 0
    }
    if any(
        command not in successful_commands
        for command in attempt.reported_successful_commands
    ):
        violations.add("unverified_test_claim")

    if not _has_required_scope(root, actual_paths, attempt.tool_evidence):
        violations.add("verification_scope_too_small")

    pit_violation = _pit_sentinel_violation(
        root, actual_paths, attempt.tool_evidence, violations
    )
    if pit_violation is not None:
        violations.add(pit_violation)

    if attempt.claims_live_behavior and not _has_live_proof(attempt.tool_evidence):
        violations.add("live_evidence_missing")

    ordered = tuple(sorted(violations))
    return Grade(verdict="fail" if ordered else "pass", violations=ordered)


def evaluate_registry(registry: EvalRegistry, root: Path = ROOT) -> tuple[str, ...]:
    """Return deterministic expectation mismatches for the full case registry."""
    mismatches: list[str] = []
    for case in registry.cases:
        actual = grade_attempt(case.attempt, root)
        if (
            actual.verdict != case.expected_verdict
            or actual.violations != case.expected_violations
        ):
            mismatch = (
                f"{case.case_id}: expected "
                + f"{case.expected_verdict}/{list(case.expected_violations)}, "
                + f"got {actual.verdict}/{list(actual.violations)}"
            )
            mismatches.append(mismatch)
    return tuple(mismatches)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--root", type=Path, default=ROOT)
    arguments = parser.parse_args(argv)
    try:
        registry = load_registry(arguments.registry)
        mismatches = evaluate_registry(registry, root=arguments.root.resolve())
    except ValueError as error:
        print(f"Agent Eval registry failed: {error}", file=sys.stderr)
        return 1
    if mismatches:
        print("Agent Eval failed:", file=sys.stderr)
        for mismatch in mismatches:
            print(f"- {mismatch}", file=sys.stderr)
        return 1
    message = (
        f"Agent Eval passed ({len(registry.cases)} cases, "
        f"suite={registry.suite_id}@{registry.suite_version})."
    )
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
