"""Task 17 literal 128-candidate scheduler acceptance wrapper."""

# ruff: noqa: E402

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest
from packages.application.tests.integration.test_r3_scheduler_capacity import (
    test_128_candidate_real_preflight_launches_at_registered_run_ceiling as _preflight,
)
from packages.application.tests.integration.test_r3_scheduler_capacity import (
    test_128_candidates_survive_restart_without_duplicate_claims as _restart,
)

pytestmark = [pytest.mark.e2e, pytest.mark.integration]


def test_literal_128_candidate_capacity_survives_restart(tmp_path: Path) -> None:
    """Prove both the registered ceiling and a four-worker restart drain."""
    _preflight(tmp_path / "preflight")
    _restart(tmp_path / "restart", 4)
