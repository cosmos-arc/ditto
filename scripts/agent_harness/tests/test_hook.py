from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.agent_harness.hook import (
    VerificationResult,
    changed_paths,
    classify_diff,
    extract_python_paths,
    policy_violation,
    receipt_path,
    stop_decision,
    verification_commands,
)


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
        )
        for command in fixtures:
            with self.subTest(command=command):
                assert policy_violation(command, "feature") is None


class DiffClassificationTests(unittest.TestCase):
    def test_five_diff_classes(self) -> None:
        fixtures = {
            "docs": ["docs/architecture/overview.md"],
            "tests": ["packages/data/tests/test_query.py"],
            "source": ["packages/data/src/ditto_data/query.py"],
            "dependency": ["pyproject.toml"],
            "harness": ["AGENTS.md", ".agents/skills/ditto-test-first/SKILL.md"],
        }
        expected = {
            "docs": "docs",
            "tests": "tests",
            "source": "source",
            "dependency": "source",
            "harness": "harness",
        }
        for name, paths in fixtures.items():
            with self.subTest(name=name):
                assert classify_diff(paths) == expected[name]

    def test_test_only_commands_are_scoped_and_read_only(self) -> None:
        path = "packages/data/tests/test_query.py"
        commands = verification_commands("tests", [path])
        flattened = [" ".join(command) for command in commands]
        assert any("ruff format --check" in command for command in flattened)
        assert any("ruff check" in command for command in flattened)
        assert any("type --tests" in command for command in flattened)
        assert any(path in command for command in flattened)

    def test_changed_test_fixture_runs_owning_package_tests(self) -> None:
        commands = verification_commands(
            "tests", ["packages/data/tests/fixtures/market_snapshot.json"]
        )
        expected = (
            "pixi run -e dev pytest -q --import-mode=importlib packages/data/tests"
        )
        assert expected in [" ".join(command) for command in commands]


class StopGateTests(unittest.TestCase):
    def test_first_failure_blocks_and_second_failure_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def fail(_root: Path, _level: str, _paths: object) -> VerificationResult:
                return VerificationResult(False, "expected fixture failure")

            first = stop_decision({}, root, ["AGENTS.md"], "failure", fail)
            second = stop_decision(
                {"stop_hook_active": True}, root, ["AGENTS.md"], "failure", fail
            )

            assert first["decision"] == "block"
            assert "expected fixture failure" in first["reason"]
            assert "decision" not in second
            assert "must report this failure" in second["systemMessage"]

    def test_success_writes_receipt_and_skips_identical_diff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = 0

            def succeed(_root: Path, _level: str, _paths: object) -> VerificationResult:
                nonlocal calls
                calls += 1
                return VerificationResult(True, "ok")

            first = stop_decision({}, root, ["AGENTS.md"], "same-diff", succeed)
            second = stop_decision({}, root, ["AGENTS.md"], "same-diff", succeed)

            assert first == {}
            assert second == {}
            assert calls == 1
            assert receipt_path(root, "same-diff").is_file()

    def test_no_tracked_diff_passes_without_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = stop_decision({}, root, [], "empty")
            assert result == {}
            assert not receipt_path(root, "empty").exists()


if __name__ == "__main__":
    unittest.main()
