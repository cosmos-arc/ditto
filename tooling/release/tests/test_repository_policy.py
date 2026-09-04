"""Executable repository delivery and supply-chain policy tests."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

from tooling.quality.large_files import validate_large_files

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
LOCAL_ACTIONS = ROOT / ".github" / "actions"
PINNED_ACTION = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
SEMANTIC_CI_JOBS = {
    "repository-policy",
    "backend-quality",
    "backend-types",
    "backend-tests",
    "architecture-harness",
    "web-quality",
    "api-contract",
    "system-e2e",
    "release-cohort",
    "container-smoke",
    "platform-smoke",
    "security-supply-chain",
}


def _workflow(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((WORKFLOWS / name).read_text())
    assert isinstance(loaded, dict)
    if True in loaded and "on" not in loaded:
        loaded["on"] = loaded.pop(True)
    return loaded


def test_ci_runs_parallel_semantic_jobs_and_has_fail_closed_gate() -> None:
    workflow = _workflow("ci.yml")
    triggers = workflow["on"]
    assert set(triggers) >= {"pull_request", "push", "merge_group"}
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["pull_request"]["branches"] == ["main"]
    assert all("paths" not in value for value in triggers.values() if value)

    jobs = workflow["jobs"]
    assert set(jobs) == SEMANTIC_CI_JOBS | {"ci-gate"}
    assert all("needs" not in jobs[name] for name in SEMANTIC_CI_JOBS)
    assert set(jobs["ci-gate"]["needs"]) == SEMANTIC_CI_JOBS
    gate_script = jobs["ci-gate"]["steps"][0]["run"]
    assert "success" in gate_script
    assert "skipped" not in gate_script


def test_backend_coverage_fetches_history_and_selects_every_event_base() -> None:
    """Changed coverage must compare against an exact base on every CI event."""
    workflow = _workflow("ci.yml")
    backend = workflow["jobs"]["backend-tests"]
    checkout = backend["steps"][0]
    assert checkout["with"]["fetch-depth"] == 0

    coverage_step = next(
        step
        for step in backend["steps"]
        if step.get("run") == "pixi run -e dev backend-coverage"
    )
    base_ref = coverage_step["env"]["COVERAGE_BASE_REF"]
    assert "github.event.pull_request.base.sha" in base_ref
    assert "github.event.merge_group.base_sha" in base_ref
    assert "github.event.before" in base_ref


def test_ci_has_explicit_pit_and_supported_platform_gates() -> None:
    workflow = _workflow("ci.yml")
    jobs = workflow["jobs"]
    backend_steps = json.dumps(jobs["backend-tests"])
    assert "pixi run -e dev pit" in backend_steps

    platform = jobs["platform-smoke"]
    matrix = platform["strategy"]["matrix"]["include"]
    by_name = {entry["name"]: entry for entry in matrix}
    assert by_name["macos-arm64"]["os"] == "macos-14"
    assert by_name["windows-x64"]["os"] == "windows-2025"
    platform_steps = json.dumps(platform)
    assert "pixi run -e dev bootstrap" in platform_steps
    assert "pixi run -e dev check-backend" in platform_steps
    assert "pixi run -e dev check-web" in platform_steps
    assert "pixi run -e dev type-all" in platform_steps
    assert "pixi run -e dev web-type" in platform_steps
    assert "platform-smoke-windows" in platform_steps


def test_every_remote_action_is_pinned_to_a_full_commit_sha() -> None:
    violations: list[str] = []
    action_files = sorted(WORKFLOWS.glob("*.yml")) + sorted(
        LOCAL_ACTIONS.glob("*/action.yml")
    )
    for workflow_path in action_files:
        for line_number, line in enumerate(workflow_path.read_text().splitlines(), 1):
            stripped = line.strip()
            if not stripped.startswith("uses:") and not stripped.startswith("- uses:"):
                continue
            reference = stripped.split("uses:", maxsplit=1)[1].strip().split()[0]
            if not reference.startswith("./") and not PINNED_ACTION.fullmatch(
                reference
            ):
                violations.append(f"{workflow_path.name}:{line_number}:{reference}")
    assert violations == []


def test_bun_setup_reads_the_root_package_manager_contract() -> None:
    action = LOCAL_ACTIONS / "setup-bun" / "action.yml"
    assert action.is_file()
    content = action.read_text(encoding="utf-8")
    assert "package.json" in content
    assert "packageManager" in content
    assert "oven-sh/setup-bun@" in content

    for workflow_path in sorted(WORKFLOWS.glob("*.yml")):
        content = workflow_path.read_text(encoding="utf-8")
        assert "BUN_VERSION:" not in content
        assert "bun-version:" not in content
        assert "oven-sh/setup-bun@" not in content
        if "bun install" in content or "bun run" in content:
            assert "uses: ./.github/actions/setup-bun" in content


def test_workflows_have_read_only_defaults_and_no_top_level_path_filters() -> None:
    for workflow_path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = _workflow(workflow_path.name)
        assert workflow.get("permissions") == {"contents": "read"}
        for trigger in workflow.get("on", {}).values():
            if isinstance(trigger, dict):
                assert "paths" not in trigger
                assert "paths-ignore" not in trigger


def test_security_workflow_covers_both_stacks_and_required_scanners() -> None:
    workflow = _workflow("security.yml")
    matrix = workflow["jobs"]["codeql"]["strategy"]["matrix"]["language"]
    assert set(matrix) == {"python", "javascript-typescript"}
    content = (WORKFLOWS / "security.yml").read_text().lower()
    for required in ("gitleaks", "osv", "trivy", "spdx", "security-gate"):
        assert required in content
    assert "scan source --recursive" in content
    assert "continue-on-error" not in content
    assert "command -v" not in content
    assert "|| true" not in content
    assert "/var/run/docker.sock" not in content
    scanner_references = re.findall(
        r"(?:docker\.io|ghcr\.io)/[^\s]+@sha256:[0-9a-f]{64}", content
    )
    assert len(scanner_references) >= 4
    assert all(
        ":" in reference.rsplit("/", maxsplit=1)[1] for reference in scanner_references
    )


def test_gitleaks_false_positives_are_individually_fingerprinted() -> None:
    ignore_path = ROOT / ".gitleaksignore"
    assert ignore_path.is_file()
    fingerprints = [
        line.strip()
        for line in ignore_path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(fingerprints) == 106
    assert len(set(fingerprints)) == len(fingerprints)
    assert all(
        re.fullmatch(r"(?:[0-9a-f]{40}:)?.+:[a-z0-9-]+:[1-9][0-9]*", fingerprint)
        for fingerprint in fingerprints
    )

    config = (ROOT / ".gitleaks.toml").read_text()
    assert "commits =" not in config
    assert "paths =" not in config


def test_ci_gate_calls_and_requires_the_complete_security_workflow() -> None:
    ci_workflow = _workflow("ci.yml")
    security_job = ci_workflow["jobs"]["security-supply-chain"]
    assert security_job["uses"] == "./.github/workflows/security.yml"
    assert security_job["permissions"] == {
        "actions": "read",
        "contents": "read",
        "security-events": "write",
    }
    assert "security-supply-chain" in ci_workflow["jobs"]["ci-gate"]["needs"]

    security_workflow = _workflow("security.yml")
    assert "workflow_call" in security_workflow["on"]


def test_gitleaks_uses_a_known_good_scanner_and_detection_sentinel() -> None:
    content = (WORKFLOWS / "security.yml").read_text()
    assert (
        "gitleaks:v8.18.4@sha256:"
        "75bdb2b2f4db213cde0b8295f13a88d6b333091bbfbf3012a4e083d00d31caba"
    ) in content
    assert "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789" in content
    assert 'test "$sentinel_status" -eq 23' in content


def test_mutation_gate_is_weekly_evidence_not_a_pr_required_dependency() -> None:
    workflow = _workflow("security.yml")
    mutation = workflow["jobs"]["mutation-critical"]
    assert "schedule" in mutation["if"]
    content = json.dumps(mutation)
    assert "pixi run -e dev mutation-critical" in content
    assert "build/mutation/mutmut-cicd-stats.json" in content
    assert "mutation-critical" not in workflow["jobs"]["security-gate"]["needs"]


def test_release_workflow_attests_the_complete_cohort() -> None:
    workflow = _workflow("release.yml")
    job = workflow["jobs"]["release-cohort"]
    assert job["permissions"] == {
        "attestations": "write",
        "contents": "write",
        "id-token": "write",
    }
    content = (WORKFLOWS / "release.yml").read_text()
    for required in (
        "actions/attest-build-provenance@",
        "--api-contract-sha256",
        "dist/ditto-image.tar",
        "dist/ditto-backend.spdx.json",
        "dist/ditto-web.tar",
        "dist/ditto-web.spdx.json",
        "--backend-artifact dist/ditto-image.tar",
        "--web-artifact dist/ditto-web.tar",
        "dist/release-cohort.json",
        "dist/SHA256SUMS",
        "gh release create",
        "github.event_name == 'push'",
    ):
        assert required in content


def test_release_injects_exact_research_code_and_environment_lock() -> None:
    """The backend image must bind research evidence to the cohort commit and lock."""
    dockerfile = (ROOT / "deploy" / "docker" / "Dockerfile").read_text()
    assert "DITTO_RESEARCH_CODE_VERSION=${DITTO_GIT_SHA}" in dockerfile
    assert "ARG DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH" in dockerfile
    assert (
        "DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH=${DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH}"
        in dockerfile
    )

    workflow = _workflow("release.yml")
    steps = workflow["jobs"]["release-cohort"]["steps"]
    identity_script = next(
        step["run"] for step in steps if step.get("id") == "identity"
    )
    assert "sha256sum pixi.lock" in identity_script
    assert "environment_lock_sha256=" in identity_script

    image_build = next(
        step for step in steps if step.get("name") == "Build OCI release artifact"
    )
    build_args = image_build["with"]["build-args"]
    assert "DITTO_GIT_SHA=${{ github.sha }}" in build_args
    assert (
        "DITTO_RESEARCH_ENVIRONMENT_LOCK_HASH="
        "${{ steps.identity.outputs.environment_lock_sha256 }}"
    ) in build_args


def test_docker_runtime_is_digest_pinned_non_root_and_readyz_gated() -> None:
    dockerfile = (ROOT / "deploy" / "docker" / "Dockerfile").read_text()
    from_lines = [
        line.strip() for line in dockerfile.splitlines() if line.startswith("FROM ")
    ]
    assert len(from_lines) >= 2
    assert all(re.search(r"@sha256:[0-9a-f]{64}", line) for line in from_lines)
    assert re.search(r"^USER (?!root|0(?:\D|$))", dockerfile, re.MULTILINE)
    assert "/readyz" in dockerfile
    assert "DITTO_DATA_ROOT" not in dockerfile
    assert "org.opencontainers.image.revision" in dockerfile
    assert "io.ditto.api-contract.sha256" in dockerfile
    for name in ("DITTO_CONFIG_ROOT", "DITTO_STATE_ROOT", "DITTO_CACHE_ROOT"):
        assert name in dockerfile


def test_container_readiness_smoke_uses_runtime_only_offline_credential() -> None:
    """A secret-free image is ready only after deployment supplies a credential."""
    workflow = _workflow("ci.yml")
    steps = workflow["jobs"]["container-smoke"]["steps"]
    build_script = next(
        step["run"]
        for step in steps
        if step.get("name") == "Build immutable runtime image"
    )
    smoke_script = next(
        step["run"]
        for step in steps
        if step.get("name") == "Verify non-root runtime and readiness"
    )
    assert "TUSHARE_TOKEN" not in build_script
    assert "--env TUSHARE_TOKEN=ci-smoke-offline-credential" in smoke_script

    dockerfile = (ROOT / "deploy" / "docker" / "Dockerfile").read_text()
    assert "ARG TUSHARE_TOKEN" not in dockerfile
    assert "ENV TUSHARE_TOKEN" not in dockerfile

    production_config = (ROOT / "config" / "production" / "data_source.env").read_text()
    assert "TUSHARE_TOKEN=your_token_here" not in production_config

    compose = yaml.safe_load(
        (ROOT / "deploy" / "docker" / "docker-compose.yml").read_text()
    )
    for service_name in ("ditto-api", "ditto-job"):
        token_input = compose["services"][service_name]["environment"]["TUSHARE_TOKEN"]
        assert token_input.startswith("${TUSHARE_TOKEN:?")


def test_checked_in_deploy_images_are_immutable() -> None:
    violations: list[str] = []
    for compose_path in sorted((ROOT / "deploy").rglob("docker-compose.yml")):
        for line_number, line in enumerate(compose_path.read_text().splitlines(), 1):
            stripped = line.strip()
            if not stripped.startswith("image:"):
                continue
            reference = stripped.removeprefix("image:").strip()
            if reference.startswith("${DITTO_IMAGE:"):
                continue
            if not re.search(r"@sha256:[0-9a-f]{64}$", reference):
                violations.append(f"{compose_path.relative_to(ROOT)}:{line_number}")
    assert violations == []


def test_codeowners_and_renovate_are_canonical() -> None:
    codeowners_path = ROOT / ".github" / "CODEOWNERS"
    assert codeowners_path.is_file()
    codeowners = codeowners_path.read_text(encoding="utf-8")
    assert "@ChevyWang" in codeowners
    assert "@chevy" not in codeowners
    assert not (ROOT / ".github" / "CODEOWNER").exists()
    assert not (ROOT / ".github" / "dependabot.yml").exists()
    assert not (ROOT / ".github" / "dependabot.md").exists()
    renovate = json.loads((ROOT / ".github" / "renovate.json").read_text())
    assert set(renovate["enabledManagers"]) >= {
        "github-actions",
        "dockerfile",
        "docker-compose",
        "npm",
        "pixi",
    }
    assert renovate["automerge"] is False


def test_root_ci_includes_security_and_built_artifact_gates() -> None:
    workspace = tomllib.loads((ROOT / "pixi.toml").read_text(encoding="utf-8"))
    tasks = workspace["tasks"]
    ci_dependencies = set(tasks["ci"]["depends-on"])

    assert "security-supply-chain" in ci_dependencies
    assert "artifact-gate" in ci_dependencies
    assert "web-ci" in tasks["artifact-gate"]["depends-on"]


def test_repository_has_no_unapproved_large_files() -> None:
    assert validate_large_files(ROOT) == []
