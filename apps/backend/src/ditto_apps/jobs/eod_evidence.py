"""Translate ingestion and DQ results into EOD dataset readiness evidence."""

from collections.abc import Mapping
from typing import Any, cast

from ditto_application.processes.execution.eod_coordinator import DatasetReadiness
from ditto_application.processes.ingestion.result_handler import (
    validated_asof_snapshot_evidence,
)

__all__ = ["dataset_states_from_ingestion"]


def dataset_states_from_ingestion(  # noqa: C901, PLR0912, PLR0915 - evidence precedence
    ingestion_result: dict[str, object],
    *,
    signal_date: str,
) -> dict[str, DatasetReadiness]:
    """Map persisted ingestion/DQ evidence to the coordinator's narrow input."""
    ingestion_date = ingestion_result.get("trade_date")
    rows: dict[str, dict[str, object]] = {}
    for section_name in ("t0_results", "t1_results"):
        raw_section = ingestion_result.get(section_name)
        if not isinstance(raw_section, dict):
            continue
        section = cast(dict[object, object], raw_section)
        for dataset, raw_row in section.items():
            if isinstance(dataset, str) and isinstance(raw_row, dict):
                rows[dataset] = cast(dict[str, object], raw_row)

    dq_rows: dict[str, dict[str, object]] = {}
    dq_date: object = None
    raw_dq = ingestion_result.get("dqc_results")
    if isinstance(raw_dq, dict):
        dq_payload = cast(dict[object, object], raw_dq)
        dq_date = dq_payload.get("trade_date")
        raw_results = dq_payload.get("results_by_dataset")
        if isinstance(raw_results, dict):
            results = cast(dict[object, object], raw_results)
            for dataset, raw_row in results.items():
                if isinstance(dataset, str) and isinstance(raw_row, dict):
                    dq_rows[dataset] = cast(dict[str, object], raw_row)

    states: dict[str, DatasetReadiness] = {}
    for dataset, row in rows.items():
        raw_status = str(row.get("status", "unknown"))
        dq_row = dq_rows.get(dataset)
        row_date = row.get("trade_date")
        snapshot_id = _ingestion_snapshot_id(row)
        if raw_status == "failed":
            status = "missing"
            detail = row.get("error") or row.get("message") or "unknown error"
            reason_value = f"INGESTION_FAILED: {detail}"
        elif raw_status == "stale":
            status = "stale"
            reason_value = "STALE_DATASET"
        elif raw_status in {"success", "skipped"}:
            if ingestion_date != signal_date:
                status = "stale"
                reason_value = f"INGESTION_DATE_MISMATCH:{ingestion_date or 'MISSING'}"
            elif row_date != signal_date:
                status = "stale"
                reason_value = f"INGESTION_DATE_MISMATCH:{row_date or 'MISSING'}"
            elif snapshot_id is None:
                status = "unknown"
                reason_value = "SNAPSHOT_ID_MISSING"
            elif dq_date != signal_date:
                status = "unknown"
                reason_value = f"DQ_DATE_MISMATCH:{dq_date or 'MISSING'}"
            elif dq_row is None:
                status = "unknown"
                reason_value = "DQ_EVIDENCE_MISSING"
            elif dq_row.get("passed") is False:
                status = "dq_failed"
                detail = dq_row.get("error") or "data quality check failed"
                reason_value = f"DQ_FAILED: {detail}"
            elif dq_row.get("passed") is not True:
                status = "unknown"
                reason_value = "DQ_EVIDENCE_INVALID"
            else:
                mismatch_reason = _dq_snapshot_mismatch_reason(
                    ingestion_row=row,
                    dq_row=dq_row,
                    signal_date=signal_date,
                )
                if mismatch_reason is not None:
                    status = "unknown"
                    reason_value = mismatch_reason
                else:
                    status = "ready"
                    reason_value = ""
        else:
            status = "unknown"
            reason_value = f"INGESTION_STATUS_UNKNOWN: {raw_status}"
        states[dataset] = DatasetReadiness(
            dataset=dataset,
            status=cast(Any, status),
            snapshot_id=snapshot_id,
            reason=str(reason_value),
        )
    return states


def _dq_snapshot_mismatch_reason(
    *,
    ingestion_row: dict[str, object],
    dq_row: dict[str, object],
    signal_date: str,
) -> str | None:
    """Validate that a DQ pass attests to the exact persisted snapshot."""
    raw_evidence = dq_row.get("evidence")
    reason: str | None = None
    if not isinstance(raw_evidence, dict):
        reason = "DQ_SNAPSHOT_EVIDENCE_MISSING"
    else:
        evidence = cast(dict[object, object], raw_evidence)
        if evidence.get("kind") == "persisted_asof_catalog_snapshot":
            return _asof_snapshot_mismatch_reason(
                ingestion_row=ingestion_row,
                dq_evidence=evidence,
                signal_date=signal_date,
            )
        evidence_date = evidence.get("trade_date")
        row_count = ingestion_row.get("row_count")
        evidence_row_count = evidence.get("row_count")
        if evidence.get("kind") != "persisted_ingestion_l1_l2":
            reason = "DQ_EVIDENCE_INVALID"
        elif evidence_date != signal_date:
            reason = f"DQ_EVIDENCE_DATE_MISMATCH:{evidence_date or 'MISSING'}"
        elif evidence.get("checksum") != ingestion_row.get("checksum"):
            reason = "DQ_CHECKSUM_MISMATCH"
        elif not _is_non_negative_int(row_count):
            reason = "INGESTION_ROW_COUNT_INVALID"
        elif not _is_non_negative_int(evidence_row_count):
            reason = "DQ_EVIDENCE_INVALID"
        elif evidence_row_count != row_count:
            reason = "DQ_ROW_COUNT_MISMATCH"
    return reason


def _ingestion_snapshot_id(row: Mapping[str, object]) -> str | None:
    checksum = row.get("checksum")
    if isinstance(checksum, str) and checksum:
        return checksum
    raw_evidence = row.get("snapshot_evidence")
    if not isinstance(raw_evidence, dict):
        return None
    snapshot_id = cast(dict[object, object], raw_evidence).get("source_snapshot_id")
    return snapshot_id if isinstance(snapshot_id, str) and snapshot_id else None


def _asof_snapshot_mismatch_reason(
    *,
    ingestion_row: Mapping[str, object],
    dq_evidence: Mapping[object, object],
    signal_date: str,
) -> str | None:
    raw_ingestion_evidence = ingestion_row.get("snapshot_evidence")
    if not isinstance(raw_ingestion_evidence, dict):
        return "INGESTION_ASOF_EVIDENCE_MISSING"
    normalized_ingestion = validated_asof_snapshot_evidence(
        cast(dict[object, object], raw_ingestion_evidence),
        trade_date=signal_date,
    )
    normalized_dq = validated_asof_snapshot_evidence(
        dq_evidence,
        trade_date=signal_date,
    )
    if normalized_ingestion is None or normalized_dq is None:
        return "DQ_EVIDENCE_INVALID"
    if normalized_ingestion != normalized_dq:
        return "DQ_ASOF_EVIDENCE_MISMATCH"
    return None


def _is_non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
