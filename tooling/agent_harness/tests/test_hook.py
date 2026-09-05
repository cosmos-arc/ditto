from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tooling.agent_harness.evidence as evidence_module
import tooling.agent_harness.hook as hook_module
from tooling.agent_harness.evidence import (
    change_manifest,
    changed_paths,
    diff_digest,
)
from tooling.agent_harness.hook import (
    VerificationResult,
    classify_diff,
    extract_python_paths,
    policy_violation,
    receipt_path,
    stop_decision,
    verification_commands,
)


def _initialize_repository(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "fixture@example.com"],
        cwd=root,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Fixture"], cwd=root, check=True)


def _commit_file(root: Path, relative: str, content: str) -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", relative], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
    return target


def _fixture_manifest(
    paths: tuple[str, ...], *, forbidden: tuple[str, ...] = ()
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "base_sha": "base",
        "head_sha": "head",
        "git_object_format": "sha1",
        "changes": {
            path: {
                "status": {"index": "?", "worktree": "?"},
                "index": {"state": "absent"},
                "worktree": {
                    "state": "present",
                    "kind": "file",
                    "mode": "0644",
                    "sha256": "0" * 64,
                },
            }
            for path in paths
        },
        "configs": {},
        "repository_policy": {"forbidden_package_manager_paths": list(forbidden)},
        "tools": {"project_python": "Python fixture"},
    }


class PathExtractionTests(unittest.TestCase):
    def test_claude_edit_and_write_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            fixtures = (
                {
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "packages/data/query.py"},
                },
                {
                    "tool_name": "Write",
                    "tool_input": {"path": str(root / "packages/data/model.py")},
                },
            )

            actual = [extract_python_paths(payload, root) for payload in fixtures]

            assert actual[0] == [root / "packages/data/query.py"]
            assert actual[1] == [root / "packages/data/model.py"]

    def test_codex_apply_patch_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            payload = {
                "tool_name": "apply_patch",
                "tool_input": {
                    "command": (
                        "*** Begin Patch\n"
                        "*** Update File: packages/data/query.py\n"
                        "*** Add File: packages/data/new_reader.py\n"
                        "*** Move to: packages/data/moved_reader.py\n"
                        "*** Update File: docs/readme.md\n"
                        "*** End Patch"
                    )
                },
            }

            assert extract_python_paths(payload, root) == [
                root / "packages/data/moved_reader.py",
                root / "packages/data/new_reader.py",
                root / "packages/data/query.py",
            ]

    def test_deleted_tracked_file_is_changed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "fixture@example.com"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Fixture"], cwd=root, check=True
            )
            source = root / "deleted.py"
            source.write_text("value = 1\n", encoding="utf-8")
            subprocess.run(["git", "add", "deleted.py"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            source.unlink()

            assert changed_paths(root) == ["deleted.py"]

    def test_untracked_file_is_changed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "fixture@example.com"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Fixture"], cwd=root, check=True
            )
            tracked = root / "tracked.txt"
            tracked.write_text("tracked\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            (root / "new-source.ts").write_text(
                "export const value = 1;\n", encoding="utf-8"
            )

            assert changed_paths(root) == ["new-source.ts"]

    def test_rename_is_recorded_as_delete_and_add(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _initialize_repository(root)
            _commit_file(root, "old.py", "VALUE = 1\n")

            subprocess.run(["git", "mv", "old.py", "new.py"], cwd=root, check=True)

            assert changed_paths(root) == ["new.py", "old.py"]

    def test_untracked_content_change_invalidates_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "fixture@example.com"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Fixture"], cwd=root, check=True
            )
            tracked = root / "tracked.txt"
            tracked.write_text("tracked\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            untracked = root / "new-source.ts"
            untracked.write_text("export const value = 1;\n", encoding="utf-8")
            before = diff_digest(root)

            untracked.write_text("export const value = 2;\n", encoding="utf-8")

            assert diff_digest(root) != before

    def test_index_and_worktree_are_both_bound_into_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _initialize_repository(root)
            tracked = _commit_file(root, "tracked.py", "VALUE = 1\n")

            with patch(
                "tooling.agent_harness.evidence._tool_versions",
                return_value={"project_python": "Python fixture"},
            ):
                tracked.write_text("VALUE = 2\n", encoding="utf-8")
                subprocess.run(["git", "add", "tracked.py"], cwd=root, check=True)
                tracked.write_text("VALUE = 3\n", encoding="utf-8")
                before = diff_digest(root)
                changes = change_manifest(root)["changes"]
                assert isinstance(changes, dict)
                before_change = changes["tracked.py"]

                tracked.write_text("VALUE = 4\n", encoding="utf-8")
                subprocess.run(["git", "add", "tracked.py"], cwd=root, check=True)
                tracked.write_text("VALUE = 3\n", encoding="utf-8")
                after = diff_digest(root)

            assert before != after
            assert set(before_change) >= {"index", "worktree"}
            assert before_change["index"]["mode"] == "100644"

    def test_index_mode_change_invalidates_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _initialize_repository(root)
            tracked = _commit_file(root, "tool.py", "VALUE = 1\n")
            with patch(
                "tooling.agent_harness.evidence._tool_versions",
                return_value={"project_python": "Python fixture"},
            ):
                before = diff_digest(root)
                tracked.chmod(0o755)
                subprocess.run(["git", "add", "tool.py"], cwd=root, check=True)
                manifest = change_manifest(root)
                assert diff_digest(root) != before
            changes = manifest["changes"]
            assert isinstance(changes, dict)
            assert changes["tool.py"]["index"]["mode"] == "100755"

    def test_tool_manifest_names_the_project_verifiers(self) -> None:
        commands = evidence_module.TOOL_VERSION_COMMANDS
        project_distributions = evidence_module.PROJECT_TOOL_DISTRIBUTIONS
        package_manifests = evidence_module.INSTALLED_TOOL_PACKAGE_MANIFESTS

        assert set(commands) >= {"bun", "git", "host_python", "pixi"}
        assert set(project_distributions) >= {
            "basedpyright",
            "coverage",
            "import_linter",
            "pytest",
            "ruff",
        }
        assert set(package_manifests) >= {
            "biome",
            "dependency_cruiser",
            "openapi_typescript",
            "playwright",
            "redocly",
            "typescript",
            "vite",
            "vitest",
        }

    def test_installed_tool_package_versions_are_bound_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "node_modules" / "fixture" / "package.json"
            package.parent.mkdir(parents=True)
            package.write_text('{"version": "1.2.3"}\n', encoding="utf-8")
            with (
                patch.object(
                    evidence_module, "_project_tool_versions", return_value={}
                ),
                patch.object(evidence_module, "TOOL_VERSION_COMMANDS", {}),
                patch.object(
                    evidence_module,
                    "INSTALLED_TOOL_PACKAGE_MANIFESTS",
                    {
                        "fixture": "node_modules/fixture/package.json",
                        "missing": "node_modules/missing/package.json",
                    },
                ),
            ):
                versions = evidence_module._tool_versions(root)

        assert versions == {"fixture": "1.2.3", "missing": "unavailable"}

    def test_project_tool_versions_use_one_stable_metadata_query(self) -> None:
        expected = {
            **{
                name: f"{index}.0"
                for index, name in enumerate(
                    evidence_module.PROJECT_TOOL_DISTRIBUTIONS, start=1
                )
            },
            "project_python": "3.13.14",
        }
        completed = subprocess.CompletedProcess(
            args=(),
            returncode=0,
            stdout=json.dumps(expected),
            stderr="",
        )
        with patch.object(
            evidence_module.subprocess, "run", return_value=completed
        ) as run_mock:
            versions = evidence_module._project_tool_versions(Path("/workspace"))

        assert versions["project_python"] == "3.13.14"
        assert versions["basedpyright"] == expected["basedpyright"]
        assert set(versions) == {
            *evidence_module.PROJECT_TOOL_DISTRIBUTIONS,
            "project_python",
        }
        assert run_mock.call_count == 1
        assert run_mock.call_args.args[0][:5] == (
            "pixi",
            "run",
            "-e",
            "dev",
            "python",
        )


class CommandPolicyTests(unittest.TestCase):
    def test_dangerous_commands_are_blocked(self) -> None:
        fixtures = {
            "git commit -m change": "main",
            "git -C . commit -m change": "main",
            "git push origin feature --force-with-lease": "feature",
            "/usr/bin/git push origin feature --force": "feature",
            "git reset --hard HEAD~1": "feature",
            "git commit --no-verify -m change": "feature",
            "rm -rf build": "feature",
            "rm -r -f build": "feature",
            "/bin/rm -rf build": "feature",
            "python3 -m pip install foo": "feature",
            "poetry add foo": "feature",
            "conda install foo": "feature",
            "npm install foo": "feature",
            "pnpm add foo": "feature",
            "yarn install": "feature",
            "npx eslint .": "feature",
        }
        for command, branch in fixtures.items():
            with self.subTest(command=command):
                assert policy_violation(command, branch) is not None

    def test_safe_project_commands_are_allowed(self) -> None:
        fixtures = (
            "pixi run -e dev check",
            "git status --short",
            "git diff --check",
            "pytest packages/data/tests/test_query.py",
            "git push origin feature",
            "rg 'npm install' tooling/agent_harness",
            "printf 'pnpm add is forbidden'",
        )
        for command in fixtures:
            with self.subTest(command=command):
                assert policy_violation(command, "feature") is None


class DiffClassificationTests(unittest.TestCase):
    def test_monorepo_diff_classes(self) -> None:
        fixtures = {
            "docs": ["docs/architecture/overview.md"],
            "backend-tests": ["packages/data/tests/test_query.py"],
            "backend": ["apps/backend/src/ditto_apps/cli/main.py"],
            "web": ["apps/web/src/features/markets/index.ts"],
            "contract": ["contracts/openapi/v1.json"],
            "high-risk": ["packages/risk/src/ditto_risk/checks.py"],
            "root": ["pyproject.toml"],
            "harness": ["AGENTS.md", ".agents/skills/ditto-test-first/SKILL.md"],
            "unknown": ["unexpected/new-tool.conf"],
        }
        for name, paths in fixtures.items():
            with self.subTest(name=name):
                assert classify_diff(paths) == name

    def test_cross_stack_and_mixed_harness_changes_fail_closed(self) -> None:
        assert (
            classify_diff(
                [
                    "apps/backend/src/ditto_apps/api/routes/system.py",
                    "apps/web/src/features/system/api/status.ts",
                ]
            )
            == "cross-stack"
        )
        assert (
            classify_diff(["AGENTS.md", "apps/web/src/features/system/api/status.ts"])
            == "root"
        )

    def test_root_toolchain_paths_are_not_reduced_to_harness_only(self) -> None:
        for path in ("pixi.toml", ".pre-commit-config.yaml"):
            with self.subTest(path=path):
                assert classify_diff([path]) == "root"

    def test_harness_change_runs_the_complete_root_check(self) -> None:
        path = ".codex/hooks.json"

        commands = verification_commands(classify_diff([path]), [path])

        assert [" ".join(command) for command in commands] == ["pixi run -e dev check"]

    def test_contract_producers_are_classified_as_contract_changes(self) -> None:
        paths = (
            ".redocly.yaml",
            "apps/backend/src/ditto_apps/main.py",
            "apps/backend/src/ditto_apps/openapi_contract.py",
            "apps/backend/src/ditto_apps/api/app_metadata.py",
            "apps/backend/src/ditto_apps/api/params.py",
            "apps/backend/src/ditto_apps/middleware.py",
            "apps/backend/src/ditto_apps/models/system.py",
            "apps/web/scripts/gen-api.sh",
            "apps/web/src/api/client.ts",
            "tooling/contracts/export_openapi.py",
        )
        for path in paths:
            with self.subTest(path=path):
                assert classify_diff([path]) == "contract"

    def test_strategy_change_is_high_risk_and_requires_pit(self) -> None:
        path = "packages/strategy/src/ditto_strategy/alpha/pipeline.py"

        level = classify_diff([path])
        commands = [
            " ".join(command) for command in verification_commands(level, [path])
        ]

        assert level == "high-risk"
        assert commands == [
            "pixi run -e dev check-backend",
            "pixi run -e dev pytest -m pit",
        ]

    def test_application_and_backend_risk_entrypoints_keep_specialized_gates(
        self,
    ) -> None:
        fixtures = {
            "packages/application/src/ditto_application/commands/trade.py": (
                "high-risk",
                ("check-backend", "pytest -m pit"),
            ),
            "packages/application/src/ditto_application/queries/factor_ic_report.py": (
                "high-risk",
                ("check-backend", "pytest -m pit"),
            ),
            "apps/backend/src/ditto_apps/jobs/flows/backtest.py": (
                "high-risk",
                ("check-backend", "pytest -m pit"),
            ),
            "apps/backend/src/ditto_apps/api/routes/trade_command_routes.py": (
                "contract-high-risk",
                ("check", "test-system", "pytest -m pit"),
            ),
        }
        for path, (expected_level, fragments) in fixtures.items():
            with self.subTest(path=path):
                level = classify_diff([path])
                commands = "\n".join(
                    " ".join(command)
                    for command in verification_commands(level, [path])
                )

                assert level == expected_level
                for fragment in fragments:
                    assert fragment in commands

    def test_test_only_commands_are_scoped_and_read_only(self) -> None:
        path = "packages/data/tests/unit/test_data_import_boundary_unit.py"
        commands = verification_commands("backend-tests", [path])
        flattened = [" ".join(command) for command in commands]
        assert any("ruff format --check" in command for command in flattened)
        assert any("ruff check" in command for command in flattened)
        assert any("type --tests" in command for command in flattened)
        assert any(path in command for command in flattened)

    def test_changed_test_fixture_runs_owning_package_tests(self) -> None:
        commands = verification_commands(
            "backend-tests", ["packages/data/tests/fixtures/market_snapshot.json"]
        )
        expected = (
            "pixi run -e dev pytest -q --import-mode=importlib packages/data/tests"
        )
        assert expected in [" ".join(command) for command in commands]

    def test_backend_fixture_runs_backend_test_suite(self) -> None:
        commands = verification_commands(
            "backend-tests",
            ["apps/backend/tests/fixtures/openapi/expected.json"],
        )
        flattened = [" ".join(command) for command in commands]
        assert (
            "pixi run -e dev pytest -q --import-mode=importlib apps/backend/tests"
            in flattened
        )

    def test_deleted_python_test_runs_owner_without_targeting_missing_file(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = "packages/data/tests/test_deleted.py"
            commands = verification_commands("backend-tests", [path], root=root)
        flattened = [" ".join(command) for command in commands]
        assert all(path not in command for command in flattened)
        assert any("packages/data/tests" in command for command in flattened)

    def test_stack_specific_and_fail_closed_commands(self) -> None:
        fixtures = {
            "backend": ["check-backend"],
            "web": ["check-web"],
            "contract": ["check", "test-system"],
            "contract-high-risk": ["check", "test-system", "pytest -m pit"],
            "high-risk": ["check-backend", "pytest -m pit"],
            "cross-stack": ["check", "test-system"],
            "root": ["check"],
            "unknown": ["check"],
        }
        for level, fragments in fixtures.items():
            with self.subTest(level=level):
                commands = [
                    " ".join(command) for command in verification_commands(level, [])
                ]
                flattened = "\n".join(commands)
                for fragment in fragments:
                    assert fragment in flattened

    def test_contract_always_runs_dual_stack_and_system_gates(self) -> None:
        path = "contracts/openapi/v1.json"
        commands = verification_commands(classify_diff([path]), [path])
        flattened = [" ".join(command) for command in commands]
        assert flattened == [
            "pixi run -e dev check",
            "pixi run -e dev test-system",
        ]

    def test_unknown_path_cannot_remove_cross_stack_or_pit_gates(self) -> None:
        cross_stack = [
            "apps/backend/src/ditto_apps/api/routes/system.py",
            "apps/web/src/features/system/api/status.ts",
            "unexpected/new-tool.conf",
        ]
        high_risk = [
            "packages/risk/src/ditto_risk/checks.py",
            "unexpected/new-tool.conf",
        ]

        cross_commands = verification_commands(classify_diff(cross_stack), cross_stack)
        risk_commands = verification_commands(classify_diff(high_risk), high_risk)

        assert "pixi run -e dev test-system" in [
            " ".join(command) for command in cross_commands
        ]
        assert any("pytest -m pit" in " ".join(command) for command in risk_commands)

    def test_docs_or_harness_paths_cannot_remove_an_owning_gate(self) -> None:
        test_path = "packages/data/tests/unit/test_data_import_boundary_unit.py"
        test_and_docs = [test_path, "docs/architecture/overview.md"]
        harness_and_web = ["AGENTS.md", "apps/web/src/features/markets/index.ts"]

        test_commands = verification_commands(
            classify_diff(test_and_docs), test_and_docs
        )
        harness_commands = verification_commands(
            classify_diff(harness_and_web), harness_and_web
        )

        assert any(test_path in " ".join(command) for command in test_commands)
        assert [" ".join(command) for command in harness_commands] == [
            "pixi run -e dev check"
        ]


class StopGateTests(unittest.TestCase):
    def test_incomplete_path_evidence_fails_closed_before_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _fixture_manifest(("AGENTS.md",))
            changes = manifest["changes"]
            assert isinstance(changes, dict)
            changes["AGENTS.md"] = {}
            calls = 0

            def succeed(_root: Path, _level: str, _paths: object) -> VerificationResult:
                nonlocal calls
                calls += 1
                return VerificationResult(True, "ok")

            result = stop_decision({}, root, manifest, succeed)

            assert result["decision"] == "block"
            assert "manifest" in result["reason"].lower()
            assert calls == 0

    def test_unknown_manifest_schema_fails_closed_before_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _fixture_manifest(("AGENTS.md",))
            manifest["schema_version"] = 999
            calls = 0

            def succeed(_root: Path, _level: str, _paths: object) -> VerificationResult:
                nonlocal calls
                calls += 1
                return VerificationResult(True, "ok")

            result = stop_decision({}, root, manifest, succeed)

            assert result["decision"] == "block"
            assert "manifest" in result["reason"].lower()
            assert calls == 0

    def test_stop_gate_derives_paths_and_digest_from_one_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _fixture_manifest(("AGENTS.md",))

            def succeed(_root: Path, _level: str, _paths: object) -> VerificationResult:
                return VerificationResult(True, "ok")

            assert stop_decision({}, root, manifest, succeed) == {}
            digest = evidence_module.manifest_digest(manifest)
            assert receipt_path(root, digest).is_file()

    def test_first_failure_blocks_and_second_failure_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _fixture_manifest(("AGENTS.md",))

            def fail(_root: Path, _level: str, _paths: object) -> VerificationResult:
                return VerificationResult(False, "expected fixture failure")

            first = stop_decision({}, root, manifest, fail)
            second = stop_decision({"stop_hook_active": True}, root, manifest, fail)

            assert first["decision"] == "block"
            assert "expected fixture failure" in first["reason"]
            assert "decision" not in second
            assert "must report this failure" in second["systemMessage"]

    def test_success_writes_receipt_and_skips_identical_diff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _fixture_manifest(("AGENTS.md",))
            calls = 0

            def succeed(_root: Path, _level: str, _paths: object) -> VerificationResult:
                nonlocal calls
                calls += 1
                return VerificationResult(True, "ok")

            first = stop_decision({}, root, manifest, succeed)
            second = stop_decision({}, root, manifest, succeed)

            assert first == {}
            assert second == {}
            assert calls == 1
            digest = evidence_module.manifest_digest(manifest)
            assert receipt_path(root, digest).is_file()

    def test_tampered_receipt_is_not_trusted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _fixture_manifest(("AGENTS.md",))
            digest = evidence_module.manifest_digest(manifest)
            calls = 0

            def succeed(_root: Path, _level: str, _paths: object) -> VerificationResult:
                nonlocal calls
                calls += 1
                return VerificationResult(True, "ok")

            stop_decision({}, root, manifest, succeed)
            receipt_path(root, digest).write_text("{}\n", encoding="utf-8")

            assert stop_decision({}, root, manifest, succeed) == {}
            assert calls == 2

    def test_receipt_evidence_must_match_its_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _initialize_repository(root)
            tracked = _commit_file(root, "AGENTS.md", "baseline\n")
            tracked.write_text("changed\n", encoding="utf-8")
            calls = 0

            def succeed(_root: Path, _level: str, _paths: object) -> VerificationResult:
                nonlocal calls
                calls += 1
                return VerificationResult(True, "ok")

            with patch(
                "tooling.agent_harness.evidence._tool_versions",
                return_value={"project_python": "Python fixture"},
            ):
                manifest = change_manifest(root)
            digest = evidence_module.manifest_digest(manifest)
            stop_decision({}, root, manifest, succeed)
            cached = receipt_path(root, digest)
            receipt = json.loads(cached.read_text(encoding="utf-8"))
            receipt["evidence"]["tools"] = {"project_python": "tampered"}
            cached.write_text(json.dumps(receipt), encoding="utf-8")

            stop_decision({}, root, manifest, succeed)

            assert calls == 2

    def test_successful_receipt_is_replaced_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _fixture_manifest(("AGENTS.md",))
            digest = evidence_module.manifest_digest(manifest)

            def succeed(_root: Path, _level: str, _paths: object) -> VerificationResult:
                return VerificationResult(True, "ok")

            cached = receipt_path(root, digest)
            cached.parent.mkdir(parents=True)
            cached.write_text("{}\n", encoding="utf-8")
            previous_inode = cached.stat().st_ino

            stop_decision({}, root, manifest, succeed)

            assert cached.stat().st_ino != previous_inode
            loaded = json.loads(cached.read_text(encoding="utf-8"))
            assert loaded["digest"] == digest

    def test_forbidden_package_manager_file_blocks_before_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _initialize_repository(root)
            _commit_file(root, "tracked.txt", "tracked\n")
            forbidden = root / "apps" / "web" / "pnpm-workspace.yaml"
            forbidden.parent.mkdir(parents=True)
            forbidden.write_text("packages: []\n", encoding="utf-8")
            calls = 0

            def succeed(_root: Path, _level: str, _paths: object) -> VerificationResult:
                nonlocal calls
                calls += 1
                return VerificationResult(True, "ok")

            with patch(
                "tooling.agent_harness.evidence._tool_versions",
                return_value={"project_python": "Python fixture"},
            ):
                manifest = change_manifest(root)
            result = stop_decision({}, root, manifest, succeed)

            assert result["decision"] == "block"
            assert "pnpm-workspace.yaml" in result["reason"]
            assert calls == 0

    def test_no_tracked_diff_passes_without_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = _fixture_manifest(())
            result = stop_decision({}, root, manifest)
            assert result == {}
            digest = evidence_module.manifest_digest(manifest)
            assert not receipt_path(root, digest).exists()


class HostEntryPointTests(unittest.TestCase):
    def test_stop_blocks_when_repository_evidence_cannot_be_captured(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(sys, "argv", ["hook.py", "--event", "stop"]),
                patch.object(sys, "stdin", io.StringIO("{}")),
                patch.object(hook_module, "git_root", return_value=root),
                patch.object(
                    hook_module,
                    "change_manifest",
                    side_effect=RuntimeError("git status failed"),
                ),
                patch.object(hook_module, "emit") as emit_mock,
            ):
                exit_code = hook_module.main()

        assert exit_code == 0
        response = emit_mock.call_args.args[0]
        assert response["decision"] == "block"
        assert "git status failed" in response["reason"]


if __name__ == "__main__":
    unittest.main()
