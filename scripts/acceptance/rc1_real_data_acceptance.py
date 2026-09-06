"""RC-1 release acceptance runner."""

from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import orjson

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

validate_maturity_status_from_stdout = importlib.import_module(
    "scripts.acceptance.rc1_requirements"
).validate_maturity_status_from_stdout

COMMAND_OUTPUT_LIMIT = 8000
TEST_COMMANDS = frozenset({"check", "targeted-golden", "real-data-e2e"})


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
    stdout = (
        completed.stdout
        if name == "maturity-status"
        else completed.stdout[-COMMAND_OUTPUT_LIMIT:]
    )
    return CommandResult(
        name=name,
        command=command,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=completed.stderr[-COMMAND_OUTPUT_LIMIT:],
    )


def _commands(real_data: bool, require_promoted: bool) -> list[tuple[str, list[str]]]:
    commands = [
        ("check", ["task", "check"]),
        (
            "targeted-golden",
            [
                "uv",
                "run",
                "--no-sync",
                "pytest",
                "apps/backend/tests/integration/test_golden_e2e.py",
                "apps/backend/tests/integration/test_stock_selection_golden_e2e.py",
                "apps/backend/tests/integration/test_stock_selection_signal_package_e2e.py",
                "packages/application/tests/integration/test_manual_signal_fill_deviation_e2e.py",
                "-q",
                "--no-cov",
            ],
        ),
        (
            "promotion-evidence-stock-daily",
            [
                "uv",
                "run",
                "--no-sync",
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
                    "uv",
                    "run",
                    "--no-sync",
                    "pytest",
                    "apps/backend/tests/e2e/test_real_data_pipeline.py",
                    "apps/backend/tests/e2e/test_real_data_stock_selection_pipeline.py",
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
                    "uv",
                    "run",
                    "--no-sync",
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
        "ENVIRONMENT": "testing",
        "DITTO_DATA_ROOT": data_root.as_posix(),
        "SQLITE_PATH": (data_root / "metadata" / "metadata.sqlite").as_posix(),
        "DUCKDB_PATH": (data_root / "db" / "ditto.duckdb").as_posix(),
    }


def _test_acceptance_env(output: Path) -> dict[str, str]:
    """Return an isolated env for code-quality tests inside real-data acceptance."""
    data_root = (output.parent / "test-runtime").resolve()
    env = dict(os.environ)
    env.update(
        {
            "ENVIRONMENT": "testing",
            "DITTO_DATA_ROOT": data_root.as_posix(),
        }
    )
    env.pop("SQLITE_PATH", None)
    env.pop("DUCKDB_PATH", None)
    return env


def _env_for_command(
    name: str,
    *,
    output: Path,
    synthetic_env: dict[str, str] | None,
) -> dict[str, str] | None:
    if synthetic_env is not None:
        return synthetic_env
    if name in TEST_COMMANDS:
        return _test_acceptance_env(output)
    return None


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
    results = []
    for name, command in _commands(args.real_data, args.require_promoted):
        results.append(
            _run(
                name,
                command,
                env=_env_for_command(
                    name,
                    output=output,
                    synthetic_env=synthetic_env,
                ),
            )
        )
    business_failures: list[str] = []
    if args.require_promoted:
        for result in results:
            if result.name == "maturity-status":
                validation = validate_maturity_status_from_stdout(result.stdout)
                business_failures.extend(validation.failures)
    payload = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "business_failures": business_failures,
        "passed": all(result.passed for result in results) and not business_failures,
        "results": [asdict(result) | {"passed": result.passed} for result in results],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(
        orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
