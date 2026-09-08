"""Prove sharded evidence cannot lose tests or combine stale coverage."""

import hashlib
import json
from pathlib import Path

import pytest

from tooling.quality.test_shards import ShardError, partition, verify_manifests


def test_partition_is_complete_and_spreads_adjacent_capacity_cases() -> None:
    inventory = [(f"capacity.py::test_restart[{n}]", n % 2 == 0) for n in range(12)]
    parts = [partition(inventory, i, 4) for i in range(4)]
    assert sorted(item for part in parts for item in part) == sorted(inventory)
    assert all(len(part) == 3 for part in parts)


@pytest.mark.parametrize(
    "corruption",
    [
        None,
        "missing",
        "duplicate",
        "commit",
        "selection",
        "inventory",
        "coverage",
        "status",
    ],
)
def test_combine_rejects_incomplete_or_stale_proof(
    tmp_path: Path, corruption: str | None
) -> None:
    inventory = [("a.py::test_a", False), ("b.py::test_b", True)]
    for index in range(2):
        data = tmp_path / f".coverage.shard-{index}"
        data.write_bytes(b"coverage data")
        report = {
            "index": index,
            "count": 2,
            "commit": "current",
            "status": "passed",
            "inventory": inventory,
            "selected": partition(inventory, index, 2),
            "coverage_sha256": hashlib.sha256(data.read_bytes()).hexdigest(),
        }
        if index == 1:
            if corruption == "missing":
                continue
            if corruption == "duplicate":
                report["index"] = 0
            if corruption == "commit":
                report["commit"] = "stale"
            if corruption == "selection":
                report["selected"] = []
            if corruption == "inventory":
                report["inventory"] = [["different", False]]
            if corruption == "coverage":
                data.write_bytes(b"changed")
            if corruption == "status":
                report["status"] = "failed"
        (tmp_path / f"shard-{index}.json").write_text(json.dumps(report))
    if corruption:
        with pytest.raises(ShardError):
            verify_manifests(tmp_path, "current", 2)
    else:
        assert len(verify_manifests(tmp_path, "current", 2)) == 2


def test_real_shards_preserve_serial_lane_and_merge_coverage(tmp_path: Path) -> None:
    """Exercise actual pytest selection, workers, coverage files and aggregation."""
    import os
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[3]
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\nmarkers=["serial: process isolated"]\n'
        '[tool.coverage.run]\nbranch=true\nsource=["calc"]\n'
    )
    (tmp_path / "calc.py").write_text(
        'def classify(n):\n    return "positive" if n > 0 else "other"\n'
    )
    (tmp_path / "test_calc.py").write_text(
        "import os, pytest\nfrom calc import classify\n"
        'def test_positive():\n    assert classify(1) == "positive"\n'
        "@pytest.mark.serial\ndef test_serial():\n"
        '    assert "PYTEST_XDIST_WORKER" not in os.environ\n'
        '    assert classify(0) == "other"\n'
    )
    environment = {
        **{
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("COV", "PYTEST_XDIST"))
        },
        "PYTHONPATH": f"{repo}{os.pathsep}{tmp_path}",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTEST_PLUGINS": "pytest_cov.plugin,xdist.plugin",
    }
    output = tmp_path / "build" / "test-shards"
    for mode, index in [("run", 0), ("run", 1), ("combine", 0)]:
        subprocess.run(  # noqa: S603 - fixed modules over an isolated synthetic suite
            [
                sys.executable,
                "-m",
                "tooling.quality.test_shards",
                mode,
                "--count",
                "2",
                "--index",
                str(index),
                "--commit",
                "current",
                "--output",
                str(output.relative_to(tmp_path)),
            ],
            cwd=tmp_path,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
    report = json.loads((tmp_path / "coverage.json").read_text())
    assert report["totals"]["missing_lines"] == 0
    assert report["totals"]["missing_branches"] == 0


def test_generated_contract_ids_are_selected_after_collection(tmp_path: Path) -> None:
    """Schemathesis IDs must survive selection and missing IDs must fail closed."""
    import os
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[3]
    test_file = "apps/backend/tests/contract/test_openapi_conformance.py"
    selection = tmp_path / "selected.txt"
    selection.write_text(
        test_file
        + "::test_side_effect_free_system_endpoints_conform_to_openapi[GET /]\n"
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COV", "PYTEST_XDIST"))
    }
    environment["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "addopts=",
        "--import-mode=importlib",
        "-n",
        "2",
        "-q",
        "--no-cov",
        "-p",
        "tooling.quality.pytest_inventory",
        "--selection-input",
        str(selection),
        test_file,
    ]
    result = subprocess.run(  # noqa: S603 - fixed repository contract test
        command, cwd=repo, env=environment, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    selection.write_text(test_file + "::missing_generated_case\n")
    rejected = subprocess.run(  # noqa: S603 - same test with invalid selection
        command, cwd=repo, env=environment, capture_output=True, text=True, check=False
    )
    assert rejected.returncode != 0
