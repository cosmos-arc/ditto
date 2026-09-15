"""Exercise committed push ranges against real Git state."""

import subprocess
import sys
from pathlib import Path

import pytest

from tooling.agent_harness import pre_push
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


def test_verifier_cannot_inherit_push_repository_into_foreign_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(tmp_path, "init", "--quiet")
    git_dir = tmp_path / ".git"
    before = (git_dir / "config").read_bytes()
    foreign = tmp_path / "foreign.git"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_DIR", str(git_dir))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path))
    monkeypatch.setenv("GIT_INDEX_FILE", str(git_dir / "index"))
    monkeypatch.setenv("HOOK_SMOKE_KEEP", "yes")
    script = (
        "import os, subprocess; "
        "assert os.environ['HOOK_SMOKE_KEEP'] == 'yes'; "
        "subprocess.run(['git', 'init', '--bare', '--quiet', "
        f"{str(foreign)!r}], check=True)"
    )
    monkeypatch.setattr(
        pre_push, "push_commands", lambda *args: [[sys.executable, "-c", script]]
    )
    assert pre_push.main() == 0
    assert (git_dir / "config").read_bytes() == before
    assert (foreign / "HEAD").is_file()
