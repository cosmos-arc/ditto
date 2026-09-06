"""Lint the canonical OpenAPI document with an exact local Redocly CLI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from tooling.contracts.generate_web_schema import load_local_schema
from tooling.dev.toolchain import node_executable

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SNAPSHOT = _REPO_ROOT / "contracts/openapi/v1.json"
_DEFAULT_CONFIG = _REPO_ROOT / ".redocly.yaml"
_REDOCLY_PACKAGE = _REPO_ROOT / "node_modules/@redocly/cli/package.json"
_REDOCLY_CLI = _REPO_ROOT / "node_modules/@redocly/cli/bin/cli.js"
EXPECTED_REDOCLY_VERSION = "2.51.1"


class RedoclyError(RuntimeError):
    """The fixed local Redocly lint contract could not run."""


def run_lint(*, snapshot_path: Path, config_path: Path) -> None:
    """Run recommended-strict without bunx, URLs, telemetry, or update checks."""
    load_local_schema(snapshot_path)
    if not config_path.is_file():
        raise RedoclyError(f"Redocly config is missing: {config_path}")
    if not _REDOCLY_PACKAGE.is_file() or not _REDOCLY_CLI.is_file():
        raise RedoclyError(
            "".join(
                (
                    "@redocly/cli is not installed locally. Run the repository's ",
                    "frozen/offline bootstrap; this pipeline never invokes bunx or ",
                    "downloads tools.",
                )
            )
        )
    package = json.loads(_REDOCLY_PACKAGE.read_text(encoding="utf-8"))
    version = package.get("version")
    if version != EXPECTED_REDOCLY_VERSION:
        raise RedoclyError(
            "Redocly version mismatch: "
            + f"expected {EXPECTED_REDOCLY_VERSION}, found {version!r}"
        )
    node = node_executable(_REPO_ROOT)
    environment = os.environ.copy()
    environment.update(
        {
            "CI": "1",
            "NO_COLOR": "1",
            "NO_UPDATE_NOTIFIER": "1",
            "REDOCLY_TELEMETRY": "off",
        }
    )
    subprocess.run(  # noqa: S603 -- exact Node and local pinned CLI paths
        [
            node,
            str(_REDOCLY_CLI),
            "lint",
            str(snapshot_path.resolve(strict=True)),
            "--config",
            str(config_path.resolve(strict=True)),
        ],
        cwd=_REPO_ROOT,
        env=environment,
        check=True,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, default=_DEFAULT_SNAPSHOT)
    parser.add_argument("--config", type=Path, default=_DEFAULT_CONFIG)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Lint the one local canonical snapshot."""
    arguments = _parser().parse_args(argv)
    try:
        run_lint(snapshot_path=arguments.schema, config_path=arguments.config)
    except (RedoclyError, OSError, subprocess.CalledProcessError) as error:
        sys.stderr.write(f"{error}\n")
        return 1
    sys.stdout.write(
        f"Redocly recommended-strict passed: {arguments.schema.resolve()}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
