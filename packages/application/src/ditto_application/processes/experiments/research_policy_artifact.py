"""Exact instrument-rules artifact trust boundary for research execution."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from types import MappingProxyType
from typing import cast

import orjson
import polars as pl
from ditto_execution.rules import InMemoryRuleProvider
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import FeeSchedule, InstrumentDefinition, TradingRuleSet

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.execution_bundle import (
    ContentAddressedResearchInput,
)

__all__ = [
    "InstrumentRulesArtifactEvidence",
    "VerifiedInstrumentRulesArtifact",
]


_ARTIFACT_KIND = "instrument_rules"
_SCHEMA_V1 = (
    ("instrument_code", pl.String),
    ("instrument_id", pl.Int64),
    ("asset_class", pl.String),
    ("exchange", pl.String),
    ("currency", pl.String),
    ("tick_size", pl.Float64),
    ("lot_size", pl.Int64),
    ("multiplier", pl.Float64),
    ("board_segment", pl.String),
    ("lifecycle_state", pl.String),
    ("ipo_date", pl.Date),
    ("delisting_date", pl.Date),
    ("as_of_date", pl.Date),
    ("known_at", pl.Date),
    ("settlement_cycle", pl.Int64),
    ("fund_settlement_cycle", pl.Int64),
    ("price_limit_pct", pl.Float64),
    ("order_types_supported", pl.List(pl.String)),
    ("call_auction_sessions", pl.List(pl.String)),
    ("commission_rate", pl.Float64),
    ("min_commission", pl.Float64),
    ("stamp_duty_rate", pl.Float64),
    ("transfer_fee_rate", pl.Float64),
    ("source_snapshot_id", pl.String),
)
_NULLABLE_COLUMNS = frozenset({"ipo_date", "delisting_date", "price_limit_pct"})
_FLOAT_COLUMNS = (
    "tick_size",
    "multiplier",
    "price_limit_pct",
    "commission_rate",
    "min_commission",
    "stamp_duty_rate",
    "transfer_fee_rate",
)

type _RawRuleRow = tuple[
    str,
    int,
    str,
    str,
    str,
    float,
    int,
    float,
    str,
    str,
    date | None,
    date | None,
    date,
    date,
    int,
    int,
    float | None,
    list[object],
    list[object],
    float,
    float,
    float,
    float,
    str,
]


def _error(message: str, reason: str, **details: object) -> AppProcessError:
    return AppProcessError(
        message,
        details={
            "code": "REPRODUCIBILITY_FAILED",
            "reason": reason,
            **details,
        },
    )


def _schema_hash(frame: pl.DataFrame) -> str:
    fields = tuple((name, str(dtype)) for name, dtype in frame.schema.items())
    return hashlib.sha256(orjson.dumps(fields)).hexdigest()


def _valid_exact_text(value: str) -> bool:
    return bool(value) and value == value.strip()


def _validate_collection(
    values: list[object],
    *,
    field_name: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    if (not allow_empty and not values) or any(
        type(item) is not str or not item or item != item.strip() for item in values
    ):
        raise _error(
            "instrument trading-rule collection is invalid",
            "invalid_trading_rule_collection",
            field=field_name,
        )
    typed_values = cast("list[str]", values)
    if len(set(typed_values)) != len(typed_values):
        raise _error(
            "instrument trading-rule collection contains duplicates",
            "invalid_trading_rule_collection",
            field=field_name,
        )
    return tuple(typed_values)


@dataclass(frozen=True, slots=True)
class _ParsedRuleRow:
    instrument_code: str
    instrument_id: int
    asset_class: str
    exchange: str
    currency: str
    tick_size: float
    lot_size: int
    multiplier: float
    board_segment: str
    lifecycle_state: str
    ipo_date: date | None
    delisting_date: date | None
    as_of_date: date
    known_at: date
    settlement_cycle: int
    fund_settlement_cycle: int
    price_limit_pct: float | None
    order_types_supported: list[object]
    call_auction_sessions: list[object]
    commission_rate: float
    min_commission: float
    stamp_duty_rate: float
    transfer_fee_rate: float
    source_snapshot_id: str


@dataclass(frozen=True, slots=True)
class _RuleRowModels:
    instrument_code: str
    source_snapshot_id: str
    mapping: _InstrumentMappingEvidence
    definition: InstrumentDefinition
    trading_rule: TradingRuleSet
    fee_schedule: FeeSchedule


@dataclass(frozen=True, slots=True)
class _InstrumentMappingEvidence:
    instrument_id: InstrumentId
    as_of_date: date
    known_at: date


@dataclass(frozen=True, slots=True)
class _CompiledRules:
    code_to_ids: Mapping[str, tuple[InstrumentId, ...]]
    code_mappings: Mapping[str, tuple[_InstrumentMappingEvidence, ...]]
    definitions: tuple[InstrumentDefinition, ...]
    trading_rules: tuple[TradingRuleSet, ...]
    fee_schedules: tuple[FeeSchedule, ...]
    source_snapshot_ids: tuple[str, ...]


def _load_verified_frame(
    raw_evidence: object,
    raw_bytes: object,
) -> tuple[ContentAddressedResearchInput, pl.DataFrame, str, str]:
    if type(raw_evidence) is not ContentAddressedResearchInput:
        raise _error(
            "instrument rules require exact content-addressed evidence",
            "invalid_instrument_rules_evidence",
        )
    evidence = raw_evidence
    if evidence.artifact_kind != _ARTIFACT_KIND:
        raise _error(
            "instrument rules evidence has the wrong artifact kind",
            "instrument_rules_kind_mismatch",
            artifact_kind=evidence.artifact_kind,
        )
    if type(raw_bytes) is not bytes or not raw_bytes:
        raise _error(
            "instrument rules artifact must be non-empty exact bytes",
            "invalid_instrument_rules_artifact_bytes",
        )
    artifact_bytes = raw_bytes
    content_hash = hashlib.sha256(artifact_bytes).hexdigest()
    if content_hash != evidence.content_hash:
        raise _error(
            "instrument rules bytes differ from frozen input evidence",
            "instrument_rules_content_hash_mismatch",
            input_id=evidence.input_id,
        )
    try:
        frame = pl.read_parquet(BytesIO(artifact_bytes))
    except (OSError, ValueError, pl.exceptions.PolarsError):
        raise _error(
            "instrument rules artifact is not readable exact Parquet",
            "invalid_instrument_rules_parquet",
            input_id=evidence.input_id,
        ) from None
    schema_hash = _schema_hash(frame)
    if schema_hash != evidence.schema_hash:
        raise _error(
            "instrument rules schema differs from frozen input evidence",
            "instrument_rules_schema_hash_mismatch",
            input_id=evidence.input_id,
        )
    return evidence, frame, content_hash, schema_hash


def _validate_frame(frame: pl.DataFrame) -> None:
    if tuple(frame.schema.items()) != _SCHEMA_V1:
        raise _error(
            "instrument rules artifact does not match canonical schema v1",
            "invalid_instrument_rules_schema_v1",
            actual_schema=tuple(
                (name, str(dtype)) for name, dtype in frame.schema.items()
            ),
        )
    if frame.is_empty():
        raise _error(
            "instrument rules artifact contains no rows",
            "empty_instrument_rules_artifact",
        )
    null_columns = [
        name
        for name, _dtype in _SCHEMA_V1
        if name not in _NULLABLE_COLUMNS and frame[name].null_count() > 0
    ]
    if null_columns:
        raise _error(
            "instrument rules required columns contain null values",
            "null_instrument_rules_column",
            columns=null_columns,
        )
    non_finite_columns = [
        column
        for column in _FLOAT_COLUMNS
        if not frame[column].drop_nulls().is_finite().all()
    ]
    if non_finite_columns:
        raise _error(
            "instrument rules numeric columns contain non-finite values",
            "non_finite_instrument_rules_numeric",
            columns=non_finite_columns,
        )


def _validate_row_identity(row: _ParsedRuleRow) -> None:
    if not _valid_exact_text(row.instrument_code):
        raise _error(
            "instrument code is not an exact non-empty identity",
            "invalid_instrument_code",
            instrument_code=row.instrument_code,
        )
    if row.instrument_id <= 0:
        raise _error(
            "instrument id must be positive",
            "invalid_instrument_id",
            instrument_id=row.instrument_id,
        )
    if not _valid_exact_text(row.source_snapshot_id):
        raise _error(
            "instrument rule row source snapshot identity is invalid",
            "invalid_source_snapshot_id",
            source_snapshot_id=row.source_snapshot_id,
        )


def _validate_definition_values(row: _ParsedRuleRow) -> None:
    definition_text = {
        "asset_class": row.asset_class,
        "exchange": row.exchange,
        "currency": row.currency,
        "board_segment": row.board_segment,
        "lifecycle_state": row.lifecycle_state,
    }
    invalid_text = tuple(
        name for name, value in definition_text.items() if not _valid_exact_text(value)
    )
    if invalid_text:
        raise _error(
            "instrument definition text fields are invalid",
            "invalid_instrument_definition_text",
            fields=invalid_text,
        )
    if row.tick_size <= 0 or row.lot_size <= 0 or row.multiplier <= 0:
        raise _error(
            "instrument definition numeric fields must be positive",
            "invalid_instrument_definition_numeric",
            instrument_id=row.instrument_id,
        )
    if (
        row.ipo_date is not None
        and row.delisting_date is not None
        and row.ipo_date > row.delisting_date
    ):
        raise _error(
            "instrument lifecycle dates are inverted",
            "invalid_instrument_lifecycle",
            instrument_id=row.instrument_id,
        )
    if (row.ipo_date is not None and row.as_of_date < row.ipo_date) or (
        row.delisting_date is not None and row.as_of_date > row.delisting_date
    ):
        raise _error(
            "instrument rule falls outside the frozen instrument lifecycle",
            "rule_outside_instrument_lifecycle",
            instrument_id=row.instrument_id,
            as_of_date=row.as_of_date.isoformat(),
        )


def _validate_rule_values(
    row: _ParsedRuleRow,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if (
        row.settlement_cycle < 0
        or row.fund_settlement_cycle < 0
        or (row.price_limit_pct is not None and not 0 < row.price_limit_pct <= 1)
    ):
        raise _error(
            "instrument trading-rule numeric fields are invalid",
            "invalid_trading_rule_numeric",
            instrument_id=row.instrument_id,
            as_of_date=row.as_of_date.isoformat(),
        )
    if row.known_at > row.as_of_date:
        raise _error(
            "instrument rules were not known by their effective date",
            "future_instrument_rule_evidence",
            instrument_id=row.instrument_id,
            as_of_date=row.as_of_date.isoformat(),
            known_at=row.known_at.isoformat(),
        )
    order_types = _validate_collection(
        row.order_types_supported,
        field_name="order_types_supported",
        allow_empty=False,
    )
    call_sessions = _validate_collection(
        row.call_auction_sessions,
        field_name="call_auction_sessions",
        allow_empty=True,
    )
    return order_types, call_sessions


def _validate_fee_values(row: _ParsedRuleRow) -> None:
    if (
        not 0 <= row.commission_rate <= 1
        or row.min_commission < 0
        or not 0 <= row.stamp_duty_rate <= 1
        or not 0 <= row.transfer_fee_rate <= 1
    ):
        raise _error(
            "instrument fee schedule numeric fields are invalid",
            "invalid_fee_schedule_numeric",
            instrument_id=row.instrument_id,
            as_of_date=row.as_of_date.isoformat(),
        )


def _build_row_models(raw_row: tuple[object, ...]) -> _RuleRowModels:
    row = _ParsedRuleRow(*cast("_RawRuleRow", raw_row))
    _validate_row_identity(row)
    _validate_definition_values(row)
    order_types, call_sessions = _validate_rule_values(row)
    _validate_fee_values(row)
    instrument_id = InstrumentId(row.instrument_id)
    as_of_date = row.as_of_date.isoformat()
    return _RuleRowModels(
        instrument_code=row.instrument_code,
        source_snapshot_id=row.source_snapshot_id,
        mapping=_InstrumentMappingEvidence(
            instrument_id=instrument_id,
            as_of_date=row.as_of_date,
            known_at=row.known_at,
        ),
        definition=InstrumentDefinition(
            instrument_id=instrument_id,
            asset_class=row.asset_class,
            exchange=row.exchange,
            currency=row.currency,
            tick_size=row.tick_size,
            lot_size=row.lot_size,
            multiplier=row.multiplier,
            board_segment=row.board_segment,
            lifecycle_state=row.lifecycle_state,
            ipo_date=None if row.ipo_date is None else row.ipo_date.isoformat(),
            delisting_date=(
                None if row.delisting_date is None else row.delisting_date.isoformat()
            ),
        ),
        trading_rule=TradingRuleSet(
            instrument_id=instrument_id,
            as_of_date=as_of_date,
            settlement_cycle=row.settlement_cycle,
            fund_settlement_cycle=row.fund_settlement_cycle,
            price_limit_pct=row.price_limit_pct,
            order_types_supported=order_types,
            call_auction_sessions=call_sessions,
        ),
        fee_schedule=FeeSchedule(
            instrument_id=instrument_id,
            as_of_date=as_of_date,
            commission_rate=row.commission_rate,
            min_commission=row.min_commission,
            stamp_duty_rate=row.stamp_duty_rate,
            transfer_fee_rate=row.transfer_fee_rate,
        ),
    )


def _compile_rows(frame: pl.DataFrame) -> _CompiledRules:
    code_to_id: dict[str, InstrumentId] = {}
    code_mappings: dict[str, list[_InstrumentMappingEvidence]] = {}
    id_to_code: dict[InstrumentId, str] = {}
    definitions: dict[InstrumentId, InstrumentDefinition] = {}
    rule_versions: set[tuple[InstrumentId, str]] = set()
    trading_rules: list[TradingRuleSet] = []
    fee_schedules: list[FeeSchedule] = []
    sources: set[str] = set()
    for raw_row in frame.iter_rows():
        models = _build_row_models(raw_row)
        instrument_id = models.definition.instrument_id
        mapped_id = code_to_id.get(models.instrument_code)
        if mapped_id is not None and mapped_id != instrument_id:
            raise _error(
                "instrument code maps to more than one frozen instrument id",
                "ambiguous_instrument_code_mapping",
                instrument_code=models.instrument_code,
                instrument_ids=tuple(sorted((int(mapped_id), int(instrument_id)))),
            )
        mapped_code = id_to_code.get(instrument_id)
        if mapped_code is not None and mapped_code != models.instrument_code:
            raise _error(
                "instrument id maps to more than one frozen instrument code",
                "ambiguous_instrument_id_mapping",
                instrument_id=int(instrument_id),
                instrument_codes=tuple(sorted((mapped_code, models.instrument_code))),
            )
        version_key = (instrument_id, models.trading_rule.as_of_date)
        if version_key in rule_versions:
            raise _error(
                "instrument rules contain a duplicate PIT version",
                "duplicate_instrument_rule_version",
                instrument_id=int(instrument_id),
                as_of_date=models.trading_rule.as_of_date,
            )
        existing_definition = definitions.get(instrument_id)
        if existing_definition is not None and existing_definition != models.definition:
            raise _error(
                "instrument definition changes across PIT rule rows",
                "inconsistent_instrument_definition",
                instrument_id=int(instrument_id),
            )
        code_to_id[models.instrument_code] = instrument_id
        code_mappings.setdefault(models.instrument_code, []).append(models.mapping)
        id_to_code[instrument_id] = models.instrument_code
        rule_versions.add(version_key)
        definitions.setdefault(instrument_id, models.definition)
        trading_rules.append(models.trading_rule)
        fee_schedules.append(models.fee_schedule)
        sources.add(models.source_snapshot_id)
    return _CompiledRules(
        code_to_ids=MappingProxyType(
            {code: (instrument_id,) for code, instrument_id in code_to_id.items()}
        ),
        code_mappings=MappingProxyType(
            {
                code: tuple(
                    sorted(
                        mappings,
                        key=lambda item: (
                            item.as_of_date,
                            item.known_at,
                            int(item.instrument_id),
                        ),
                    )
                )
                for code, mappings in code_mappings.items()
            }
        ),
        definitions=tuple(
            sorted(definitions.values(), key=lambda item: int(item.instrument_id))
        ),
        trading_rules=tuple(
            sorted(
                trading_rules,
                key=lambda item: (int(item.instrument_id), item.as_of_date),
            )
        ),
        fee_schedules=tuple(
            sorted(
                fee_schedules,
                key=lambda item: (int(item.instrument_id), item.as_of_date),
            )
        ),
        source_snapshot_ids=tuple(sorted(sources)),
    )


@dataclass(frozen=True, slots=True)
class InstrumentRulesArtifactEvidence:
    """Immutable attestation for the exact parsed instrument-rules artifact."""

    input_evidence: ContentAddressedResearchInput
    verified_content_hash: str
    verified_schema_hash: str
    row_count: int
    source_snapshot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class VerifiedInstrumentRulesArtifact:
    """Verify exact Parquet bytes before building executable PIT rule objects."""

    input_evidence: ContentAddressedResearchInput
    artifact_bytes: bytes = field(repr=False)
    evidence: InstrumentRulesArtifactEvidence = field(init=False)
    _frame: pl.DataFrame = field(init=False, repr=False, compare=False)
    _code_to_ids: Mapping[str, tuple[InstrumentId, ...]] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _code_mappings: Mapping[str, tuple[_InstrumentMappingEvidence, ...]] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _definitions: tuple[InstrumentDefinition, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _trading_rules: tuple[TradingRuleSet, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _fee_schedules: tuple[FeeSchedule, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        """Recompute every identity from exact bytes inside the boundary."""
        evidence, frame, content_hash, schema_hash = _load_verified_frame(
            self.input_evidence,
            self.artifact_bytes,
        )
        _validate_frame(frame)
        compiled = _compile_rows(frame)
        object.__setattr__(self, "_frame", frame.clone())
        object.__setattr__(self, "_code_to_ids", compiled.code_to_ids)
        object.__setattr__(self, "_code_mappings", compiled.code_mappings)
        object.__setattr__(self, "_definitions", compiled.definitions)
        object.__setattr__(self, "_trading_rules", compiled.trading_rules)
        object.__setattr__(self, "_fee_schedules", compiled.fee_schedules)
        object.__setattr__(
            self,
            "evidence",
            InstrumentRulesArtifactEvidence(
                input_evidence=evidence,
                verified_content_hash=content_hash,
                verified_schema_hash=schema_hash,
                row_count=frame.height,
                source_snapshot_ids=compiled.source_snapshot_ids,
            ),
        )

    @property
    def frame(self) -> pl.DataFrame:
        """Return a clone so callers cannot mutate the verified internal frame."""
        return self._frame.clone()

    @property
    def source_snapshot_ids(self) -> tuple[str, ...]:
        """Return exact unique row-level source snapshot identities."""
        return self.evidence.source_snapshot_ids

    def resolve_instrument_id(self, instrument_code: str) -> InstrumentId:
        """Resolve one exact code without metadata or provider fallback."""
        matches = self._code_to_ids.get(instrument_code, ())
        if not matches:
            raise _error(
                "instrument code is absent from frozen rules evidence",
                "instrument_code_not_found",
                instrument_code=instrument_code,
            )
        if len(matches) != 1:
            raise _error(
                "instrument code is ambiguous in frozen rules evidence",
                "ambiguous_instrument_code",
                instrument_code=instrument_code,
                instrument_ids=tuple(int(item) for item in matches),
            )
        return matches[0]

    def resolve_instrument_id_at(
        self,
        instrument_code: str,
        *,
        knowledge_date: date,
    ) -> InstrumentId:
        """Resolve a mapping only when exact known/effective evidence is available."""
        if type(knowledge_date) is not date:
            raise _error(
                "mapping knowledge_date must be an exact date",
                "invalid_mapping_knowledge_date",
            )
        if type(instrument_code) is not str or not _valid_exact_text(instrument_code):
            raise _error(
                "instrument code lookup identity is invalid",
                "invalid_instrument_code_lookup",
            )
        mappings = self._code_mappings.get(instrument_code, ())
        if not mappings:
            raise _error(
                "instrument code is absent from frozen rules evidence",
                "instrument_code_not_found",
                instrument_code=instrument_code,
            )
        eligible = tuple(
            item
            for item in mappings
            if item.known_at <= knowledge_date and item.as_of_date <= knowledge_date
        )
        if not eligible:
            raise _error(
                "instrument code mapping was unavailable at knowledge_date",
                "instrument_code_not_known_at_knowledge_date",
                instrument_code=instrument_code,
                knowledge_date=knowledge_date.isoformat(),
            )
        instrument_ids = tuple(
            sorted({item.instrument_id for item in eligible}, key=int)
        )
        if len(instrument_ids) != 1:
            raise _error(
                "instrument code is ambiguous at knowledge_date",
                "ambiguous_instrument_code",
                instrument_code=instrument_code,
                knowledge_date=knowledge_date.isoformat(),
                instrument_ids=tuple(int(item) for item in instrument_ids),
            )
        return instrument_ids[0]

    def build_rule_provider(self) -> InMemoryRuleProvider:
        """Build an isolated provider solely from already verified rows."""
        trading_rules: dict[InstrumentId, list[TradingRuleSet]] = {}
        fee_schedules: dict[InstrumentId, list[FeeSchedule]] = {}
        for item in self._trading_rules:
            trading_rules.setdefault(item.instrument_id, []).append(item)
        for item in self._fee_schedules:
            fee_schedules.setdefault(item.instrument_id, []).append(item)
        return InMemoryRuleProvider(
            definitions={item.instrument_id: item for item in self._definitions},
            trading_rules=trading_rules,
            fee_schedules=fee_schedules,
        )
