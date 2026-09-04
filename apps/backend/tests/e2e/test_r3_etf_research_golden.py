"""Task 17 ETF proving-lane deterministic golden wrapper."""

# ruff: noqa: E402

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest
from packages.application.tests.integration import (
    r3_evidence_closure_support as golden_support,
)
from packages.application.tests.integration.test_r3_evidence_closure_golden import (
    test_r3_evidence_closure_drives_review_packet_and_completed_status as _run_golden,
)

pytestmark = [pytest.mark.e2e, pytest.mark.integration]


def test_etf_proving_lane_closes_evidence_and_blocks_live_promotion(
    tmp_path: Path,
) -> None:
    """Exercise the real ETF pipeline through immutable review evidence."""
    _run_golden(tmp_path, golden_support.ETF_GOLDEN_LANE, False)
