"""Integration contract for the acceptance runner's two-run idempotency gate."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from ditto_application.processes.ingestion.r2_preflight import (
    R2AcceptanceRuntimeEvidence,
)
from ditto_apps.scripts.r2_data_acceptance import (
    R2IdempotencySnapshot,
    run_fixture_acceptance,
    run_live_acceptance,
    verify_consecutive_idempotency,
)


@dataclass
class _FixtureIngestion:
    """Small deterministic chunk store with observable durable write attempts."""

    rewrite_completed_chunk: bool = False

    def __post_init__(self) -> None:
        self.payloads: dict[str, str] = {}
        self.snapshot_ids: set[str] = set()
        self.write_attempt_count = 0

    def run(self) -> None:
        chunk_id = "chunk:tushare:stock_daily:2026-07-17"
        if chunk_id in self.payloads and not self.rewrite_completed_chunk:
            return
        self.write_attempt_count += 1
        self.payloads[chunk_id] = "sha256:payload"
        self.snapshot_ids.add("snapshot:tushare:stock_daily:sha256:payload")

    def snapshot(self) -> R2IdempotencySnapshot:
        return R2IdempotencySnapshot(
            durable_identity_count=len(self.payloads),
            write_attempt_count=self.write_attempt_count,
            snapshot_ids=tuple(sorted(self.snapshot_ids)),
        )


@pytest.mark.integration
def test_second_run_has_no_duplicate_writes_and_same_snapshots() -> None:
    ingestion = _FixtureIngestion()

    report = verify_consecutive_idempotency(
        run=ingestion.run,
        observe=ingestion.snapshot,
    )

    assert report.passed is True
    assert report.second_run_write_attempts == 0
    assert report.first.durable_identity_count == 1
    assert report.second.durable_identity_count == 1
    assert report.first.snapshot_ids == report.second.snapshot_ids


@pytest.mark.integration
def test_rewriting_completed_chunk_fails_acceptance() -> None:
    ingestion = _FixtureIngestion(rewrite_completed_chunk=True)

    report = verify_consecutive_idempotency(
        run=ingestion.run,
        observe=ingestion.snapshot,
    )

    assert report.passed is False
    assert report.second_run_write_attempts == 1
    assert "second_run_wrote_durable_state" in report.reason_codes


@pytest.mark.integration
def test_deterministic_fixture_acceptance_covers_all_release_gates() -> None:
    report = run_fixture_acceptance()

    assert report.status == "ready"
    assert report.preflight.contract_count == 19
    assert report.recoverability.passed is True
    assert report.idempotency is not None
    assert report.idempotency.passed is True


@pytest.mark.integration
def test_live_mode_without_credentials_or_evidence_is_configuration_blocked(
    mocker,
) -> None:
    container = mocker.MagicMock()
    container.get.return_value = R2AcceptanceRuntimeEvidence(
        credential_sources=frozenset(),
        license_records=(),
    )
    mocker.patch(
        "ditto_apps.scripts.r2_data_acceptance.make_app_container",
        return_value=container,
    )

    report = run_live_acceptance(evidence_path=None)

    assert report.status == "configuration_blocked"
    assert "entitlement_unverified" in report.reason_codes
    assert "performance_evidence_missing" in report.reason_codes
    assert "recoverability_evidence_missing" in report.reason_codes
    assert "idempotency_evidence_missing" in report.reason_codes
    assert "token" not in repr(report).casefold()
    assert "secret" not in repr(report).casefold()
    container.close.assert_called_once()
