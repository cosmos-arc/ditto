"""Run the complete local, deterministic OpenAPI contract gate."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from tooling.contracts import (
    bootstrap_oasdiff,
    export_openapi,
    generate_web_schema,
    lint_openapi,
    oasdiff,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SNAPSHOT = _REPO_ROOT / "contracts/openapi/v1.json"
_GENERATED = _REPO_ROOT / "apps/web/src/api/generated/schema.d.ts"
_GENERATED_RESPONSES = _REPO_ROOT / "apps/web/src/api/generated/operation-contracts.ts"


def _dist_dir(argument: Path | None) -> Path:
    if argument is not None:
        return argument.resolve()
    configured = os.environ.get("DITTO_OASDIFF_DIST_DIR")
    if configured:
        return Path(configured).resolve()
    return bootstrap_oasdiff.prepared_distribution(
        system=platform.system(),
        machine=platform.machine(),
    )


def _check_resolution(
    resolution: oasdiff.BaselineResolution,
    *,
    dist_dir: Path | None,
) -> None:
    sys.stdout.write(json.dumps(resolution.public_result(), sort_keys=True) + "\n")
    if resolution.status == "found":
        result = oasdiff.run_breaking_check(
            resolution=resolution,
            current_path=_SNAPSHOT,
            dist_dir=_dist_dir(dist_dir),
        )
        if result != 0:
            raise oasdiff.OasdiffError(
                f"oasdiff found breaking changes against {resolution.kind} baseline"
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--release-ref")
    parser.add_argument("--oasdiff-dist-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run export, strict lint, two compatibility baselines, and Web zero-diff."""
    arguments = _parser().parse_args(argv)
    try:
        export_openapi.check_runtime_snapshot(_SNAPSHOT)
        sys.stdout.write(f"OpenAPI snapshot is canonical: {_SNAPSHOT}\n")
        lint_openapi.run_lint(
            snapshot_path=_SNAPSHOT,
            config_path=_REPO_ROOT / ".redocly.yaml",
        )
        sys.stdout.write("Redocly recommended-strict passed\n")
        _check_resolution(
            oasdiff.resolve_merge_base(
                repo_root=_REPO_ROOT,
                base_ref=arguments.base_ref,
            ),
            dist_dir=arguments.oasdiff_dist_dir,
        )
        _check_resolution(
            oasdiff.resolve_release(
                repo_root=_REPO_ROOT,
                release_ref=arguments.release_ref,
            ),
            dist_dir=arguments.oasdiff_dist_dir,
        )
        generator_version, generator = generate_web_schema.local_generator()
        candidate, response_candidate = generate_web_schema.generate_candidates_bytes(
            snapshot_path=_SNAPSHOT,
            generator_version=generator_version,
            run_generator=generator,
        )
        generate_web_schema.check_generated_schema(_GENERATED, candidate)
        sys.stdout.write(f"Web OpenAPI types are reproducible: {_GENERATED}\n")
        generate_web_schema.check_generated_schema(
            _GENERATED_RESPONSES,
            response_candidate,
        )
        sys.stdout.write(
            "Web operation response contracts are reproducible: "
            + f"{_GENERATED_RESPONSES}\n"
        )
    except (
        export_openapi.SnapshotMismatchError,
        generate_web_schema.CodegenError,
        lint_openapi.RedoclyError,
        oasdiff.OasdiffError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        sys.stderr.write(f"{error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
