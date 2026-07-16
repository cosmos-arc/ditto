"""Persisted ingestion evidence policy tests for quality batches."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from ditto_application.processes.quality.evidence_policy import (
    verify_batch_ingestion_evidence,
)


def _exact_payload() -> dict[str, object]:
    return {
        "dataset": "stock_daily",
        "trade_date": "2026-07-16",
        "status": "success",
        "checksum": "sha256:stock",
        "row_count": 5_000,
        "quality_evidence": {
            "kind": "write_time_l1_l2",
            "status": "passed",
            "source": "tushare",
            "trade_date": "2026-07-16",
            "levels": ["l1", "l2"],
            "row_count": 5_000,
            "checksum": "sha256:stock",
        },
    }


def _sparse_payload(*, quality_source: str = "tushare") -> dict[str, object]:
    snapshot_id = "snapshot:tushare:balance_sheet:2026-07-01:sha256:sheet:quality=l1-l2"
    return {
        "dataset": "balance_sheet",
        "trade_date": "2026-07-16",
        "status": "success",
        "checksum": None,
        "row_count": 0,
        "snapshot_evidence": {
            "kind": "persisted_asof_catalog_snapshot",
            "source": "tushare",
            "signal_date": "2026-07-16",
            "checked_at": "2026-07-16T20:00:00+00:00",
            "effective_partition_date": "2026-07-01",
            "source_snapshot_id": snapshot_id,
            "source_snapshot_ids": [snapshot_id],
            "row_count": 75,
            "freshness_sla_hours": 1080,
        },
        "quality_evidence": {
            "kind": "no_new_rows",
            "status": "not_applicable_no_new_rows",
            "source": quality_source,
            "trade_date": "2026-07-16",
            "levels": [],
            "row_count": 0,
            "checksum": None,
        },
    }


@pytest.mark.unit
def test_exact_evidence_requires_matching_durable_catalog_and_log() -> None:
    verifier = MagicMock()
    verifier.verify_exact_date.return_value = False

    decision = verify_batch_ingestion_evidence(
        _exact_payload(),
        dataset="stock_daily",
        trade_date="2026-07-16",
        verifier=verifier,
    )

    assert decision.evidence is None
    assert decision.error == "INGESTION_COMPONENT_QUALITY_EVIDENCE_INVALID"
    verifier.verify_exact_date.assert_called_once_with(
        dataset="stock_daily",
        source="tushare",
        trade_date="2026-07-16",
        checksum="sha256:stock",
        row_count=5_000,
    )


@pytest.mark.unit
def test_sparse_evidence_verifies_every_asof_snapshot_component() -> None:
    snapshot_id = "snapshot:tushare:balance_sheet:2026-07-01:sha256:sheet:quality=l1-l2"
    payload = _sparse_payload()
    verifier = MagicMock()
    verifier.verify_asof_snapshot.return_value = False

    decision = verify_batch_ingestion_evidence(
        payload,
        dataset="balance_sheet",
        trade_date="2026-07-16",
        verifier=verifier,
    )

    assert decision.evidence is None
    assert decision.error == "PIT_COMPONENT_QUALITY_EVIDENCE_INVALID"
    verifier.verify_asof_snapshot.assert_called_once_with(
        dataset="balance_sheet",
        source="tushare",
        signal_date="2026-07-16",
        expected_snapshot_ids=(snapshot_id,),
        expected_row_count=75,
    )


@pytest.mark.unit
def test_sparse_evidence_rejects_quality_source_snapshot_source_mismatch() -> None:
    verifier = MagicMock()
    verifier.verify_asof_snapshot.return_value = True

    decision = verify_batch_ingestion_evidence(
        _sparse_payload(quality_source="akshare"),
        dataset="balance_sheet",
        trade_date="2026-07-16",
        verifier=verifier,
    )

    assert decision.evidence is None
    assert decision.error == "PIT_COMPONENT_QUALITY_EVIDENCE_INVALID"
    verifier.verify_asof_snapshot.assert_not_called()


@pytest.mark.unit
def test_exact_durable_evidence_returns_normalized_application_evidence() -> None:
    verifier = MagicMock()
    verifier.verify_exact_date.return_value = True

    decision = verify_batch_ingestion_evidence(
        _exact_payload(),
        dataset="stock_daily",
        trade_date="2026-07-16",
        verifier=verifier,
    )

    assert decision.error is None
    assert decision.evidence is not None
    assert decision.evidence.quality_evidence == {
        "kind": "persisted_ingestion_l1_l2",
        "status": "passed",
        "source": "tushare",
        "trade_date": "2026-07-16",
        "levels": ["l1", "l2"],
        "row_count": 5_000,
        "checksum": "sha256:stock",
    }


@pytest.mark.unit
def test_missing_explicit_write_quality_evidence_fails_closed() -> None:
    payload = _exact_payload()
    payload.pop("quality_evidence")

    decision = verify_batch_ingestion_evidence(
        payload,
        dataset="stock_daily",
        trade_date="2026-07-16",
        verifier=MagicMock(),
    )

    assert decision.evidence is None
    assert decision.error == "INGESTION_QUALITY_EVIDENCE_MISSING"
