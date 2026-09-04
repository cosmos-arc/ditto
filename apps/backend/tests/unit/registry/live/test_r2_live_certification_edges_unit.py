"""Fail-closed edge contracts for R2 live certification evidence."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import orjson
import pytest
from apps.backend.tests.unit.scripts import test_r2_live_certification_unit as fixtures
from ditto_apps.registry.live import r2_live_certification as subject
from ditto_data.catalog import DataSchemaFingerprint
from ditto_data.catalog.certification import (
    CertificationEvidence,
    DatasetCertificationReport,
    EvidenceCheck,
)


@pytest.mark.parametrize(
    "condition",
    ["unknown_dataset", "empty_catalog", "incomplete"],
)
def test_snapshot_selection_rejects_incomplete_current_evidence(
    condition: str,
) -> None:
    entry = fixtures._entry(
        schema_version="fundamental.dividend.v2",
        row_count=5,
        created_at=fixtures._NOW,
    )
    snapshot = fixtures._snapshot(
        schema_version="fundamental.dividend.v2",
        row_count=5,
        created_at=fixtures._NOW,
        checksum="current",
    )
    dataset_id = "missing" if condition == "unknown_dataset" else "dividend"
    entries = () if condition == "empty_catalog" else (entry,)
    if condition == "incomplete":
        entries = (
            replace(
                entry,
                schema=DataSchemaFingerprint(
                    schema_hash=entry.schema.schema_hash,
                    row_count=None,
                    created_at=entry.schema.created_at,
                    schema_version=entry.schema.schema_version,
                    columns=entry.schema.columns,
                ),
            ),
        )

    with pytest.raises(ValueError):
        subject.select_current_snapshot_ids(
            dataset_id=dataset_id,
            catalog_entries=entries,
            snapshots=(snapshot,),
        )


def test_snapshot_selection_rejects_unverifiable_payload_identity() -> None:
    entry = fixtures._entry(
        schema_version="fundamental.dividend.v2",
        row_count=0,
        created_at=fixtures._NOW,
    )
    snapshot = fixtures._snapshot(
        schema_version="fundamental.dividend.v2",
        row_count=0,
        created_at=fixtures._NOW,
        checksum="not-an-empty-proof",
        payload_retained=False,
    )

    with pytest.raises(ValueError, match="exactly one current provider snapshot"):
        subject.select_current_snapshot_ids(
            dataset_id="dividend",
            catalog_entries=(entry,),
            snapshots=(snapshot,),
        )


def test_expected_dates_rejects_reversed_or_empty_schedule() -> None:
    with pytest.raises(ValueError, match="reversed"):
        subject.build_expected_dates(
            schedule="natural_days",
            target_from=date(2026, 8, 2),
            target_to=date(2026, 8, 1),
            trading_days_provider=lambda _start, _end: [],
        )


@pytest.mark.parametrize("condition", ["outside_scope", "missing_raw", "symbolic"])
def test_literal_target_from_rejects_missing_contract_or_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    condition: str,
) -> None:
    contract = {
        "outside_scope": SimpleNamespace(r2_scope="soft", raw_target_from="2015-01-01"),
        "missing_raw": SimpleNamespace(r2_scope="hard", raw_target_from=None),
        "symbolic": SimpleNamespace(r2_scope="hard", raw_target_from="first_available"),
    }[condition]
    monkeypatch.setattr(
        subject,
        "default_dataset_metadata",
        lambda: {"dataset": SimpleNamespace(dataset_spec=contract)},
    )

    if condition == "symbolic":
        assert subject._literal_target_from("dataset") == date(2015, 1, 1)
    else:
        with pytest.raises(ValueError):
            subject._literal_target_from("dataset")


def test_symbolic_coverage_target_requires_expected_dates() -> None:
    with pytest.raises(ValueError, match="requires expected dates"):
        subject.resolve_coverage_target_from("index_weight", ())

    with pytest.raises(ValueError, match="expected schedule is empty"):
        subject.build_expected_dates(
            schedule="trading_days",
            target_from=date(2026, 8, 1),
            target_to=date(2026, 8, 2),
            trading_days_provider=lambda _start, _end: [],
        )


def test_coverage_target_requires_declared_raw_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subject,
        "default_dataset_metadata",
        lambda: {
            "dataset": SimpleNamespace(
                dataset_spec=SimpleNamespace(raw_target_from=None)
            )
        },
    )

    with pytest.raises(ValueError, match="has no R2 raw target"):
        subject.resolve_coverage_target_from("dataset", (date(2026, 8, 1),))


@pytest.mark.parametrize("condition", ["sqlite", "unknown", "parquet"])
def test_consumer_probe_rejects_missing_physical_contract(
    tmp_path: Path,
    condition: str,
) -> None:
    dataset_id = {
        "sqlite": "dividend",
        "unknown": "not-declared",
        "parquet": "stock_daily",
    }[condition]

    with pytest.raises(ValueError, match=r"missing|no production consumer probe"):
        subject.probe_consumer_payload(tmp_path, dataset_id)


def test_addressed_write_is_idempotent_and_rejects_content_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, digest = subject._write_addressed(tmp_path, "evidence", {"value": 1})
    assert subject._write_addressed(tmp_path, "evidence", {"value": 1}) == (
        path,
        digest,
    )

    monkeypatch.setattr(subject.hashlib, "sha256", lambda _content: _FixedDigest())
    conflict = tmp_path / f"conflict.sha256-{'a' * 64}.json"
    conflict.write_bytes(b"different")
    with pytest.raises(ValueError, match="content-addressed evidence conflict"):
        subject._write_addressed(tmp_path, "conflict", {"value": 1})


class _FixedDigest:
    def hexdigest(self) -> str:
        return "a" * 64


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"schema": "wrong"},
        {
            "schema": "ditto.r2-live-gate-artifact",
            "version": 1,
            "kind": "recoverability",
            "recoverability": [],
        },
    ],
)
def test_recovery_evidence_rejects_wrong_outer_contract(
    tmp_path: Path,
    payload: object,
) -> None:
    path = tmp_path / "recoverability.json"
    path.write_bytes(orjson.dumps(payload))

    with pytest.raises(ValueError, match="recovery evidence"):
        subject.load_passing_recovery_evidence(path)


def _consumer_case(
    tmp_path: Path,
    *,
    content: bytes | None = None,
    uri_digest: str | None = None,
) -> tuple[
    subject.DatasetCertificationReport,
    subject.ReusableCertificationRequest,
    Path,
]:
    data_root = tmp_path / "live-data"
    evidence_root = tmp_path / "evidence"
    snapshot_ids = ("snapshot:tushare:dividend:sha256:current",)
    if content is None:
        content = orjson.dumps(
            {
                "schema": "ditto.r2-live-consumer-evidence.v1",
                "dataset_id": "dividend",
                "data_root": str(data_root.resolve()),
                "generated_at": fixtures._NOW.isoformat(),
                "probe": {"kind": "sqlite", "object": "dividend", "row_count": 5},
                "snapshot_ids": list(snapshot_ids),
            },
            option=orjson.OPT_SORT_KEYS,
        )
    digest = uri_digest or hashlib.sha256(content).hexdigest()
    consumer_path = (
        evidence_root
        / "products"
        / "dividend"
        / f"consumer-read-smoke.sha256-{digest}.json"
    )
    consumer_path.parent.mkdir(parents=True)
    consumer_path.write_bytes(content)
    recovery_uri = "artifact+sha256://recovery/current"
    report = fixtures._active_report(
        snapshot_ids=snapshot_ids,
        recovery_uri=recovery_uri,
        consumer_uri="artifact+sha256://r2-live/consumer/dividend/" + digest,
    )
    request = subject.ReusableCertificationRequest(
        dataset_id="dividend",
        profile="r2-modern-a-share-v1",
        target_from=date(2015, 1, 1),
        target_to=date(2026, 7, 31),
        snapshot_ids=snapshot_ids,
        recovery_evidence_uri=recovery_uri,
        data_root=data_root,
        evidence_root=evidence_root,
    )
    return report, request, consumer_path


def _with_evidence(
    report: DatasetCertificationReport,
    evidence: CertificationEvidence,
) -> DatasetCertificationReport:
    return DatasetCertificationReport.create(
        dataset_id=report.dataset_id,
        profile=report.profile,
        coverage=report.coverage,
        evidence=evidence,
        generated_at=report.generated_at,
    )


class _ActiveStore:
    def __init__(
        self,
        report: DatasetCertificationReport,
        events: tuple[SimpleNamespace, ...],
    ) -> None:
        self.report = report
        self.events = events

    def get_active_report(
        self,
        dataset_id: str,
        profile: str,
    ) -> DatasetCertificationReport:
        assert dataset_id == self.report.dataset_id
        assert profile == self.report.profile
        return self.report

    def list_events(self, report_id: str) -> tuple[SimpleNamespace, ...]:
        assert report_id == self.report.report_id
        return self.events


@pytest.mark.parametrize("event_state", ["missing", "action", "actor", "valid"])
def test_existing_active_certification_requires_exact_review_identity(
    tmp_path: Path,
    event_state: str,
) -> None:
    report, reusable, expected_path = _consumer_case(tmp_path)
    events = {
        "missing": (),
        "action": (SimpleNamespace(action="frozen", actor="operator"),),
        "actor": (SimpleNamespace(action="approved", actor="other"),),
        "valid": (SimpleNamespace(action="approved", actor="operator"),),
    }[event_state]
    request = subject._LiveCertificationRequest(
        dataset_id=reusable.dataset_id,
        profile=reusable.profile,
        target_from=reusable.target_from,
        target_to=reusable.target_to,
        expected_dates=(reusable.target_from, reusable.target_to),
        snapshot_ids=reusable.snapshot_ids,
        recovery_evidence_uri=reusable.recovery_evidence_uri,
        recovery_path=tmp_path / "recovery.json",
        recovery_hash="a" * 64,
        data_root=reusable.data_root,
        evidence_root=reusable.evidence_root,
        generated_at=fixtures._NOW,
        actor="operator",
    )
    store = cast(
        subject.CertificationGovernanceStore,
        _ActiveStore(report, events),
    )

    if event_state != "valid":
        with pytest.raises(ValueError, match=r"review|reviewer"):
            subject._freeze_or_resume_product(
                request,
                store,
                cast(subject.DataProductCertificationCommands, object()),
                cast(subject.DataProductCertificationBuilder, object()),
            )
    else:
        frozen, path, digest = subject._freeze_or_resume_product(
            request,
            store,
            cast(subject.DataProductCertificationCommands, object()),
            cast(subject.DataProductCertificationBuilder, object()),
        )
        assert frozen == report
        assert path == expected_path.resolve()
        assert digest == hashlib.sha256(expected_path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("drift", "message"),
    [
        ("product", "product drift"),
        ("coverage", "coverage drift"),
        ("recovery", "recovery evidence drift"),
        ("consumer", "consumer evidence drift"),
        ("uri", "consumer URI drift"),
    ],
)
def test_reusable_certification_rejects_governance_drift(
    tmp_path: Path,
    drift: str,
    message: str,
) -> None:
    report, request, _path = _consumer_case(tmp_path)
    if drift == "product":
        request = replace(request, profile="other-profile")
    elif drift == "coverage":
        request = replace(request, target_to=date(2026, 7, 30))
    elif drift == "recovery":
        report = _with_evidence(
            report,
            replace(
                report.evidence,
                recovery_results=(
                    EvidenceCheck("different_recovery", "evidence://other", True),
                ),
            ),
        )
    elif drift == "consumer":
        report = _with_evidence(
            report,
            replace(
                report.evidence,
                consumer_results=(
                    EvidenceCheck("different_consumer", "evidence://other", True),
                ),
            ),
        )
    else:
        report = _with_evidence(
            report,
            replace(
                report.evidence,
                consumer_results=(
                    EvidenceCheck(
                        "production_consumer_read_smoke",
                        "artifact+sha256://r2-live/consumer/dividend/not-a-digest",
                        passed=True,
                    ),
                ),
            ),
        )

    with pytest.raises(ValueError, match=message):
        subject.resolve_reusable_certification(
            active_report=report,
            request=request,
        )


@pytest.mark.parametrize("drift", ["hash", "shape", "payload"])
def test_reusable_certification_rejects_consumer_artifact_drift(
    tmp_path: Path,
    drift: str,
) -> None:
    if drift == "hash":
        report, request, _path = _consumer_case(
            tmp_path,
            content=b"{}",
            uri_digest="a" * 64,
        )
    elif drift == "shape":
        report, request, _path = _consumer_case(tmp_path, content=b"[]")
    else:
        report, request, _path = _consumer_case(
            tmp_path,
            content=orjson.dumps(
                {
                    "schema": "ditto.r2-live-consumer-evidence.v1",
                    "dataset_id": "different",
                    "data_root": str((tmp_path / "live-data").resolve()),
                    "generated_at": fixtures._NOW.isoformat(),
                    "probe": {"row_count": 5},
                    "snapshot_ids": ["snapshot:tushare:dividend:sha256:current"],
                },
                option=orjson.OPT_SORT_KEYS,
            ),
        )

    with pytest.raises(ValueError, match=r"consumer (hash|payload) drift"):
        subject.resolve_reusable_certification(
            active_report=report,
            request=request,
        )


def _passing_recovery(path: Path) -> None:
    path.write_bytes(
        orjson.dumps(
            {
                "schema": "ditto.r2-live-gate-artifact",
                "version": 1,
                "kind": "recoverability",
                "recoverability": {
                    "passed": True,
                    "reason_codes": [],
                    "payload_root_sha256": "a" * 64,
                    "sqlite_table_row_counts": {"provider_snapshots": 1},
                },
            },
            option=orjson.OPT_SORT_KEYS,
        )
    )


@pytest.mark.parametrize("condition", ["root", "actor", "uri", "naive_time"])
def test_certification_rejects_invalid_runtime_identity_before_container_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    condition: str,
) -> None:
    data_root = tmp_path / "state"
    data_root.mkdir()
    recovery = tmp_path / "recovery.json"
    _passing_recovery(recovery)
    monkeypatch.setattr(
        subject,
        "state_root_matches",
        lambda _root: condition != "root",
    )
    actor = " operator " if condition == "actor" else "operator"
    uri = " " if condition == "uri" else "artifact+sha256://recovery/current"
    generated_at = datetime(2026, 8, 1) if condition == "naive_time" else fixtures._NOW

    with pytest.raises(ValueError):
        subject.certify_live_products(
            data_root=data_root,
            evidence_root=tmp_path / "evidence",
            recovery_evidence_path=recovery,
            recovery_evidence_uri=uri,
            target_to=date(2026, 7, 31),
            actor=actor,
            generated_at=generated_at,
        )


def test_certification_rejects_registry_cardinality_before_composition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "state"
    data_root.mkdir()
    recovery = tmp_path / "recovery.json"
    _passing_recovery(recovery)
    monkeypatch.setattr(subject, "state_root_matches", lambda _root: True)
    monkeypatch.setattr(subject, "default_dataset_metadata", dict)

    with pytest.raises(ValueError, match="must contain 22 products"):
        subject.certify_live_products(
            data_root=data_root,
            evidence_root=tmp_path / "evidence",
            recovery_evidence_path=recovery,
            recovery_evidence_uri="artifact+sha256://recovery/current",
            target_to=date(2026, 7, 31),
            actor="operator",
            generated_at=datetime(2026, 8, 1, tzinfo=UTC),
        )


class _ExplodingQueryContext:
    def __enter__(self) -> None:
        raise RuntimeError("query-context-sentinel")

    def __exit__(self, *_args: object) -> None:
        return None


def test_certification_enters_composition_only_after_full_registry_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "state"
    data_root.mkdir()
    recovery = tmp_path / "recovery.json"
    _passing_recovery(recovery)
    registry = {
        f"dataset-{index}": SimpleNamespace(
            dataset_id=f"dataset-{index}",
            dataset_spec=SimpleNamespace(r2_scope="hard"),
        )
        for index in range(22)
    }
    monkeypatch.setattr(subject, "state_root_matches", lambda _root: True)
    monkeypatch.setattr(subject, "default_dataset_metadata", lambda: registry)
    monkeypatch.setattr(
        subject,
        "create_query_context",
        _ExplodingQueryContext,
    )

    with pytest.raises(RuntimeError, match="query-context-sentinel"):
        subject.certify_live_products(
            data_root=data_root,
            evidence_root=tmp_path / "evidence",
            recovery_evidence_path=recovery,
            recovery_evidence_uri="artifact+sha256://recovery/current",
            target_to=date(2026, 7, 31),
            actor="operator",
            generated_at=datetime(2026, 8, 1, tzinfo=UTC),
        )
