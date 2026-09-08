"""Exercise committed push ranges against real Git state."""

import subprocess
from pathlib import Path

import pytest

from tooling.agent_harness.pre_push import push_commands


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _commit(root: Path) -> str:
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "fixture")
    return _git(root, "rev-parse", "HEAD")


def test_push_uses_committed_range_and_rejects_unchecked_state(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    source = tmp_path / "apps/web/src/app.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("first\n")
    base = _commit(tmp_path)
    source.write_text("second\n")
    target = _commit(tmp_path)
    assert push_commands(tmp_path, base, target) == [["task", "check-web"]]
    assert push_commands(tmp_path, target, target) == []
    assert push_commands(tmp_path, "", target) == [["task", "check"]]
    assert push_commands(tmp_path, "0" * 40, target) == [["task", "check"]]
    assert push_commands(tmp_path, "missing-history", target) == [["task", "check"]]
    with pytest.raises(ValueError, match="checked out"):
        push_commands(tmp_path, target, base)
    branch = _git(tmp_path, "symbolic-ref", "HEAD")
    assert push_commands(tmp_path, "", "", branch) == [["task", "check"]]
    with pytest.raises(ValueError, match="checked out"):
        push_commands(tmp_path, "", "")
    source.write_text("uncommitted\n")
    with pytest.raises(ValueError, match="clean worktree"):
        push_commands(tmp_path, base, target)
    _commit(tmp_path)
    source.chmod(0o755)
    target = _commit(tmp_path)
    assert push_commands(tmp_path, base, target) == [["task", "check"]]
    source.unlink()
    deleted = _commit(tmp_path)
    assert push_commands(tmp_path, target, deleted) == [["task", "check"]]
