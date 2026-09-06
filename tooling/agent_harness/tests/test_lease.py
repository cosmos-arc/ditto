from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Never

import pytest

from tooling.agent_harness.hook import (
    extract_edited_paths,
    pre_tool_decision,
    verification_decision,
)
from tooling.agent_harness.lease import (
    LeaseConflict,
    acquire_lease,
    authorize_paths,
    git_lease_paths,
    protected_resources,
    release_lease,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _run_git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ("git", *arguments),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def _initialize_repository(root: Path) -> None:
    root.mkdir()
    _run_git(root, "init", "-q")
    _run_git(root, "config", "user.email", "lease@example.com")
    _run_git(root, "config", "user.name", "Lease Fixture")
    (root / "tracked.txt").write_text("fixture\n", encoding="utf-8")
    _run_git(root, "add", "tracked.txt")
    _run_git(root, "commit", "-qm", "fixture")


def _add_worktree(root: Path, worktree: Path) -> None:
    _run_git(root, "worktree", "add", "--detach", str(worktree), "HEAD")


class ProtectedPathTests(unittest.TestCase):
    def test_protected_resources_are_declared_and_precise(self) -> None:
        fixtures = {
            "contracts/openapi/v1.json": ("contract",),
            "apps/web/src/api/generated/schema.d.ts": ("contract",),
            "bun.lock": ("lockfile",),
            "pixi.lock": ("lockfile",),
            "packages/analysis/src/ditto_analysis/storage/migration_v1_to_v2.sql": (
                "migration",
            ),
            ".redocly.yaml": ("generator-config",),
            "tooling/contracts/export_openapi.py": ("generator-config",),
            "apps/web/scripts/gen-api.sh": ("generator-config",),
            "apps/web/scripts/generate-route-tree.mjs": ("generator-config",),
            "apps/web/scripts/export-tokens.ts": ("generator-config",),
            "apps/web/scripts/export-tokens/dtcg-writer.ts": ("generator-config",),
            ".agents/skills/ditto-page-contract/scripts/generate.mjs": (
                "generator-config",
            ),
            ".agents/skills/ditto-page-contract/scripts/schema/contract.schema.json": (
                "generator-config",
            ),
            "apps/web/src/features/shell/page-contracts.generated.ts": (
                "generator-config",
            ),
            "apps/web/scripts/visual-audit.config.generated.mjs": ("generator-config",),
            "apps/web/src/routeTree.gen.ts": ("generator-config",),
            "tooling/agent_harness/hook.py": (),
            "docs/migrations/2026-09-04/README.md": (),
        }

        for path, expected in fixtures.items():
            with self.subTest(path=path):
                assert protected_resources((path,)) == expected


class SharedLeaseTests(unittest.TestCase):
    def test_acquire_binds_owner_task_worktree_and_expiry(self) -> None:
        now = datetime(2030, 1, 1, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main"
            _initialize_repository(root)

            record = acquire_lease(
                root,
                owner="agent-1",
                task="/root/contract",
                ttl=timedelta(minutes=15),
                now=now,
            )
            decision = authorize_paths(root, ("contracts/openapi/v1.json",), now=now)

            assert record.owner == "agent-1"
            assert record.task == "/root/contract"
            assert record.worktree == root.resolve().as_posix()
            assert record.expires_at == now + timedelta(minutes=15)
            assert decision.allowed

    def test_non_integrator_fails_closed_and_active_lease_conflicts(self) -> None:
        now = datetime(2030, 1, 1, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            main = temporary / "main"
            secondary = temporary / "secondary"
            _initialize_repository(main)
            _add_worktree(main, secondary)
            acquire_lease(
                main,
                owner="integrator",
                task="/root/integration",
                ttl=timedelta(minutes=10),
                now=now,
            )

            with pytest.raises(LeaseConflict):
                acquire_lease(
                    secondary,
                    owner="worker",
                    task="/root/worker",
                    ttl=timedelta(minutes=10),
                    now=now,
                )
            decision = authorize_paths(secondary, ("bun.lock",), now=now)

            assert not decision.allowed
            assert "integrator" in decision.reason

    def test_expired_lease_can_be_reclaimed_by_another_worktree(self) -> None:
        now = datetime(2030, 1, 1, tzinfo=UTC)
        after_expiry = now + timedelta(seconds=6)
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            main = temporary / "main"
            secondary = temporary / "secondary"
            _initialize_repository(main)
            _add_worktree(main, secondary)
            acquire_lease(
                main,
                owner="expired-owner",
                task="/root/expired",
                ttl=timedelta(seconds=5),
                now=now,
            )

            replacement = acquire_lease(
                secondary,
                owner="replacement",
                task="/root/replacement",
                ttl=timedelta(minutes=5),
                now=after_expiry,
            )

            assert replacement.owner == "replacement"
            assert not authorize_paths(main, ("pixi.lock",), now=after_expiry).allowed
            assert authorize_paths(secondary, ("pixi.lock",), now=after_expiry).allowed

    def test_worktree_identity_isolated_but_guard_and_lease_are_shared(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            main = temporary / "main"
            secondary = temporary / "secondary"
            _initialize_repository(main)
            _add_worktree(main, secondary)

            main_paths = git_lease_paths(main)
            secondary_paths = git_lease_paths(secondary)

            assert main_paths.git_dir != secondary_paths.git_dir
            assert main_paths.identity_path != secondary_paths.identity_path
            assert main_paths.common_dir == secondary_paths.common_dir
            assert main_paths.lease_path == secondary_paths.lease_path
            assert main_paths.guard_path == secondary_paths.guard_path

    def test_concurrent_acquire_in_one_common_dir_has_one_winner(self) -> None:
        now = datetime(2030, 1, 1, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            main = temporary / "main"
            secondary = temporary / "secondary"
            _initialize_repository(main)
            _add_worktree(main, secondary)
            barrier = threading.Barrier(2)

            def attempt(root: Path, owner: str) -> str:
                barrier.wait()
                try:
                    acquire_lease(
                        root,
                        owner=owner,
                        task=f"/root/{owner}",
                        ttl=timedelta(minutes=5),
                        now=now,
                    )
                except LeaseConflict:
                    return "conflict"
                return "acquired"

            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = tuple(
                    executor.map(attempt, (main, secondary), ("one", "two"))
                )

            assert sorted(outcomes) == ["acquired", "conflict"]

    def test_invalid_shared_metadata_fails_closed(self) -> None:
        now = datetime(2030, 1, 1, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main"
            _initialize_repository(root)
            paths = git_lease_paths(root)
            paths.lease_path.parent.mkdir(parents=True)
            paths.lease_path.write_text("{}\n", encoding="utf-8")

            decision = authorize_paths(root, ("bun.lock",), now=now)

            assert not decision.allowed
            assert "invalid" in decision.reason.lower()

    def test_release_frees_the_shared_lease_for_another_worktree(self) -> None:
        now = datetime(2030, 1, 1, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            main = temporary / "main"
            secondary = temporary / "secondary"
            _initialize_repository(main)
            _add_worktree(main, secondary)
            acquired = acquire_lease(
                main,
                owner="integrator",
                task="/root/integration",
                now=now,
            )

            released = release_lease(main)
            replacement = acquire_lease(
                secondary,
                owner="next-integrator",
                task="/root/next",
                now=now,
            )

            assert released == acquired
            assert replacement.owner == "next-integrator"


class HookLeaseTests(unittest.TestCase):
    def test_extract_edited_paths_covers_structured_write_and_patch_operations(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            payload = {
                "tool_name": "apply_patch",
                "tool_input": {
                    "command": (
                        "*** Begin Patch\n"
                        "*** Update File: contracts/openapi/v1.json\n"
                        "*** Delete File: pixi.lock\n"
                        "*** Move to: migrations/0002.sql\n"
                        "*** End Patch"
                    )
                },
            }

            assert extract_edited_paths(payload, root) == [
                "contracts/openapi/v1.json",
                "migrations/0002.sql",
                "pixi.lock",
            ]

    def test_pre_write_blocks_without_lease_and_allows_current_integrator(
        self,
    ) -> None:
        now = datetime(2030, 1, 1, tzinfo=UTC)
        payload = {
            "tool_name": "Write",
            "tool_input": {"file_path": "contracts/openapi/v1.json"},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main"
            _initialize_repository(root)

            blocked = pre_tool_decision(payload, root, "feature", now=now)
            acquire_lease(
                root,
                owner="integrator",
                task="/root/integration",
                ttl=timedelta(minutes=5),
                now=now,
            )
            allowed = pre_tool_decision(payload, root, "feature", now=now)

            assert blocked["decision"] == "block"
            assert "lease" in blocked["reason"].lower()
            assert allowed == {}

    def test_known_bash_writers_cannot_bypass_pre_write_lease(self) -> None:
        commands = (
            "pixi run -e dev python -m tooling.contracts.export_openapi --write",
            "bun run contract:codegen -- --write",
            "bun run --cwd apps/web generate-contracts",
            "bun .agents/skills/ditto-page-contract/scripts/generate.mjs",
            "bun install",
            "pixi update",
            "printf changed > bun.lock",
            "cp fixture.ts apps/web/src/features/shell/page-contracts.generated.ts",
            "mv fixture.ts apps/web/src/routeTree.gen.ts",
            "sed -i.bak 's/a/b/' apps/web/scripts/generate-route-tree.mjs",
            "tee apps/web/scripts/visual-audit.config.generated.mjs",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main"
            _initialize_repository(root)

            for command in commands:
                with self.subTest(command=command):
                    decision = pre_tool_decision(
                        {"tool_name": "Bash", "tool_input": {"command": command}},
                        root,
                        "feature",
                    )
                    assert decision["decision"] == "block"
                    assert "lease" in decision["reason"].lower()
            assert (
                pre_tool_decision(
                    {
                        "tool_name": "Bash",
                        "tool_input": {"command": "pixi run -e dev check-contract"},
                    },
                    root,
                    "feature",
                )
                == {}
            )

    def test_stop_gate_rejects_unleased_protected_diff_before_verifier(self) -> None:
        now = datetime.now(UTC)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main"
            _initialize_repository(root)
            calls = 0

            def verifier(_root: Path, _level: str, _paths: object) -> Never:
                nonlocal calls
                calls += 1
                raise AssertionError("verifier must not run")

            manifest = {
                "schema_version": 2,
                "base_sha": "base",
                "head_sha": "head",
                "git_object_format": "sha1",
                "changes": {
                    "contracts/openapi/v1.json": {
                        "status": {"index": "?", "worktree": "?"},
                        "index": {"state": "absent"},
                        "worktree": {
                            "state": "present",
                            "kind": "file",
                            "mode": "0644",
                            "sha256": "0" * 64,
                        },
                    }
                },
                "configs": {},
                "repository_policy": {"forbidden_package_manager_paths": []},
                "tools": {"project_python": "Python fixture"},
            }

            result = verification_decision(root, manifest, verifier=verifier, now=now)

            assert result["decision"] == "block"
            assert "lease" in result["reason"].lower()
            assert calls == 0

    def test_non_protected_write_needs_no_git_or_lease(self) -> None:
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "tooling/agent_harness/hook.py"},
        }

        assert pre_tool_decision(payload, Path("/not/a/repository"), "feature") == {}

    def test_real_hook_entrypoint_enforces_pre_write_lease(self) -> None:
        payload = {
            "tool_name": "apply_patch",
            "tool_input": {
                "command": (
                    "*** Begin Patch\n"
                    "*** Update File: contracts/openapi/v1.json\n"
                    "*** End Patch"
                )
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "main"
            _initialize_repository(root)

            blocked = subprocess.run(
                (
                    sys.executable,
                    str(PROJECT_ROOT / "tooling/agent_harness/hook.py"),
                    "--host",
                    "codex",
                    "--event",
                    "pre-tool",
                ),
                cwd=root,
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                check=True,
            )
            acquire_lease(
                root,
                owner="integrator",
                task="/root/integration",
            )
            allowed = subprocess.run(
                (
                    sys.executable,
                    str(PROJECT_ROOT / "tooling/agent_harness/hook.py"),
                    "--host",
                    "codex",
                    "--event",
                    "pre-tool",
                ),
                cwd=root,
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                check=True,
            )

        assert json.loads(blocked.stdout)["decision"] == "block"
        assert json.loads(allowed.stdout) == {}


if __name__ == "__main__":
    unittest.main()
