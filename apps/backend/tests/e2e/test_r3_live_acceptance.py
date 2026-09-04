"""Task 18 real-data R3 acceptance over one explicitly isolated live root."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from ditto_apps.scripts.r3_live_acceptance_driver import (
    run_live_backup_restore,
    run_live_golden_lane,
    run_live_governance_lifecycle,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("DITTO_RUN_REAL_DATA_ACCEPTANCE") != "1",
        reason="real-data acceptance requires DITTO_RUN_REAL_DATA_ACCEPTANCE=1",
    ),
]


def _required_path(name: str, *, must_exist: bool) -> Path:
    value = os.environ.get(name)
    if value is None:
        pytest.fail(f"{name} is required for isolated live acceptance")
    path = Path(value).expanduser().resolve(strict=must_exist)
    if not path.is_absolute():
        pytest.fail(f"{name} must resolve to an absolute path")
    return path


def test_stock_live_golden_lane() -> None:
    """Run the stock primary lane through one real-data immutable review packet."""
    result = run_live_golden_lane(
        lane="stock",
        data_root=_required_path("DITTO_DATA_ROOT", must_exist=True),
        evidence_root=_required_path(
            "DITTO_R3_LIVE_EVIDENCE_ROOT",
            must_exist=False,
        ),
        purpose="backend-stock",
    )

    assert result.status == "completed"
    assert result.eligible_month_count >= 96
    assert result.factor_contribution_count > 0
    assert result.industry_exposure_count > 0
    assert result.size_exposure_count > 0
    assert result.r2_live_gate == "pass"


def test_etf_live_golden_lane() -> None:
    """Run the ETF proving lane through one real-data immutable review packet."""
    result = run_live_golden_lane(
        lane="etf",
        data_root=_required_path("DITTO_DATA_ROOT", must_exist=True),
        evidence_root=_required_path(
            "DITTO_R3_LIVE_EVIDENCE_ROOT",
            must_exist=False,
        ),
        purpose="backend-etf",
    )

    assert result.status == "completed"
    assert result.eligible_month_count >= 96
    assert result.holdout_duplicate_blocked
    assert result.r2_live_gate == "pass"


def test_live_publish_r1_and_reactivate() -> None:
    """Publish both reviewed candidates, prove R1 active truth, then return to v1."""
    result = run_live_governance_lifecycle(
        data_root=_required_path("DITTO_DATA_ROOT", must_exist=True),
        evidence_root=_required_path(
            "DITTO_R3_LIVE_EVIDENCE_ROOT",
            must_exist=True,
        ),
        actor="chevy",
    )

    assert result.lanes == ("stock", "etf")
    assert all(
        item.published_active_version == item.candidate_version
        for item in result.results
    )
    assert all(item.reactivated_active_version == 1 for item in result.results)


def test_isolated_live_backup_restore() -> None:
    """Verify metadata, research DB, pinned artifacts, and domain restore parity."""
    result = run_live_backup_restore(
        data_root=_required_path("DITTO_DATA_ROOT", must_exist=True),
        evidence_root=_required_path(
            "DITTO_R3_LIVE_EVIDENCE_ROOT",
            must_exist=True,
        ),
        backup_root=_required_path("DITTO_R3_LIVE_BACKUP_ROOT", must_exist=False),
        restore_root=_required_path("DITTO_R3_LIVE_RESTORE_ROOT", must_exist=False),
    )

    assert result.metadata_hash_matches
    assert result.research_hash_matches
    assert result.artifact_hash_matches
    assert result.domain_matches
