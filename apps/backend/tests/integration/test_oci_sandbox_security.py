"""Physical OrbStack acceptance for the hardened generated-code sandbox."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from ditto_apps.scripts.r5_sandbox_live_acceptance import run_live_acceptance


@pytest.mark.sandbox_live
def test_orbstack_hardened_sandbox_blocks_the_complete_attack_suite() -> None:
    repo_root = Path(__file__).parents[4]

    report = run_live_acceptance(repo_root=repo_root)

    assert report["status"] == "passed"
    assert report["release_gate_passed"] is True
    assert report["attack_case_count"] == 11
    attack_results = report["attack_results"]
    assert isinstance(attack_results, list)
    assert all(
        isinstance(case, Mapping) and case.get("passed") is True
        for case in attack_results
    )
    fresh_container_check = report["fresh_container_check"]
    concurrency_check = report["concurrency_check"]
    assert isinstance(fresh_container_check, Mapping)
    assert isinstance(concurrency_check, Mapping)
    assert fresh_container_check["passed"] is True
    assert concurrency_check["passed"] is True
    assert report["containers_remaining"] == []
