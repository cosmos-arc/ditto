#!/usr/bin/env python3
"""Shared repository hook policy for Claude Code and Codex."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

CACHE_DIR = Path(".cache/ditto-agent-harness")
MAX_FEEDBACK = 6_000
PACKAGE_TEST_PARTS = 3

try:
    from datetime import UTC as _UTC
except ImportError:  # Python 3.9/3.10 host fallback; project runtime is 3.13.
    from datetime import timezone

    _UTC = timezone.utc  # noqa: UP017 - compatibility with host Python 3.9/3.10.


@dataclass(frozen=True)
class VerificationResult:
    """Result of a changed-scope verification run."""

    ok: bool
    summary: str


def git_root(start: Path | None = None) -> Path:
    """Resolve the repository root from any session subdirectory."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip()).resolve()


def current_branch(root: Path) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def command_from_payload(payload: dict[str, Any]) -> str:
    """Extract a shell or patch command from either host's hook input."""
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        command = tool_input.get("command")
        if isinstance(command, str):
            return command
    command = payload.get("command")
    return command if isinstance(command, str) else ""


def _tokenized_segments(command: str) -> list[list[str]]:
    segments: list[list[str]] = []
    for segment in re.split(r"(?:&&|\|\||;|\n)", command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            tokens = segment.split()
        if tokens:
            segments.append(tokens)
    return segments


def _executable_index(tokens: Sequence[str], name: str) -> int | None:
    return next(
        (index for index, token in enumerate(tokens) if Path(token).name == name),
        None,
    )


def _git_invocation(tokens: Sequence[str]) -> tuple[str, list[str]] | None:
    git_index = _executable_index(tokens, "git")
    if git_index is None:
        return None
    arguments = list(tokens[git_index + 1 :])
    index = 0
    while index < len(arguments) and arguments[index].startswith("-"):
        option = arguments[index]
        index += 2 if option in {"-C", "-c", "--git-dir", "--work-tree"} else 1
    subcommand = arguments[index] if index < len(arguments) else ""
    return subcommand, arguments[index + 1 :]


def _git_violation(tokens: Sequence[str], branch: str) -> str | None:
    invocation = _git_invocation(tokens)
    if invocation is None:
        return None
    subcommand, arguments = invocation
    force = any(
        argument.startswith("--force")
        or (
            argument.startswith("-")
            and not argument.startswith("--")
            and "f" in argument[1:]
        )
        for argument in arguments
    )
    if subcommand == "push" and force:
        return "force push is blocked; publish a normal branch update"
    if subcommand == "reset" and "--hard" in arguments:
        return "git reset --hard is blocked because it can discard work"
    if subcommand in {"commit", "push"} and "--no-verify" in arguments:
        return "--no-verify is blocked; fix or report the failing gate"
    if branch == "main" and subcommand in {"commit", "push"}:
        return "commit and push are blocked on main; create a feature branch"
    return None


def _is_dangerous_rm(tokens: Sequence[str]) -> bool:
    rm_index = _executable_index(tokens, "rm")
    if rm_index is None:
        return False
    flags: set[str] = set()
    for option in tokens[rm_index + 1 :]:
        if option == "--" or not option.startswith("-"):
            break
        if option == "--recursive":
            flags.add("r")
        elif option == "--force":
            flags.add("f")
        elif not option.startswith("--"):
            flags.update(option.lstrip("-"))
    return {"r", "f"}.issubset(flags)


def policy_violation(command: str, branch: str) -> str | None:
    """Return a narrow, evidence-based command policy violation."""
    compact = " ".join(command.split())
    if not compact:
        return None

    for tokens in _tokenized_segments(command):
        if violation := _git_violation(tokens, branch):
            return violation
        if _is_dangerous_rm(tokens):
            return (
                "recursive forced deletion is blocked; "
                "use an exact recoverable operation"
            )

    package_mutations = (
        r"\b(?:python(?:3)?\s+-m\s+)?pip\s+(?:install|uninstall)\b",
        r"\bpoetry\s+(?:add|remove|install|update)\b",
        r"\b(?:conda|mamba)\s+(?:install|create|remove|update)\b",
    )
    if any(re.search(pattern, compact) for pattern in package_mutations):
        return (
            "direct environment mutation is blocked; use the repository Pixi workflow"
        )
    return None


def _normalize_python_path(raw: str, root: Path) -> Path | None:
    path = Path(raw)
    candidate = path if path.is_absolute() else root / path
    try:
        candidate = candidate.resolve()
        candidate.relative_to(root)
    except (OSError, ValueError):
        return None
    return candidate if candidate.suffix == ".py" else None


def extract_python_paths(payload: dict[str, Any], root: Path) -> list[Path]:
    """Extract edited Python files from Claude Edit/Write or Codex apply_patch."""
    raw_paths: list[str] = []
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("file_path", "path"):
            value = tool_input.get(key)
            if isinstance(value, str):
                raw_paths.append(value)
        command = tool_input.get("command")
        if isinstance(command, str):
            raw_paths.extend(
                match.group(1).strip()
                for match in re.finditer(
                    r"^\*\*\* (?:(?:Add|Update) File|Move to):\s*(.+)$",
                    command,
                    re.MULTILINE,
                )
            )

    for key in ("file_path", "path"):
        value = payload.get(key)
        if isinstance(value, str):
            raw_paths.append(value)

    paths = {
        normalized
        for raw in raw_paths
        if (normalized := _normalize_python_path(raw, root)) is not None
    }
    return sorted(paths)


def post_edit(payload: dict[str, Any], root: Path) -> VerificationResult:
    """Apply file-scoped Ruff fixes only when edited paths are unambiguous."""
    paths = [path for path in extract_python_paths(payload, root) if path.exists()]
    if not paths:
        return VerificationResult(
            True, "No reliably parsed Python file; Stop gate will verify the diff."
        )

    relative = [path.relative_to(root).as_posix() for path in paths]
    commands = [
        ["pixi", "run", "-e", "dev", "ruff", "check", "--fix", *relative],
        ["pixi", "run", "-e", "dev", "ruff", "format", *relative],
    ]
    output: list[str] = []
    for command in commands:
        result = subprocess.run(
            command, cwd=root, capture_output=True, text=True, check=False
        )
        output.append(f"$ {' '.join(command)}\n{result.stdout}{result.stderr}".strip())
        if result.returncode != 0:
            return VerificationResult(False, "\n\n".join(output)[-MAX_FEEDBACK:])
    return VerificationResult(True, "\n\n".join(output)[-MAX_FEEDBACK:])


def _git_nul_paths(root: Path, arguments: Sequence[str]) -> set[str]:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.decode(errors="replace").strip()
            or f"unable to run git {' '.join(arguments)}"
        )
    return {
        os.fsdecode(raw)
        for raw in result.stdout.split(b"\0")
        if raw
    }


def changed_paths(root: Path) -> list[str]:
    """Return every staged, unstaged, deleted, renamed, or untracked path."""
    tracked = _git_nul_paths(
        root,
        (
            "diff",
            "--name-only",
            "-z",
            "--no-renames",
            "--diff-filter=ACDMRT",
            "HEAD",
            "--",
        ),
    )
    untracked = _git_nul_paths(
        root, ("ls-files", "--others", "--exclude-standard", "-z", "--")
    )
    return sorted(tracked | untracked)


_FINGERPRINT_CONFIGS = (
    ".importlinter",
    ".pre-commit-config.yaml",
    "biome.json",
    "bun.lock",
    "bunfig.toml",
    "package.json",
    "pixi.lock",
    "pixi.toml",
    "pyproject.toml",
    "apps/web/package.json",
    "apps/web/tsconfig.json",
    "apps/web/tsconfig.app.json",
    "apps/web/tsconfig.node.json",
    "apps/web/vitest.config.ts",
)


def _git_text(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def _file_fingerprint(path: Path) -> dict[str, object]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {"state": "deleted"}
    if path.is_symlink():
        content = os.fsencode(os.readlink(path))
        kind = "symlink"
    elif path.is_file():
        content = path.read_bytes()
        kind = "file"
    else:
        content = b""
        kind = "other"
    return {
        "state": "present",
        "kind": kind,
        "mode": f"{metadata.st_mode & 0o7777:04o}",
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _tool_versions(root: Path) -> dict[str, str]:
    commands = {
        "bun": ("bun", "--version"),
        "git": ("git", "--version"),
        "pixi": ("pixi", "--version"),
        "python": (sys.executable, "--version"),
    }
    versions: dict[str, str] = {}
    for name, command in commands.items():
        try:
            result = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            versions[name] = "unavailable"
            continue
        output = (result.stdout or result.stderr).strip()
        versions[name] = output if result.returncode == 0 and output else "unavailable"
    return versions


def change_manifest(root: Path, paths: Sequence[str] | None = None) -> dict[str, object]:
    """Build the canonical evidence hashed by a verification receipt."""
    selected = sorted(paths if paths is not None else changed_paths(root))
    head = _git_text(root, "rev-parse", "HEAD")
    upstream_base = _git_text(root, "merge-base", "HEAD", "origin/main")
    base = head if upstream_base == "unavailable" else upstream_base
    return {
        "schema_version": 1,
        "base_sha": base,
        "head_sha": head,
        "changes": {
            relative: _file_fingerprint(root / relative) for relative in selected
        },
        "configs": {
            relative: _file_fingerprint(root / relative)
            for relative in _FINGERPRINT_CONFIGS
        },
        "tools": _tool_versions(root),
    }


def diff_digest(root: Path) -> str:
    manifest = change_manifest(root)
    encoded = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8", errors="surrogateescape")
    return hashlib.sha256(encoded).hexdigest()


def _is_harness(path: str) -> bool:
    return (
        path in {"AGENTS.md", "CLAUDE.md", "pixi.toml", ".pre-commit-config.yaml"}
        or bool(re.fullmatch(r"packages/[^/]+/(?:AGENTS|CLAUDE)\.md", path))
        or path.startswith(
            (".agents/", ".claude/", ".codex/", "scripts/agent_harness/")
        )
        or path == "docs/engineering/agent-harness.md"
    )


def _is_test(path: str) -> bool:
    return (
        "/tests/" in path
        or path.startswith("tests/")
        or Path(path).name.startswith("test_")
    )


def classify_diff(paths: Sequence[str]) -> str:
    """Map a tracked diff to none, docs, tests, harness, or source."""
    if not paths:
        return "none"
    if all(
        path.endswith((".md", ".rst", ".txt")) and not _is_harness(path)
        for path in paths
    ):
        return "docs"

    source_or_config = any(
        (
            path.endswith(".py")
            and not _is_test(path)
            and not path.startswith("scripts/agent_harness/")
        )
        or path in {"pyproject.toml", "pixi.lock", ".importlinter"}
        or (
            path.startswith(("config/", "packages/"))
            and not _is_test(path)
            and not path.endswith(("AGENTS.md", "CLAUDE.md", "README.md"))
        )
        or path.startswith(".github/workflows/")
        for path in paths
    )
    if source_or_config:
        return "source"
    if all(
        _is_test(path) or path.endswith((".md", ".rst", ".txt")) for path in paths
    ) and any(_is_test(path) for path in paths):
        return "tests"
    if any(_is_harness(path) for path in paths):
        return "harness"
    return "source"


def verification_commands(level: str, paths: Sequence[str]) -> list[list[str]]:
    """Build non-destructive validation commands for a diff level."""
    if level in {"none", "docs"}:
        return []
    if level == "harness":
        return [["pixi", "run", "-e", "dev", "harness-check"]]
    if level == "source":
        return [["pixi", "run", "-e", "dev", "check"]]

    test_files = [path for path in paths if _is_test(path) and path.endswith(".py")]
    test_targets = set(test_files)
    for path in paths:
        parts = Path(path).parts
        if _is_test(path) and not path.endswith(".py"):
            if (
                len(parts) >= PACKAGE_TEST_PARTS
                and parts[0] == "packages"
                and parts[2] == "tests"
            ):
                test_targets.add(f"packages/{parts[1]}/tests")
            elif parts and parts[0] == "tests":
                test_targets.add("tests")
    commands: list[list[str]] = []
    if test_files:
        commands.extend(
            [
                ["pixi", "run", "-e", "dev", "ruff", "format", "--check", *test_files],
                ["pixi", "run", "-e", "dev", "ruff", "check", *test_files],
            ]
        )
    commands.append(["pixi", "run", "-e", "dev", "type", "--tests"])
    if test_targets:
        commands.append(
            [
                "pixi",
                "run",
                "-e",
                "dev",
                "pytest",
                "-q",
                "--import-mode=importlib",
                *sorted(test_targets),
            ]
        )
    return commands


def run_verification(
    root: Path, level: str, paths: Sequence[str]
) -> VerificationResult:
    commands = verification_commands(level, paths)
    if not commands:
        return VerificationResult(True, f"{level}: no Python verification required")

    transcripts: list[str] = []
    for command in commands:
        result = subprocess.run(
            command, cwd=root, capture_output=True, text=True, check=False
        )
        transcript = f"$ {' '.join(command)}\n{result.stdout}{result.stderr}".strip()
        transcripts.append(transcript)
        if result.returncode != 0:
            return VerificationResult(False, "\n\n".join(transcripts)[-MAX_FEEDBACK:])
    return VerificationResult(True, "\n\n".join(transcripts)[-MAX_FEEDBACK:])


def receipt_path(root: Path, digest: str) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        raw_git_dir = Path(result.stdout.strip())
        git_dir = raw_git_dir if raw_git_dir.is_absolute() else root / raw_git_dir
        return git_dir.resolve() / "ditto-agent-harness" / "receipts" / f"{digest}.json"
    return root / CACHE_DIR / f"{digest}.json"


def stop_decision(
    payload: dict[str, Any],
    root: Path,
    paths: Sequence[str],
    digest: str,
    verifier: Callable[
        [Path, str, Sequence[str]], VerificationResult
    ] = run_verification,
) -> dict[str, Any]:
    """Verify once per exact diff and return a host-compatible Stop result."""
    if not paths:
        return {}
    cached = receipt_path(root, digest)
    if cached.is_file():
        return {}

    level = classify_diff(paths)
    result = verifier(root, level, paths)
    if result.ok:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(
            json.dumps(
                {
                    "digest": digest,
                    "level": level,
                    "paths": list(paths),
                    "evidence": change_manifest(root, paths),
                    "verified_at": datetime.now(_UTC).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return {}

    reason = (
        f"Changed-scope verification ({level}) failed. Fix it and retry.\n\n"
        f"{result.summary}"
    )
    if payload.get("stop_hook_active") is True:
        return {
            "systemMessage": (
                "Verification still fails after the Stop retry. You may finish, "
                "but the final "
                f"response must report this failure explicitly.\n\n{result.summary}"
            )[-MAX_FEEDBACK:]
        }
    return {"decision": "block", "reason": reason[-MAX_FEEDBACK:]}


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--event",
        required=True,
        choices=("pre-tool", "post-tool", "stop", "check-changed"),
    )
    parser.add_argument("--host", choices=("claude", "codex"), default="codex")
    args = parser.parse_args()

    root = git_root(Path.cwd())
    payload: dict[str, Any] = {}
    if args.event != "check-changed":
        try:
            loaded = json.load(sys.stdin)
            payload = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError as error:
            emit({"systemMessage": f"Ditto hook received invalid JSON: {error}"})
            return 1

    if args.event == "pre-tool":
        violation = policy_violation(
            command_from_payload(payload), current_branch(root)
        )
        emit({"decision": "block", "reason": violation} if violation else {})
        return 0

    if args.event == "post-tool":
        result = post_edit(payload, root)
        if result.ok:
            emit({})
        else:
            emit(
                {
                    "decision": "block",
                    "reason": f"File-scoped Ruff failed:\n{result.summary}",
                }
            )
        return 0

    paths = changed_paths(root)
    digest = diff_digest(root) if paths else hashlib.sha256(b"").hexdigest()
    if args.event == "check-changed":
        level = classify_diff(paths)
        result = run_verification(root, level, paths)
        print(result.summary)
        return 0 if result.ok else 1

    emit(stop_decision(payload, root, paths, digest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
