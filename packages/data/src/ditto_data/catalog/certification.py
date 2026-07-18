"""Immutable certification evidence and append-only governance contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from typing import Any, Literal, Protocol, cast

import orjson

from ditto_data.catalog.coverage import CoverageException, DatasetCoverage
from ditto_data.catalog.metadata import DatasetSchedule

__all__ = [
    "CertificationEvidence",
    "CertificationGovernanceStore",
    "CertificationReader",
    "CertificationReviewEvent",
    "CertificationReviewer",
    "CertificationRevoker",
    "CertificationWriter",
    "DatasetCertificationReport",
    "EvidenceCheck",
    "report_from_json",
    "report_to_json",
]

type CertificationAction = Literal["approved", "revoked"]


@dataclass(frozen=True, slots=True)
class EvidenceCheck:
    """One named, addressable certification check."""

    name: str
    evidence_uri: str
    passed: bool

    def __post_init__(self) -> None:
        """Validate the evidence label and durable reference."""
        _validate_text("evidence check name", self.name)
        _validate_text("evidence check URI", self.evidence_uri)


@dataclass(frozen=True, slots=True)
class CertificationEvidence:
    """Complete evidence bundle required to certify one dataset independently."""

    source_ids: tuple[str, ...]
    schema_versions: tuple[str, ...]
    snapshot_ids: tuple[str, ...]
    dq_rule_version: str
    dq_results: tuple[EvidenceCheck, ...]
    pit_replay_results: tuple[EvidenceCheck, ...]
    fallback_history: tuple[str, ...]
    override_history: tuple[str, ...]
    freshness_results: tuple[EvidenceCheck, ...]
    recovery_results: tuple[EvidenceCheck, ...]
    license_record_ids: tuple[str, ...]
    consumer_results: tuple[EvidenceCheck, ...]

    def __post_init__(self) -> None:
        """Validate that every mandatory evidence group is populated."""
        _validate_text("DQ rule version", self.dq_rule_version)
        for field_name in (
            "source_ids",
            "schema_versions",
            "snapshot_ids",
            "fallback_history",
            "license_record_ids",
        ):
            values = cast(tuple[str, ...], getattr(self, field_name))
            if not values or len(set(values)) != len(values):
                raise ValueError(f"invalid certification {field_name}: {values!r}")
            for value in values:
                _validate_text(field_name, value)
        for value in self.override_history:
            _validate_text("override_history", value)
        for field_name in (
            "dq_results",
            "pit_replay_results",
            "freshness_results",
            "recovery_results",
            "consumer_results",
        ):
            checks = cast(tuple[EvidenceCheck, ...], getattr(self, field_name))
            if not checks:
                raise ValueError(f"certification {field_name} cannot be empty")

    @property
    def all_checks_passed(self) -> bool:
        """Return whether all DQ, replay, operational, and consumer checks pass."""
        groups = (
            self.dq_results,
            self.pit_replay_results,
            self.freshness_results,
            self.recovery_results,
            self.consumer_results,
        )
        return all(check.passed for group in groups for check in group)


@dataclass(frozen=True, slots=True)
class DatasetCertificationReport:
    """Content-addressed machine report awaiting independent human review."""

    report_id: str
    dataset_id: str
    profile: str
    coverage: DatasetCoverage
    evidence: CertificationEvidence
    generated_at: datetime
    content_hash: str

    def __post_init__(self) -> None:
        """Recompute identities and reject mutation of frozen report facts."""
        _validate_text("dataset_id", self.dataset_id)
        _validate_text("profile", self.profile)
        if self.coverage.dataset_id != self.dataset_id:
            raise ValueError("certification coverage dataset does not match report")
        if not self.coverage.is_complete:
            raise ValueError("certification coverage is incomplete")
        if not self.evidence.all_checks_passed:
            raise ValueError("certification evidence contains failed checks")
        if self.generated_at.tzinfo is None:
            raise ValueError("certification generated_at must be timezone-aware")
        expected_hash = _content_hash(
            dataset_id=self.dataset_id,
            profile=self.profile,
            coverage=self.coverage,
            evidence=self.evidence,
        )
        if self.content_hash != expected_hash:
            raise ValueError("certification content_hash does not match frozen facts")
        if self.report_id != _report_id(
            dataset_id=self.dataset_id,
            profile=self.profile,
            content_hash=self.content_hash,
            generated_at=self.generated_at,
        ):
            raise ValueError("certification report_id does not match frozen report")

    @classmethod
    def create(
        cls,
        *,
        dataset_id: str,
        profile: str,
        coverage: DatasetCoverage,
        evidence: CertificationEvidence,
        generated_at: datetime,
    ) -> DatasetCertificationReport:
        """Create a content-addressed immutable report from machine facts."""
        content_hash = _content_hash(
            dataset_id=dataset_id,
            profile=profile,
            coverage=coverage,
            evidence=evidence,
        )
        return cls(
            report_id=_report_id(
                dataset_id=dataset_id,
                profile=profile,
                content_hash=content_hash,
                generated_at=generated_at,
            ),
            dataset_id=dataset_id,
            profile=profile,
            coverage=coverage,
            evidence=evidence,
            generated_at=generated_at,
            content_hash=content_hash,
        )


@dataclass(frozen=True, slots=True)
class CertificationReviewEvent:
    """Append-only human approval or revocation event."""

    event_id: int
    report_id: str
    dataset_id: str
    profile: str
    action: CertificationAction
    actor: str
    occurred_at: datetime
    reason: str | None = None


class CertificationWriter(Protocol):
    """Port for freezing machine-generated certification reports."""

    def append_report(
        self,
        report: DatasetCertificationReport,
    ) -> DatasetCertificationReport:
        """Freeze one machine-generated report."""
        ...


class CertificationReader(Protocol):
    """Port for certification reports and their immutable review history."""

    def get_report(self, report_id: str) -> DatasetCertificationReport | None:
        """Return one report by immutable identity."""
        ...

    def get_active_report(
        self,
        dataset_id: str,
        profile: str,
    ) -> DatasetCertificationReport | None:
        """Return the currently approved report for a dataset profile."""
        ...

    def list_reports(
        self,
        dataset_id: str,
        profile: str,
    ) -> tuple[DatasetCertificationReport, ...]:
        """Return immutable report history in insertion order."""
        ...

    def list_events(
        self,
        report_id: str,
    ) -> tuple[CertificationReviewEvent, ...]:
        """Return all human decisions for one report."""
        ...


class CertificationReviewer(Protocol):
    """Port for appending an independent approval event."""

    def approve_report(
        self,
        report_id: str,
        *,
        reviewer: str,
        reviewed_at: datetime,
    ) -> CertificationReviewEvent:
        """Append an approval event."""
        ...


class CertificationRevoker(Protocol):
    """Port for revoking an approved certification without deleting history."""

    def revoke_report(
        self,
        report_id: str,
        *,
        revoked_by: str,
        revoked_at: datetime,
        reason: str,
    ) -> CertificationReviewEvent:
        """Append a revocation event."""
        ...


class CertificationGovernanceStore(
    CertificationWriter,
    CertificationReader,
    CertificationReviewer,
    CertificationRevoker,
    Protocol,
):
    """Combined application command boundary for certification governance."""


def report_to_json(report: DatasetCertificationReport) -> str:
    """Serialize a validated report for durable storage."""
    return orjson.dumps(_report_payload(report), option=orjson.OPT_SORT_KEYS).decode()


def report_from_json(value: str) -> DatasetCertificationReport:
    """Deserialize and revalidate a stored report."""
    payload = cast(dict[str, Any], orjson.loads(value))
    coverage_payload = cast(dict[str, Any], payload["coverage"])
    evidence_payload = cast(dict[str, Any], payload["evidence"])
    coverage = DatasetCoverage(
        dataset_id=str(coverage_payload["dataset_id"]),
        schedule=cast(DatasetSchedule, coverage_payload["schedule"]),
        target_from=_date(coverage_payload["target_from"]),
        target_to=_date(coverage_payload["target_to"]),
        native_from=_optional_date(coverage_payload["native_from"]),
        native_to=_optional_date(coverage_payload["native_to"]),
        actual_from=_optional_date(coverage_payload["actual_from"]),
        actual_to=_optional_date(coverage_payload["actual_to"]),
        raw_from=_optional_date(coverage_payload["raw_from"]),
        complete_from=_optional_date(coverage_payload["complete_from"]),
        expected_partitions=int(coverage_payload["expected_partitions"]),
        actual_partitions=int(coverage_payload["actual_partitions"]),
        gaps=tuple(_date(item) for item in coverage_payload["gaps"]),
        exceptions=tuple(
            _coverage_exception(cast(dict[str, Any], item))
            for item in coverage_payload["exceptions"]
        ),
        collected_at=datetime.fromisoformat(str(coverage_payload["collected_at"])),
    )
    evidence = CertificationEvidence(
        source_ids=_strings(evidence_payload["source_ids"]),
        schema_versions=_strings(evidence_payload["schema_versions"]),
        snapshot_ids=_strings(evidence_payload["snapshot_ids"]),
        dq_rule_version=str(evidence_payload["dq_rule_version"]),
        dq_results=_checks(evidence_payload["dq_results"]),
        pit_replay_results=_checks(evidence_payload["pit_replay_results"]),
        fallback_history=_strings(evidence_payload["fallback_history"]),
        override_history=_strings(evidence_payload["override_history"]),
        freshness_results=_checks(evidence_payload["freshness_results"]),
        recovery_results=_checks(evidence_payload["recovery_results"]),
        license_record_ids=_strings(evidence_payload["license_record_ids"]),
        consumer_results=_checks(evidence_payload["consumer_results"]),
    )
    return DatasetCertificationReport(
        report_id=str(payload["report_id"]),
        dataset_id=str(payload["dataset_id"]),
        profile=str(payload["profile"]),
        coverage=coverage,
        evidence=evidence,
        generated_at=datetime.fromisoformat(str(payload["generated_at"])),
        content_hash=str(payload["content_hash"]),
    )


def _report_payload(report: DatasetCertificationReport) -> dict[str, object]:
    return {
        "report_id": report.report_id,
        "dataset_id": report.dataset_id,
        "profile": report.profile,
        "coverage": _coverage_payload(report.coverage),
        "evidence": _evidence_payload(report.evidence),
        "generated_at": report.generated_at.isoformat(),
        "content_hash": report.content_hash,
    }


def _coverage_payload(coverage: DatasetCoverage) -> dict[str, object]:
    return {
        "dataset_id": coverage.dataset_id,
        "schedule": coverage.schedule,
        "target_from": coverage.target_from.isoformat(),
        "target_to": coverage.target_to.isoformat(),
        "native_from": _optional_isoformat(coverage.native_from),
        "native_to": _optional_isoformat(coverage.native_to),
        "actual_from": _optional_isoformat(coverage.actual_from),
        "actual_to": _optional_isoformat(coverage.actual_to),
        "raw_from": _optional_isoformat(coverage.raw_from),
        "complete_from": _optional_isoformat(coverage.complete_from),
        "expected_partitions": coverage.expected_partitions,
        "actual_partitions": coverage.actual_partitions,
        "gaps": [item.isoformat() for item in coverage.gaps],
        "exceptions": [
            {
                "code": item.code,
                "owner": item.owner,
                "evidence_uri": item.evidence_uri,
                "start_date": item.start_date.isoformat(),
                "end_date": item.end_date.isoformat(),
            }
            for item in coverage.exceptions
        ],
        "collected_at": coverage.collected_at.isoformat(),
    }


def _evidence_payload(evidence: CertificationEvidence) -> dict[str, object]:
    return {
        "source_ids": evidence.source_ids,
        "schema_versions": evidence.schema_versions,
        "snapshot_ids": evidence.snapshot_ids,
        "dq_rule_version": evidence.dq_rule_version,
        "dq_results": _check_payloads(evidence.dq_results),
        "pit_replay_results": _check_payloads(evidence.pit_replay_results),
        "fallback_history": evidence.fallback_history,
        "override_history": evidence.override_history,
        "freshness_results": _check_payloads(evidence.freshness_results),
        "recovery_results": _check_payloads(evidence.recovery_results),
        "license_record_ids": evidence.license_record_ids,
        "consumer_results": _check_payloads(evidence.consumer_results),
    }


def _check_payloads(checks: tuple[EvidenceCheck, ...]) -> list[dict[str, object]]:
    return [
        {
            "name": check.name,
            "evidence_uri": check.evidence_uri,
            "passed": check.passed,
        }
        for check in checks
    ]


def _content_hash(
    *,
    dataset_id: str,
    profile: str,
    coverage: DatasetCoverage,
    evidence: CertificationEvidence,
) -> str:
    payload = {
        "dataset_id": dataset_id,
        "profile": profile,
        "coverage": _coverage_payload(coverage),
        "evidence": _evidence_payload(evidence),
    }
    return sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()


def _report_id(
    *,
    dataset_id: str,
    profile: str,
    content_hash: str,
    generated_at: datetime,
) -> str:
    identity = (
        f"{dataset_id}\x1f{profile}\x1f{content_hash}\x1f{generated_at.isoformat()}"
    )
    return f"certification:{sha256(identity.encode()).hexdigest()}"


def _coverage_exception(payload: dict[str, Any]) -> CoverageException:
    return CoverageException(
        code=str(payload["code"]),
        owner=str(payload["owner"]),
        evidence_uri=str(payload["evidence_uri"]),
        start_date=_date(payload["start_date"]),
        end_date=_date(payload["end_date"]),
    )


def _strings(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in cast(list[object], value))


def _checks(value: object) -> tuple[EvidenceCheck, ...]:
    payloads = cast(list[dict[str, Any]], value)
    return tuple(
        EvidenceCheck(
            name=str(payload["name"]),
            evidence_uri=str(payload["evidence_uri"]),
            passed=bool(payload["passed"]),
        )
        for payload in payloads
    )


def _date(value: object) -> date:
    return date.fromisoformat(str(value))


def _optional_date(value: object) -> date | None:
    return None if value is None else _date(value)


def _optional_isoformat(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _validate_text(field: str, value: str) -> None:
    if not value or value.strip() != value:
        raise ValueError(f"invalid certification {field}: {value!r}")
