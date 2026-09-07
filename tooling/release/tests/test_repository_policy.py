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


def _workflow(name: str) -> dict[str, Any]:
    loaded = yaml.safe_load((WORKFLOWS / name).read_text())
    assert isinstance(loaded, dict)
    if True in loaded and "on" not in loaded:
        loaded["on"] = loaded.pop(True)
    return loaded


def _dependencies(task: dict[str, Any]) -> set[str]:
    return {command["task"] for command in task["cmds"] if isinstance(command, dict)}


def _command(task: dict[str, Any]) -> str:
    return " && ".join(command for command in task["cmds"] if isinstance(command, str))


def test_ci_runs_parallel_semantic_jobs_and_has_fail_closed_gate() -> None:
    workflow = _workflow("ci.yml")
    triggers = workflow["on"]
    assert set(triggers) >= {"pull_request", "push", "merge_group"}
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["pull_request"]["branches"] == ["main"]
    assert all("paths" not in value for value in triggers.values() if value)

    jobs = workflow["jobs"]
    assert set(jobs["ci-gate"]["needs"]) == set(jobs) - {"ci-gate"}
    assert jobs["ci-gate"]["if"] == "${{ always() }}"
    assert "required" in jobs["repository-policy"]["outputs"]
    assert "schedule" in triggers
    for name, job in jobs.items():
        if name not in {"ci-gate", "repository-policy"}:
            assert "repository-policy" in job["needs"]
            assert name in job["if"]


def test_ci_preserves_system_failure_evidence_and_checks_diff_hygiene() -> None:
    workflow = _workflow("ci.yml")
    repository_steps = workflow["jobs"]["repository-policy"]["steps"]
    checkout = repository_steps[0]
    assert checkout["with"]["fetch-depth"] == 0
    diff_hygiene = next(
        step["run"] for step in repository_steps if step.get("name") == "Diff hygiene"
    )
    assert 'git diff --check "$base" "$GITHUB_SHA"' in diff_hygiene
    assert 'git show --check --format= "$GITHUB_SHA"' in diff_hygiene

    system_steps = workflow["jobs"]["system-e2e"]["steps"]
    upload = next(
        step
        for step in system_steps
        if step.get("name") == "Upload system browser evidence"
    )
    assert upload["if"] == "${{ always() }}"
    assert upload["with"]["path"] == "build/system-e2e"
    assert "github.event_name == 'pull_request'" in str(
        upload["with"]["retention-days"]
    )

    for job_name, step_name in (
        ("backend-tests", "Upload coverage evidence"),
        ("web-quality", "Upload Web build"),
    ):
        step = next(
            item
            for item in workflow["jobs"][job_name]["steps"]
            if item.get("name") == step_name
        )
        assert "github.event_name == 'pull_request'" in str(
            step["with"]["retention-days"]
        )


def test_backend_coverage_fetches_history_and_selects_every_event_base() -> None:
    """Changed coverage must compare against an exact base on every CI event."""
    workflow = _workflow("ci.yml")
    backend = workflow["jobs"]["backend-tests"]
    checkout = backend["steps"][0]
    assert checkout["with"]["fetch-depth"] == 0

    coverage_step = next(
        step for step in backend["steps"] if step.get("run") == "task backend-coverage"
    )
    base_ref = coverage_step["env"]["COVERAGE_BASE_REF"]
    assert "github.event.pull_request.base.sha" in base_ref
    assert "github.event.merge_group.base_sha" in base_ref
    assert "github.event.before" in base_ref


def test_ci_has_explicit_pit_and_supported_platform_gates() -> None:
    workflow = _workflow("ci.yml")
    jobs = workflow["jobs"]
    backend_steps = json.dumps(jobs["backend-tests"])
    assert "task pit" in backend_steps

    platform = jobs["platform-smoke"]
    matrix = platform["strategy"]["matrix"]["include"]
    by_name = {entry["name"]: entry for entry in matrix}
    assert by_name["macos-arm64"]["os"] == "macos-14"
    assert by_name["windows-x64"]["os"] == "windows-2025"
    platform_steps = json.dumps(platform)
    assert "./.github/actions/setup-toolchain" in platform_steps
    assert "task check-backend" in platform_steps
    assert "task check-web" in platform_steps
    assert "task type-all" in platform_steps
    assert "task web-type" in platform_steps


def test_windows_gate_runs_representative_units_and_a_real_loopback_api() -> None:
    """Windows support must execute behavior, not only compile both stacks."""
    workflow = _workflow("ci.yml")
    steps = workflow["jobs"]["platform-smoke"]["steps"]
    windows_steps = {
        step.get("name"): step
        for step in steps
        if "matrix.name == 'windows-x64'" in str(step.get("if", ""))
    }
    expected = {
        "Windows backend core unit": "task platform-backend-unit",
        "Windows Web unit": "task platform-web-unit",
        "Windows loopback API smoke": "task platform-api-smoke",
    }
    for name, command in expected.items():
        assert windows_steps[name]["run"] == command

    workspace = yaml.safe_load((ROOT / "Taskfile.yml").read_text(encoding="utf-8"))
    tasks = workspace["tasks"]
    backend = _command(tasks["platform-backend-unit"])
    assert "packages/kernel/tests/unit/test_identity.py" in backend
    assert "apps/backend/tests/unit/test_main_unit.py" in backend
    assert "test_artifact_file_primitives_unit.py" in backend
    assert "test_artifact_service_unit.py" in backend
    assert "--no-cov" in backend

    web = tasks["platform-web-unit"]
    assert web["dir"] == "apps/web"
    assert "vitest.mjs run" in _command(web)
    assert "src/api/compatibility.test.ts" in _command(web)

    assert "python -m tooling.dev.platform_smoke" in _command(
        tasks["platform-api-smoke"]
    )


def test_contract_job_uses_the_complete_root_contract_gate() -> None:
    """Hosted CI must include conformance, not only the static snapshot checks."""
    workflow = _workflow("ci.yml")
    steps = workflow["jobs"]["api-contract"]["steps"]
    contract_step = next(step for step in steps if step.get("name") == "Contract gate")
    assert contract_step["run"] == "task check-contract"
    assert any(step.get("run") == "task contract-toolchain-bootstrap" for step in steps)


def test_required_ci_executes_all_release_and_supply_chain_policy_tests() -> None:
    workflow = _workflow("ci.yml")
    steps = workflow["jobs"]["release-cohort"]["steps"]
    test_step = next(
        step for step in steps if step.get("name") == "Test release and security policy"
    )
    command = test_step["run"]
    assert "tooling/release/tests" in command
    assert "tooling/security/tests" in command
    assert "test_cohort_manifest.py" not in command


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


def test_bun_workspace_uses_one_isolated_registry_contract() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["private"] is True
    assert package["packageManager"] == "bun@1.3.14"
    assert package["workspaces"] == ["apps/web"]
    assert package["trustedDependencies"] == []

    bunfig = tomllib.loads((ROOT / "bunfig.toml").read_text(encoding="utf-8"))
    install = bunfig["install"]
    assert install["linker"] == "isolated"
    assert install["registry"] == "https://registry.npmjs.org"
    assert install["hoistPattern"] == []
    assert install["publicHoistPattern"] == []
    assert bunfig["install"]["lockfile"]["save"] is True

    assert (ROOT / "bun.lock").is_file()
    forbidden = (
        "bun.lockb",
        "package-lock.json",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "yarn.lock",
    )
    assert [name for name in forbidden if (ROOT / name).exists()] == []


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
    content = (
        (WORKFLOWS / "security.yml").read_text()
        + (ROOT / "tooling/release/artifact_gate.py").read_text()
    ).lower()
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
    assert scanner_references
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
    assert fingerprints
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
    sentinel = "".join(("ghp_", "aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"))
    assert sentinel in content
    assert 'test "$sentinel_status" -eq 23' in content


def test_mutation_gate_is_weekly_evidence_not_a_pr_required_dependency() -> None:
    workflow = _workflow("security.yml")
    mutation = workflow["jobs"]["mutation-critical"]
    assert "schedule" in mutation["if"]
    content = json.dumps(mutation)
    assert "task mutation-critical" in content
    assert "build/mutation/mutmut-cicd-stats.json" in content
    assert "mutation-critical" in workflow["jobs"]["security-gate"]["needs"]


def test_release_workflow_attests_the_complete_cohort() -> None:
    workflow = _workflow("release.yml")
    build = workflow["jobs"]["release-cohort"]
    publish = workflow["jobs"]["publish-cohort"]
    assert build["permissions"] == {
        "actions": "read",
        "contents": "read",
    }
    assert publish["needs"] == "release-cohort"
    assert publish["permissions"] == {
        "actions": "read",
        "artifact-metadata": "write",
        "attestations": "write",
        "contents": "write",
        "id-token": "write",
    }
    assert not any(
        str(step.get("uses", "")).startswith("actions/checkout@")
        for step in publish["steps"]
    )
    publish_scripts = "\n".join(str(step.get("run", "")) for step in publish["steps"])
    for forbidden in ("bun ", "docker ", "pixi ", "python "):
        assert forbidden not in publish_scripts
    staging = next(
        step
        for step in build["steps"]
        if step.get("name") == "Upload verified release staging"
    )
    assert staging["with"]["retention-days"] == 1
    content = (WORKFLOWS / "release.yml").read_text()
    for required in (
        "actions/attest-build-provenance@",
        "--api-contract-sha256",
        "dist/ditto-image.tar",
        "dist/ditto-backend.spdx.json",
        "dist/ditto-web.tar",
        "dist/ditto-web.spdx.json",
        "--backend-artifact ditto-image.tar",
        "--web-artifact ditto-web.tar",
        "dist/release-cohort.json",
        "dist/SHA256SUMS",
        "dist/ditto-release-cohort.attestation.json",
        "gh release create",
        "github.event_name == 'push'",
    ):
        assert required in content


def test_release_cohort_is_self_contained_and_verified_before_distribution() -> None:
    """Downloaded evidence must verify without the repository checkout."""
    workflow = _workflow("release.yml")
    steps = workflow["jobs"]["release-cohort"]["steps"]
    stage = next(step for step in steps if step.get("name") == "Stage release inputs")
    generation = next(
        step["run"]
        for step in steps
        if step.get("name") == "Generate and verify release cohort manifest"
    )
    required_inputs = (
        "dist/release-inputs/contracts/openapi/v1.json",
        "dist/release-inputs/uv.lock",
        "dist/release-inputs/bun.lock",
    )
    for source, destination in (
        ("contracts/openapi/v1.json", required_inputs[0]),
        ("uv.lock", required_inputs[1]),
        ("bun.lock", required_inputs[2]),
    ):
        assert source in stage["run"]
        assert destination in stage["run"]

    assert "--workspace-root dist" in generation
    assert "cd dist" in generation
    for relative in (
        "release-inputs/contracts/openapi/v1.json",
        "release-inputs/uv.lock",
        "release-inputs/bun.lock",
    ):
        assert f"--artifact {relative}" in generation
    assert "--backend-artifact ditto-image.tar" in generation
    assert "--web-artifact ditto-web.tar" in generation
    assert "--output release-cohort.json" in generation
    generator = generation.index("tooling.release.cohort_manifest")
    verifier = generation.index("tooling.release.cohort_verify")
    checksums = generation.index("sha256sum")
    assert generator < verifier < checksums

    publish_steps = workflow["jobs"]["publish-cohort"]["steps"]
    attest = next(
        step
        for step in publish_steps
        if step.get("name") == "Attest release provenance"
    )
    upload = next(
        step
        for step in publish_steps
        if step.get("name") == "Upload immutable release cohort"
    )
    publish = next(
        step
        for step in publish_steps
        if step.get("name") == "Publish long-lived release evidence"
    )
    for required in required_inputs:
        assert required.removeprefix("dist/") in generation
        assert required in attest["with"]["subject-path"]
        assert required in upload["with"]["path"]
        assert required in publish["run"]


def test_release_ships_a_non_recursive_deterministic_offline_bundle() -> None:
    workflow = _workflow("release.yml")
    steps = workflow["jobs"]["release-cohort"]["steps"]
    stage = next(step for step in steps if step.get("name") == "Stage release inputs")
    generation = next(
        step["run"]
        for step in steps
        if step.get("name") == "Generate and verify release cohort manifest"
    )
    required_tools = (
        "release-tools/tooling/__init__.py",
        "release-tools/tooling/release/__init__.py",
        "release-tools/tooling/release/cohort_manifest.py",
        "release-tools/tooling/release/cohort_verify.py",
        "release-tools/verify-cohort.py",
    )
    assert "tooling.release.cohort_bundle stage-tools" in stage["run"]
    for relative in required_tools:
        assert f"--artifact {relative}" in generation

    bundle_command = "tooling.release.cohort_bundle create"
    assert bundle_command in generation
    assert "--output ditto-release-cohort.tar" in generation
    assert "--source-date-epoch" in generation
    assert generation.index(
        "compatibility_policy register-previous"
    ) < generation.index(bundle_command)
    assert generation.index(bundle_command) < generation.index("sha256sum")
    assert "--artifact ditto-release-cohort.tar" not in generation

    publish_steps = workflow["jobs"]["publish-cohort"]["steps"]
    attest = next(
        step
        for step in publish_steps
        if step.get("name") == "Attest release provenance"
    )
    upload = next(
        step
        for step in publish_steps
        if step.get("name") == "Upload immutable release cohort"
    )
    publish = next(
        step["run"]
        for step in publish_steps
        if step.get("name") == "Publish long-lived release evidence"
    )
    bundle = "dist/ditto-release-cohort.tar"
    assert "ditto-release-cohort.tar" in generation[generation.index("sha256sum") :]
    assert bundle in attest["with"]["subject-path"]
    assert bundle in upload["with"]["path"]
    assert bundle in publish
    assert "--workspace-root dist" in generation

    documentation = (WORKFLOWS / "README.md").read_text(encoding="utf-8")
    for required in (
        "gh attestation verify ditto-release-cohort.tar",
        "--bundle ditto-release-cohort.attestation.json",
        "--custom-trusted-root /trusted/github-attestation-root.jsonl",
        "--repo cosmos-arc/ditto",
        "--signer-workflow github.com/cosmos-arc/ditto/.github/workflows/release.yml",
        '--source-digest "$expected_git_sha"',
        '--source-ref "refs/tags/$release_tag"',
        "sha256sum --check --ignore-missing SHA256SUMS",
        "tar -xf ditto-release-cohort.tar",
        "python3 release-tools/verify-cohort.py",
        "--workspace-root .",
        "--manifest release-cohort.json",
    ):
        assert required in documentation
    attestation = documentation.index("gh attestation verify ditto-release-cohort.tar")
    checksums = documentation.index("sha256sum --check --ignore-missing SHA256SUMS")
    extraction = documentation.index("tar -xf ditto-release-cohort.tar")
    bundled_verifier = documentation.index("python3 release-tools/verify-cohort.py")
    assert attestation < checksums < extraction < bundled_verifier

    attestation_step = next(
        step
        for step in publish_steps
        if step.get("name") == "Attest release provenance"
    )
    assert attestation_step["id"] == "attest"
    export_step = next(
        step
        for step in publish_steps
        if step.get("name") == "Export and verify attestation bundle"
    )
    assert (
        "steps.attest.outputs.bundle-path" in export_step["env"]["ATTESTATION_BUNDLE"]
    )
    export_script = export_step["run"]
    for required in (
        "dist/ditto-release-cohort.attestation.json",
        "gh attestation verify",
        '--repo "$GITHUB_REPOSITORY"',
        '--source-digest "$GITHUB_SHA"',
        '--source-ref "$GITHUB_REF"',
        "--deny-self-hosted-runners",
    ):
        assert required in export_script
    assert "--signer-workflow" in export_script

    for step in (upload,):
        assert "dist/ditto-release-cohort.attestation.json" in step["with"]["path"]
    assert "dist/ditto-release-cohort.attestation.json" in publish


def test_contract_gate_validates_policy_and_release_emits_next_policy() -> None:
    """Each release must validate today's allowlist and emit a real next one."""
    workspace = yaml.safe_load((ROOT / "Taskfile.yml").read_text(encoding="utf-8"))
    tasks = workspace["tasks"]
    assert "python -m tooling.release.compatibility_policy validate" in _command(
        tasks["cohort-compatibility-check"]
    )
    assert "cohort-compatibility-check" in _dependencies(tasks["check-contract"])

    content = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
    for required in (
        "tooling.release.compatibility_policy register-previous",
        "--release-manifest dist/release-cohort.json",
        "dist/next-cohort-policy/compatibility-policy.json",
        "dist/next-cohort-policy/compatibility-policy.sha256",
    ):
        assert required in content


def test_release_requires_main_ci_and_verifies_the_exact_runtime_subject() -> None:
    """A tag must not turn an unverified commit or unstarted image into a release."""
    workflow = _workflow("release.yml")
    steps = workflow["jobs"]["release-cohort"]["steps"]
    provenance = next(
        step["run"]
        for step in steps
        if step.get("name") == "Verify release source provenance"
    )
    for required in (
        "git merge-base --is-ancestor",
        "origin/main",
        "actions/workflows/ci.yml/runs",
        "head_sha=$GITHUB_SHA",
        '.event == "push"',
        '.head_branch == "main"',
        'latest_conclusion" = "success"',
    ):
        assert required in provenance
    assert "status=success" not in provenance

    image_build = next(
        step for step in steps if step.get("name") == "Build OCI release artifact"
    )
    assert image_build["with"]["load"] is True
    assert "ditto-release:${{ github.sha }}" in image_build["with"]["tags"]

    verification = next(
        step["run"]
        for step in steps
        if step.get("name") == "Verify and export the release image"
    )
    for required in (
        "docker image inspect",
        "65532:65532",
        "TUSHARE_TOKEN=ci-smoke-offline-credential",
        "/readyz",
        "/api/v1/status",
        ".product_version == $version",
        ".git_sha == $sha",
        '.api_contract_version == "v1"',
        ".api_contract_sha256 == $contract",
        "docker save --output dist/ditto-image.tar",
        "trivy:0.74.0@sha256:",
        "--severity HIGH,CRITICAL",
    ):
        assert required in verification

    sbom = next(
        step["run"]
        for step in steps
        if step.get("name") == "Generate SPDX SBOM from release subject"
    )
    for required in (
        "_verify_web_artifact_metadata",
        "_bind_and_verify_web_sbom",
        "_canonicalize_spdx_sbom",
        "apps/web/package.json",
        "package.json bun.lock",
    ):
        assert required in sbom
    assert "$PWD/apps/web/dist:/web:ro" not in sbom


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
    assert "tooling.release.environment_identity" in identity_script
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
    assert any(
        step.get("run") == "uv run --no-sync python -m tooling.release.artifact_gate"
        for step in steps
    )
    assert "web-quality" in workflow["jobs"]["container-smoke"]["needs"]
    # Runtime credentials, exact identity and immutable build/export/smoke binding
    # are exercised by test_artifact_gate, rather than duplicated shell snippets.
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
        "pep621",
    }
    assert renovate["automerge"] is False


def test_root_ci_includes_security_and_built_artifact_gates() -> None:
    workspace = yaml.safe_load((ROOT / "Taskfile.yml").read_text(encoding="utf-8"))
    tasks = workspace["tasks"]
    ci_dependencies = set(_dependencies(tasks["ci"]))

    assert "security-supply-chain" in ci_dependencies
    assert "artifact-gate" in ci_dependencies
    assert "web-ci" in _dependencies(tasks["artifact-gate"])


def test_web_ci_uses_the_canonical_root_task() -> None:
    """Hosted and local full Web validation must use the canonical Task task."""
    workspace = yaml.safe_load((ROOT / "Taskfile.yml").read_text(encoding="utf-8"))
    tasks = workspace["tasks"]
    assert "web-manifest-check" not in _dependencies(tasks["web-ci"])

    workflow = _workflow("ci.yml")
    web_job = workflow["jobs"]["web-quality"]
    uses = {step.get("uses") for step in web_job["steps"]}
    assert any(
        isinstance(reference, str) and reference == "./.github/actions/setup-toolchain"
        for reference in uses
    )
    commands = {step.get("run") for step in web_job["steps"]}
    assert "task web-ci" in commands
    assert "bun --cwd apps/web run ci" not in commands


def test_web_composite_validation_is_owned_only_by_task() -> None:
    workspace = yaml.safe_load((ROOT / "Taskfile.yml").read_text(encoding="utf-8"))
    scripts = json.loads((ROOT / "apps/web/package.json").read_text())["scripts"]
    assert "check" not in scripts
    assert "ci" not in scripts
    tasks = workspace["tasks"]
    assert not _command(tasks["check-web"])
    assert not _command(tasks["web-ci"])

    def leaves(name: str) -> set[str]:
        task = tasks[name]
        deps = _dependencies(task)
        return {name} | set().union(*(leaves(dep) for dep in deps))

    static = {
        "web-lint",
        "web-type",
        "web-architecture",
        "web-product-check",
        "web-token-check",
    }
    assert static | {"web-test"} <= leaves("check-web")
    assert static | {"web-coverage", "web-prototype", "web-build"} <= leaves("web-ci")
    assert "web-test" not in leaves("web-ci")
    assert "web-manifest-check" not in leaves("check-web")


def test_repository_has_no_unapproved_large_files() -> None:
    assert validate_large_files(ROOT) == []
