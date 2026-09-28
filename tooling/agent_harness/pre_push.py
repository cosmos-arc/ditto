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
import sys
from pathlib import Path

from tooling.agent_harness.hook import (
    classify_diff,
    needs_full_check_fallback,
    prepare_fast_lane,
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
    resolve_usage: bool = True,
) -> tuple[str, list[list[str]], list[str]]:
    """Identity-check a push and return (level, explicit commands, notes).

    The commands are what the developer owes before requesting review; the
    hook itself only prints them. Raises ValueError on identity violations
    (dirty worktree, target not checked out). Missing history and mode
    anomalies fail closed to the full gate inside the plan — they expand the
    explicit scope instead of silently re-entering the synchronous push path.
    ``resolve_usage=False`` keeps planning side-effect free (no AST usage
    scan): test-usage additions and the fast-lane completeness proof are
    then resolved by the explicit ``--verify`` entry instead.
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
    commands = verification_commands(
        level, paths, root=root, resolve_usage=resolve_usage
    )
    return level, commands, [*notes, *_deferred_scope_note(level, resolve_usage)]


def _deferred_scope_note(level: str, resolve_usage: bool) -> list[str]:
    """Escalation note for scan-free backend plans (hook mode, #340/#317-C)."""
    if resolve_usage or level not in {"backend", "high-risk"}:
        return []
    return [
        "test-usage scan deferred to task verify-push: the plan lists the",
        "static closure only; verify may widen it and an owner without fast",
        "cases escalates to task check there",
    ]


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


def _run_explicit_verification(
    commands: list[list[str]], root: Path, environment: dict[str, str]
) -> int:
    """Execute the owed commands; fail-closed escalation keeps completeness."""
    for command in commands:
        run_command, junit_path, scope_dirs = prepare_fast_lane(command)
        print("verify:", " ".join(run_command), flush=True)
        result = subprocess.run(run_command, cwd=root, env=environment, check=False)
        escalate = needs_full_check_fallback(
            command, result.returncode, junit_path, scope_dirs, root
        )
        if escalate and result.returncode == 0:
            print(
                "verify: fast-lane evidence incomplete "
                + "(a scope owner executed no case); running task check",
                flush=True,
            )
        if junit_path is not None:
            junit_path.unlink(missing_ok=True)
        if escalate:
            fallback = ["task", "check"]
            print("verify:", " ".join(fallback), flush=True)
            subprocess.run(fallback, cwd=root, env=environment, check=True)
            continue
        if result.returncode != 0:
            raise SystemExit(result.returncode)
    return 0


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

    def report(message: str) -> None:
        # pre-commit hides a passing hook's stdout, but Git streams pre-push
        # stderr straight to the developer: the owed-verification plan must
        # stay visible on every successful push.
        print(message, file=sys.stderr, flush=True)

    try:
        level, commands, notes = push_verification_plan(
            root,
            os.environ.get("PRE_COMMIT_FROM_REF", ""),
            os.environ.get("PRE_COMMIT_TO_REF", ""),
            os.environ.get("PRE_COMMIT_LOCAL_BRANCH", ""),
            default_target="HEAD" if args.verify else "",
            resolve_usage=args.verify,
        )
    except (ValueError, subprocess.SubprocessError) as error:
        report(f"pre-push: {error}")
        return 1
    for note in notes:
        report(f"pre-push: {note}")
    if not commands:
        report(
            f"pre-push: identity verified; scope '{level}' owes no local verification"
        )
        return 0
    report(f"pre-push: identity verified; scope '{level}'")
    report("pre-push: explicit verification owed before review:")
    for command in commands:
        report(f"pre-push:    {' '.join(command)}")
    if not args.verify:
        report("pre-push: run `task verify-push` to execute them")
        report("pre-push: PR CI remains the authoritative merge gate")
        return 0

    return _run_explicit_verification(commands, root, _sanitized_environment())


if __name__ == "__main__":
    raise SystemExit(main())
