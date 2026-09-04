"""Auditable, non-mutating fresh-bootstrap planning."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import orjson

_AMBIGUOUS_PATH_TOKENS = frozenset(("*", "?", "[", "]", "$", "%"))
_BROAD_ROOTS = frozenset(
    (
        Path("/"),
        Path("/Users"),
        Path("/home"),
        Path("/").joinpath("tmp"),
        Path("/var"),
        Path("/data"),
    )
)


@dataclass(frozen=True, slots=True)
class _TargetSpec:
    relative_path: str
    recoverability: str = "NEEDS_EXPLICIT_APPROVAL"


_TARGET_SPECS = (
    _TargetSpec("metadata/metadata.sqlite"),
    _TargetSpec("metadata/metadata.sqlite-wal"),
    _TargetSpec("metadata/metadata.sqlite-shm"),
    _TargetSpec("db/ditto.duckdb"),
    _TargetSpec("market"),
    _TargetSpec("capital"),
    _TargetSpec("fundamental"),
    _TargetSpec("macro"),
    _TargetSpec("freezes"),
    _TargetSpec("locks"),
    _TargetSpec("features"),
    _TargetSpec("factors"),
    _TargetSpec("derived/artifacts"),
    _TargetSpec("derived/publication_safety"),
    _TargetSpec("research/research.sqlite"),
    _TargetSpec("research/research.sqlite-wal"),
    _TargetSpec("research/research.sqlite-shm"),
    _TargetSpec("research/artifacts", "BACKUP_FIRST"),
    _TargetSpec("agent/agent.sqlite", "BACKUP_FIRST"),
    _TargetSpec("agent/agent.sqlite-wal", "BACKUP_FIRST"),
    _TargetSpec("agent/agent.sqlite-shm", "BACKUP_FIRST"),
    _TargetSpec("agent/agent-presentation.sqlite3"),
    _TargetSpec("agent/agent-presentation.sqlite3-wal"),
    _TargetSpec("agent/agent-presentation.sqlite3-shm"),
    _TargetSpec("agent-shadow/decision-opinion.sqlite"),
    _TargetSpec("agent-shadow/decision-opinion.sqlite-wal"),
    _TargetSpec("agent-shadow/decision-opinion.sqlite-shm"),
    _TargetSpec("logs"),
    _TargetSpec("temp"),
)


class FreshBootstrapTargetError(ValueError):
    """Raised when a reset target cannot be proven narrow and unambiguous."""


@dataclass(frozen=True, slots=True)
class FreshBootstrapCandidate:
    """One exact, observed runtime target in a dry-run manifest."""

    relative_path: str
    target_type: str
    size_bytes: int
    modified_ns: int
    tree_fingerprint: str
    recoverability: str


@dataclass(frozen=True, slots=True)
class FreshBootstrapPlan:
    """Content-addressed dry-run plan; creating it never changes the filesystem."""

    mode: str
    schema_version: int
    data_root: Path
    candidates: tuple[FreshBootstrapCandidate, ...]
    plan_hash: str


def _validate_data_root(raw_target: str) -> Path:
    if not raw_target or raw_target == "~" or raw_target.startswith("~/"):
        raise FreshBootstrapTargetError("fresh bootstrap target is ambiguous")
    if any(token in raw_target for token in _AMBIGUOUS_PATH_TOKENS):
        raise FreshBootstrapTargetError("fresh bootstrap target contains expansion")

    unresolved = Path(raw_target)
    if unresolved.is_symlink():
        raise FreshBootstrapTargetError("fresh bootstrap target cannot be a symlink")
    resolved = unresolved.resolve(strict=False)
    broad_roots = {*_BROAD_ROOTS, Path.home().resolve(strict=False)}
    if resolved in broad_roots:
        raise FreshBootstrapTargetError("fresh bootstrap target is too broad")
    if (resolved / ".git").exists() or (resolved / "pyproject.toml").exists():
        raise FreshBootstrapTargetError("fresh bootstrap target is a repository")
    if resolved.exists() and not resolved.is_dir():
        raise FreshBootstrapTargetError("fresh bootstrap target is not a directory")
    return resolved


def _candidate_fingerprint(path: Path) -> tuple[int, int, str]:
    entries = [path]
    if path.is_dir():
        entries.extend(sorted(path.rglob("*")))

    size_bytes = 0
    modified_ns = 0
    fingerprint_rows: list[dict[str, object]] = []
    for entry in entries:
        if entry.is_symlink():
            raise FreshBootstrapTargetError(
                f"fresh bootstrap candidate contains a symlink: {entry}"
            )
        stat = entry.stat()
        entry_type = "directory" if entry.is_dir() else "file"
        if entry_type == "file":
            size_bytes += stat.st_size
        modified_ns = max(modified_ns, stat.st_mtime_ns)
        fingerprint_rows.append(
            {
                "path": entry.relative_to(path.parent).as_posix(),
                "type": entry_type,
                "size_bytes": stat.st_size if entry_type == "file" else 0,
                "modified_ns": stat.st_mtime_ns,
            }
        )
    fingerprint = hashlib.sha256(
        orjson.dumps(fingerprint_rows, option=orjson.OPT_SORT_KEYS)
    ).hexdigest()
    return size_bytes, modified_ns, fingerprint


def _candidate(root: Path, spec: _TargetSpec) -> FreshBootstrapCandidate | None:
    target = root / spec.relative_path
    if not target.exists():
        return None
    if not target.resolve(strict=True).is_relative_to(root):
        raise FreshBootstrapTargetError(
            f"fresh bootstrap candidate escapes data root: {target}"
        )
    size_bytes, modified_ns, tree_fingerprint = _candidate_fingerprint(target)
    return FreshBootstrapCandidate(
        relative_path=spec.relative_path,
        target_type="directory" if target.is_dir() else "file",
        size_bytes=size_bytes,
        modified_ns=modified_ns,
        tree_fingerprint=tree_fingerprint,
        recoverability=spec.recoverability,
    )


def _plan_payload(
    *,
    data_root: Path,
    candidates: tuple[FreshBootstrapCandidate, ...],
) -> dict[str, object]:
    return {
        "mode": "dry_run",
        "schema_version": 1,
        "data_root": str(data_root),
        "candidate_count": len(candidates),
        "candidates": [
            {
                "relative_path": item.relative_path,
                "target_type": item.target_type,
                "size_bytes": item.size_bytes,
                "modified_ns": item.modified_ns,
                "tree_fingerprint": item.tree_fingerprint,
                "recoverability": item.recoverability,
            }
            for item in candidates
        ],
        "permanent_exclusions": ["backups", "unknown_user_files"],
    }


def build_fresh_bootstrap_plan(raw_target: str) -> FreshBootstrapPlan:
    """Inspect known runtime targets and return a deterministic dry-run plan."""
    data_root = _validate_data_root(raw_target)
    candidates = tuple(
        item
        for spec in _TARGET_SPECS
        if (item := _candidate(data_root, spec)) is not None
    )
    payload = _plan_payload(data_root=data_root, candidates=candidates)
    plan_hash = hashlib.sha256(
        orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    ).hexdigest()
    return FreshBootstrapPlan(
        mode="dry_run",
        schema_version=1,
        data_root=data_root,
        candidates=candidates,
        plan_hash=plan_hash,
    )


def fresh_bootstrap_plan_payload(plan: FreshBootstrapPlan) -> dict[str, object]:
    """Serialize a dry-run plan for stable CLI output."""
    return {
        **_plan_payload(data_root=plan.data_root, candidates=plan.candidates),
        "plan_hash": plan.plan_hash,
    }


__all__ = [
    "FreshBootstrapCandidate",
    "FreshBootstrapPlan",
    "FreshBootstrapTargetError",
    "build_fresh_bootstrap_plan",
    "fresh_bootstrap_plan_payload",
]
