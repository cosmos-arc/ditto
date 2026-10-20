"""Translate ingestion and DQ results into EOD dataset readiness evidence."""

from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any, cast

from ditto_application.processes.execution.eod_coordinator import DatasetReadiness
from ditto_application.processes.ingestion.eod_readiness import (
    DEFAULT_EOD_VERIFICATION_DATASETS,
    EodReadinessVerifier,
)
from ditto_application.processes.ingestion.result_handler import (
    validated_asof_snapshot_evidence,
)
from ditto_application.providers_selection import completed_snapshot_index
from ditto_platform.foundation import logger
from ditto_platform.services import AlertManager, NotificationLevel

from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts import create_ingestion_bundle

__all__ = ["dataset_states_from_ingestion", "run_eod_readiness_verification"]


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


def run_eod_readiness_verification(
    trade_date: str,
    *,
    retry: bool = True,
    datasets: tuple[str, ...] = DEFAULT_EOD_VERIFICATION_DATASETS,
) -> dict[str, object]:
    """
    核验 EOD 数据就绪：缺则重拉一次，仍缺发超高优先级告警（#583）。

    就绪判定以账本证据为准（与活体选池滚动日同一条规则），不信任
    摄取结果的 success 字样——同晚空响应在切片 B 之后是失败，但
    旧账本里的历史空观察同样不算覆盖。
    """
    with create_ingestion_bundle() as bundle:

        def reingest(dataset: str, day: str) -> object:
            return bundle.coordinator.ingest_date(dataset, day, False)

        report = EodReadinessVerifier(
            completed_snapshot_index(bundle.lifecycle_reader, bundle.snapshot_reader),
            reingest=reingest if retry else None,
        ).verify(datasets=datasets, trade_date=_parse_day(trade_date))

    payload: dict[str, object] = {
        "trade_date": trade_date,
        "status": "ready" if not report.missing else "incomplete",
        "refetched": list(report.refetched),
        "datasets": [
            {
                "dataset": item.dataset,
                "ready": item.ready,
                "attested_through": (
                    item.attested_through.isoformat()
                    if item.attested_through is not None
                    else None
                ),
            }
            for item in report.datasets
        ],
        "missing": list(report.missing),
    }
    if report.missing:
        container = make_app_container()
        try:
            alert_manager = container.get(AlertManager)
            _send_readiness_alert_safely(alert_manager, trade_date, report.missing)
        finally:
            container.close()
    return payload


def _parse_day(trade_date: str) -> date:
    return date.fromisoformat(trade_date)


def _send_readiness_alert_safely(
    alert_manager: AlertManager, trade_date: str, missing: tuple[str, ...]
) -> None:
    """超高优先级告警；发送失败只记日志，不阻断核验结果。"""
    try:
        alert_manager.send_alert(
            template="eod_readiness_failure",
            context={
                "trade_date": trade_date,
                "missing_datasets": ", ".join(missing),
            },
            level=NotificationLevel.ERROR,
            timestamp=datetime.now(UTC),
        )
    except Exception as exc:
        logger.error(
            "发送 EOD 就绪告警失败",
            event="eod_readiness_alert_send_failed",
            error_code="EOD_READINESS_ALERT_SEND_FAILED",
            error_type=type(exc).__name__,
        )
