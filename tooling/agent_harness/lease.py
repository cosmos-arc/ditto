#!/usr/bin/env python3
"""Cross-worktree single-writer lease for protected repository paths."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

LEASE_SCHEMA_VERSION = 1
DEFAULT_TTL = timedelta(minutes=30)
MAX_TTL = timedelta(hours=4)
_GUARD_TIMEOUT_SECONDS = 5.0
_STALE_GUARD_SECONDS = 60.0
_LEASE_SCOPE = "protected-write"
_LEASE_ID = re.compile(r"[0-9a-f]{32}")
_PROTECTED_RESOURCE_ORDER = (
    "contract",
    "generator-config",
    "lockfile",
    "migration",
)
_LOCKFILES = frozenset({"bun.lock", "pixi.lock"})
_GENERATOR_PATH_REGISTRY = (
    {
        "name": "api-contract",
        "paths": frozenset({".redocly.yaml"}),
        "prefixes": ("tooling/contracts/", "apps/web/scripts/gen-api"),
    },
    {
        "name": "page-contract",
        "paths": frozenset(
            {
                "apps/web/scripts/visual-audit.config.generated.mjs",
                "apps/web/src/features/shell/page-contracts.generated.ts",
            }
        ),
        "prefixes": (".agents/skills/ditto-page-contract/scripts/",),
    },
    {
        "name": "route-tree",
        "paths": frozenset(
            {
                "apps/web/scripts/generate-route-tree.mjs",
                "apps/web/src/routeTree.gen.ts",
            }
        ),
        "prefixes": (),
    },
    {
        "name": "design-token",
        "paths": frozenset({"apps/web/scripts/export-tokens.ts"}),
        "prefixes": ("apps/web/scripts/export-tokens/",),
    },
)
_GENERATOR_COMMAND_REGISTRY = (
    {
        "markers": frozenset(
            {
                "tooling.contracts.export_openapi",
                "tooling/contracts/export_openapi.py",
            }
        ),
        "requires_write_flag": True,
        "targets": ("contracts/openapi/v1.json",),
    },
    {
        "markers": frozenset(
            {
                "contract:codegen",
                "gen:api",
                "tooling.contracts.generate_web_schema",
                "tooling/contracts/generate_web_schema.py",
            }
        ),
        "requires_write_flag": True,
        "targets": (
            "apps/web/src/api/generated/operation-contracts.ts",
            "apps/web/src/api/generated/schema.d.ts",
        ),
    },
    {
        "markers": frozenset(
            {
                "generate-contracts",
                ".agents/skills/ditto-page-contract/scripts/generate.mjs",
            }
        ),
        "requires_write_flag": False,
        "targets": (
            "apps/web/scripts/visual-audit.config.generated.mjs",
            "apps/web/src/features/shell/page-contracts.generated.ts",
        ),
    },
)
_GENERATED_CONTRACT_PREFIXES = ("apps/web/src/api/generated/",)
_RECORD_KEYS = frozenset(
    {
        "acquired_at",
        "expires_at",
        "lease_id",
        "owner",
        "schema_version",
        "scope",
        "task",
        "worktree",
    }
)

try:
    from datetime import UTC as _UTC
except ImportError:  # Python 3.9/3.10 host fallback; project runtime is 3.13.
    from datetime import timezone

    _UTC = timezone.utc  # noqa: UP017 - compatibility with host Python 3.9/3.10.


class LeaseError(RuntimeError):
    """Base error for invalid or unavailable lease state."""


class LeaseConflict(LeaseError):
    """Raised when another worktree owns the active shared lease."""


@dataclass(frozen=True)
class GitLeasePaths:
    """Shared and worktree-local Git metadata paths used by the lease."""

    worktree: Path
    git_dir: Path
    common_dir: Path
    identity_path: Path
    lease_path: Path
    guard_path: Path


@dataclass(frozen=True)
class LeaseRecord:
    """Strict persisted identity for the elected integrator."""

    schema_version: int
    scope: str
    lease_id: str
    owner: str
    task: str
    worktree: str
    acquired_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class LeaseDecision:
    """Fail-closed authorization result for a set of repository paths."""

    allowed: bool
    reason: str
    resources: tuple[str, ...]


def _git_absolute_path(root: Path, argument: str) -> Path:
    result = subprocess.run(
        ("git", "rev-parse", "--path-format=absolute", argument),
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        message = result.stderr.strip() or f"unable to resolve {argument}"
        raise LeaseError(message)
    return Path(result.stdout.strip()).resolve()


def git_lease_paths(root: Path) -> GitLeasePaths:
    """Resolve one shared common-dir and one isolated git-dir."""
    worktree = _git_absolute_path(root, "--show-toplevel")
    git_dir = _git_absolute_path(root, "--git-dir")
    common_dir = _git_absolute_path(root, "--git-common-dir")
    shared = common_dir / "ditto-agent-harness" / "leases"
    return GitLeasePaths(
        worktree=worktree,
        git_dir=git_dir,
        common_dir=common_dir,
        identity_path=git_dir / "ditto-agent-harness" / "integrator-lease.json",
        lease_path=shared / f"{_LEASE_SCOPE}.json",
        guard_path=shared / ".guard",
    )


def _is_migration_path(path: str) -> bool:
    pure = PurePosixPath(path)
    if not pure.parts or pure.parts[0] == "docs":
        return False
    return (
        pure.parts[0] == "migrations"
        or "migrations" in pure.parts
        or pure.name.startswith("migration_")
    )


def _resources_for_path(path: str) -> set[str]:
    resources: set[str] = set()
    if path.startswith("contracts/") or path.startswith(_GENERATED_CONTRACT_PREFIXES):
        resources.add("contract")
    if path in _LOCKFILES:
        resources.add("lockfile")
    if _is_migration_path(path):
        resources.add("migration")
    if any(
        path in registration["paths"] or path.startswith(registration["prefixes"])
        for registration in _GENERATOR_PATH_REGISTRY
    ):
        resources.add("generator-config")
    return resources


def generator_write_targets(tokens: Sequence[str]) -> tuple[str, ...]:
    """Return registered canonical outputs written by a generator command."""
    token_set = set(tokens)
    targets: set[str] = set()
    for registration in _GENERATOR_COMMAND_REGISTRY:
        markers = registration["markers"]
        if not any(
            token in markers or any(token.endswith(f"/{marker}") for marker in markers)
            for token in tokens
        ):
            continue
        if registration["requires_write_flag"] and "--write" not in token_set:
            continue
        targets.update(registration["targets"])
    return tuple(sorted(targets))


def protected_resources(paths: Sequence[str]) -> tuple[str, ...]:
    """Return deterministic protected resource classes for changed paths."""
    resources = {resource for path in paths for resource in _resources_for_path(path)}
    return tuple(
        resource for resource in _PROTECTED_RESOURCE_ORDER if resource in resources
    )


def _aware_utc(value: datetime, context: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise LeaseError(f"{context} must be timezone-aware")
    return value.astimezone(_UTC)


def _timestamp(value: object, context: str) -> datetime:
    if not isinstance(value, str):
        raise LeaseError(f"{context} must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise LeaseError(f"{context} must be an ISO-8601 timestamp") from error
    return _aware_utc(parsed, context)


def _identity_text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise LeaseError(f"{context} must be a non-empty trimmed string")
    if any(character.isspace() and character not in {" "} for character in value):
        raise LeaseError(f"{context} contains unsupported whitespace")
    return value


def _record_from_json(value: object, context: str) -> LeaseRecord:
    if not isinstance(value, dict) or set(value) != _RECORD_KEYS:
        raise LeaseError(f"invalid {context}: expected exact lease record keys")
    if value.get("schema_version") != LEASE_SCHEMA_VERSION:
        raise LeaseError(f"invalid {context}: unsupported schema version")
    if value.get("scope") != _LEASE_SCOPE:
        raise LeaseError(f"invalid {context}: unsupported lease scope")
    lease_id = value.get("lease_id")
    if not isinstance(lease_id, str) or _LEASE_ID.fullmatch(lease_id) is None:
        raise LeaseError(f"invalid {context}: malformed lease ID")
    owner = _identity_text(value.get("owner"), f"{context}.owner")
    task = _identity_text(value.get("task"), f"{context}.task")
    worktree = _identity_text(value.get("worktree"), f"{context}.worktree")
    if not Path(worktree).is_absolute():
        raise LeaseError(f"invalid {context}: worktree must be absolute")
    acquired_at = _timestamp(value.get("acquired_at"), f"{context}.acquired_at")
    expires_at = _timestamp(value.get("expires_at"), f"{context}.expires_at")
    if expires_at <= acquired_at:
        raise LeaseError(f"invalid {context}: expiry must follow acquisition")
    return LeaseRecord(
        schema_version=LEASE_SCHEMA_VERSION,
        scope=_LEASE_SCOPE,
        lease_id=lease_id,
        owner=owner,
        task=task,
        worktree=Path(worktree).resolve().as_posix(),
        acquired_at=acquired_at,
        expires_at=expires_at,
    )


def _record_json(record: LeaseRecord) -> dict[str, object]:
    value = asdict(record)
    value["acquired_at"] = record.acquired_at.isoformat()
    value["expires_at"] = record.expires_at.isoformat()
    return value


def _read_record(path: Path, context: str, *, optional: bool) -> LeaseRecord | None:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if optional:
            return None
        raise LeaseError(f"missing {context}") from None
    except (json.JSONDecodeError, OSError) as error:
        raise LeaseError(f"invalid {context}: {error}") from error
    return _record_from_json(raw, context)


def _atomic_write(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        temporary.chmod(0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _reclaim_stale_guard(guard: Path) -> None:
    try:
        age = time.time() - guard.stat().st_mtime
    except FileNotFoundError:
        return
    if age <= _STALE_GUARD_SECONDS:
        return
    stale = guard.with_name(f".guard.stale.{uuid.uuid4().hex}")
    try:
        guard.rename(stale)
    except FileNotFoundError:
        return
    shutil.rmtree(stale, ignore_errors=True)


@contextmanager
def _shared_guard(paths: GitLeasePaths) -> Iterator[None]:
    paths.guard_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + _GUARD_TIMEOUT_SECONDS
    token = uuid.uuid4().hex
    while True:
        try:
            paths.guard_path.mkdir()
        except FileExistsError:
            _reclaim_stale_guard(paths.guard_path)
            if time.monotonic() >= deadline:
                raise LeaseError("timed out acquiring the shared lease guard") from None
            time.sleep(0.01)
            continue
        break
    token_path = paths.guard_path / "owner"
    try:
        token_path.write_text(token, encoding="ascii")
        yield
    finally:
        try:
            owns_guard = token_path.read_text(encoding="ascii") == token
        except (FileNotFoundError, OSError):
            owns_guard = False
        if owns_guard:
            released = paths.guard_path.with_name(f".guard.released.{token}")
            try:
                paths.guard_path.rename(released)
            except FileNotFoundError:
                pass
            else:
                shutil.rmtree(released, ignore_errors=True)


def _validated_ttl(ttl: timedelta) -> timedelta:
    if ttl <= timedelta(0) or ttl > MAX_TTL:
        raise LeaseError("lease TTL must be greater than zero and at most four hours")
    return ttl


def _lease_conflict(record: LeaseRecord) -> LeaseConflict:
    return LeaseConflict(
        "protected-write lease is held by "
        + f"owner={record.owner!r}, task={record.task!r}, "
        + f"worktree={record.worktree!r} until {record.expires_at.isoformat()}"
    )


def acquire_lease(
    root: Path,
    *,
    owner: str,
    task: str,
    ttl: timedelta = DEFAULT_TTL,
    now: datetime | None = None,
) -> LeaseRecord:
    """Elect the current worktree as integrator or renew its active lease."""
    paths = git_lease_paths(root)
    current_time = _aware_utc(now or datetime.now(_UTC), "now")
    duration = _validated_ttl(ttl)
    owner = _identity_text(owner, "owner")
    task = _identity_text(task, "task")
    with _shared_guard(paths):
        existing = _read_record(paths.lease_path, "shared lease", optional=True)
        same_integrator = (
            existing is not None
            and existing.owner == owner
            and existing.task == task
            and existing.worktree == paths.worktree.as_posix()
        )
        if existing is not None and existing.expires_at > current_time:
            if not same_integrator:
                raise _lease_conflict(existing)
            record = LeaseRecord(
                schema_version=LEASE_SCHEMA_VERSION,
                scope=_LEASE_SCOPE,
                lease_id=existing.lease_id,
                owner=owner,
                task=task,
                worktree=paths.worktree.as_posix(),
                acquired_at=existing.acquired_at,
                expires_at=current_time + duration,
            )
        else:
            record = LeaseRecord(
                schema_version=LEASE_SCHEMA_VERSION,
                scope=_LEASE_SCOPE,
                lease_id=uuid.uuid4().hex,
                owner=owner,
                task=task,
                worktree=paths.worktree.as_posix(),
                acquired_at=current_time,
                expires_at=current_time + duration,
            )
        serialized = _record_json(record)
        _atomic_write(paths.lease_path, serialized)
        _atomic_write(paths.identity_path, serialized)
    return record


def authorize_paths(
    root: Path,
    paths: Sequence[str],
    *,
    now: datetime | None = None,
) -> LeaseDecision:
    """Authorize protected paths only for the active integrator worktree."""
    resources = protected_resources(paths)
    if not resources:
        return LeaseDecision(True, "", ())
    try:
        metadata = git_lease_paths(root)
        current_time = _aware_utc(now or datetime.now(_UTC), "now")
        shared = _read_record(metadata.lease_path, "shared lease", optional=False)
        if shared is None:
            raise LeaseError("missing active integrator lease")
        if shared.expires_at <= current_time:
            raise LeaseError("integrator lease is expired; acquire a new lease")
        identity = _read_record(
            metadata.identity_path, "worktree lease identity", optional=True
        )
        if identity is None:
            raise _lease_conflict(shared)
        if identity != shared or shared.worktree != metadata.worktree.as_posix():
            raise _lease_conflict(shared)
    except LeaseError as error:
        return LeaseDecision(False, f"Protected write lease denied: {error}", resources)
    return LeaseDecision(True, "", resources)


def release_lease(root: Path) -> LeaseRecord:
    """Release only the lease bound to the current worktree identity."""
    paths = git_lease_paths(root)
    with _shared_guard(paths):
        shared = _read_record(paths.lease_path, "shared lease", optional=False)
        identity = _read_record(
            paths.identity_path, "worktree lease identity", optional=False
        )
        if shared is None or identity is None:
            raise LeaseError("missing active integrator lease")
        if shared != identity or shared.worktree != paths.worktree.as_posix():
            raise _lease_conflict(shared)
        paths.lease_path.unlink()
        paths.identity_path.unlink()
    return shared


def _print_record(record: LeaseRecord) -> None:
    print(json.dumps(_record_json(record), ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    acquire = commands.add_parser("acquire", help="acquire or renew the lease")
    acquire.add_argument("--owner", required=True)
    acquire.add_argument("--task", required=True)
    acquire.add_argument("--ttl-seconds", type=int, default=1800)
    commands.add_parser("release", help="release the current worktree lease")
    commands.add_parser("status", help="show the current shared lease")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "acquire":
            record = acquire_lease(
                arguments.root,
                owner=arguments.owner,
                task=arguments.task,
                ttl=timedelta(seconds=arguments.ttl_seconds),
            )
        elif arguments.command == "release":
            record = release_lease(arguments.root)
        else:
            paths = git_lease_paths(arguments.root)
            record = _read_record(paths.lease_path, "shared lease", optional=False)
            if record is None:
                raise LeaseError("missing shared lease")
    except LeaseError as error:
        print(f"Integrator lease failed: {error}", file=sys.stderr)
        return 1
    _print_record(record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
