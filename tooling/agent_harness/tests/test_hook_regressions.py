"""Host protocol regressions observed during the hooks audit."""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from tooling.agent_harness import hook
from tooling.agent_harness.lease import (
    LeaseError,
    acquire_lease,
    git_lease_paths,
    release_lease,
)


def git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=root, check=True, capture_output=True)


def test_shell_context_regressions_from_independent_review(tmp_path: Path) -> None:
    root, other = tmp_path / "main", tmp_path / "other"
    repository(root)
    git(root, "worktree", "add", "-b", "feature", str(other))

    def bash(command: str) -> dict[str, object]:
        return invoke(root, {"tool_name": "Bash", "tool_input": {"command": command}})

    assert bash("cat <<-'EOF'\n\tdata\n\tEOF\ngit reset --hard")["decision"] == "block"
    assert bash(f"cd {other} | cat; printf x > uv.lock")["decision"] == "block"
    acquire_lease(other, owner="fixture", task="review-regression")
    try:
        assert bash(f"bun run --cwd {other} generate-contracts") == {}
        assert bash(f"bun --cwd {root} run generate-contracts")["decision"] == "block"
    finally:
        release_lease(other)
    acquire_lease(root, owner="fixture", task="review-regression")
    try:
        assert bash(f"bun --cwd {other} run generate-contracts")["decision"] == "block"
        assert bash(f"bun run --cwd {root} generate-contracts") == {}
    finally:
        release_lease(root)


def repository(root: Path) -> None:
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "config", "user.name", "Test")
    git(root, "commit", "--allow-empty", "-m", "fixture")


def invoke(root: Path, payload: object, event: str = "pre-tool") -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, hook.__file__, "--event", event],
        cwd=root,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    return json.loads(result.stdout)


def test_target_worktree_owns_authorization(tmp_path: Path) -> None:
    root, other = tmp_path / "main", tmp_path / "other"
    repository(root)
    git(root, "worktree", "add", "-b", "feature", str(other))
    payload = {
        "cwd": str(root),
        "tool_name": "Write",
        "tool_input": {"file_path": str(other / "uv.lock")},
    }
    assert invoke(root, payload)["decision"] == "block"
    acquire_lease(other, owner="fixture", task="hooks-regression")
    try:
        assert invoke(root, payload) == {}
        payload["tool_input"] = {"file_path": str(root / "uv.lock")}
        assert invoke(root, payload)["decision"] == "block"
        for command, denied in (
            (f"git -C {other} commit -m fixture", False),
            (f"git -C {root} commit -m fixture", True),
            ("git push origin +HEAD:refs/heads/feature", True),
            ("git push origin HEAD:main", True),
        ):
            response = invoke(
                root,
                {
                    "cwd": str(other),
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                },
            )
            assert (response.get("decision") == "block") is denied
    finally:
        release_lease(other)


def test_external_prose_and_quoted_heredoc_are_not_protected_writes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    repository(root)
    assert (
        invoke(
            root,
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(tmp_path / "log.txt")},
            },
        )
        == {}
    )
    assert (
        invoke(
            root,
            {
                "tool_name": "Bash",
                "tool_input": {"command": "cat <<'EOF'\ngit reset --hard\nEOF\n"},
            },
        )
        == {}
    )
    response = invoke(
        root,
        {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "uv.lock")}},
    )
    assert response["decision"] == "block"


def test_ruff_formats_only_successful_edit_at_effective_directory(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    repository(root)
    child = root / "sub"
    child.mkdir()
    original = "value= [1,2]\n"
    (root / "same.py").write_text(original)
    target = child / "same.py"
    target.write_text(original)
    runtime = root / ".venv" / ("Scripts/ruff.exe" if os.name == "nt" else "bin/ruff")
    runtime.parent.mkdir(parents=True)
    shutil.copyfile(Path(sys.executable).parent / runtime.name, runtime)
    runtime.chmod(0o755)
    payload = {
        "cwd": str(root),
        "tool_name": "Edit",
        "tool_input": {"workdir": str(child), "file_path": "same.py"},
    }
    assert invoke(root, {**payload, "is_error": True}, "post-tool") == {}
    assert target.read_text() == original
    assert invoke(root, payload, "post-tool") == {}
    assert target.read_text() == "value = [1, 2]\n"
    assert (root / "same.py").read_text() == original


@pytest.mark.skipif(os.name != "posix", reason="POSIX executable boundary probe")
def test_verification_children_receive_isolated_keyring(tmp_path: Path) -> None:
    target = tmp_path / "tests/test_environment.py"
    target.parent.mkdir()
    target.write_text("# fixture\n")
    executable = tmp_path / "bin"
    executable.mkdir()
    for name in ("task", "uv"):
        script = executable / name
        script.write_text(
            f"#!{sys.executable}\nimport os, subprocess, sys\n"
            "assert os.environ['PYTHON_KEYRING_BACKEND'] == "
            "'keyring.backends.null.Keyring'\n"
            "subprocess.run([sys.executable, '-c', "
            "\"import keyring; assert keyring.get_password('fixture', "
            "'fixture') is None\"], check=True)\n"
        )
        script.chmod(0o755)
    with patch.dict(
        os.environ, {"PATH": f"{executable}{os.pathsep}{os.environ['PATH']}"}
    ):
        result = hook.run_verification(
            tmp_path, "backend-tests", ["tests/test_environment.py"]
        )
    assert result.ok, result.summary


@pytest.mark.skipif(os.name != "posix", reason="POSIX lock holder probe")
def test_lease_guard_survives_old_timestamp_and_releases_after_crash(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    repository(root)
    guard = git_lease_paths(root).guard_path
    guard.parent.mkdir(parents=True)
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl,sys,time; "
            "f=open(sys.argv[1], 'a+b'); fcntl.flock(f, fcntl.LOCK_EX); "
            "print('ready',flush=True); time.sleep(30)",
            str(guard),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "ready"
        os.utime(guard, (0, 0))
        with pytest.raises(LeaseError, match="timed out"):
            acquire_lease(root, owner="fixture", task="hooks-regression")
    finally:
        holder.kill()
        holder.wait(timeout=2)
    acquire_lease(root, owner="fixture", task="hooks-regression")
    release_lease(root)


@pytest.mark.skipif(os.name != "posix", reason="POSIX cancellation probe")
def test_host_cancellation_stops_formatter_descendants(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    repository(root)
    (root / "sample.py").write_text("value=1\n")
    executable = root / ".venv/bin/ruff"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        f"#!{sys.executable}\nimport subprocess,sys,time\n"
        "from pathlib import Path\n"
        "subprocess.Popen([sys.executable, '-c', "
        '"import time; from pathlib import Path; time.sleep(1); '
        "Path('late-write').touch()\"])\n"
        "Path('ready').touch()\ntime.sleep(30)\n"
    )
    executable.chmod(0o755)
    process = subprocess.Popen(
        [sys.executable, hook.__file__, "--event", "post-tool"],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdin is not None
        process.stdin.write(
            json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "sample.py"}})
        )
        process.stdin.close()
        deadline = time.monotonic() + 3
        while not (root / "ready").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert (root / "ready").exists()
        process.terminate()
        assert process.wait(timeout=2) == 0
        assert process.stdout is not None
        assert "cancelled" in json.loads(process.stdout.read())["systemMessage"]
        time.sleep(1.1)
        assert not (root / "late-write").exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
