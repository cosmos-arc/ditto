"""Verify push identity and report the explicit verification owed for the range.

The synchronous push path carries identity and scope checks only (#340):
pytest, full type checks, PIT and system tests run through the explicit
``--verify`` entry (``task verify-push``) before requesting review, and the
PR CI remains the authoritative merge gate.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from tooling.agent_harness.hook import (
    _PYTEST_NO_TESTS_COLLECTED,
    classify_diff,
    verification_commands,
)

_FULL_CHECK = [["task", "check"]]


def _scan_push_paths(raw: list[str]) -> tuple[list[str], str | None]:
    """Parse ``diff --raw -z`` records; return (paths, mode-anomaly path)."""
    paths: list[str] = []
    for index in range(0, len(raw) - 1, 2):
        header, path = raw[index : index + 2]
        if any(
            mode.lstrip(":") not in {"100644", "000000"} for mode in header.split()[:2]
        ):
            return [], path
        paths.append(path)
    return paths, None


def push_verification_plan(
    root: Path,
    base: str,
    target: str,
    local_branch: str = "",
    *,
    default_target: str = "",
) -> tuple[str, list[list[str]], list[str]]:
    """Identity-check a push and return (level, explicit commands, notes).

    The commands are what the developer owes before requesting review; the
    hook itself only prints them. Raises ValueError on identity violations
    (dirty worktree, target not checked out). Missing history and mode
    anomalies fail closed to the full gate inside the plan — they expand the
    explicit scope instead of silently re-entering the synchronous push path.
    """

    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    if git("status", "--porcelain"):
        raise ValueError(
            "pre-push requires a clean worktree; commit or stash pending changes"
        )
    if not target and not base and local_branch:
        target = local_branch
    if not target and default_target:
        target = default_target
    if not target or git("rev-parse", target) != git("rev-parse", "HEAD"):
        raise ValueError("pre-push requires the pushed commit to be checked out")
    notes: list[str] = []
    if not base or not base.strip("0"):
        # New branch: no remote ref yet, so diff against the fork point with
        # the remote default branch instead of degrading to the full gate.
        try:
            base = git("merge-base", target, "origin/main")
        except subprocess.CalledProcessError:
            notes.append("no remote default branch to fork from; full gate required")
            return "missing-history", [*_FULL_CHECK], notes
    try:
        raw = git("diff", "--raw", "-z", "--no-renames", base, target).split("\0")
    except subprocess.CalledProcessError:
        notes.append("push range not derivable from history; full gate required")
        return "missing-history", [*_FULL_CHECK], notes
    paths, anomaly = _scan_push_paths(raw)
    if anomaly is not None:
        notes.append(f"non-plain file mode on {anomaly}; full gate required")
        return "mode-anomaly", [*_FULL_CHECK], notes
    level = classify_diff(paths, root=root)
    return level, verification_commands(level, paths, root=root), notes


def _sanitized_environment() -> dict[str, str]:
    # Git exports repository selectors to hooks; the check subprocesses must
    # not inherit them. Tests create foreign repositories.
    environment = {
        **os.environ,
        "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
    }
    for name in subprocess.check_output(
        ["git", "rev-parse", "--local-env-vars"], cwd=Path.cwd(), text=True
    ).splitlines():
        environment.pop(name, None)
    return environment


def main(argv: list[str] | None = None) -> int:
    """Print the identity-checked plan; ``--verify`` additionally runs it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="run the planned checks explicitly (pre-review verification)",
    )
    args = parser.parse_args(argv)
    root = Path.cwd()
    try:
        level, commands, notes = push_verification_plan(
            root,
            os.environ.get("PRE_COMMIT_FROM_REF", ""),
            os.environ.get("PRE_COMMIT_TO_REF", ""),
            os.environ.get("PRE_COMMIT_LOCAL_BRANCH", ""),
            default_target="HEAD" if args.verify else "",
        )
    except (ValueError, subprocess.SubprocessError) as error:
        print(f"pre-push: {error}")
        return 1
    for note in notes:
        print(f"pre-push: {note}")
    if not commands:
        print(
            f"pre-push: identity verified; scope '{level}' owes no local verification"
        )
        return 0
    print(f"pre-push: identity verified; scope '{level}'")
    print("pre-push: explicit verification owed before review:")
    for command in commands:
        print("pre-push:   ", " ".join(command))
    if not args.verify:
        print("pre-push: run `task verify-push` to execute them")
        print("pre-push: PR CI remains the authoritative merge gate")
        return 0

    environment = _sanitized_environment()
    for command in commands:
        print("verify:", " ".join(command), flush=True)
        result = subprocess.run(command, cwd=root, env=environment, check=False)
        if result.returncode == _PYTEST_NO_TESTS_COLLECTED and command[:2] == [
            "task",
            "test",
        ]:
            # fast 车道无可选用例（pytest exit 5）：fail-closed 升级全量检查
            fallback = ["task", "check"]
            print("verify:", " ".join(fallback), flush=True)
            subprocess.run(fallback, cwd=root, env=environment, check=True)
            continue
        if result.returncode != 0:
            raise SystemExit(result.returncode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
