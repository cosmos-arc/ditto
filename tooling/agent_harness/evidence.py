"""Immutable Git index/worktree evidence for changed-scope verification."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    from .repository_policy import forbidden_package_manager_paths
except ImportError:  # Direct script execution.
    from repository_policy import forbidden_package_manager_paths

MANIFEST_SCHEMA_VERSION = 2
_MANIFEST_KEYS = frozenset(
    {
        "base_sha",
        "changes",
        "configs",
        "git_object_format",
        "head_sha",
        "repository_policy",
        "schema_version",
        "tools",
    }
)
_GIT_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
_SHA256 = re.compile(r"[0-9a-f]{64}")

_FINGERPRINT_CONFIGS = (
    ".agents/skills/registry.toml",
    ".claude/settings.json",
    ".codex/hooks.json",
    ".importlinter",
    ".pre-commit-config.yaml",
    ".redocly.yaml",
    ".zcode/config.json",
    "apps/web/dependency-cruiser.config.mjs",
    "apps/web/package.json",
    "apps/web/tsconfig.base.json",
    "apps/web/tsconfig.browser.json",
    "apps/web/tsconfig.json",
    "apps/web/tsconfig.playwright.json",
    "apps/web/tsconfig.tooling.json",
    "apps/web/tsconfig.unit.json",
    "apps/web/vite.config.ts",
    "apps/web/vitest.config.ts",
    "biome.json",
    "bun.lock",
    ".node-version",
    "bunfig.toml",
    "contracts/openapi/v1.json",
    "package.json",
    "uv.lock",
    ".python-version",
    "Taskfile.yml",
    ".task-version",
    "pyproject.toml",
    "tests/system/playwright.config.ts",
    "tooling/agent_harness/agent_eval.py",
    "tooling/agent_harness/evals/v1/cases.json",
    "tooling/agent_harness/hook.py",
    "tooling/agent_harness/lease.py",
    "tooling/agent_harness/repository_policy.py",
    "tooling/agent_harness/validate.py",
    "tooling/contracts/oasdiff.py",
)

TOOL_VERSION_COMMANDS = {
    "bun": ("bun", "--version"),
    "node": ("node", "--version"),
    "git": ("git", "--version"),
    "host_python": (sys.executable, "--version"),
    "uv": ("uv", "--version"),
    "task": ("task", "--version"),
}
PROJECT_TOOL_DISTRIBUTIONS = {
    "basedpyright": "basedpyright",
    "coverage": "coverage",
    "import_linter": "import-linter",
    "pytest": "pytest",
    "ruff": "ruff",
}

INSTALLED_TOOL_PACKAGE_MANIFESTS = {
    "axe_playwright": "node_modules/@axe-core/playwright/package.json",
    "biome": "apps/web/node_modules/@biomejs/biome/package.json",
    "dependency_cruiser": "apps/web/node_modules/dependency-cruiser/package.json",
    "openapi_typescript": "node_modules/openapi-typescript/package.json",
    "playwright": "node_modules/playwright/package.json",
    "playwright_test": "node_modules/@playwright/test/package.json",
    "redocly": "node_modules/@redocly/cli/package.json",
    "typescript": "apps/web/node_modules/typescript/package.json",
    "vite": "apps/web/node_modules/vite/package.json",
    "vitest": "apps/web/node_modules/vitest/package.json",
    "web_playwright": "apps/web/node_modules/playwright/package.json",
}


def _git_status(root: Path) -> dict[str, dict[str, str]]:
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
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.decode(errors="replace").strip()
            or "unable to capture git status"
        )
    statuses: dict[str, dict[str, str]] = {}
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        if len(raw) < len(b"XY path") or raw[2:3] != b" ":
            raise RuntimeError("git status returned an unsupported record")
        code = os.fsdecode(raw[:2])
        statuses[os.fsdecode(raw[3:])] = {
            "index": code[0],
            "worktree": code[1],
        }
    return statuses


def changed_paths(root: Path) -> list[str]:
    """Return every staged, unstaged, deleted, renamed, or untracked path."""
    return sorted(_git_status(root))


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
        content = os.fsencode(path.readlink())
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


def _index_fingerprints(root: Path, selected: set[str]) -> dict[str, dict[str, object]]:
    result = subprocess.run(
        ["git", "ls-files", "--stage", "-z", "--"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.decode(errors="replace").strip()
            or "unable to capture git index"
        )
    entries: dict[str, list[dict[str, str]]] = {}
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            header, raw_path = raw.split(b"\t", 1)
            mode, blob_oid, stage = os.fsdecode(header).split(" ", 2)
        except ValueError as error:
            raise RuntimeError("git index returned an unsupported record") from error
        path = os.fsdecode(raw_path)
        if path in selected:
            entries.setdefault(path, []).append(
                {"mode": mode, "blob_oid": blob_oid, "stage": stage}
            )

    fingerprints: dict[str, dict[str, object]] = {}
    for path in selected:
        path_entries = entries.get(path, [])
        if not path_entries:
            fingerprints[path] = {"state": "absent"}
        elif len(path_entries) == 1 and path_entries[0]["stage"] == "0":
            fingerprints[path] = {"state": "present", **path_entries[0]}
        else:
            fingerprints[path] = {
                "state": "unmerged",
                "entries": sorted(path_entries, key=lambda entry: entry["stage"]),
            }
    return fingerprints


def _project_tool_versions(root: Path) -> dict[str, str]:
    expected = {*PROJECT_TOOL_DISTRIBUTIONS, "project_python"}
    code = (
        "import importlib.metadata as m,json,sys;"
        f"distributions={PROJECT_TOOL_DISTRIBUTIONS!r};"
        "versions={name:m.version(distribution) "
        "for name,distribution in distributions.items()};"
        "versions['project_python']=sys.version.split()[0];"
        "print(json.dumps(versions,sort_keys=True))"
    )
    try:
        result = subprocess.run(
            (
                str(
                    root
                    / ".venv"
                    / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
                ),
                "-c",
                code,
            ),
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return dict.fromkeys(expected, "unavailable")
    try:
        loaded = json.loads(result.stdout) if result.returncode == 0 else {}
    except json.JSONDecodeError:
        loaded = {}
    return {
        name: value
        if isinstance(value := loaded.get(name), str) and value
        else "unavailable"
        for name in expected
    }


def _tool_versions(root: Path) -> dict[str, str]:
    versions = _project_tool_versions(root)
    for name, command in TOOL_VERSION_COMMANDS.items():
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
    for name, relative in INSTALLED_TOOL_PACKAGE_MANIFESTS.items():
        try:
            loaded = json.loads((root / relative).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            versions[name] = "unavailable"
            continue
        version = loaded.get("version") if isinstance(loaded, dict) else None
        versions[name] = (
            version if isinstance(version, str) and version else "unavailable"
        )
    return versions


def change_manifest(root: Path) -> dict[str, object]:
    """Capture the one canonical evidence object hashed by a receipt."""
    statuses = _git_status(root)
    selected = sorted(statuses)
    index = _index_fingerprints(root, set(selected))
    head = _git_text(root, "rev-parse", "HEAD")
    upstream_base = _git_text(root, "merge-base", "HEAD", "origin/main")
    base = head if upstream_base == "unavailable" else upstream_base
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "base_sha": base,
        "head_sha": head,
        "git_object_format": _git_text(root, "rev-parse", "--show-object-format"),
        "changes": {
            relative: {
                "status": statuses.get(
                    relative, {"index": "unknown", "worktree": "unknown"}
                ),
                "index": index[relative],
                "worktree": _file_fingerprint(root / relative),
            }
            for relative in selected
        },
        "configs": {
            relative: _file_fingerprint(root / relative)
            for relative in _FINGERPRINT_CONFIGS
        },
        "repository_policy": {
            "forbidden_package_manager_paths": list(
                forbidden_package_manager_paths(root)
            )
        },
        "tools": _tool_versions(root),
    }


def _validate_index_fingerprint(value: object, context: str) -> None:
    if not isinstance(value, dict):
        raise RuntimeError(f"Harness manifest {context} index must be an object")
    state = value.get("state")
    if state == "absent" and set(value) == {"state"}:
        return
    if state == "present" and set(value) == {
        "blob_oid",
        "mode",
        "stage",
        "state",
    }:
        entries = [value]
    elif (
        state == "unmerged"
        and set(value) == {"entries", "state"}
        and isinstance(value.get("entries"), list)
        and value["entries"]
    ):
        entries = value["entries"]
    else:
        raise RuntimeError(f"Harness manifest {context} index state is invalid")
    for entry in entries:
        if not isinstance(entry, dict) or not {
            "blob_oid",
            "mode",
            "stage",
        }.issubset(entry):
            raise RuntimeError(f"Harness manifest {context} index entry is invalid")
        mode = entry.get("mode")
        oid = entry.get("blob_oid")
        stage = entry.get("stage")
        if (
            not isinstance(mode, str)
            or re.fullmatch(r"[0-7]{6}", mode) is None
            or not isinstance(oid, str)
            or _GIT_OID.fullmatch(oid) is None
            or not isinstance(stage, str)
            or stage not in {"0", "1", "2", "3"}
        ):
            raise RuntimeError(f"Harness manifest {context} index entry is invalid")


def _validate_file_fingerprint(value: object, context: str) -> None:
    if not isinstance(value, dict):
        raise RuntimeError(f"Harness manifest {context} must be an object")
    state = value.get("state")
    if state == "deleted" and set(value) == {"state"}:
        return
    if state != "present" or set(value) != {
        "kind",
        "mode",
        "sha256",
        "state",
    }:
        raise RuntimeError(f"Harness manifest {context} state is invalid")
    mode = value.get("mode")
    sha256 = value.get("sha256")
    if (
        value.get("kind") not in {"file", "other", "symlink"}
        or not isinstance(mode, str)
        or re.fullmatch(r"[0-7]{4}", mode) is None
        or not isinstance(sha256, str)
        or _SHA256.fullmatch(sha256) is None
    ):
        raise RuntimeError(f"Harness manifest {context} fingerprint is invalid")


def _validate_change(relative: str, value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "index",
        "status",
        "worktree",
    }:
        raise RuntimeError(f"Harness manifest change {relative} is incomplete")
    status = value.get("status")
    if (
        not isinstance(status, dict)
        or set(status) != {"index", "worktree"}
        or not all(
            isinstance(status.get(name), str) and len(status[name]) == 1
            for name in ("index", "worktree")
        )
    ):
        raise RuntimeError(f"Harness manifest change {relative} status is invalid")
    _validate_index_fingerprint(value.get("index"), f"change {relative}")
    _validate_file_fingerprint(value.get("worktree"), f"change {relative} worktree")


def _validate_configs_and_tools(manifest: dict[str, object]) -> None:
    configs = manifest.get("configs")
    tools = manifest.get("tools")
    if not isinstance(configs, dict) or not isinstance(tools, dict):
        raise RuntimeError("Harness manifest configs and tools must be objects")
    for relative, fingerprint in configs.items():
        if not isinstance(relative, str):
            raise RuntimeError("Harness manifest config paths must be text")
        _validate_file_fingerprint(fingerprint, f"config {relative}")
    if not tools or not all(
        isinstance(name, str) and name and isinstance(version, str) and version
        for name, version in tools.items()
    ):
        raise RuntimeError("Harness manifest tools must contain named versions")


def _validate_repository_policy(manifest: dict[str, object]) -> None:
    policy = manifest.get("repository_policy")
    if (
        not isinstance(policy, dict)
        or set(policy) != {"forbidden_package_manager_paths"}
        or not isinstance(policy["forbidden_package_manager_paths"], list)
        or not all(
            isinstance(path, str) for path in policy["forbidden_package_manager_paths"]
        )
    ):
        raise RuntimeError("Harness manifest repository policy is invalid")


def manifest_paths(manifest: dict[str, object]) -> list[str]:
    """Read the ordered path set from a validated in-memory manifest."""
    if (
        manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION
        or set(manifest) != _MANIFEST_KEYS
    ):
        raise RuntimeError("Harness manifest schema is unsupported or incomplete")
    for field in ("base_sha", "git_object_format", "head_sha"):
        if not isinstance(manifest.get(field), str):
            raise RuntimeError(f"Harness manifest {field} must be text")
    _validate_configs_and_tools(manifest)
    raw_changes = manifest.get("changes")
    if not isinstance(raw_changes, dict) or not all(
        isinstance(path, str) for path in raw_changes
    ):
        raise RuntimeError("Harness manifest changes must be a path object")
    for relative, change in raw_changes.items():
        _validate_change(relative, change)
    _validate_repository_policy(manifest)
    return list(raw_changes)


def manifest_digest(manifest: dict[str, object]) -> str:
    """Hash one immutable manifest without recapturing repository state."""
    encoded = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8", errors="surrogateescape")
    return hashlib.sha256(encoded).hexdigest()


def diff_digest(root: Path) -> str:
    """Compatibility helper for callers that need only the current digest."""
    return manifest_digest(change_manifest(root))
