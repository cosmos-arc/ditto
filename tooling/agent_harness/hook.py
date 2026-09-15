#!/usr/bin/env python3
"""Shared repository hook policy for Codex and ZCode."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Any

try:
    from .lease import authorize_paths, generator_write_targets, protected_resources
    from .repository_policy import forbidden_package_manager_paths
except ImportError:  # Direct script execution.
    from lease import authorize_paths, generator_write_targets, protected_resources
    from repository_policy import forbidden_package_manager_paths

MAX_FEEDBACK = 6_000
MAX_HOOK_INPUT = 1_048_576
PACKAGE_TEST_PARTS = 3
APPEND_REDIRECT_PREFIX_LENGTH = len(">>")
FORMAT_TIMEOUT_SECONDS = 5
GIT_TIMEOUT_SECONDS = 0.5


@dataclass(frozen=True)
class VerificationResult:
    """Result of a changed-scope verification run."""

    ok: bool
    summary: str


def changed_paths(root: Path) -> list[str]:
    """Return every staged, unstaged, deleted, renamed, or untracked path."""
    result = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=all",
            "--no-renames",
            "--",
        ],
        cwd=root,
        timeout=GIT_TIMEOUT_SECONDS,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.decode(errors="replace").strip()
            or "unable to capture git status"
        )
    paths: list[str] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        if len(raw) < len(b"XY path") or raw[2:3] != b" ":
            raise RuntimeError("git status returned an unsupported record")
        paths.append(os.fsdecode(raw[3:]))
    return sorted(paths)


def git_root(start: Path | None = None) -> Path:
    """Resolve the repository root from any session subdirectory."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        timeout=GIT_TIMEOUT_SECONDS,
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip()).resolve()


def current_branch(root: Path) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=root,
        timeout=GIT_TIMEOUT_SECONDS,
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


class _ShellWord(str):
    """Retain whether a redirection was syntax or quoted data."""

    redirect: bool = False


_SHELL_WORDS = re.compile(
    r"""(?:[^\s;&|<>"'\\]|\\.|"(?:[^"\\]|\\.)*"|'[^']*')+|&&|\|\||<<-?|>>?|[<;&|\n]"""
)


def _shell_source(command: str) -> str:
    """Quoted heredoc bodies are data, not shell invocations."""
    source: list[str] = []
    delimiter: str | None = None
    for line in command.splitlines(keepends=True):
        if delimiter is not None:
            if line.rstrip("\r\n") == delimiter:
                delimiter = None
            continue
        source.append(line)
        words = _SHELL_WORDS.findall(line)
        for index, word in enumerate(words):
            if word not in {"<<", "<<-"}:
                continue
            if index + 1 >= len(words) or words[index + 1][0] not in {"'", '"'}:
                raise ValueError(
                    "Use a quoted heredoc delimiter for reliable hook analysis"
                )
            delimiter = shlex.split(words[index + 1])[0]
    return "".join(source)


def _tokenized_segments(command: str) -> list[list[str]]:
    # Only recognize explicit invocations. Expansions are not evaluated.
    source = _shell_source(command)
    shlex.split(source)  # Reject malformed quoting instead of silently dropping it.
    words = _SHELL_WORDS.findall(source)
    segments: list[list[str]] = []
    tokens: list[str] = []
    for word in words:
        if word in {"&&", "||", ";", "&", "|", "\n"}:
            if tokens:
                segments.append(tokens)
                tokens = []
        else:
            for value in shlex.split(word):
                token = _ShellWord(value)
                token.redirect = word.startswith(">")
                tokens.append(token)
    if tokens:
        segments.append(tokens)
    return segments


def _executable_index(tokens: Sequence[str], name: str) -> int | None:
    index = 0
    while index < len(tokens) and re.fullmatch(
        r"[A-Za-z_][A-Za-z_0-9]*=.*", tokens[index]
    ):
        index += 1
    if index < len(tokens) and tokens[index] in {"env", "command"}:
        index += 1
        while index < len(tokens) and (
            tokens[index].startswith("-") or "=" in tokens[index]
        ):
            index += 1
    return index if index < len(tokens) and Path(tokens[index]).name == name else None


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
    if subcommand == "push" and (
        force
        or "--mirror" in arguments
        or any(arg.startswith("+") for arg in arguments)
    ):
        return "force push is blocked; publish a normal branch update"
    if subcommand == "reset" and "--hard" in arguments:
        return "git reset --hard is blocked because it can discard work"
    if subcommand in {"commit", "push"} and "--no-verify" in arguments:
        return "--no-verify is blocked; fix or report the failing gate"
    if (branch == "main" and subcommand in {"commit", "push"}) or (
        subcommand == "push"
        and any(arg.split(":")[-1] in {"main", "refs/heads/main"} for arg in arguments)
    ):
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


def _javascript_package_violation(tokens: Sequence[str]) -> bool:
    if not tokens:
        return False
    index = 0
    executable = Path(tokens[index]).name
    if executable in {"command", "env"}:
        index += 1
        while index < len(tokens) and (
            tokens[index].startswith("-") or "=" in tokens[index]
        ):
            index += 1
        if index >= len(tokens):
            return False
        executable = Path(tokens[index]).name
    arguments = tokens[index + 1 :]
    if executable in {"npx", "pnpx"}:
        return True
    if executable == "corepack" and arguments:
        executable, arguments = Path(arguments[0]).name, arguments[1:]
    if executable not in {"npm", "pnpm", "yarn"}:
        return False
    mutation_commands = {
        "add",
        "ci",
        "dlx",
        "exec",
        "install",
        "remove",
        "rm",
        "uninstall",
        "update",
        "upgrade",
    }
    subcommand = next(
        (argument for argument in arguments if not argument.startswith("-")), ""
    )
    return subcommand in mutation_commands


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
        if _javascript_package_violation(tokens):
            return "non-Bun package execution is blocked; use the root Bun workspace"

    package_mutations = (
        r"\bpixi\s+(?:add|install|lock|remove|run|update|upgrade)\b",
        r"\b(?:python(?:3)?\s+-m\s+)?pip\s+(?:install|uninstall)\b",
        r"\bpoetry\s+(?:add|remove|install|update)\b",
        r"\b(?:conda|mamba)\s+(?:install|create|remove|update)\b",
    )
    if any(
        re.match(pattern, " ".join(tokens))
        for tokens in _tokenized_segments(command)
        for pattern in package_mutations
    ):
        return (
            "direct environment mutation is blocked; "
            "use the repository uv bootstrap workflow"
        )
    return None


def effective_cwd(payload: dict[str, Any], fallback: Path) -> Path:
    """Resolve tool overrides against the host session directory."""
    session = payload.get("cwd", str(fallback))
    if not isinstance(session, str) or not session:
        raise ValueError("hook cwd must be a nonempty path")
    directory = (fallback / session).resolve()
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        override = tool_input.get("workdir", tool_input.get("cwd"))
        if override is not None:
            if not isinstance(override, str) or not override:
                raise ValueError("tool cwd must be a nonempty path")
            directory = (directory / override).resolve()
    return directory


def _normalize_repository_path(raw: str, root: Path) -> str | None:
    path = Path(raw)
    candidate = path if path.is_absolute() else root / path
    try:
        candidate = candidate.resolve()
        relative = candidate.relative_to(root.resolve())
    except ValueError:
        return candidate.as_posix()
    except OSError:
        return None
    return relative.as_posix()


def _redirection_targets(tokens: Sequence[str]) -> tuple[str, ...]:
    targets: list[str] = []
    for index, token in enumerate(tokens):
        if isinstance(token, _ShellWord) and not token.redirect:
            continue
        if token in {">", ">>"} and index + 1 < len(tokens):
            targets.append(tokens[index + 1])
        elif token.startswith(">>") and len(token) > APPEND_REDIRECT_PREFIX_LENGTH:
            targets.append(token[APPEND_REDIRECT_PREFIX_LENGTH:])
        elif token.startswith(">") and len(token) > 1:
            targets.append(token[1:])
    return tuple(targets)


def _command_after_executable(tokens: Sequence[str], executable: str) -> str:
    index = _executable_index(tokens, executable)
    if index is None:
        return ""
    return next(
        (value for value in tokens[index + 1 :] if not value.startswith("-")),
        "",
    )


def _generator_arguments(tokens: Sequence[str]) -> list[str]:
    """Locate the script/module/task position, never a matching data argument."""
    executables = ("bun", "node", "python", "python3", "uv", "bash", "sh", "task")
    index = next(
        (
            value
            for name in executables
            if (value := _executable_index(tokens, name)) is not None
        ),
        None,
    )
    if index is None:
        return []
    executable = Path(tokens[index]).name
    arguments = list(tokens[index + 1 :])
    if executable == "uv":
        if not arguments or arguments.pop(0) != "run":
            return []
        while arguments and arguments[0].startswith("-"):
            arguments.pop(0)
        return _generator_arguments(arguments)
    if arguments and arguments[0] == "run" and executable == "bun":
        arguments.pop(0)
    while arguments and arguments[0].startswith("-"):
        option = arguments.pop(0)
        if option in {"-c", "--eval", "-e", "--print", "-p"}:
            return []
        if option in {"--cwd", "--directory"} and arguments:
            arguments.pop(0)
    return arguments


def _codegen_write_targets(tokens: Sequence[str]) -> tuple[str, ...]:
    arguments = _generator_arguments(tokens)
    if not arguments:
        return ()
    if arguments[0].endswith("/gen-api.sh") and "--write" in arguments:
        return (
            "apps/web/src/api/generated/operation-contracts.ts",
            "apps/web/src/api/generated/schema.d.ts",
        )
    return generator_write_targets(arguments)


def _direct_write_targets(tokens: Sequence[str], root: Path) -> tuple[str, ...]:
    candidates: list[str] = []
    for executable in ("cp", "install", "mv"):
        index = _executable_index(tokens, executable)
        if index is not None:
            operands = [
                argument
                for argument in tokens[index + 1 :]
                if not argument.startswith("-")
            ]
            if operands:
                candidates.append(operands[-1])
    tee_index = _executable_index(tokens, "tee")
    if tee_index is not None:
        candidates.extend(
            token for token in tokens[tee_index + 1 :] if not token.startswith("-")
        )
    sed_index = _executable_index(tokens, "sed")
    if sed_index is not None and any(
        argument == "--in-place" or argument.startswith("-i")
        for argument in tokens[sed_index + 1 :]
    ):
        candidates.extend(tokens[sed_index + 1 :])

    targets: set[str] = set()
    for candidate in candidates:
        normalized = _normalize_repository_path(candidate, root)
        if normalized is not None:
            targets.add(normalized)
    return tuple(sorted(targets))


def _mutates_bun_lock(tokens: Sequence[str]) -> bool:
    token_set = set(tokens)
    return _command_after_executable(tokens, "bun") in {
        "add",
        "install",
        "remove",
        "update",
    } and not ({"--frozen-lockfile", "--no-save"} & token_set)


def _known_command_write_targets(tokens: Sequence[str], root: Path) -> tuple[str, ...]:
    targets: set[str] = set()
    for raw in _redirection_targets(tokens):
        normalized = _normalize_repository_path(raw, root)
        if normalized is not None:
            targets.add(normalized)
    targets.update(_codegen_write_targets(tokens))
    targets.update(_direct_write_targets(tokens, root))
    if _mutates_bun_lock(tokens):
        targets.add("bun.lock")
    uv_command = _command_after_executable(tokens, "uv")
    if uv_command in {"add", "remove", "lock", "sync", "run"}:
        options = tokens[tokens.index(uv_command) + 1 :]
        if uv_command == "run":
            # Application arguments must never exempt uv's implicit lock write.
            end = next(
                (
                    i
                    for i, value in enumerate(options)
                    if not value.startswith("-") or value == "--"
                ),
                len(options),
            )
            options = options[:end]
        readonly = {"--locked", "--frozen"}
        if uv_command == "run":
            readonly.add("--no-sync")
        if uv_command == "lock":
            readonly.add("--check")
        if not readonly.intersection(options):
            targets.add("uv.lock")
    return tuple(sorted(targets))


def shell_commands(payload: dict[str, Any], root: Path) -> list[tuple[list[str], Path]]:
    """Recognize explicit directory changes; retain each invocation's directory."""
    directory = effective_cwd(payload, root)
    commands: list[tuple[list[str], Path]] = []
    for tokens in _tokenized_segments(command_from_payload(payload)):
        if tokens[0] == "cd":
            if len(tokens) != len(("cd", "directory")):
                raise ValueError("Use cd with one explicit directory")
            directory = (directory / tokens[1]).resolve()
        else:
            commands.append((tokens, directory))
    return commands


def _git_directory(tokens: Sequence[str], directory: Path) -> Path:
    git_index = _executable_index(tokens, "git")
    if git_index is None:
        return directory
    index = git_index + 1
    while index < len(tokens) and tokens[index].startswith("-"):
        option = tokens[index]
        if option == "-C":
            if index + 1 >= len(tokens):
                raise ValueError("git -C needs a directory")
            directory = (directory / tokens[index + 1]).resolve()
        elif option.startswith("-C"):
            directory = (directory / option[len("-C") :]).resolve()
        elif option.startswith(("--git-dir", "--work-tree")):
            raise ValueError("Use git -C with an explicit worktree")
        index += 2 if option in {"-C", "-c"} else 1
    return directory


def _bash_write_paths(payload: dict[str, Any], root: Path) -> list[str]:
    paths: list[str] = []
    for tokens, directory in shell_commands(payload, root):
        targets = _known_command_write_targets(tokens, directory)
        if not targets:
            continue
        command_root = git_root(directory)
        generated = set(_codegen_write_targets(tokens))
        generated.update(
            target for target in targets if target in {"uv.lock", "bun.lock"}
        )
        paths.extend(
            str((command_root if target in generated else directory) / target)
            for target in targets
        )
    return paths


def extract_edited_paths(payload: dict[str, Any], root: Path) -> list[str]:
    """Extract repository-relative paths from structured write tool payloads."""
    raw_paths: list[str] = []
    directory = effective_cwd(payload, root)
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
                    r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to):\s*(.+)$",
                    command,
                    re.MULTILINE,
                )
            )
            if payload.get("tool_name") == "Bash":
                raw_paths.extend(_bash_write_paths(payload, root))

    for key in ("file_path", "path"):
        value = payload.get(key)
        if isinstance(value, str):
            raw_paths.append(value)

    return sorted(
        {
            normalized
            for raw in raw_paths
            if (normalized := _normalize_repository_path(str(directory / raw), root))
            is not None
        }
    )


def extract_python_paths(payload: dict[str, Any], root: Path) -> list[Path]:
    """Extract edited Python files from host Edit/Write or Codex apply_patch."""
    return [
        root / path
        for path in extract_edited_paths(payload, root)
        if Path(path).suffix == ".py"
    ]


def _group_targets(paths: Sequence[str], root: Path) -> dict[Path, list[str]]:
    root = root.resolve()
    grouped: dict[Path, list[str]] = {}
    for raw in paths:
        target = (root / raw).resolve()
        target_root = root
        if not target.is_relative_to(root):
            parent = target.parent
            while not parent.exists() and parent != parent.parent:
                parent = parent.parent
            try:
                target_root = git_root(parent)
            except (OSError, subprocess.SubprocessError):
                if any(
                    protected_resources((Path(*target.parts[index:]).as_posix(),))
                    for index in range(len(target.parts))
                ):
                    raise ValueError(
                        f"Cannot resolve protected target worktree: {target}"
                    ) from None
                target_root = parent
        grouped.setdefault(target_root, []).append(
            target.relative_to(target_root).as_posix()
        )
    return grouped


def pre_tool_decision(
    payload: dict[str, Any],
    root: Path,
    branch: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Apply command policy and protected-path lease policy before a tool runs."""
    if payload.get("tool_name") == "Bash":
        for tokens, directory in shell_commands(payload, root):
            command_directory = _git_directory(tokens, directory)
            command_branch = branch
            if command_directory != root and _git_invocation(tokens) is not None:
                command_branch = current_branch(command_directory)
            if violation := policy_violation(shlex.join(tokens), command_branch):
                return {
                    "decision": "block",
                    "reason": f"Bash cwd {command_directory}: {violation}",
                }
    grouped = _group_targets(extract_edited_paths(payload, root), root)
    for target_root, paths in grouped.items():
        decision = authorize_paths(target_root, paths, now=now)
        if not decision.allowed:
            return {
                "decision": "block",
                "reason": f"Target worktree {target_root}: {decision.reason}",
            }
    return {}


def _terminate_formatter(process: subprocess.Popen[str]) -> None:
    """Reap this formatter and its POSIX descendants before returning to the host."""
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=0.5,
                check=False,
            )
            process.terminate()
        process.communicate(timeout=0.5)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.communicate()
    except ProcessLookupError:
        process.communicate()


def post_edit(payload: dict[str, Any], root: Path) -> VerificationResult:
    """Format exact edited files without installing or solving an environment."""
    paths = [path for path in extract_python_paths(payload, root) if path.is_file()]
    if not paths:
        return VerificationResult(
            True, "No reliably parsed Python file; automatic formatting skipped."
        )

    if payload.get("is_error") is True or (
        isinstance(payload.get("tool_response"), dict)
        and payload["tool_response"].get("is_error") is True
    ):
        return VerificationResult(True, "Failed edit; formatting skipped.")
    try:
        grouped = _group_targets([str(path) for path in paths], root)
    except ValueError as error:
        return VerificationResult(False, str(error))
    for target_root, relative in grouped.items():
        result = _format_repository(target_root, relative)
        if not result.ok:
            return result
    return VerificationResult(True, "Formatting completed.")


def _format_repository(root: Path, relative: Sequence[str]) -> VerificationResult:
    ruff = root / ".venv" / ("Scripts/ruff.exe" if os.name == "nt" else "bin/ruff")
    command = [str(ruff), "format", "--", *relative]
    with tempfile.TemporaryFile(mode="w+t") as transcript:
        try:
            process = subprocess.Popen(
                command,
                cwd=root,
                stdout=transcript,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=True,
            )
        except OSError as error:
            return VerificationResult(
                False, f"Automatic formatting unavailable: {error}"
            )
        try:
            process.wait(timeout=FORMAT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            _terminate_formatter(process)
            return VerificationResult(
                False, "Formatting exceeded time budget; run task fmt explicitly."
            )
        except BaseException:
            _terminate_formatter(process)
            raise
        transcript.seek(0)
        output = transcript.read(MAX_FEEDBACK)
    return VerificationResult(process.returncode == 0, output)


def _is_harness(path: str) -> bool:
    return (
        path in {"AGENTS.md", "Taskfile.yml", ".pre-commit-config.yaml"}
        or bool(
            re.fullmatch(
                r"(?:packages/[^/]+|apps/(?:backend|web)|contracts)/AGENTS\.md",
                path,
            )
        )
        or path.startswith((".agents/", ".codex/", ".zcode/", "tooling/agent_harness/"))
        or path == "docs/engineering/agent-harness.md"
    )


def _is_test(path: str) -> bool:
    return (
        "/tests/" in path
        or path.startswith("tests/")
        or Path(path).name.startswith("test_")
    )


_ROOT_GATE_PATHS = {
    ".gitattributes",
    ".importlinter",
    ".pre-commit-config.yaml",
    "bun.lock",
    "bunfig.toml",
    "package.json",
    "Taskfile.yml",
    ".node-version",
    ".python-version",
    ".task-version",
    "uv.lock",
    "pyproject.toml",
}
_HIGH_RISK_PREFIXES = tuple(
    f"packages/{name}/"
    for name in (
        "backtest",
        "data",
        "execution",
        "features",
        "portfolio",
        "risk",
        "strategy",
    )
)
_HIGH_RISK_APPLICATION_PREFIXES = (
    "packages/application/src/ditto_application/builders/",
    "packages/application/src/ditto_application/processes/",
    "packages/application/src/ditto_application/queries/",
)
_HIGH_RISK_APPLICATION_PATHS = frozenset(
    f"packages/application/src/ditto_application/commands/{name}.py"
    for name in (
        "account",
        "account_ledger",
        "backtest",
        "candidate_selection",
        "experiments",
        "ingestion",
        "paper_account",
        "paper_session",
        "strategy",
        "strategy_governance",
        "trade",
        "universe",
    )
)
_HIGH_RISK_BACKEND_PREFIXES = (
    "apps/backend/src/ditto_apps/api/routes/account_ledger",
    "apps/backend/src/ditto_apps/api/routes/backtest",
    "apps/backend/src/ditto_apps/api/routes/paper",
    "apps/backend/src/ditto_apps/api/routes/portfolio_",
    "apps/backend/src/ditto_apps/api/routes/strategy",
    "apps/backend/src/ditto_apps/api/routes/trade",
    "apps/backend/src/ditto_apps/models/account_ledger",
    "apps/backend/src/ditto_apps/models/backtest",
    "apps/backend/src/ditto_apps/models/paper",
    "apps/backend/src/ditto_apps/models/portfolio_",
    "apps/backend/src/ditto_apps/models/strategy",
    "apps/backend/src/ditto_apps/models/trade",
)
_HIGH_RISK_BACKEND_PATHS = frozenset(
    {
        "apps/backend/src/ditto_apps/jobs/flows/backtest.py",
        "apps/backend/src/ditto_apps/jobs/flows/materialization.py",
        "apps/backend/src/ditto_apps/jobs/paper_eod.py",
    }
)
_CONTRACT_PROVIDER_PATHS = {
    ".redocly.yaml",
    "apps/backend/src/ditto_apps/main.py",
    "apps/backend/src/ditto_apps/middleware.py",
    "apps/backend/src/ditto_apps/openapi_contract.py",
}
_CONTRACT_PREFIXES = (
    "contracts/",
    "tooling/contracts/",
    "apps/backend/src/ditto_apps/api/",
    "apps/backend/src/ditto_apps/models/",
    "apps/web/src/api/",
    "apps/web/scripts/gen-api",
)
_BACKEND_TEST_PREFIX = ("apps", "backend", "tests")


def _path_classes(paths: Sequence[str], *, root: Path | None = None) -> set[str]:
    classes = {category for path in paths for category in _path_categories(path)}
    prose = [
        path
        for path in paths
        if path.endswith((".md", ".rst"))
        or _path_categories(path) in ({"docs"}, {"skills"})
    ]
    if root is not None and prose:
        # Executable/symlink prose is an execution change, including deletions
        # and staged mode changes whose old form only survives in HEAD/index.
        for path in prose:
            candidate = root / path
            if candidate.is_symlink() or (
                candidate.is_file() and candidate.stat().st_mode & 0o111
            ):
                classes.add("root")
        for args in (("ls-files", "--stage", "-z"), ("ls-tree", "-rz", "HEAD")):
            result = subprocess.run(
                ["git", *args, "--", *prose],
                cwd=root,
                timeout=GIT_TIMEOUT_SECONDS,
                capture_output=True,
                check=False,
            )
            if result.returncode:
                classes.add("unknown")
            elif any(
                record and not record.startswith(b"100644 ")
                for record in result.stdout.split(b"\0")
            ):
                classes.add("root")
    return classes


def _is_high_risk_path(path: str) -> bool:
    return (
        path in _HIGH_RISK_APPLICATION_PATHS
        or path in _HIGH_RISK_BACKEND_PATHS
        or path.startswith(
            (
                *_HIGH_RISK_PREFIXES,
                *_HIGH_RISK_APPLICATION_PREFIXES,
                *_HIGH_RISK_BACKEND_PREFIXES,
            )
        )
    )


def _is_web_input(path: str) -> bool:
    return (
        path.startswith(
            (
                "apps/web/design/specs/",
                "apps/web/contracts/pages/",
                "apps/web/prototype/",
            )
        )
        or path == "apps/web/contracts/prototype-chart-interactions.md"
    )


def _prototype_commands(paths: Sequence[str]) -> list[list[str]]:
    return [["task", "web-prototype"]] if any(map(_is_web_input, paths)) else []


def _material_category(path: str) -> str | None:
    """Classify authored materials before generic source-code path rules."""
    if path.startswith(".agents/skills/") and path.endswith(
        (".md", ".rst", ".yaml", ".yml", ".toml", ".json", ".txt")
    ):
        return "skills"
    if _is_web_input(path):
        return "web"
    if path.startswith("apps/backend/tests/fixtures/contracts/"):
        return "backend-tests"
    if path != "apps/web/DESIGN.md" and (
        path.endswith((".md", ".rst"))
        or (path.startswith("docs/") and path.endswith(".txt"))
    ):
        return "docs"
    return None


def _path_categories(path: str) -> set[str]:
    if path in _ROOT_GATE_PATHS or path.startswith(".github/"):
        return {"root"}
    if category := _material_category(path):
        return {category}
    if _is_harness(path):
        return {"harness"}

    categories: set[str] = set()
    if path in _CONTRACT_PROVIDER_PATHS or path.startswith(_CONTRACT_PREFIXES):
        categories.add("contract")
    if _is_high_risk_path(path):
        categories.add("backend-tests" if _is_test(path) else "high-risk")
    elif not categories and path.startswith(
        ("packages/", "apps/backend/", "config/", "scripts/")
    ):
        categories.add("backend-tests" if _is_test(path) else "backend")
    elif not categories and path.startswith("apps/web/"):
        categories.add("web")
    elif (
        not categories
        and path.startswith(("docs/", "deploy/"))
        and path.endswith((".md", ".rst", ".txt"))
    ):
        categories.add("docs")
    return categories or {"unknown"}


def _collapse_diff_classes(classes: set[str]) -> str:
    non_docs = classes - {"docs"}
    exact_level = {
        frozenset(): "docs",
        frozenset({"harness"}): "harness",
        frozenset({"contract", "high-risk"}): "contract-high-risk",
    }.get(frozenset(non_docs))
    if exact_level is not None:
        level = exact_level
    elif "unknown" in non_docs:
        level = "unknown"
    elif "root" in non_docs or (
        bool(non_docs & {"harness", "skills"}) and len(non_docs) > 1
    ):
        level = "root"
    elif "web" in non_docs and non_docs != {"web"}:
        level = "cross-stack"
    elif non_docs <= {"contract", "backend", "backend-tests"} and (
        "contract" in non_docs
    ):
        level = "contract"
    elif non_docs <= {"high-risk", "backend", "backend-tests"} and (
        "high-risk" in non_docs
    ):
        level = "high-risk"
    elif non_docs <= {"backend", "backend-tests"}:
        level = "backend" if "backend" in non_docs else "backend-tests"
    elif len(non_docs) == 1:
        level = next(iter(non_docs))
    else:
        level = "cross-stack"
    return level


def classify_diff(paths: Sequence[str], *, root: Path | None = None) -> str:
    """Map the full changed set to a fail-closed monorepo verification class."""
    if not paths:
        return "none"
    return _collapse_diff_classes(_path_classes(paths, root=root))


def _test_owner(path: str) -> str | None:
    parts = Path(path).parts
    if (
        len(parts) >= PACKAGE_TEST_PARTS
        and parts[0] == "packages"
        and parts[2] == "tests"
    ):
        return f"packages/{parts[1]}/tests"
    if (
        len(parts) >= len(_BACKEND_TEST_PREFIX)
        and parts[: len(_BACKEND_TEST_PREFIX)] == _BACKEND_TEST_PREFIX
    ):
        return "apps/backend/tests"
    if parts and parts[0] == "tests":
        return "tests"
    return None


def _backend_test_commands(
    paths: Sequence[str], *, root: Path | None = None
) -> list[list[str]]:
    workspace = root if root is not None else git_root(Path.cwd())
    test_files = [path for path in paths if _is_test(path) and path.endswith(".py")]
    existing_test_files = [path for path in test_files if (workspace / path).is_file()]
    test_targets = set(test_files)
    test_targets.intersection_update(existing_test_files)
    for path in paths:
        if (
            _is_test(path)
            and (not path.endswith(".py") or path not in existing_test_files)
            and (owner := _test_owner(path))
        ):
            test_targets.add(owner)
    commands: list[list[str]] = []
    if existing_test_files:
        commands.extend(
            [
                [
                    "uv",
                    "run",
                    "--no-sync",
                    "ruff",
                    "format",
                    "--check",
                    *existing_test_files,
                ],
                [
                    "uv",
                    "run",
                    "--no-sync",
                    "ruff",
                    "check",
                    *existing_test_files,
                ],
            ]
        )
    commands.append(["task", "type", "--", "--tests"])
    if test_targets:
        commands.append(
            [
                "uv",
                "run",
                "--no-sync",
                "pytest",
                "-q",
                "--import-mode=importlib",
                *sorted(test_targets),
            ]
        )
    return commands


def _backend_source_commands(
    paths: Sequence[str], *, high_risk: bool
) -> list[list[str]]:
    owners = {
        "/".join(path.split("/")[:2])
        for path in paths
        if path.endswith(".py") and path.startswith(("packages/", "apps/backend/"))
    }
    if high_risk or len(owners) != 1:
        return [["task", "check"]]
    owner = next(iter(owners))
    return [
        ["task", "lint"],
        ["task", "fmt-check"],
        ["task", "type-all"],
        ["task", "test", "--", "--fast", f"{owner}/tests"],
    ]


def verification_commands(
    level: str, paths: Sequence[str], *, root: Path | None = None
) -> list[list[str]]:
    """Build a monotonic, non-destructive validation plan for all path classes."""
    if paths:
        classes = _path_classes(paths, root=root)
    elif level == "contract-high-risk":
        classes = {"contract", "high-risk"}
    else:
        classes = {level}
    active_classes = classes - {"docs"}
    if active_classes <= {"none", "skills"}:
        return {
            frozenset({"skills"}): [["task", "harness-validate"]],
        }.get(frozenset(active_classes), [])

    backend_classes = {"backend", "backend-tests", "high-risk"}
    crosses_stacks = "web" in active_classes and bool(active_classes & backend_classes)
    needs_system = (
        "contract" in active_classes or crosses_stacks or level == "cross-stack"
    )
    needs_full_check = (
        bool(active_classes & {"contract", "harness", "root", "unknown", "skills"})
        or needs_system
    )

    commands: list[list[str]] = []
    if needs_full_check:
        commands.append(["task", "check"])
    elif "web" in active_classes:
        commands.append(["task", "check-web"])
    elif active_classes & {"backend", "high-risk"}:
        commands.extend(
            _backend_source_commands(paths, high_risk="high-risk" in active_classes)
        )

    if needs_system:
        commands.append(["task", "test-system"])
    if "high-risk" in active_classes:
        commands.append(["task", "pit"])
    commands.extend(_prototype_commands(paths))
    if needs_full_check or active_classes != {"backend-tests"}:
        return commands
    return _backend_test_commands(paths, root=root)


def run_verification(
    root: Path, level: str, paths: Sequence[str]
) -> VerificationResult:
    commands = verification_commands(level, paths, root=root)
    if not commands:
        return VerificationResult(True, f"{level}: no Python verification required")

    transcripts: list[str] = []
    for command in commands:
        print(f"$ {shlex.join(command)}", flush=True)
        result = subprocess.run(
            command,
            cwd=root,
            check=False,
            env={
                **os.environ,
                "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
                "_TYPER_FORCE_DISABLE_TERMINAL": "1",
            },
        )
        transcript = f"$ {shlex.join(command)}\nexit code: {result.returncode}"
        transcripts.append(transcript)
        if result.returncode != 0:
            return VerificationResult(False, "\n\n".join(transcripts)[-MAX_FEEDBACK:])
    return VerificationResult(True, "\n\n".join(transcripts)[-MAX_FEEDBACK:])


def verification_decision(
    root: Path,
    paths: Sequence[str],
    verifier: Callable[
        [Path, str, Sequence[str]], VerificationResult
    ] = run_verification,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Block policy violations, enforce the lease, then run the scope ladder."""
    violations = forbidden_package_manager_paths(root)
    if violations:
        reason = (
            "Bun-only repository policy failed; remove forbidden package-manager "
            f"files: {', '.join(violations)}"
        )
        return {"decision": "block", "reason": reason[-MAX_FEEDBACK:]}
    if not paths:
        return {}
    lease_decision = authorize_paths(root, paths, now=now)
    if not lease_decision.allowed:
        return {
            "decision": "block",
            "reason": lease_decision.reason[-MAX_FEEDBACK:],
        }
    level = classify_diff(paths, root=root)
    result = verifier(root, level, paths)
    if result.ok:
        return {}
    reason = (
        f"Changed-scope verification ({level}) failed. Fix it and retry.\n\n"
        f"{result.summary}"
    )
    return {"decision": "block", "reason": reason[-MAX_FEEDBACK:]}


def emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False))


def _capture_failure(error: Exception) -> int:
    print(f"Harness change capture failed closed: {error}"[-MAX_FEEDBACK:])
    return 1


def _run_check_changed(root: Path, paths: Sequence[str]) -> int:
    response = verification_decision(root, paths, verifier=run_verification)
    if response.get("decision") == "block":
        print(response["reason"])
        return 1
    print(
        "Changed-scope verification passed; no pending changes."
        if not paths
        else "Changed-scope verification passed."
    )
    return 0


def stop_feedback(payload: dict[str, Any], root: Path) -> dict[str, Any]:
    """Keep conversation completion independent of project tooling and CI."""
    if payload.get("stop_hook_active") is True:
        return {}
    try:
        paths = changed_paths(root)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        return {
            "systemMessage": f"Unable to inspect pending changes: {error}"[
                -MAX_FEEDBACK:
            ]
        }
    if not paths:
        return {}
    return {
        "systemMessage": (
            f"Worktree has {len(paths)} pending paths "
            f"({classify_diff(paths, root=root)}); "
            "these may predate this task. Stop does not run or certify quality gates. "
            "For code changes, run task check-changed explicitly "
            "and report actual results."
        )
    }


def _emit_pre_tool(payload: dict[str, Any], root: Path) -> None:
    try:
        tool = payload.get("tool_name")
        if tool not in {"Bash", "Edit", "Write", "apply_patch"}:
            raise ValueError("missing or unsupported tool_name")
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            raise ValueError("tool_input must be an object")
        if tool == "Bash" and not command_from_payload(payload):
            raise ValueError("Bash command is missing")
        if tool in {"Edit", "Write", "apply_patch"} and not extract_edited_paths(
            payload, root
        ):
            raise ValueError("write target is missing; provide an explicit path")
        emit(pre_tool_decision(payload, root, current_branch(root)))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        emit(
            {
                "decision": "block",
                "reason": f"PreToolUse could not establish authorization: {error}",
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--event",
        required=True,
        choices=("pre-tool", "post-tool", "stop", "check-changed"),
    )
    parser.add_argument("--host", choices=("codex", "zcode"), default="codex")
    args = parser.parse_args()

    if args.event == "check-changed":
        return _run_event(args.event)
    previous = signal.signal(signal.SIGTERM, _cancel_hook)
    previous_alarm = None
    previous_timer = None
    if os.name == "posix":
        previous_alarm = signal.signal(signal.SIGALRM, _cancel_hook)
        previous_timer = signal.setitimer(
            signal.ITIMER_REAL, 2.5 if args.event == "stop" else 8
        )
    try:
        return _run_event(args.event)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        message = f"{args.event} hook did not complete: {error}"
        emit(
            {"decision": "block", "reason": message}
            if args.event == "pre-tool"
            else {"systemMessage": message}
        )
        return 0
    finally:
        signal.signal(signal.SIGTERM, previous)
        if previous_alarm is not None and previous_timer is not None:
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)
            signal.signal(signal.SIGALRM, previous_alarm)


def _cancel_hook(_signal: int, _frame: FrameType | None) -> None:
    raise TimeoutError("hook cancelled or event deadline exceeded")


def _run_event(event: str) -> int:
    try:
        payload: dict[str, Any] = {}
        if event != "check-changed":
            raw = sys.stdin.read(MAX_HOOK_INPUT + 1)
            if len(raw) > MAX_HOOK_INPUT:
                raise ValueError("hook input exceeds 1 MiB")
            loaded = json.loads(raw)
            if not isinstance(loaded, dict):
                raise ValueError("hook payload must be an object")
            payload = loaded
        root = git_root(effective_cwd(payload, Path.cwd()))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        message = f"Cannot establish hook input/worktree: {error}"
        emit(
            {"decision": "block", "reason": message}
            if event == "pre-tool"
            else {"systemMessage": message}
        )
        return 1 if event == "check-changed" else 0

    if event == "pre-tool":
        _emit_pre_tool(payload, root)
        return 0

    if event == "post-tool":
        result = post_edit(payload, root)
        if result.ok:
            emit({})
        else:
            emit(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": (
                            f"Automatic formatting did not complete:\n{result.summary}"
                        ),
                    },
                }
            )
        return 0

    if event == "check-changed":
        try:
            return _run_check_changed(root, changed_paths(root))
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            return _capture_failure(error)
    emit(stop_feedback(payload, root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
