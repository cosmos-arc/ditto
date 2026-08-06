"""Content-verified R2 live evidence input for the R3 hard gate."""

from __future__ import annotations

import hashlib
import math
import os
import stat
from collections.abc import Mapping
from dataclasses import InitVar, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Protocol, cast

import orjson

from ditto_application.exceptions import AppProcessError

__all__ = [
    "FileR2LiveGateEvidenceReader",
    "NullR2LiveGateEvidenceReader",
    "R2LiveGateArtifactSource",
    "R2LiveGateEvidenceReader",
    "R2LiveGateEvidenceRef",
    "R2LiveGateEvidenceSource",
    "VerifiedR2LiveGateEvidence",
]

type R2LiveGateStatus = Literal[
    "ready",
    "configuration_blocked",
    "performance_blocked",
    "acceptance_failed",
]

_READY_STATUS = "ready"
_REPORT_STATUSES = frozenset(
    {
        _READY_STATUS,
        "configuration_blocked",
        "performance_blocked",
        "acceptance_failed",
    }
)
_EXPECTED_CONTRACT_COUNT = 19
_SHA256_HEX_LENGTH = 64
_SHA256_URN_LENGTH = len("sha256:") + _SHA256_HEX_LENGTH
_MAX_EVIDENCE_BYTES = 16 * 1024 * 1024
_EVIDENCE_READ_CHUNK_BYTES = 64 * 1024
_R2_HARD_DATASET_PROVIDER_CONTRACTS = {
    "stock_basic": ("tushare:stock_basic", "tushare:bak_basic"),
    "etf_basic": ("tushare:fund_basic",),
    "index_basic": ("tushare:index_basic",),
    "calendar": ("tushare:trade_cal",),
    "stock_daily": ("tushare:daily", "local_tdx:day"),
    "etf_daily": ("tushare:fund_daily", "local_tdx:day"),
    "index_daily": ("tushare:index_daily", "local_tdx:day"),
    "stock_status": ("tushare:stock_st", "tushare:suspend_d", "tushare:bak_basic"),
    "adj_factor": ("tushare:adj_factor",),
    "fund_adj": ("tushare:fund_adj",),
    "balance_sheet": ("tushare:balancesheet",),
    "income_statement": ("tushare:income",),
    "cash_flow": ("tushare:cashflow",),
    "dividend": ("tushare:dividend",),
    "valuation_metrics": ("tushare:daily_basic",),
    "macro_indicators": (
        "tushare:cn_macro",
        "fred:series_observations",
        "alfred:vintages",
    ),
    "commodity_daily": ("fred:commodity_series", "tushare:commodity_reference"),
    "corporate_actions": ("tushare:corporate_actions",),
    "index_weight": ("tushare:index_weight",),
}
_REPRESENTATIVE_DATASETS = frozenset(
    {"stock_daily", "index_daily", "adj_factor", "fund_adj"}
)
_BOOTSTRAP_LIMIT_SECONDS = 24 * 60 * 60
_INCREMENTAL_LIMIT_SECONDS = 30 * 60
_WORKBENCH_QUERY_LIMIT_SECONDS = 5.0
_R2_CERTIFICATION_PROFILE = "r2-modern-a-share-v1"
_MAX_CERTIFICATION_LAG_DAYS = 7
_R2_REQUIRED_CERTIFIED_FROM = {
    dataset_id: "2015-01-01"
    for dataset_id in _R2_HARD_DATASET_PROVIDER_CONTRACTS
    if dataset_id not in {"macro_indicators", "commodity_daily", "index_weight"}
} | {"stock_basic": "2016-01-01", "stock_status": "2016-01-01"}
_VERIFIED_EVIDENCE_TOKEN = object()


def _contract_error(
    message: str,
    *,
    reason: str,
    code: str = "SPEC_INVALID",
) -> AppProcessError:
    return AppProcessError(message, details={"code": code, "reason": reason})


def _is_content_hash(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == _SHA256_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(frozen=True, slots=True)
class R2LiveGateArtifactSource:
    """One exact local artifact path bound to its audit URI and expected hash."""

    path: Path
    artifact_uri: str
    expected_content_hash: str

    def __post_init__(self) -> None:
        """Reject ambiguous source declarations before any filesystem read."""
        if not isinstance(cast("object", self.path), Path):
            raise _contract_error(
                "R2 live artifact path must be Path",
                reason="r2_live_artifact_path_invalid",
            )
        if type(self.artifact_uri) is not str or not self.artifact_uri.strip():
            raise _contract_error(
                "R2 live artifact URI cannot be blank",
                reason="r2_live_artifact_uri_invalid",
            )
        if not _is_content_hash(self.expected_content_hash):
            raise _contract_error(
                "R2 live artifact hash must be lowercase SHA-256",
                reason="r2_live_artifact_hash_invalid",
            )


@dataclass(frozen=True, slots=True)
class R2LiveGateEvidenceSource:
    """Explicit source manifest; the reader never discovers paths implicitly."""

    report_path: Path
    report_uri: str
    expected_report_hash: str
    provider_entitlement_artifacts: tuple[R2LiveGateArtifactSource, ...]
    performance_artifacts: tuple[R2LiveGateArtifactSource, ...]
    recoverability_artifacts: tuple[R2LiveGateArtifactSource, ...]
    idempotency_artifacts: tuple[R2LiveGateArtifactSource, ...]

    def __post_init__(self) -> None:
        """Require exact typed source fields without making any I/O claim."""
        if not isinstance(cast("object", self.report_path), Path):
            raise _contract_error(
                "R2 live report path must be Path",
                reason="r2_live_report_path_invalid",
            )
        if type(self.report_uri) is not str or not self.report_uri.strip():
            raise _contract_error(
                "R2 live report URI cannot be blank",
                reason="r2_live_report_uri_invalid",
            )
        if not _is_content_hash(self.expected_report_hash):
            raise _contract_error(
                "R2 live report hash must be lowercase SHA-256",
                reason="r2_live_report_hash_invalid",
            )
        groups = (
            self.provider_entitlement_artifacts,
            self.performance_artifacts,
            self.recoverability_artifacts,
            self.idempotency_artifacts,
        )
        if any(
            type(group) is not tuple
            or any(type(item) is not R2LiveGateArtifactSource for item in group)
            for group in groups
        ):
            raise _contract_error(
                "R2 live evidence artifact groups must be typed tuples",
                reason="r2_live_artifact_groups_invalid",
            )


@dataclass(frozen=True, slots=True)
class R2LiveGateEvidenceRef:
    """Verified artifact identity safe to persist in a review packet."""

    artifact_uri: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class VerifiedR2LiveGateEvidence:
    """A live acceptance report whose report and referenced bytes were verified."""

    report_uri: str
    report_hash: str
    checked_at: datetime
    status: R2LiveGateStatus
    reason_codes: tuple[str, ...]
    provider_entitlement_evidence_refs: tuple[R2LiveGateEvidenceRef, ...]
    performance_evidence_refs: tuple[R2LiveGateEvidenceRef, ...]
    recoverability_evidence_refs: tuple[R2LiveGateEvidenceRef, ...]
    idempotency_evidence_refs: tuple[R2LiveGateEvidenceRef, ...]
    _factory_token: InitVar[object | None] = None

    def __post_init__(self, _factory_token: object | None) -> None:
        """Prevent callers from hand-constructing a trusted PASS value."""
        if _factory_token is not _VERIFIED_EVIDENCE_TOKEN:
            raise _contract_error(
                "verified R2 live evidence must be reader-produced",
                code="EXPERIMENT_INTEGRITY_FAILED",
                reason="r2_live_verified_evidence_factory_invalid",
            )
        if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
            raise _contract_error(
                "verified R2 checked_at must be timezone-aware",
                code="EXPERIMENT_INTEGRITY_FAILED",
                reason="r2_live_checked_at_invalid",
            )
        groups = (
            self.provider_entitlement_evidence_refs,
            self.performance_evidence_refs,
            self.recoverability_evidence_refs,
            self.idempotency_evidence_refs,
        )
        if self.status == _READY_STATUS and any(not group for group in groups):
            raise _contract_error(
                "ready R2 live evidence requires all artifact groups",
                code="EXPERIMENT_INTEGRITY_FAILED",
                reason="r2_live_verified_artifacts_missing",
            )

    def gate_detail(self) -> dict[str, object]:
        """Return the verified source identity safe to freeze in a review packet."""
        return _evidence_detail(self)


class R2LiveGateEvidenceReader(Protocol):
    """Consumer-owned port returning only content-verified live evidence."""

    def read_verified_live_gate(self) -> VerifiedR2LiveGateEvidence | None:
        """Return one verified live report or None when trust is incomplete."""
        ...


@dataclass(frozen=True, slots=True)
class NullR2LiveGateEvidenceReader:
    """Production-safe default until an explicit live source is injected."""

    def read_verified_live_gate(self) -> None:
        """Keep the gate NOT_EVALUATED without an explicit source manifest."""
        return None


@dataclass(frozen=True, slots=True)
class FileR2LiveGateEvidenceReader:
    """Verify one exact report and its four explicit evidence groups."""

    source: R2LiveGateEvidenceSource

    def read_verified_live_gate(self) -> VerifiedR2LiveGateEvidence | None:
        """Fail closed on any path, byte, hash, shape, or live-mode drift."""
        report_bytes = _read_exact_bytes(
            self.source.report_path,
            expected_uri=self.source.report_uri,
            expected_hash=self.source.expected_report_hash,
        )
        if report_bytes is None:
            return None
        report = _decode_report(report_bytes)
        if report is None or report.get("mode") != "live":
            return None
        status = _status(report.get("status"))
        checked_at = _checked_at(report.get("checked_at"))
        reason_codes = _string_tuple(report.get("reason_codes"))
        if status is None or checked_at is None or reason_codes is None:
            return None
        refs = _verified_source_refs(self.source)
        if refs is None:
            return None
        provider, performance, recoverability, idempotency = refs
        if status == _READY_STATUS and not _ready_report_is_complete(
            report,
            checked_at=checked_at,
            refs=refs,
        ):
            return None
        return VerifiedR2LiveGateEvidence(
            report_uri=self.source.report_uri,
            report_hash=self.source.expected_report_hash,
            checked_at=checked_at,
            status=status,
            reason_codes=reason_codes,
            provider_entitlement_evidence_refs=provider,
            performance_evidence_refs=performance,
            recoverability_evidence_refs=recoverability,
            idempotency_evidence_refs=idempotency,
            _factory_token=_VERIFIED_EVIDENCE_TOKEN,
        )


def _read_exact_bytes(
    path: Path,
    *,
    expected_uri: str,
    expected_hash: str,
) -> bytes | None:
    descriptor: int | None = None
    try:
        resolved = path.resolve(strict=True)
        if resolved.as_uri() != expected_uri:
            return None
        descriptor = os.open(
            resolved,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0),
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size <= 0
            or metadata.st_size > _MAX_EVIDENCE_BYTES
        ):
            return None
        chunks: list[bytes] = []
        remaining = _MAX_EVIDENCE_BYTES + 1
        while remaining > 0:
            chunk = os.read(
                descriptor,
                min(remaining, _EVIDENCE_READ_CHUNK_BYTES),
            )
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
    except (OSError, RuntimeError, ValueError):
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if len(payload) > _MAX_EVIDENCE_BYTES:
        return None
    observed = hashlib.sha256(payload).hexdigest()
    return payload if observed == expected_hash else None


def _decode_report(payload: bytes) -> Mapping[str, object] | None:
    try:
        decoded = orjson.loads(payload)
    except orjson.JSONDecodeError:
        return None
    if type(decoded) is not dict:
        return None
    return cast("Mapping[str, object]", decoded)


def _status(value: object) -> R2LiveGateStatus | None:
    if type(value) is str and value in _REPORT_STATUSES:
        return cast("R2LiveGateStatus", value)
    return None


def _checked_at(value: object) -> datetime | None:
    if type(value) is not str:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _string_tuple(value: object) -> tuple[str, ...] | None:
    if type(value) is not list:
        return None
    strings = cast("list[object]", value)
    if any(type(item) is not str or not item for item in strings):
        return None
    result = tuple(cast("str", item) for item in strings)
    return result if len(set(result)) == len(result) else None


def _string_list_is_nonempty(value: object) -> bool:
    result = _string_tuple(value)
    return result is not None and bool(result)


def _mapping(value: object) -> Mapping[str, object] | None:
    if type(value) is not dict:
        return None
    return cast("Mapping[str, object]", value)


def _verified_ref(source: R2LiveGateArtifactSource) -> R2LiveGateEvidenceRef | None:
    payload = _read_exact_bytes(
        source.path,
        expected_uri=source.artifact_uri,
        expected_hash=source.expected_content_hash,
    )
    if payload is None:
        return None
    return R2LiveGateEvidenceRef(source.artifact_uri, source.expected_content_hash)


def _verified_group(
    sources: tuple[R2LiveGateArtifactSource, ...],
) -> tuple[R2LiveGateEvidenceRef, ...] | None:
    refs: list[R2LiveGateEvidenceRef] = []
    for source in sources:
        ref = _verified_ref(source)
        if ref is None:
            return None
        refs.append(ref)
    if len({ref.artifact_uri for ref in refs}) != len(refs):
        return None
    return tuple(refs)


def _verified_source_refs(
    source: R2LiveGateEvidenceSource,
) -> (
    tuple[
        tuple[R2LiveGateEvidenceRef, ...],
        tuple[R2LiveGateEvidenceRef, ...],
        tuple[R2LiveGateEvidenceRef, ...],
        tuple[R2LiveGateEvidenceRef, ...],
    ]
    | None
):
    groups = (
        _verified_group(source.provider_entitlement_artifacts),
        _verified_group(source.performance_artifacts),
        _verified_group(source.recoverability_artifacts),
        _verified_group(source.idempotency_artifacts),
    )
    provider, performance, recoverability, idempotency = groups
    if (
        provider is None
        or performance is None
        or recoverability is None
        or idempotency is None
    ):
        return None
    all_refs = provider + performance + recoverability + idempotency
    artifact_uris = tuple(ref.artifact_uri for ref in all_refs)
    if (
        len(set(artifact_uris)) != len(artifact_uris)
        or source.report_uri in artifact_uris
    ):
        return None
    return provider, performance, recoverability, idempotency


def _ready_report_is_complete(
    report: Mapping[str, object],
    *,
    checked_at: datetime,
    refs: tuple[
        tuple[R2LiveGateEvidenceRef, ...],
        tuple[R2LiveGateEvidenceRef, ...],
        tuple[R2LiveGateEvidenceRef, ...],
        tuple[R2LiveGateEvidenceRef, ...],
    ],
) -> bool:
    if any(not group for group in refs):
        return False
    if _string_tuple(report.get("reason_codes")) != ():
        return False
    preflight = _mapping(report.get("preflight"))
    recoverability = _mapping(report.get("recoverability"))
    idempotency = _mapping(report.get("idempotency"))
    return (
        preflight is not None
        and recoverability is not None
        and idempotency is not None
        and _ready_preflight(preflight, checked_at)
        and _ready_recoverability(recoverability)
        and _ready_idempotency(idempotency)
    )


def _ready_preflight(value: Mapping[str, object], checked_at: datetime) -> bool:
    if (
        value.get("status") != _READY_STATUS
        or type(value.get("contract_count")) is not int
        or value.get("contract_count") != _EXPECTED_CONTRACT_COUNT
        or _checked_at(value.get("checked_at")) != checked_at
        or _string_tuple(value.get("reason_codes")) != ()
    ):
        return False
    products = value.get("products")
    performance = _mapping(value.get("performance"))
    return (
        type(products) is list
        and _ready_products(cast("list[object]", products), checked_at)
        and performance is not None
        and _ready_performance(performance)
    )


def _iso_date(value: object) -> date | None:
    if type(value) is not str:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _ready_product_certification(
    product: Mapping[str, object],
    *,
    dataset_id: str,
    checked_at: datetime,
) -> bool:
    report_id = product.get("certification_report_id")
    content_hash = product.get("certification_content_hash")
    certified_from = _iso_date(product.get("certified_from"))
    certified_through = _iso_date(product.get("certified_through"))
    required_value = _R2_REQUIRED_CERTIFIED_FROM.get(dataset_id)
    required_from = date.fromisoformat(required_value) if required_value else None
    return (
        product.get("certification_profile") == _R2_CERTIFICATION_PROFILE
        and type(report_id) is str
        and bool(report_id)
        and _is_content_hash(content_hash)
        and certified_from is not None
        and certified_through is not None
        and certified_from <= certified_through
        and (required_from is None or certified_from <= required_from)
        and certified_through <= checked_at.date()
        and (checked_at.date() - certified_through).days <= _MAX_CERTIFICATION_LAG_DAYS
    )


def _ready_products(products: list[object], checked_at: datetime) -> bool:
    if len(products) != _EXPECTED_CONTRACT_COUNT:
        return False
    dataset_ids: list[str] = []
    for item in products:
        product = _mapping(item)
        if product is None:
            return False
        dataset_id = product.get("dataset_id")
        provider_datasets = _string_tuple(product.get("provider_datasets"))
        usable_provider_datasets = _string_tuple(
            product.get("usable_provider_datasets")
        )
        if type(dataset_id) is not str:
            return False
        expected_providers = _R2_HARD_DATASET_PROVIDER_CONTRACTS.get(dataset_id)
        if (
            expected_providers is None
            or provider_datasets is None
            or provider_datasets != expected_providers
            or usable_provider_datasets is None
            or not usable_provider_datasets
            or not set(usable_provider_datasets).issubset(provider_datasets)
            or product.get("ready") is not True
            or _string_tuple(product.get("reason_codes")) != ()
            or not _string_list_is_nonempty(product.get("license_record_ids"))
            or not _string_list_is_nonempty(product.get("usable_provider_datasets"))
            or not _ready_product_certification(
                product,
                dataset_id=dataset_id,
                checked_at=checked_at,
            )
        ):
            return False
        dataset_ids.append(dataset_id)
    return frozenset(dataset_ids) == frozenset(_R2_HARD_DATASET_PROVIDER_CONTRACTS)


def _ready_duration_pair(
    value: Mapping[str, object],
    *,
    observed_key: str,
    limit_key: str,
    expected_limit: int | float,
) -> bool:
    observed = value.get(observed_key)
    limit = value.get(limit_key)
    if type(observed) not in {int, float} or type(limit) not in {int, float}:
        return False
    observed_number = cast("int | float", observed)
    limit_number = cast("int | float", limit)
    return (
        math.isfinite(observed_number)
        and math.isfinite(limit_number)
        and observed_number >= 0
        and limit_number == expected_limit
        and observed_number <= expected_limit
    )


def _ready_performance(value: Mapping[str, object]) -> bool:
    datasets = _string_tuple(value.get("representative_datasets"))
    return (
        datasets is not None
        and frozenset(datasets) == _REPRESENTATIVE_DATASETS
        and value.get("bootstrap_passed") is True
        and value.get("incremental_passed") is True
        and value.get("workbench_query_passed") is True
        and _ready_duration_pair(
            value,
            observed_key="projected_bootstrap_seconds",
            limit_key="bootstrap_limit_seconds",
            expected_limit=_BOOTSTRAP_LIMIT_SECONDS,
        )
        and _ready_duration_pair(
            value,
            observed_key="incremental_elapsed_seconds",
            limit_key="incremental_limit_seconds",
            expected_limit=_INCREMENTAL_LIMIT_SECONDS,
        )
        and _ready_duration_pair(
            value,
            observed_key="workbench_query_seconds",
            limit_key="workbench_query_limit_seconds",
            expected_limit=_WORKBENCH_QUERY_LIMIT_SECONDS,
        )
        and _string_tuple(value.get("reason_codes")) == ()
    )


def _ready_recoverability(value: Mapping[str, object]) -> bool:
    row_counts = value.get("sqlite_table_row_counts")
    payload_hash = value.get("payload_root_sha256")
    if type(row_counts) is not dict or not row_counts:
        return False
    typed_counts = cast("dict[object, object]", row_counts)
    counts_valid = all(
        type(key) is str and bool(key) and type(count) is int and count >= 0
        for key, count in typed_counts.items()
    )
    nonempty_data = any(
        type(count) is int and count > 0 for count in typed_counts.values()
    )
    return (
        value.get("passed") is True
        and counts_valid
        and nonempty_data
        and type(payload_hash) is str
        and payload_hash.startswith("sha256:")
        and len(payload_hash) == _SHA256_URN_LENGTH
        and _is_content_hash(payload_hash.removeprefix("sha256:"))
        and _string_tuple(value.get("reason_codes")) == ()
    )


def _idempotency_snapshot(value: Mapping[str, object]) -> tuple[object, ...] | None:
    durable_identity_count = value.get("durable_identity_count")
    write_attempt_count = value.get("write_attempt_count")
    snapshot_ids = _string_tuple(value.get("snapshot_ids"))
    if (
        type(durable_identity_count) is not int
        or durable_identity_count <= 0
        or type(write_attempt_count) is not int
        or write_attempt_count < 0
        or snapshot_ids is None
        or not snapshot_ids
    ):
        return None
    return durable_identity_count, write_attempt_count, snapshot_ids


def _ready_idempotency(value: Mapping[str, object]) -> bool:
    first = _mapping(value.get("first"))
    second = _mapping(value.get("second"))
    if first is None or second is None:
        return False
    first_snapshot = _idempotency_snapshot(first)
    second_snapshot = _idempotency_snapshot(second)
    second_run_write_attempts = value.get("second_run_write_attempts")
    return (
        value.get("passed") is True
        and type(second_run_write_attempts) is int
        and second_run_write_attempts == 0
        and _string_tuple(value.get("reason_codes")) == ()
        and first_snapshot is not None
        and first_snapshot == second_snapshot
    )


def _ref_payload(ref: R2LiveGateEvidenceRef) -> dict[str, str]:
    return {
        "artifact_uri": ref.artifact_uri,
        "content_hash": ref.content_hash,
    }


def _evidence_detail(evidence: VerifiedR2LiveGateEvidence) -> dict[str, object]:
    return {
        "report_uri": evidence.report_uri,
        "report_hash": evidence.report_hash,
        "checked_at": evidence.checked_at.isoformat(),
        "status": evidence.status,
        "reason_codes": evidence.reason_codes,
        "provider_entitlement_evidence_refs": tuple(
            _ref_payload(ref) for ref in evidence.provider_entitlement_evidence_refs
        ),
        "performance_evidence_refs": tuple(
            _ref_payload(ref) for ref in evidence.performance_evidence_refs
        ),
        "recoverability_evidence_refs": tuple(
            _ref_payload(ref) for ref in evidence.recoverability_evidence_refs
        ),
        "idempotency_evidence_refs": tuple(
            _ref_payload(ref) for ref in evidence.idempotency_evidence_refs
        ),
    }
