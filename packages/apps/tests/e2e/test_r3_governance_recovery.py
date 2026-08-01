"""Task 17 governance, hard-gate, and isolated recovery wrappers."""

# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest
from packages.application.tests.integration.test_r3_governance_recovery_golden import (
    test_active_pointer_switches_to_new_version as _pointer_swap,
)
from packages.application.tests.integration.test_r3_governance_recovery_golden import (
    test_reactivate_switches_pointer_back_with_correct_cas as _reactivate,
)
from packages.application.tests.integration.test_r3_governance_recovery_golden import (
    test_review_decisions_are_append_only as _append_only,
)
from packages.application.tests.integration.test_r3_governance_recovery_golden import (
    test_stale_pointer_revision_is_mapped_to_typed_command_error as _stale_cas,
)
from packages.apps.tests.integration.api import (
    test_r3_strategy_publish_api_integration as publish_support,
)
from packages.apps.tests.integration.research.test_r3_backup_restore import (
    test_r3_backup_restore_preserves_governance_holdout_and_pinned_packet as _backup_restore,
)

pytestmark = [pytest.mark.e2e, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _inline_strategy_route_thread_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run_inline(
        function: object,
        /,
        *args: object,
        **kwargs: object,
    ) -> object:
        assert callable(function)
        return function(*args, **kwargs)

    monkeypatch.setattr(
        "ditto_apps.api.routes.strategy.run_blocking",
        run_inline,
    )


def test_fixture_governance_recovery(tmp_path: Path) -> None:
    """Prove append-only history, pointer CAS, rollback, and typed conflict."""
    case_roots = tuple(
        tmp_path / name
        for name in ("append-only", "pointer-swap", "reactivate", "stale-cas")
    )
    for case_root in case_roots:
        case_root.mkdir()
    _append_only(case_roots[0])
    _pointer_swap(case_roots[1])
    _reactivate(case_roots[2])
    _stale_cas(case_roots[3])


@pytest.mark.asyncio
async def test_fixture_hard_gate_paths_are_zero_write(tmp_path: Path) -> None:
    """Call both public mutation paths and prove the fixture gate writes nothing."""
    submit = publish_support._build_harness(
        tmp_path / "submit-review",
        r2_live_gate=None,
        prepare_candidate_review=False,
    )
    try:
        pointer_before = submit.governance_store.get_active_pointer(submit.strategy_id)
        state_before = submit.governance_store.get_state(
            submit.strategy_id,
            submit.candidate_version,
        )
        history_before = publish_support._governance_history(
            submit.governance_pool,
            submit.strategy_id,
        )
        response = await publish_support._submit_review(
            submit,
            bundle_hash=str(submit.packet.bundle_hash),
            idempotency_key="r3-acceptance-submit-hard-gate",
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "HARD_GATE_FAILED"
        assert (
            submit.governance_store.get_active_pointer(submit.strategy_id)
            == pointer_before
        )
        assert (
            submit.governance_store.get_state(
                submit.strategy_id,
                submit.candidate_version,
            )
            == state_before
        )
        assert (
            publish_support._governance_history(
                submit.governance_pool,
                submit.strategy_id,
            )
            == history_before
        )
    finally:
        await submit.close()

    publish = publish_support._build_harness(tmp_path / "publish-promotion")
    try:
        await publish_support._assert_typed_zero_write_rejection(
            publish,
            expected_status=422,
            expected_error_code="hard_gate_blocked",
        )
    finally:
        await publish.close()


def test_fixture_backup_restore_preserves_domain_identity(tmp_path: Path) -> None:
    """Restore metadata, research state, pinned artifacts, and packet hashes."""
    _backup_restore(tmp_path)
