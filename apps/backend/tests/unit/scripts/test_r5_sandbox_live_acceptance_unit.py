"""Deterministic report contracts for the physical R5 sandbox acceptance."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import orjson
from ditto_apps.scripts import r5_sandbox_live_acceptance as subject
from ditto_apps.scripts.r5_sandbox_live_acceptance import (
    finalize_report,
    validate_live_report,
    verify_report,
)

REPO_ROOT = Path(__file__).parents[5]


def test_live_sandbox_report_hash_covers_every_result_and_identity() -> None:
    draft: dict[str, object] = {
        "schema_id": "r5-sandbox-live-acceptance",
        "schema_version": 1,
        "approval_id": "A3-test",
        "image_digest": "1" * 64,
        "attack_results": [{"name": "network", "passed": True}],
        "release_gate_passed": True,
        "status": "passed",
    }

    report = finalize_report(draft)

    assert verify_report(report) is True
    mutated = deepcopy(report)
    mutated["attack_results"] = [{"name": "network", "passed": False}]
    assert verify_report(mutated) is False


def test_live_report_validator_recomputes_every_execution_attestation() -> None:
    report_path = REPO_ROOT / "docs/evidence/r5/release/sandbox-live-status.json"
    report = orjson.loads(report_path.read_bytes())

    assert validate_live_report(report) is True
    report["attack_results"][0]["manifest"]["attestation_hash"] = "0" * 64
    forged = finalize_report(report)
    assert verify_report(forged) is True
    assert validate_live_report(forged) is False


def test_host_mount_probe_is_portable_and_contains_no_developer_path() -> None:
    host_mount = next(
        case for case in subject._attack_cases() if case.name == "host_mount"
    )

    assert "/Users/" not in host_mount.source
    for generic_mount in ("/workspace", "/repo", "/host", "/mnt/host"):
        assert generic_mount in host_mount.source
