"""Composition-root helper for building one frozen code environment lock."""

from __future__ import annotations

from ditto_application.processes.experiments.execution_bundle import CodeEnvironmentLock

__all__ = ["build_code_environment_lock"]


def build_code_environment_lock(
    *,
    git_commit_sha: str,
    environment_lock_hash: str,
) -> CodeEnvironmentLock:
    """
    Build a code environment lock from raw composition-root inputs.

    The application layer never performs git or dependency-lock I/O. The
    composition root reads the current ``git HEAD`` and the hashed lockfile
    digest and passes both as canonical strings; this helper preserves the
    exact validation rules of :class:`CodeEnvironmentLock` without duplicating
    them.
    """
    return CodeEnvironmentLock(
        code_version=git_commit_sha,
        environment_lock_hash=environment_lock_hash,
    )
