"""Verify the committed push range, rather than an unrelated pending worktree diff."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tooling.agent_harness.hook import classify_diff, verification_commands


def push_commands(
    root: Path, base: str, target: str, local_branch: str = ""
) -> list[list[str]]:
    """Select a clean checked-out push range; missing history requires full checks."""

    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    if git("status", "--porcelain"):
        raise ValueError(
            "pre-push requires a clean worktree; commit or stash pending changes"
        )
    if not target and not base and local_branch:
        target = local_branch
    if not target or git("rev-parse", target) != git("rev-parse", "HEAD"):
        raise ValueError("pre-push requires the pushed commit to be checked out")
    if not base or not base.strip("0"):
        return [["task", "check"]]
    try:
        raw = git("diff", "--raw", "-z", "--no-renames", base, target).split("\0")
    except subprocess.CalledProcessError:
        return [["task", "check"]]
    paths: list[str] = []
    for index in range(0, len(raw) - 1, 2):
        header, path = raw[index : index + 2]
        if any(
            mode.lstrip(":") not in {"100644", "000000"} for mode in header.split()[:2]
        ):
            return [["task", "check"]]
        paths.append(path)
    return verification_commands(classify_diff(paths, root=root), paths, root=root)


def main() -> int:
    """Run the selected local checks without issuing remote verification receipts."""
    root = Path.cwd()
    commands = push_commands(
        root,
        os.environ.get("PRE_COMMIT_FROM_REF", ""),
        os.environ.get("PRE_COMMIT_TO_REF", ""),
        os.environ.get("PRE_COMMIT_LOCAL_BRANCH", ""),
    )
    environment = {
        **os.environ,
        "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
    }
    for command in commands:
        print("pre-push:", " ".join(command), flush=True)
        subprocess.run(command, cwd=root, env=environment, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
