"""
Run the local secret and dependency gates used by the root CI task.

GitHub CodeQL remains a hosted CI concern.  This module covers the checks that
can be reproduced locally: committed history, the current tracked/untracked
tree, and both package-manager lockfiles.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_GITLEAKS_CURRENT = (
    "docker.io/zricethezav/gitleaks:v8.30.1@sha256:"
    "c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f"
)
_GITLEAKS_KNOWN_GOOD = (
    "ghcr.io/gitleaks/gitleaks:v8.18.4@sha256:"
    "75bdb2b2f4db213cde0b8295f13a88d6b333091bbfbf3012a4e083d00d31caba"
)
_OSV_SCANNER = (
    "ghcr.io/google/osv-scanner:v2.5.1@sha256:"
    "8108ae94eadea5a02c9bec6e646909d5b790b44bd62d7f5b7f0b1d6d0ffc7734"
)
_SENTINEL = 'token = "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"\n'


class SupplyChainGateError(RuntimeError):
    """Raised when a local security prerequisite or scanner fails."""


def _executable(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise SupplyChainGateError(f"required executable is unavailable: {name}")
    return executable


def _run(
    command: list[str],
    *,
    cwd: Path,
    expected: frozenset[int] = frozenset({0}),
) -> int:
    result = subprocess.run(command, cwd=cwd, check=False)  # noqa: S603
    if result.returncode not in expected:
        rendered = " ".join(command)
        raise SupplyChainGateError(
            f"security command failed ({result.returncode}): {rendered}"
        )
    return result.returncode


def _docker_user_arguments() -> list[str]:
    if not hasattr(os, "getuid") or not hasattr(os, "getgid"):
        return []
    return ["--user", f"{os.getuid()}:{os.getgid()}"]


def _require_docker(root: Path) -> str:
    docker = _executable("docker")
    _run(
        [docker, "version", "--format", "{{.Server.Version}}"],
        cwd=root,
    )
    return docker


def _repository_files(root: Path) -> tuple[Path, ...]:
    git = _executable("git")
    result = subprocess.run(  # noqa: S603
        [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise SupplyChainGateError("could not enumerate the current repository tree")
    files: list[Path] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        candidate = root / relative
        if candidate.is_file() or candidate.is_symlink():
            files.append(relative)
    return tuple(files)


def _stage_current_tree(root: Path, destination: Path) -> None:
    for relative in _repository_files(root):
        source = root / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            target.write_text(str(source.readlink()), encoding="utf-8")
        else:
            shutil.copy2(source, target)


def run_supply_chain_gate(root: Path) -> None:
    """Scan immutable history, the exact current tree, and lockfile dependencies."""
    workspace = root.expanduser().resolve(strict=True)
    docker = _require_docker(workspace)
    mount = f"{workspace}:/repo:ro"
    user = _docker_user_arguments()

    _run(
        [
            docker,
            "run",
            "--rm",
            "--network",
            "none",
            *user,
            "--volume",
            mount,
            "--workdir",
            "/repo",
            _GITLEAKS_CURRENT,
            "git",
            "--redact",
            "--no-banner",
            "--exit-code",
            "1",
            "--log-opts=--all",
            ".",
        ],
        cwd=workspace,
    )
    _run(
        [
            docker,
            "run",
            "--rm",
            "--network",
            "none",
            *user,
            "--volume",
            mount,
            "--workdir",
            "/repo",
            _GITLEAKS_KNOWN_GOOD,
            "detect",
            "--source",
            ".",
            "--redact",
            "--no-banner",
            "--exit-code",
            "1",
            "--log-opts=--all",
        ],
        cwd=workspace,
    )

    with tempfile.TemporaryDirectory(prefix="ditto-security-tree-") as raw_tree:
        staged_tree = Path(raw_tree)
        _stage_current_tree(workspace, staged_tree)
        _run(
            [
                docker,
                "run",
                "--rm",
                "--network",
                "none",
                *user,
                "--volume",
                f"{staged_tree}:/scan:ro",
                "--workdir",
                "/scan",
                _GITLEAKS_CURRENT,
                "dir",
                "--redact",
                "--no-banner",
                "--exit-code",
                "1",
                ".",
            ],
            cwd=workspace,
        )

    with tempfile.TemporaryDirectory(prefix="ditto-gitleaks-sentinel-") as raw_probe:
        probe = Path(raw_probe)
        (probe / "leak.txt").write_text(_SENTINEL, encoding="utf-8")
        _run(
            [
                docker,
                "run",
                "--rm",
                "--network",
                "none",
                *user,
                "--volume",
                f"{probe}:/probe:ro",
                _GITLEAKS_KNOWN_GOOD,
                "detect",
                "--no-git",
                "--source",
                "/probe/leak.txt",
                "--redact",
                "--no-banner",
                "--exit-code",
                "23",
            ],
            cwd=workspace,
            expected=frozenset({23}),
        )

    _run(
        [
            docker,
            "run",
            "--rm",
            *user,
            "--env",
            "HOME=/tmp",
            "--volume",
            mount,
            "--workdir",
            "/repo",
            _OSV_SCANNER,
            "scan",
            "source",
            "--recursive",
            "./",
        ],
        cwd=workspace,
    )


def main() -> int:
    """Run the root-local security gate."""
    root = Path(__file__).resolve().parents[2]
    try:
        run_supply_chain_gate(root)
    except SupplyChainGateError as error:
        sys.stderr.write(f"security-supply-chain: FAIL: {error}\n")
        return 1
    sys.stdout.write("security-supply-chain: PASS\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
