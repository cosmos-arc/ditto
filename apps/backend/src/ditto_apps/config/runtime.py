"""Explicit runtime path configuration and readiness checks."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from ditto_platform.foundation import Environment

__all__ = [
    "ReadinessCheck",
    "RuntimeConfigurationError",
    "RuntimePaths",
    "configured_state_root",
    "evaluate_runtime_readiness",
    "load_runtime_paths",
    "resolve_cors_origins",
    "resolve_runtime_paths",
    "state_root_matches",
]

_DEFAULT_CORS_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)


class RuntimeConfigurationError(RuntimeError):
    """Raised when the deployment runtime path contract is incomplete."""


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """Filesystem roots supplied by the deployment composition root."""

    config_root: Path
    state_root: Path
    cache_root: Path


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    """Result of one operational readiness check."""

    ok: bool
    detail: str


def resolve_runtime_paths(
    environment: Environment,
    *,
    environ: Mapping[str, str] | None = None,
    fallback: RuntimePaths | None = None,
) -> RuntimePaths:
    """Resolve roots without inspecting a checkout or the process working directory."""
    values = os.environ if environ is None else environ
    config_root = _configured_path(values, "DITTO_CONFIG_ROOT")
    state_root = configured_state_root(values)
    cache_root = _configured_path(values, "DITTO_CACHE_ROOT")

    if fallback is not None and environment is not Environment.PRODUCTION:
        config_root = config_root or fallback.config_root
        state_root = state_root or fallback.state_root
        cache_root = cache_root or fallback.cache_root

    missing: list[str] = []
    if config_root is None:
        missing.append("DITTO_CONFIG_ROOT")
    if state_root is None:
        missing.append("DITTO_STATE_ROOT")
    if cache_root is None:
        missing.append("DITTO_CACHE_ROOT")
    if config_root is None or state_root is None or cache_root is None:
        names = ", ".join(missing)
        raise RuntimeConfigurationError(f"Missing required runtime path(s): {names}")

    resolved = RuntimePaths(
        config_root=config_root,
        state_root=state_root,
        cache_root=cache_root,
    )
    for name, path in (
        ("DITTO_CONFIG_ROOT", resolved.config_root),
        ("DITTO_STATE_ROOT", resolved.state_root),
        ("DITTO_CACHE_ROOT", resolved.cache_root),
    ):
        if not path.is_absolute():
            raise RuntimeConfigurationError(f"{name} must be an absolute path")
    return resolved


def configured_state_root(
    environ: Mapping[str, str] | None = None,
) -> Path | None:
    """Return the state root, with transition aliases isolated here."""
    values = os.environ if environ is None else environ
    for name in ("DITTO_STATE_ROOT", "DITTO_DATA_ROOT", "DATA_ROOT"):
        if configured := _configured_path(values, name):
            return configured
    return None


def state_root_matches(expected: Path) -> bool:
    """Return whether runtime composition is bound to an exact state root."""
    configured = configured_state_root()
    return configured is not None and configured.resolve(
        strict=False
    ) == expected.expanduser().resolve(strict=False)


def resolve_cors_origins(
    environ: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Resolve an exact CORS allowlist with one legacy environment alias."""
    values = os.environ if environ is None else environ
    if "DITTO_CORS_ORIGINS" in values:
        raw = values["DITTO_CORS_ORIGINS"]
    elif "CORS_ORIGINS" in values:
        raw = values["CORS_ORIGINS"]
    else:
        return _DEFAULT_CORS_ORIGINS

    origins: list[str] = []
    seen: set[str] = set()
    for candidate in raw.split(","):
        origin = candidate.strip()
        if not origin:
            continue
        _validate_origin(origin)
        if origin not in seen:
            seen.add(origin)
            origins.append(origin)
    return tuple(origins)


def load_runtime_paths(environment: Environment) -> RuntimePaths:
    """Load paths from deployment input or non-checkout environment defaults."""
    if environment is Environment.PRODUCTION:
        return resolve_runtime_paths(environment)

    if environment is Environment.TESTING:
        isolated_root = Path(tempfile.mkdtemp(prefix="ditto-backend-test-"))
        fallback = RuntimePaths(
            config_root=isolated_root,
            state_root=isolated_root / "state",
            cache_root=isolated_root / "cache",
        )
    else:
        values = os.environ
        fallback = RuntimePaths(
            config_root=_xdg_root(
                values,
                variable="XDG_CONFIG_HOME",
                default=Path.home() / ".config",
            ),
            state_root=_xdg_root(
                values,
                variable="XDG_STATE_HOME",
                default=Path.home() / ".local" / "state",
            ),
            cache_root=_xdg_root(
                values,
                variable="XDG_CACHE_HOME",
                default=Path.home() / ".cache",
            ),
        )
    return resolve_runtime_paths(environment, fallback=fallback)


def _xdg_root(
    values: Mapping[str, str],
    *,
    variable: str,
    default: Path,
) -> Path:
    """Resolve one development-only user root without consulting a checkout."""
    configured = _configured_path(values, variable)
    root = configured or default
    if not root.is_absolute():
        raise RuntimeConfigurationError(f"{variable} must be an absolute path")
    return root / "ditto"


def evaluate_runtime_readiness(
    paths: RuntimePaths | None,
    *,
    initialized: bool,
) -> dict[str, ReadinessCheck]:
    """Evaluate startup state and actual filesystem availability."""
    checks = {
        "startup": ReadinessCheck(
            ok=initialized,
            detail="initialized" if initialized else "initialization incomplete",
        )
    }
    if paths is None:
        unavailable = ReadinessCheck(ok=False, detail="runtime path not configured")
        checks.update(
            config_root=unavailable,
            state_root=unavailable,
            cache_root=unavailable,
        )
        return checks

    checks["config_root"] = _check_directory(paths.config_root, writable=False)
    checks["state_root"] = _check_directory(paths.state_root, writable=True)
    checks["cache_root"] = _check_directory(paths.cache_root, writable=True)
    return checks


def _configured_path(values: Mapping[str, str], name: str) -> Path | None:
    raw = values.get(name, "").strip()
    return Path(raw).expanduser() if raw else None


def _validate_origin(origin: str) -> None:
    if "*" in origin:
        raise RuntimeConfigurationError("CORS origin must not contain wildcards")
    try:
        parsed = urlsplit(origin)
        _ = parsed.port
    except ValueError as error:
        raise RuntimeConfigurationError(f"Invalid CORS origin: {origin!r}") from error
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.netloc.endswith(":")
    ):
        raise RuntimeConfigurationError(f"Invalid CORS origin: {origin!r}")


def _check_directory(path: Path, *, writable: bool) -> ReadinessCheck:
    if not path.is_dir():
        return ReadinessCheck(ok=False, detail="directory unavailable")
    try:
        if writable:
            with tempfile.NamedTemporaryFile(
                dir=path,
                prefix=".ditto-readiness-",
            ):
                pass
        else:
            with os.scandir(path):
                pass
    except OSError as error:
        return ReadinessCheck(
            ok=False,
            detail=f"filesystem error: {type(error).__name__}",
        )
    return ReadinessCheck(ok=True, detail="available")
