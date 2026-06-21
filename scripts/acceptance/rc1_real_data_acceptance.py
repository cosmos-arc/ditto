"""RC-1 release acceptance runner."""

from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
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


def _run(name: str, command: list[str]) -> CommandResult:
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
    )
    return CommandResult(
        name=name,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout
        if name == "maturity-status"
        else completed.stdout[-COMMAND_OUTPUT_LIMIT:],
        stderr=completed.stderr[-COMMAND_OUTPUT_LIMIT:],
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
                "packages/application/tests/integration/test_manual_signal_fill_deviation_e2e.py",
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
                    "packages/apps/tests/e2e/test_real_data_stock_selection_pipeline.py",
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


def main() -> int:
    """Run the RC-1 acceptance command set and write a JSON report."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-data", action="store_true")
    parser.add_argument("--require-promoted", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    results = [
        _run(name, command)
        for name, command in _commands(args.real_data, args.require_promoted)
    ]
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
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(
        orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
