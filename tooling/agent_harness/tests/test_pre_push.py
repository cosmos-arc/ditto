"""Exercise push identity checks and verification plans on real Git state."""

import subprocess
import sys
from pathlib import Path

import pytest

from tooling.agent_harness import pre_push
from tooling.agent_harness.pre_push import push_verification_plan


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _commit(root: Path) -> str:
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "fixture")
    return _git(root, "rev-parse", "HEAD")


def test_plan_uses_committed_range_and_rejects_unchecked_state(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    source = tmp_path / "apps/web/src/app.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("first\n")
    base = _commit(tmp_path)
    source.write_text("second\n")
    target = _commit(tmp_path)
    assert push_verification_plan(tmp_path, base, target) == (
        "web",
        [["task", "check-web"]],
        [],
    )
    assert push_verification_plan(tmp_path, target, target) == ("none", [], [])
    for missing, note in (
        ("", "no remote default branch to fork from; full gate required"),
        ("0" * 40, "no remote default branch to fork from; full gate required"),
        (
            "missing-history",
            "push range not derivable from history; full gate required",
        ),
    ):
        _, commands, notes = push_verification_plan(tmp_path, missing, target)
        assert commands == [["task", "check"]]
        assert notes == [note]
    with pytest.raises(ValueError, match="checked out"):
        push_verification_plan(tmp_path, target, base)
    branch = _git(tmp_path, "symbolic-ref", "HEAD")
    assert push_verification_plan(tmp_path, "", "", branch)[1] == [["task", "check"]]
    with pytest.raises(ValueError, match="checked out"):
        push_verification_plan(tmp_path, "", "")
    source.write_text("uncommitted\n")
    with pytest.raises(ValueError, match="clean worktree"):
        push_verification_plan(tmp_path, base, target)
    _commit(tmp_path)
    source.chmod(0o755)
    target = _commit(tmp_path)
    assert push_verification_plan(tmp_path, base, target) == (
        "mode-anomaly",
        [["task", "check"]],
        ["non-plain file mode on apps/web/src/app.tsx; full gate required"],
    )
    source.unlink()
    deleted = _commit(tmp_path)
    assert push_verification_plan(tmp_path, target, deleted)[1] == [["task", "check"]]


def test_new_branch_plan_scopes_via_merge_base_with_remote_default(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    source = tmp_path / "apps/web/src/app.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("first\n")
    base = _commit(tmp_path)
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", base)
    source.write_text("second\n")
    target = _commit(tmp_path)
    for base_ref in ("", "0" * 40):
        assert push_verification_plan(tmp_path, base_ref, target) == (
            "web",
            [["task", "check-web"]],
            [],
        )


def test_hook_mode_reports_without_running_checks(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        pre_push,
        "push_verification_plan",
        lambda *args, **kwargs: ("web", [["task", "check-web"]], ["note"]),
    )

    def _fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("hook mode must not run verification commands")

    monkeypatch.setattr(pre_push.subprocess, "run", _fail)
    assert pre_push.main([]) == 0
    output = capsys.readouterr().err
    assert "task check-web" in output
    assert "task verify-push" in output
    assert "PR CI remains the authoritative merge gate" in output
    assert "note" in output


def test_verify_mode_runs_the_plan_and_propagates_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pre_push,
        "push_verification_plan",
        lambda *args, **kwargs: (
            "backend",
            [[sys.executable, "-c", "import sys; sys.exit(3)"]],
            [],
        ),
    )
    monkeypatch.setattr(
        pre_push, "_sanitized_environment", lambda: {"PATH": "/usr/bin:/bin"}
    )
    with pytest.raises(SystemExit) as raised:
        pre_push.main(["--verify"])
    assert raised.value.code == 3


def test_identity_failure_reports_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _fail(
        *args: object, **kwargs: object
    ) -> tuple[str, list[list[str]], list[str]]:
        raise ValueError("pre-push requires a clean worktree; commit or stash")

    monkeypatch.setattr(pre_push, "push_verification_plan", _fail)
    assert pre_push.main([]) == 1
    assert "clean worktree" in capsys.readouterr().err


def test_verify_mode_defaults_target_to_head(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    source = tmp_path / "apps/web/src/app.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("first\n")
    _commit(tmp_path)
    # No PRE_COMMIT_* context: --verify must still resolve HEAD and fall back
    # to the remote default branch fork point instead of rejecting the run.
    assert push_verification_plan(tmp_path, "", "", "", default_target="HEAD") == (
        "missing-history",
        [["task", "check"]],
        ["no remote default branch to fork from; full gate required"],
    )
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    source.write_text("second\n")
    _commit(tmp_path)
    assert push_verification_plan(tmp_path, "", "", "", default_target="HEAD") == (
        "web",
        [["task", "check-web"]],
        [],
    )


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
        pre_push,
        "push_verification_plan",
        lambda *args, **kwargs: ("backend", [[sys.executable, "-c", script]], []),
    )
    assert pre_push.main(["--verify"]) == 0
    assert (git_dir / "config").read_bytes() == before
    assert (foreign / "HEAD").is_file()
