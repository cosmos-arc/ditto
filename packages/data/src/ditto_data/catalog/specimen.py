"""
Five-category data specimen evidence contracts.

A specimen is one adjudicated evidence pack for a concrete security/event
sample (issue #259): financial restatement, delisted security, index rebalance,
dividend ETF, cross-border ETF. Records keep what was actually collected;
missing evidence stays explicit and never upgrades to a pass.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from typing import Literal, Protocol, cast, runtime_checkable

import orjson

from ditto_data.catalog.field_admission import DATA_USES, DataUse

__all__ = [
    "SPECIMEN_CATEGORIES",
    "DataSpecimen",
    "SpecimenCategory",
    "SpecimenConventionAlignment",
    "SpecimenProcurement",
    "SpecimenReader",
    "SpecimenSource",
    "SpecimenVerification",
    "SpecimenWriter",
]

type SpecimenCategory = Literal[
    "financial_restatement",
    "delisted_security",
    "index_rebalance",
    "dividend_etf",
    "cross_border_etf",
]
SPECIMEN_CATEGORIES: tuple[SpecimenCategory, ...] = (
    "financial_restatement",
    "delisted_security",
    "index_rebalance",
    "dividend_etf",
    "cross_border_etf",
)

type SpecimenVerification = Literal["verified", "unverified"]
type SpecimenConventionAlignment = Literal["aligned", "divergent", "single_source"]
type ProcurementOption = Literal["in_budget", "professional"]
type QuoteStatus = Literal["unknown", "recorded"]

_TIME_PRECISIONS = ("timestamp", "date", "unknown")
_MIN_INDEPENDENT_SOURCES = 2
_DATE_TEXT_WIDTH = 10


@dataclass(frozen=True)
class SpecimenSource:
    """One provider's collected original for the specimen anchor."""

    source: str
    provider_snapshot_id: str | None = None
    upstream_group: str | None = None


@dataclass(frozen=True)
class SpecimenProcurement:
    """One procurement track record; quotes stay unknown until actually asked."""

    option: ProcurementOption
    quote_status: QuoteStatus
    notes: str | None = None


@dataclass(frozen=True)
class DataSpecimen:
    """Immutable adjudicated specimen evidence, content-addressed."""

    category: SpecimenCategory
    dataset_id: str
    anchor: str
    sources: tuple[SpecimenSource, ...]
    upstream_independent: bool = False
    convention_alignment: SpecimenConventionAlignment = "single_source"
    coverage_from: date | None = None
    coverage_to: date | None = None
    knowable_from: datetime | None = None
    time_precision: str = "unknown"
    as_of_counterexample: str | None = None
    license_record_ids: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
    allowed_uses: tuple[DataUse, ...] = ()
    verification_status: SpecimenVerification = "unverified"
    procurement: tuple[SpecimenProcurement, ...] = ()
    adjudicated_by: str | None = None
    adjudicated_at: datetime | None = None
    evidence_uri: str | None = None
    specimen_id: str = field(init=False)

    def __post_init__(self) -> None:
        """Normalize gaps and fail closed on unverifiable claims."""
        _validate_identity(self)
        _validate_sources(self)
        _validate_temporal_fields(self)
        if any(use not in DATA_USES for use in self.allowed_uses) or len(
            set(self.allowed_uses)
        ) != len(self.allowed_uses):
            raise ValueError(f"invalid specimen allowed uses: {self.allowed_uses!r}")
        _validate_convention_alignment(self)
        gaps = list(self.gaps)
        gaps.extend(_structural_gaps(self))
        if self.verification_status == "verified":
            _require_verified_evidence(self)
        elif self.allowed_uses:
            raise ValueError("unverified specimen cannot claim allowed uses")
        elif not gaps:
            raise ValueError("unverified specimen must record explicit gaps")
        object.__setattr__(self, "gaps", tuple(dict.fromkeys(gaps)))
        object.__setattr__(self, "specimen_id", _identity(self))

    def to_payload(self) -> dict[str, object]:
        """JSON-safe payload for persistence and transport."""
        return {str(key): _normalize(value) for key, value in asdict(self).items()}

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> DataSpecimen:
        """Rebuild one record from persisted JSON, re-running validation."""
        return cls(
            category=_enum(payload, "category", SPECIMEN_CATEGORIES),
            dataset_id=_required_str(payload, "dataset_id"),
            anchor=_required_str(payload, "anchor"),
            sources=_sources(payload),
            upstream_independent=_flag(payload, "upstream_independent"),
            convention_alignment=_enum(
                payload,
                "convention_alignment",
                ("aligned", "divergent", "single_source"),
                default="single_source",
            ),
            coverage_from=_optional_date(payload.get("coverage_from")),
            coverage_to=_optional_date(payload.get("coverage_to")),
            knowable_from=_optional_datetime(payload.get("knowable_from")),
            time_precision=_enum(
                payload, "time_precision", _TIME_PRECISIONS, default="unknown"
            ),
            as_of_counterexample=_optional_str(payload, "as_of_counterexample"),
            license_record_ids=_str_tuple(payload, "license_record_ids"),
            gaps=_str_tuple(payload, "gaps"),
            allowed_uses=tuple(
                cast(
                    DataUse,
                    use,
                )
                for use in _str_tuple(payload, "allowed_uses")
            ),
            verification_status=_enum(
                payload,
                "verification_status",
                ("verified", "unverified"),
                default="unverified",
            ),
            procurement=_procurement(payload),
            adjudicated_by=_optional_str(payload, "adjudicated_by"),
            adjudicated_at=_optional_datetime(payload.get("adjudicated_at")),
            evidence_uri=_optional_str(payload, "evidence_uri"),
        )


def _validate_identity(specimen: DataSpecimen) -> None:
    if specimen.category not in SPECIMEN_CATEGORIES:
        raise ValueError(f"unknown specimen category: {specimen.category!r}")
    for name in ("dataset_id", "anchor"):
        value: str = getattr(specimen, name)
        if not value or value.strip() != value:
            raise ValueError(f"invalid specimen {name}: {value!r}")


def _validate_sources(specimen: DataSpecimen) -> None:
    if not specimen.sources:
        raise ValueError("specimen requires at least one source")
    seen: set[str] = set()
    for item in specimen.sources:
        if not item.source or item.source != item.source.lower():
            raise ValueError(f"invalid specimen source name: {item.source!r}")
        if item.source in seen:
            raise ValueError(f"duplicate specimen source: {item.source!r}")
        seen.add(item.source)


def _validate_temporal_fields(specimen: DataSpecimen) -> None:
    if specimen.time_precision not in _TIME_PRECISIONS:
        raise ValueError(f"invalid time precision: {specimen.time_precision!r}")
    if (
        specimen.coverage_from is not None
        and specimen.coverage_to is not None
        and specimen.coverage_to < specimen.coverage_from
    ):
        raise ValueError("specimen coverage_to precedes coverage_from")
    for name in ("knowable_from", "adjudicated_at"):
        value: datetime | None = getattr(specimen, name)
        if value is not None and value.tzinfo is None:
            raise ValueError(f"specimen {name} must be timezone-aware")


def _validate_convention_alignment(specimen: DataSpecimen) -> None:
    alignment = specimen.convention_alignment
    if alignment not in ("aligned", "divergent", "single_source"):
        raise ValueError(f"invalid convention alignment: {alignment!r}")
    if len(specimen.sources) == 1 and alignment != "single_source":
        raise ValueError("single-source specimen must declare single_source")
    if len(specimen.sources) > 1 and alignment == "single_source":
        raise ValueError("multi-source specimen must declare aligned or divergent")


def _structural_gaps(specimen: DataSpecimen) -> tuple[str, ...]:
    """Gaps the structure itself proves, regardless of adjudication."""
    gaps: list[str] = []
    sources = specimen.sources
    if len(sources) > 1:
        if not specimen.upstream_independent:
            gaps.append("UPSTREAM_INDEPENDENCE_UNPROVEN")
        groups = [
            item.upstream_group for item in sources if item.upstream_group is not None
        ]
        if len(set(groups)) != len(groups):
            gaps.append("UPSTREAM_SHARED")
    if specimen.convention_alignment == "divergent":
        gaps.append("CONVENTION_DIVERGENCE")
    if any(item.quote_status == "unknown" for item in specimen.procurement):
        gaps.append("QUOTE_UNKNOWN")
    return tuple(gaps)


def _require_verified_evidence(specimen: DataSpecimen) -> None:
    if specimen.adjudicated_at is not None and (specimen.adjudicated_at.tzinfo is None):
        raise ValueError("specimen adjudicated_at must be timezone-aware")
    missing = (
        specimen.coverage_from is None
        or specimen.knowable_from is None
        or not specimen.license_record_ids
        or not specimen.as_of_counterexample
        or specimen.as_of_counterexample.strip() != specimen.as_of_counterexample
        or specimen.adjudicated_by is None
        or specimen.adjudicated_at is None
        or not any(item.provider_snapshot_id for item in specimen.sources)
    )
    if missing:
        raise ValueError(
            "verified specimen requires original snapshot, coverage, knowable time, "
            + "licenses, as-of counterexample and adjudication"
        )
    if specimen.upstream_independent:
        collected = all(item.provider_snapshot_id for item in specimen.sources)
        groups = [item.upstream_group for item in specimen.sources]
        distinct = (
            len(specimen.sources) >= _MIN_INDEPENDENT_SOURCES
            and all(group is not None for group in groups)
            and len(set(groups)) == len(groups)
        )
        if not (collected and distinct):
            raise ValueError(
                "independent verification requires two collected sources with "
                + "distinct declared upstream groups"
            )


def _normalize(value: object) -> object:
    if isinstance(value, dict):
        entries = cast("dict[object, object]", value)
        return {str(key): _normalize(item) for key, item in entries.items()}
    if isinstance(value, (list, tuple)):
        items = cast("Sequence[object]", value)
        return [_normalize(item) for item in items]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"specimen date field must be an ISO string: {value!r}")
    if len(value) != _DATE_TEXT_WIDTH:
        raise ValueError(f"specimen date field must be YYYY-MM-DD: {value!r}")
    return date.fromisoformat(value)


def _optional_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"specimen datetime field must be an ISO string: {value!r}")
    return datetime.fromisoformat(value)


def _required_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"specimen payload field {key} must be a non-empty string")
    return value


def _optional_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"specimen payload field {key} must be a string")
    return value


def _flag(payload: dict[str, object], key: str) -> bool:
    value = payload.get(key, False)
    if not isinstance(value, bool):
        raise ValueError(f"specimen payload field {key} must be a boolean")
    return value


def _enum[T: str](
    payload: dict[str, object],
    key: str,
    choices: tuple[T, ...],
    *,
    default: T | None = None,
) -> T:
    value = payload.get(key, default)
    if value is None:
        raise ValueError(f"specimen payload field {key} is required")
    if not isinstance(value, str) or value not in choices:
        raise ValueError(
            f"specimen payload field {key} must be one of {choices}: {value!r}"
        )
    return cast("T", value)


def _str_tuple(payload: dict[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key, ())
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"specimen payload field {key} must be a list of strings")
    items = cast("Sequence[object]", value)
    if any(not isinstance(item, str) for item in items):
        raise ValueError(f"specimen payload field {key} must be a list of strings")
    return tuple(cast("Sequence[str]", items))


def _sources(payload: dict[str, object]) -> tuple[SpecimenSource, ...]:
    value = payload.get("sources", ())
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("specimen payload field sources must be a non-empty list")
    sources: list[SpecimenSource] = []
    for raw in cast("Sequence[object]", value):
        if not isinstance(raw, dict):
            raise ValueError("each specimen source must be an object")
        item = cast("dict[str, object]", raw)
        sources.append(
            SpecimenSource(
                source=_required_str(item, "source"),
                provider_snapshot_id=_optional_str(item, "provider_snapshot_id"),
                upstream_group=_optional_str(item, "upstream_group"),
            )
        )
    return tuple(sources)


def _procurement(payload: dict[str, object]) -> tuple[SpecimenProcurement, ...]:
    value = payload.get("procurement", ())
    if not isinstance(value, (list, tuple)):
        raise ValueError("specimen payload field procurement must be a list")
    tracks: list[SpecimenProcurement] = []
    for raw in cast("Sequence[object]", value):
        if not isinstance(raw, dict):
            raise ValueError("each procurement track must be an object")
        item = cast("dict[str, object]", raw)
        tracks.append(
            SpecimenProcurement(
                option=_enum(item, "option", ("in_budget", "professional")),
                quote_status=_enum(item, "quote_status", ("unknown", "recorded")),
                notes=_optional_str(item, "notes"),
            )
        )
    return tuple(tracks)


def _identity(specimen: DataSpecimen) -> str:
    payload = {
        item.name: _normalize(getattr(specimen, item.name))
        for item in fields(specimen)
        if item.name != "specimen_id"
    }
    digest = hashlib.sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS))
    return f"specimen:{specimen.category}:sha256:{digest.hexdigest()}"


@runtime_checkable
class SpecimenReader(Protocol):
    """Read append-only specimen evidence."""

    def get_specimen(self, specimen_id: str) -> DataSpecimen | None:
        """Return one immutable specimen record by ID."""
        ...

    def list_specimens(
        self,
        *,
        category: SpecimenCategory | None = None,
        dataset_id: str | None = None,
    ) -> tuple[DataSpecimen, ...]:
        """List adjudicated records newest-first with optional filters."""
        ...


@runtime_checkable
class SpecimenWriter(Protocol):
    """Append adjudicated specimen evidence."""

    def append_specimen(self, specimen: DataSpecimen) -> None:
        """Append one immutable specimen record idempotently."""
        ...
