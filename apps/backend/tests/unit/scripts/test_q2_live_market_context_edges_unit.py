"""Isolated fail-closed evidence tests for the Q2 MarketContext driver."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import orjson
import polars as pl
import pytest
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext
from ditto_application.commands.data_product_certification import (
    DataProductCertificationCommands,
)
from ditto_application.commands.data_product_certification_builder import (
    CertificationBuildRequest,
    DataProductCertificationBuilder,
)
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.market_context import MarketContextFacade
from ditto_application.queries.market_context_evidence import (
    MarketContextEvidenceQueryFacade,
)
from ditto_apps.scripts import q2_live_market_context as subject
from ditto_data.catalog.certification import (
    CertificationEvidence,
    CertificationGovernanceStore,
    CertificationReviewEvent,
    DatasetCertificationReport,
    EvidenceCheck,
)
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.coverage import DatasetCoverage
from ditto_data.catalog.provider_payload import (
    ProviderPayloadArtifact,
    ProviderPayloadReader,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotReader

_TARGET_DATE = date(2024, 3, 29)
_WINDOWS = {
    "global_index_daily": (_TARGET_DATE, _TARGET_DATE),
    "index_daily": (date(2024, 2, 1), _TARGET_DATE),
    "macro_indicators": (_TARGET_DATE, _TARGET_DATE),
    "stock_daily": (_TARGET_DATE, _TARGET_DATE),
}


def _snapshot(
    *,
    snapshot_id: str = "snapshot-1",
    dataset_id: str = "index_daily",
    request_start: str = "2024-03-29",
    request_end: str = "2024-03-29",
    payload_uri: str | None = (
        "provider_payloads/tushare/index_daily/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.parquet"
    ),
    payload_retained: bool = True,
    created_at: datetime = datetime(2024, 3, 29, tzinfo=UTC),
) -> ProviderSnapshot:
    return ProviderSnapshot(
        snapshot_id=snapshot_id,
        dataset_id=dataset_id,
        source="tushare",
        request_start=request_start,
        request_end=request_end,
        schema_version="1",
        checksum="a" * 32,
        canonical_asset=DataAssetRef(
            dataset_id=dataset_id,
            namespace="market/daily",
        ),
        request_parameters_hash=f"request:{snapshot_id}",
        response_metadata=(),
        license_record_id=f"license:{dataset_id}",
        row_count=1,
        payload_uri=payload_uri,
        payload_retained=payload_retained,
        created_at=created_at,
    )


def _report(
    *,
    dataset_id: str = "index_daily",
    target_from: date = _TARGET_DATE,
    target_to: date = _TARGET_DATE,
    snapshot_ids: tuple[str, ...] = ("snapshot-1",),
    generated_at: datetime = datetime(2024, 3, 29, 0, 1, tzinfo=UTC),
) -> DatasetCertificationReport:
    coverage = DatasetCoverage(
        dataset_id=dataset_id,
        schedule="trading_days",
        target_from=target_from,
        target_to=target_to,
        native_from=target_from,
        native_to=target_to,
        actual_from=target_from,
        actual_to=target_to,
        raw_from=target_from,
        complete_from=target_from,
        expected_partitions=1,
        actual_partitions=1,
        gaps=(),
        exceptions=(),
        collected_at=generated_at,
    )
    passing = EvidenceCheck(
        name="passing",
        evidence_uri="artifact+sha256://passing",
        passed=True,
    )
    evidence = CertificationEvidence(
        source_ids=("tushare",),
        schema_versions=("1",),
        snapshot_ids=snapshot_ids,
        dq_rule_version="dq-v1",
        dq_results=(passing,),
        pit_replay_results=(passing,),
        fallback_history=("source:tushare:primary:no-fallback-event",),
        override_history=(),
        freshness_results=(passing,),
        recovery_results=(passing,),
        license_record_ids=(f"license:{dataset_id}",),
        consumer_results=(passing,),
    )
    return DatasetCertificationReport.create(
        dataset_id=dataset_id,
        profile="research_daily",
        coverage=coverage,
        evidence=evidence,
        generated_at=generated_at,
    )


class _EventStore:
    def __init__(self, events: tuple[CertificationReviewEvent, ...]) -> None:
        self.events = events

    def list_events(self, report_id: str) -> tuple[CertificationReviewEvent, ...]:
        del report_id
        return self.events


class _PayloadReader:
    def __init__(self, frame: pl.DataFrame) -> None:
        self.frame = frame
        self.uri: str | None = None

    def read_payload(self, artifact: ProviderPayloadArtifact) -> pl.DataFrame:
        self.uri = artifact.uri
        return self.frame


class _SnapshotReader:
    def __init__(self, snapshots: tuple[ProviderSnapshot, ...]) -> None:
        self.snapshots = snapshots

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
    ) -> tuple[ProviderSnapshot, ...]:
        return tuple(
            snapshot
            for snapshot in self.snapshots
            if dataset_id is None or snapshot.dataset_id == dataset_id
        )


class _GovernanceStore:
    def __init__(self) -> None:
        self.reports: dict[str, DatasetCertificationReport] = {}
        self.active: dict[tuple[str, str], DatasetCertificationReport] = {}
        self.events: dict[str, list[CertificationReviewEvent]] = {}

    def append_report(
        self,
        report: DatasetCertificationReport,
    ) -> DatasetCertificationReport:
        self.reports[report.report_id] = report
        return report

    def approve_report(
        self,
        report_id: str,
        *,
        reviewer: str,
        reviewed_at: datetime,
    ) -> CertificationReviewEvent:
        report = self.reports[report_id]
        event = CertificationReviewEvent(
            event_id=sum(len(events) for events in self.events.values()) + 1,
            report_id=report.report_id,
            dataset_id=report.dataset_id,
            profile=report.profile,
            action="approved",
            actor=reviewer,
            occurred_at=reviewed_at,
        )
        self.events.setdefault(report_id, []).append(event)
        self.active[(report.dataset_id, report.profile)] = report
        return event

    def get_active_report(
        self,
        dataset_id: str,
        profile: str,
    ) -> DatasetCertificationReport | None:
        return self.active.get((dataset_id, profile))

    def list_events(
        self,
        report_id: str,
    ) -> tuple[CertificationReviewEvent, ...]:
        return tuple(self.events.get(report_id, ()))

    def install_active(self, report: DatasetCertificationReport) -> None:
        self.append_report(report)
        self.approve_report(
            report.report_id,
            reviewer="existing-reviewer",
            reviewed_at=report.generated_at,
        )


class _CertificationBuilder:
    def __init__(self) -> None:
        self.requests: list[CertificationBuildRequest] = []

    def build(
        self,
        request: CertificationBuildRequest,
    ) -> DatasetCertificationReport:
        self.requests.append(request)
        return _report(
            dataset_id=request.dataset_id,
            target_from=request.target_from or request.target_to,
            target_to=request.target_to,
            snapshot_ids=request.snapshot_ids,
            generated_at=request.generated_at,
        )


class _MarketFacade:
    def __init__(self, *, rejects_early_query: bool) -> None:
        self.rejects_early_query = rejects_early_query

    def get_context(self, request: object) -> object:
        del request
        if self.rejects_early_query:
            raise AppQueryError("snapshot had not yet been acquired")
        return object()


class _EvidenceTool:
    def __init__(self, *, payload: dict[str, object], tampered: bool) -> None:
        self.payload = payload
        self.tampered = tampered

    def invoke(
        self,
        *,
        arguments: dict[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        assert arguments == {}
        envelope = EvidenceEnvelope.seal(
            evidence_id="q2-market-context-evidence",
            tool_name="market_context_evidence",
            result={"payload": self.payload},
            artifact_refs=("artifact+sha256://market-context",),
            temporal_context=context,
            lineage=("q2-snapshot-lineage",),
        )
        if self.tampered:
            return replace(envelope, integrity_hash="0" * 64)
        return envelope


class _QueryMetadata:
    def list_trading_days(
        self,
        *args: object,
        **kwargs: object,
    ) -> tuple[date, ...]:
        del args, kwargs
        return (_TARGET_DATE,)


class _QueryContext:
    def __init__(self) -> None:
        self.metadata = _QueryMetadata()

    def __enter__(self) -> _QueryContext:
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        del exc_type, exc_value, traceback


class _Container:
    def __init__(self, services: dict[type[object], object]) -> None:
        self.services = services
        self.closed = False

    def get(self, service_type: type[object]) -> object:
        return self.services[service_type]

    def close(self) -> None:
        self.closed = True


def _install_acceptance_fakes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    rejects_early_query: bool = True,
    tampered_evidence: bool = False,
) -> tuple[Path, Path, Path, _Container, _CertificationBuilder]:
    data_root = tmp_path / "state"
    data_root.mkdir()
    evidence_root = tmp_path / "evidence"
    recovery_path = tmp_path / "recovery.json"
    recovery_path.write_bytes(orjson.dumps({"passed": True}))

    snapshots = tuple(
        _snapshot(
            snapshot_id=f"snapshot-{dataset_id}",
            dataset_id=dataset_id,
            request_start=target_from.isoformat(),
            request_end=target_to.isoformat(),
            payload_uri=(
                f"provider_payloads/tushare/{dataset_id}/"
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.parquet"
            ),
        )
        for dataset_id, (target_from, target_to) in _WINDOWS.items()
    )
    store = _GovernanceStore()
    builder = _CertificationBuilder()
    commands = DataProductCertificationCommands(
        cast(CertificationGovernanceStore, store),
    )
    global_frame = pl.DataFrame(
        {
            "source_ticker": ["N225"],
            "timezone": ["Asia/Tokyo"],
            "event_time": [datetime(2024, 3, 29, 6, tzinfo=UTC)],
        },
    )
    services: dict[type[object], object] = {
        ProviderSnapshotReader: cast(
            ProviderSnapshotReader,
            _SnapshotReader(snapshots),
        ),
        DataProductCertificationBuilder: cast(DataProductCertificationBuilder, builder),
        DataProductCertificationCommands: commands,
        CertificationGovernanceStore: cast(CertificationGovernanceStore, store),
        MarketContextFacade: cast(
            MarketContextFacade,
            _MarketFacade(rejects_early_query=rejects_early_query),
        ),
        MarketContextEvidenceQueryFacade: cast(
            MarketContextEvidenceQueryFacade,
            object(),
        ),
        ProviderPayloadReader: cast(
            ProviderPayloadReader,
            _PayloadReader(global_frame),
        ),
    }
    container = _Container(services)

    monkeypatch.setattr(subject, "state_root_matches", lambda root: root == data_root)
    monkeypatch.setattr(subject, "create_query_context", _QueryContext)
    monkeypatch.setattr(subject, "make_app_container", lambda: container)
    monkeypatch.setattr(
        subject,
        "build_expected_dates",
        lambda **kwargs: (cast(date, kwargs["target_to"]),),
    )

    def probe_consumer_payload(
        probe_root: Path,
        dataset_id: str,
    ) -> dict[str, int | str]:
        assert probe_root == data_root
        return {"dataset_id": dataset_id, "row_count": 1}

    monkeypatch.setattr(subject, "probe_consumer_payload", probe_consumer_payload)

    def evidence_tool_factory(*, facade: object) -> _EvidenceTool:
        del facade
        return _EvidenceTool(
            payload=_valid_market_context(status="degraded"),
            tampered=tampered_evidence,
        )

    monkeypatch.setattr(subject, "MarketContextEvidenceTool", evidence_tool_factory)
    return data_root, evidence_root, recovery_path, container, builder


def _valid_market_context(*, status: str = "ready") -> dict[str, object]:
    return {
        "status": status,
        "regime_label": "neutral",
        "regime_score": 0.25,
        "impacts": [
            {"target_domain": "industry", "summary": "industry impact"},
            {"target_domain": "risk", "summary": "risk impact"},
        ],
        "metrics": [
            {
                "name": "market_breadth",
                "value": 0.5,
                "evidence_ref": "artifact+sha256://metric",
            },
        ],
        "missing_inputs": ["optional_macro"] if status == "degraded" else [],
        "uncertainties": [],
    }


def test_snapshot_selection_fails_when_exact_retained_interval_is_absent() -> None:
    with pytest.raises(ValueError, match="exact retained snapshot interval"):
        subject.select_interval_snapshot_ids(
            dataset_id="index_daily",
            target_from=date(2024, 2, 1),
            target_to=_TARGET_DATE,
            snapshots=(
                _snapshot(
                    request_start="2024-03-29",
                    request_end="2024-03-29",
                ),
            ),
        )


def test_global_visibility_rejects_invalid_session_and_payload_evidence() -> None:
    valid_frame = pl.DataFrame(
        {
            "source_ticker": ["N225"],
            "timezone": ["Asia/Tokyo"],
            "event_time": [datetime(2024, 3, 29, 6, tzinfo=UTC)],
        },
    )
    with pytest.raises(ValueError, match="boundaries must be ordered and aware"):
        subject.inspect_global_session_visibility(
            valid_frame,
            a_share_open=datetime(2024, 3, 29, 1, 30),
            a_share_close=datetime(2024, 3, 29, 7, tzinfo=UTC),
        )

    with pytest.raises(ValueError, match="lacks session-time evidence"):
        subject.inspect_global_session_visibility(
            pl.DataFrame({"source_ticker": ["N225"]}),
            a_share_open=datetime(2024, 3, 29, 1, 30, tzinfo=UTC),
            a_share_close=datetime(2024, 3, 29, 7, tzinfo=UTC),
        )


def test_global_visibility_rejects_naive_and_uninformative_event_times() -> None:
    with pytest.raises(ValueError, match="event_time must be timezone-aware"):
        subject.inspect_global_session_visibility(
            pl.DataFrame(
                {
                    "source_ticker": ["N225"],
                    "timezone": ["Asia/Tokyo"],
                    "event_time": [datetime(2024, 3, 29, 6)],
                },
            ),
            a_share_open=datetime(2024, 3, 29, 1, 30, tzinfo=UTC),
            a_share_close=datetime(2024, 3, 29, 7, tzinfo=UTC),
        )

    with pytest.raises(ValueError, match="same-day future close"):
        subject.inspect_global_session_visibility(
            pl.DataFrame(
                {
                    "source_ticker": ["N225"],
                    "timezone": ["Asia/Tokyo"],
                    "event_time": [datetime(2024, 3, 29, 1, tzinfo=UTC)],
                },
            ),
            a_share_open=datetime(2024, 3, 29, 1, 30, tzinfo=UTC),
            a_share_close=datetime(2024, 3, 29, 7, tzinfo=UTC),
        )


def test_addressed_evidence_is_idempotent_and_detects_corruption(
    tmp_path: Path,
) -> None:
    path, digest = subject._write_addressed(tmp_path, "evidence", {"value": 1})
    repeated, repeated_digest = subject._write_addressed(
        tmp_path,
        "evidence",
        {"value": 1},
    )
    assert (repeated, repeated_digest) == (path, digest)

    path.write_text("corrupt", encoding="utf-8")
    with pytest.raises(ValueError, match="content-addressed evidence conflict"):
        subject._write_addressed(tmp_path, "evidence", {"value": 1})


def test_recovery_evidence_requires_a_passing_addressed_payload(
    tmp_path: Path,
) -> None:
    wrong_shape = tmp_path / "wrong-shape.json"
    wrong_shape.write_bytes(orjson.dumps([{"passed": True}]))
    with pytest.raises(ValueError, match="passing addressed artifact"):
        subject._validate_recovery_evidence(wrong_shape)

    failed = tmp_path / "failed.json"
    failed.write_bytes(orjson.dumps({"passed": False}))
    with pytest.raises(ValueError, match="passing addressed artifact"):
        subject._validate_recovery_evidence(failed)

    passing = tmp_path / "passing.json"
    passing.write_bytes(orjson.dumps({"passed": True}))
    resolved, digest = subject._validate_recovery_evidence(passing)
    assert resolved == passing.resolve()
    assert digest == subject._sha256_file(passing)


def test_active_report_requires_a_matching_approved_event() -> None:
    report = _report()
    empty_store = cast(CertificationGovernanceStore, _EventStore(()))
    with pytest.raises(ValueError, match="active certification drift"):
        subject._validate_active_report(
            report,
            target_from=_TARGET_DATE,
            target_to=_TARGET_DATE,
            snapshot_ids=("snapshot-1",),
            store=empty_store,
        )

    approved = CertificationReviewEvent(
        event_id=1,
        report_id=report.report_id,
        dataset_id=report.dataset_id,
        profile=report.profile,
        action="approved",
        actor="q2-test",
        occurred_at=report.generated_at,
    )
    subject._validate_active_report(
        report,
        target_from=_TARGET_DATE,
        target_to=_TARGET_DATE,
        snapshot_ids=("snapshot-1",),
        store=cast(CertificationGovernanceStore, _EventStore((approved,))),
    )


def test_global_payload_requires_retention_and_preserves_artifact_identity() -> None:
    frame = pl.DataFrame({"value": [1]})
    reader = _PayloadReader(frame)
    loaded = subject._global_payload(
        _snapshot(),
        cast(ProviderPayloadReader, reader),
    )
    assert loaded.equals(frame)
    assert reader.uri == (
        "provider_payloads/tushare/index_daily/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.parquet"
    )

    with pytest.raises(ValueError, match="lacks retained payload URI"):
        subject._global_payload(
            _snapshot(payload_uri=None, payload_retained=False),
            cast(ProviderPayloadReader, reader),
        )


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            {**_valid_market_context(), "status": "unknown"},
            id="unknown-status",
        ),
        pytest.param(
            {**_valid_market_context(), "regime_label": None},
            id="missing-regime",
        ),
        pytest.param(
            {**_valid_market_context(), "impacts": "not-a-sequence"},
            id="missing-impacts",
        ),
        pytest.param(
            {
                **_valid_market_context(),
                "impacts": [{"target_domain": "industry"}],
            },
            id="incomplete-impact-domains",
        ),
        pytest.param(
            {**_valid_market_context(), "metrics": []},
            id="missing-metrics",
        ),
        pytest.param(
            {**_valid_market_context(), "metrics": [object()]},
            id="untyped-metric",
        ),
        pytest.param(
            {
                **_valid_market_context(),
                "metrics": [{"value": "0.5", "evidence_ref": "artifact"}],
            },
            id="non-numeric-metric",
        ),
        pytest.param(
            {**_valid_market_context(status="degraded"), "missing_inputs": []},
            id="dishonest-degradation",
        ),
    ],
)
def test_market_context_contract_rejects_incomplete_evidence(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        subject._assert_market_context_contract(payload)


@pytest.mark.parametrize(
    "impacts",
    [
        pytest.param([object()], id="untyped-impact"),
        pytest.param([{"target_domain": 1}], id="untyped-domain"),
    ],
)
def test_market_context_contract_rejects_impacts_without_typed_domains(
    impacts: list[object],
) -> None:
    payload = _valid_market_context()
    payload["impacts"] = impacts

    with pytest.raises(ValueError, match="both industry and risk impacts"):
        subject._assert_market_context_contract(payload)


def test_market_context_contract_accepts_honest_degradation() -> None:
    subject._assert_market_context_contract(_valid_market_context(status="degraded"))


def test_certification_reuses_a_matching_active_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report = _report()
    store = _GovernanceStore()
    store.install_active(report)
    builder = _CertificationBuilder()
    commands = DataProductCertificationCommands(
        cast(CertificationGovernanceStore, store),
    )
    data_root = tmp_path / "state"
    data_root.mkdir()
    recovery = tmp_path / "recovery.json"
    recovery.write_bytes(orjson.dumps({"passed": True}))

    def probe_consumer_payload(
        probe_root: Path,
        dataset_id: str,
    ) -> dict[str, int | str]:
        assert probe_root == data_root
        return {"dataset_id": dataset_id, "row_count": 1}

    monkeypatch.setattr(subject, "probe_consumer_payload", probe_consumer_payload)
    authority = subject._CertificationAuthority(
        data_root=data_root,
        evidence_root=tmp_path / "evidence",
        recovery_path=recovery,
        recovery_hash=subject._sha256_file(recovery),
        generated_at=report.generated_at,
        actor="q2-test",
        builder=cast(DataProductCertificationBuilder, builder),
        commands=commands,
        store=cast(CertificationGovernanceStore, store),
    )

    product = subject._certify_product(
        dataset_id="index_daily",
        target_from=_TARGET_DATE,
        target_to=_TARGET_DATE,
        expected_dates=(_TARGET_DATE,),
        snapshot_ids=("snapshot-1",),
        authority=authority,
    )

    assert product.report_id == report.report_id
    assert product.snapshot_ids == ("snapshot-1",)
    assert builder.requests == []


def test_acceptance_rejects_wrong_state_root_and_noncanonical_actor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "state"
    data_root.mkdir()
    monkeypatch.setattr(subject, "state_root_matches", lambda root: False)

    with pytest.raises(ValueError, match="DITTO_STATE_ROOT"):
        subject.run_q2_live_market_context_acceptance(
            data_root=data_root,
            evidence_root=tmp_path / "evidence",
            recovery_evidence=tmp_path / "unused-recovery.json",
            actor="q2-test",
        )

    monkeypatch.setattr(subject, "state_root_matches", lambda root: root == data_root)
    with pytest.raises(ValueError, match="actor is invalid"):
        subject.run_q2_live_market_context_acceptance(
            data_root=data_root,
            evidence_root=tmp_path / "evidence",
            recovery_evidence=tmp_path / "unused-recovery.json",
            actor=" q2-test ",
        )


def test_acceptance_builds_an_isolated_deterministic_degraded_evidence_chain(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_root, evidence_root, recovery, container, builder = _install_acceptance_fakes(
        monkeypatch, tmp_path
    )

    result = subject.run_q2_live_market_context_acceptance(
        data_root=data_root,
        evidence_root=evidence_root,
        recovery_evidence=recovery,
        actor="q2-test",
    )

    assert result["passed"] is True
    assert isinstance(result["market_context"], Mapping)
    assert isinstance(result["missing_data_behavior"], Mapping)
    assert isinstance(result["historical_replay"], Mapping)
    assert isinstance(result["certifications"], Sequence)
    assert result["market_context"]["status"] == "degraded"
    assert result["missing_data_behavior"]["passed"] is True
    assert result["historical_replay"]["deterministic"] is True
    assert len(result["certifications"]) == len(_WINDOWS)
    assert len(builder.requests) == len(_WINDOWS)
    assert container.closed is True


def test_acceptance_requires_the_pre_acquisition_query_to_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_root, evidence_root, recovery, container, _ = _install_acceptance_fakes(
        monkeypatch,
        tmp_path,
        rejects_early_query=False,
    )

    with pytest.raises(ValueError, match="pre-acquisition historical query"):
        subject.run_q2_live_market_context_acceptance(
            data_root=data_root,
            evidence_root=evidence_root,
            recovery_evidence=recovery,
            actor="q2-test",
        )

    assert container.closed is True


def test_acceptance_rejects_tampered_agent_replay_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    data_root, evidence_root, recovery, container, _ = _install_acceptance_fakes(
        monkeypatch,
        tmp_path,
        tampered_evidence=True,
    )

    with pytest.raises(ValueError, match="Agent replay is non-deterministic"):
        subject.run_q2_live_market_context_acceptance(
            data_root=data_root,
            evidence_root=evidence_root,
            recovery_evidence=recovery,
            actor="q2-test",
        )

    assert container.closed is True


def test_main_writes_canonical_evidence_and_stdout_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_root = tmp_path / "state"
    evidence_root = tmp_path / "evidence"
    recovery = tmp_path / "recovery.json"
    output = tmp_path / "nested" / "q2.json"
    result: dict[str, object] = {
        "schema": "ditto.q2-live-market-context.v1",
        "passed": True,
        "source_snapshot_set_id": "snapshot-set:sha256:test",
    }

    def run_acceptance(**kwargs: object) -> dict[str, object]:
        assert kwargs == {
            "data_root": data_root,
            "evidence_root": evidence_root,
            "recovery_evidence": recovery,
            "actor": "q2-test",
        }
        return result

    monkeypatch.setattr(
        subject,
        "run_q2_live_market_context_acceptance",
        run_acceptance,
    )

    exit_code = subject.main(
        [
            "--data-root",
            str(data_root),
            "--evidence-root",
            str(evidence_root),
            "--recovery-evidence",
            str(recovery),
            "--actor",
            "q2-test",
            "--output",
            str(output),
        ],
    )

    assert exit_code == 0
    assert orjson.loads(output.read_bytes()) == result
    summary = orjson.loads(capsys.readouterr().out)
    assert summary["passed"] is True
    assert summary["source_snapshot_set_id"] == "snapshot-set:sha256:test"
    assert summary["evidence_sha256"] == subject._sha256_file(output)
