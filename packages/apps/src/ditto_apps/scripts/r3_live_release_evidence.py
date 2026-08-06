"""CLI wrapper for the final cross-repository R3 live evidence bundle."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import orjson

from ditto_apps.registry.live.r3_live_release_evidence import (
    LiveReleaseEvidenceRequest,
    build_live_release_evidence,
)


def _head(repo: Path) -> str:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git executable is required")
    completed = subprocess.run(  # noqa: S603 - resolved git executable only
        (git, "rev-parse", "HEAD"),
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-repo", required=True, type=Path)
    parser.add_argument("--frontend-repo", required=True, type=Path)
    parser.add_argument("--backend-live-evidence-root", required=True, type=Path)
    parser.add_argument("--frontend-live-evidence-root", required=True, type=Path)
    parser.add_argument("--r2-report", required=True, type=Path)
    parser.add_argument("--r2-source-manifest", required=True, type=Path)
    parser.add_argument("--r3-report", required=True, type=Path)
    parser.add_argument("--openapi", required=True, type=Path)
    parser.add_argument("--r2-archive-root", required=True, type=Path)
    parser.add_argument("--r3-archive-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--r2-command", required=True)
    parser.add_argument("--r3-command", required=True)
    parser.add_argument("--frontend-command", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Resolve exact commits, generate the release bundle, and print its JSON."""
    args = _parser().parse_args(argv)
    backend_repo = args.backend_repo.expanduser().resolve(strict=True)
    frontend_repo = args.frontend_repo.expanduser().resolve(strict=True)
    manifest = build_live_release_evidence(
        LiveReleaseEvidenceRequest(
            backend_repo=backend_repo,
            frontend_repo=frontend_repo,
            backend_live_evidence_root=args.backend_live_evidence_root,
            frontend_live_evidence_root=args.frontend_live_evidence_root,
            r2_report=args.r2_report,
            r2_source_manifest=args.r2_source_manifest,
            r3_report=args.r3_report,
            openapi_path=args.openapi,
            r2_archive_root=args.r2_archive_root,
            r3_archive_root=args.r3_archive_root,
            output=args.output,
            backend_commit=_head(backend_repo),
            frontend_commit=_head(frontend_repo),
            r2_command=args.r2_command,
            r3_command=args.r3_command,
            frontend_command=args.frontend_command,
        )
    )
    sys.stdout.write(
        orjson.dumps(
            manifest,
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        ).decode()
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
