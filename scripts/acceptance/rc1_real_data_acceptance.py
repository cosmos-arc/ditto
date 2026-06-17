"""RC-1 release acceptance runner."""

from __future__ import annotations

import argparse
import os
import subprocess
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import orjson


@dataclass(frozen=True)
class CommandResult:
    """Captured result for one release acceptance command."""

    name: str
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def passed(self) -> bool:
        """Return whether the command exited successfully."""
        return self.returncode == 0


def _run(
    name: str,
    command: list[str],
    *,
    env: Mapping[str, str] | None = None,
) -> CommandResult:
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )
    return CommandResult(
        name=name,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout[-8000:],
        stderr=completed.stderr[-8000:],
    )


def _commands(real_data: bool, require_promoted: bool) -> list[tuple[str, list[str]]]:
    commands = [
        ("check", ["pixi", "run", "-e", "dev", "check"]),
        (
            "targeted-golden",
            [
                "pixi",
                "run",
                "-e",
                "dev",
                "pytest",
                "packages/apps/tests/integration/test_golden_e2e.py",
                "packages/apps/tests/integration/test_stock_selection_golden_e2e.py",
                "packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py",
                "-q",
                "--no-cov",
            ],
        ),
        (
            "promotion-evidence-stock-daily",
            [
                "pixi",
                "run",
                "-e",
                "dev",
                "python",
                "-m",
                "ditto_apps.cli.main",
                "ops",
                "promotion-collect",
                "stock_daily",
            ],
        ),
    ]
    if real_data:
        commands.append(
            (
                "real-data-e2e",
                [
                    "pixi",
                    "run",
                    "-e",
                    "dev",
                    "pytest",
                    "packages/apps/tests/e2e/test_real_data_pipeline.py",
                    "-m",
                    "e2e",
                    "--no-cov",
                ],
            )
        )
    if require_promoted:
        commands.append(
            (
                "maturity-status",
                [
                    "pixi",
                    "run",
                    "-e",
                    "dev",
                    "python",
                    "-m",
                    "ditto_apps.cli.main",
                    "ops",
                    "status",
                    "--json",
                ],
            )
        )
    return commands


def _synthetic_acceptance_env(output: Path) -> dict[str, str]:
    data_root = (output.parent / "runtime").resolve()
    return os.environ | {
        "DITTO_DATA_ROOT": data_root.as_posix(),
        "SQLITE_PATH": (data_root / "metadata" / "metadata.sqlite").as_posix(),
        "DUCKDB_PATH": (data_root / "db" / "ditto.duckdb").as_posix(),
    }


def main() -> int:
    """Run the RC-1 acceptance command set and write a JSON report."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-data", action="store_true")
    parser.add_argument("--require-promoted", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    synthetic_env = (
        None
        if args.real_data or args.require_promoted
        else _synthetic_acceptance_env(output)
    )
    results = [
        _run(
            name,
            command,
            env=synthetic_env if name == "promotion-evidence-stock-daily" else None,
        )
        for name, command in _commands(args.real_data, args.require_promoted)
    ]
    payload = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "passed": all(result.passed for result in results),
        "results": [asdict(result) | {"passed": result.passed} for result in results],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(
        orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
