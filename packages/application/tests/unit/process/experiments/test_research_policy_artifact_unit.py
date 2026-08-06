"""Exact instrument-rules research artifact trust-boundary tests."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date
from io import BytesIO

import orjson
import polars as pl
import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments.execution_bundle import (
    ContentAddressedResearchInput,
)
from ditto_application.processes.experiments.research_policy_artifact import (
    VerifiedInstrumentRulesArtifact,
)
from ditto_kernel.identity import InstrumentId

_SCHEMA_V1: dict[str, pl.DataType] = {
    "instrument_code": pl.String,
    "instrument_id": pl.Int64,
    "asset_class": pl.String,
    "exchange": pl.String,
    "currency": pl.String,
    "tick_size": pl.Float64,
    "lot_size": pl.Int64,
    "multiplier": pl.Float64,
    "board_segment": pl.String,
    "lifecycle_state": pl.String,
    "ipo_date": pl.Date,
    "delisting_date": pl.Date,
    "as_of_date": pl.Date,
    "known_at": pl.Date,
    "settlement_cycle": pl.Int64,
    "fund_settlement_cycle": pl.Int64,
    "price_limit_pct": pl.Float64,
    "order_types_supported": pl.List(pl.String),
    "call_auction_sessions": pl.List(pl.String),
    "commission_rate": pl.Float64,
    "min_commission": pl.Float64,
    "stamp_duty_rate": pl.Float64,
    "transfer_fee_rate": pl.Float64,
    "source_snapshot_id": pl.String,
}


def _frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_code": ["510300.SH", "510300.SH"],
            "instrument_id": [2_000_001, 2_000_001],
            "asset_class": ["etf", "etf"],
            "exchange": ["XSHG", "XSHG"],
            "currency": ["CNY", "CNY"],
            "tick_size": [0.001, 0.001],
            "lot_size": [100, 100],
            "multiplier": [1.0, 1.0],
            "board_segment": ["fund", "fund"],
            "lifecycle_state": ["normal", "normal"],
            "ipo_date": [date(2012, 5, 28), date(2012, 5, 28)],
            "delisting_date": [None, None],
            "as_of_date": [date(2026, 1, 1), date(2026, 2, 1)],
            "known_at": [date(2025, 12, 31), date(2025, 12, 31)],
            "settlement_cycle": [1, 1],
            "fund_settlement_cycle": [0, 0],
            "price_limit_pct": [0.1, 0.2],
            "order_types_supported": [
                ["market", "limit"],
                ["market", "limit"],
            ],
            "call_auction_sessions": [["open", "close"], ["open", "close"]],
            "commission_rate": [0.0003, 0.0003],
            "min_commission": [5.0, 5.0],
            "stamp_duty_rate": [0.0, 0.0],
            "transfer_fee_rate": [0.00001, 0.00001],
            "source_snapshot_id": ["rules:snapshot:b", "rules:snapshot:a"],
        },
        schema=_SCHEMA_V1,
    )


def _parquet_bytes(frame: pl.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.write_parquet(buffer)
    return buffer.getvalue()


def _schema_hash(frame: pl.DataFrame) -> str:
    fields = tuple((name, str(dtype)) for name, dtype in frame.schema.items())
    return hashlib.sha256(orjson.dumps(fields)).hexdigest()


def _artifact(frame: pl.DataFrame | None = None) -> VerifiedInstrumentRulesArtifact:
    exact_frame = frame if frame is not None else _frame()
    artifact_bytes = _parquet_bytes(exact_frame)
    return VerifiedInstrumentRulesArtifact(
        input_evidence=ContentAddressedResearchInput(
            input_id="instrument_rules.parquet",
            artifact_kind="instrument_rules",
            content_hash=hashlib.sha256(artifact_bytes).hexdigest(),
            schema_hash=_schema_hash(exact_frame),
        ),
        artifact_bytes=artifact_bytes,
    )


def _replace_row_value(
    frame: pl.DataFrame,
    *,
    row_index: int,
    column: str,
    value: object,
) -> pl.DataFrame:
    return frame.with_columns(
        pl.when(pl.int_range(pl.len()) == row_index)
        .then(pl.lit(value))
        .otherwise(pl.col(column))
        .cast(_SCHEMA_V1[column])
        .alias(column),
    )


def test_verified_artifact_builds_only_exact_pit_rules_and_immutable_evidence() -> None:
    artifact = _artifact()

    assert artifact.resolve_instrument_id("510300.SH") == InstrumentId(2_000_001)
    assert artifact.source_snapshot_ids == (
        "rules:snapshot:a",
        "rules:snapshot:b",
    )
    assert artifact.evidence.input_evidence.input_id == "instrument_rules.parquet"
    assert artifact.evidence.row_count == 2
    assert (
        artifact.evidence.verified_content_hash
        == hashlib.sha256(
            artifact.artifact_bytes,
        ).hexdigest()
    )
    assert artifact.evidence.verified_schema_hash == _schema_hash(_frame())

    exposed = artifact.frame
    exposed.replace_column(
        exposed.get_column_index("tick_size"),
        pl.Series("tick_size", [999.0, 999.0], dtype=pl.Float64),
    )
    assert artifact.frame["tick_size"].to_list() == [0.001, 0.001]

    provider = artifact.build_rule_provider()
    definition = provider.get_definition(InstrumentId(2_000_001))
    assert definition is not None
    assert definition.asset_class == "etf"
    assert definition.exchange == "XSHG"
    assert definition.ipo_date == "2012-05-28"

    january_rule = provider.get_trading_rule(InstrumentId(2_000_001), "2026-01-15")
    assert january_rule is not None
    assert january_rule.as_of_date == "2026-01-01"
    assert january_rule.price_limit_pct == 0.1

    february_fee = provider.get_fee_schedule(InstrumentId(2_000_001), "2026-02-15")
    assert february_fee is not None
    assert february_fee.as_of_date == "2026-02-01"
    assert february_fee.min_commission == 5.0


def test_mapping_resolution_is_fenced_by_exact_known_and_effective_dates() -> None:
    boundary = date(2026, 1, 15)
    boundary_frame = (
        _frame()
        .slice(0, 1)
        .with_columns(
            pl.lit(boundary).cast(pl.Date).alias("as_of_date"),
            pl.lit(boundary).cast(pl.Date).alias("known_at"),
        )
    )
    artifact = _artifact(boundary_frame)

    assert artifact.resolve_instrument_id_at(
        "510300.SH",
        knowledge_date=boundary,
    ) == InstrumentId(2_000_001)

    for future_field in ("known_at", "as_of_date"):
        poisoned = boundary_frame.with_columns(
            pl.lit(date(2026, 1, 16)).cast(pl.Date).alias(future_field),
        )
        if future_field == "known_at":
            poisoned = poisoned.with_columns(
                pl.lit(date(2026, 1, 16)).cast(pl.Date).alias("as_of_date"),
            )
        future = _artifact(poisoned)

        with pytest.raises(AppProcessError) as exc_info:
            future.resolve_instrument_id_at(
                "510300.SH",
                knowledge_date=boundary,
            )

        assert exc_info.value.details["reason"] == (
            "instrument_code_not_known_at_knowledge_date"
        )


def test_mapping_resolution_requires_an_exact_knowledge_date() -> None:
    artifact = _artifact()

    with pytest.raises(AppProcessError) as exc_info:
        artifact.resolve_instrument_id_at(
            "510300.SH",
            knowledge_date="2026-01-15",  # type: ignore[arg-type]
        )

    assert exc_info.value.details["reason"] == "invalid_mapping_knowledge_date"


def test_verified_artifact_preserves_canonical_nullable_fields() -> None:
    frame = _frame().with_columns(
        pl.lit(None, dtype=pl.Date).alias("ipo_date"),
        pl.when(pl.int_range(pl.len()) == 0)
        .then(pl.lit(None))
        .otherwise(pl.col("price_limit_pct"))
        .cast(pl.Float64)
        .alias("price_limit_pct"),
    )

    artifact = _artifact(frame)
    provider = artifact.build_rule_provider()

    definition = provider.get_definition(InstrumentId(2_000_001))
    rule = provider.get_trading_rule(InstrumentId(2_000_001), "2026-01-15")
    assert definition is not None
    assert definition.ipo_date is None
    assert rule is not None
    assert rule.price_limit_pct is None


def test_verified_artifact_rejects_an_empty_canonical_frame() -> None:
    with pytest.raises(AppProcessError) as exc_info:
        _artifact(_frame().head(0))

    assert exc_info.value.details["reason"] == "empty_instrument_rules_artifact"


@pytest.mark.parametrize(
    ("column", "value", "reason"),
    [
        ("instrument_code", None, "null_instrument_rules_column"),
        ("tick_size", float("nan"), "non_finite_instrument_rules_numeric"),
        ("commission_rate", float("inf"), "non_finite_instrument_rules_numeric"),
    ],
)
def test_verified_artifact_rejects_required_null_and_non_finite_values(
    column: str,
    value: object,
    reason: str,
) -> None:
    poisoned = _frame().with_columns(
        pl.when(pl.int_range(pl.len()) == 0)
        .then(pl.lit(value))
        .otherwise(pl.col(column))
        .cast(_SCHEMA_V1[column])
        .alias(column),
    )

    with pytest.raises(AppProcessError) as exc_info:
        _artifact(poisoned)

    assert exc_info.value.details == {
        "code": "REPRODUCIBILITY_FAILED",
        "reason": reason,
        "columns": [column],
    }


@pytest.mark.parametrize(
    ("column", "value", "reason"),
    [
        ("instrument_id", 2_000_002, "ambiguous_instrument_code_mapping"),
        ("instrument_code", "510301.SH", "ambiguous_instrument_id_mapping"),
        ("as_of_date", date(2026, 1, 1), "duplicate_instrument_rule_version"),
        ("lot_size", 200, "inconsistent_instrument_definition"),
        ("known_at", date(2026, 2, 2), "future_instrument_rule_evidence"),
    ],
)
def test_verified_artifact_rejects_conflicting_identity_and_pit_rows(
    column: str,
    value: object,
    reason: str,
) -> None:
    poisoned = _replace_row_value(
        _frame(),
        row_index=1,
        column=column,
        value=value,
    )

    with pytest.raises(AppProcessError) as exc_info:
        _artifact(poisoned)

    assert exc_info.value.details["code"] == "REPRODUCIBILITY_FAILED"
    assert exc_info.value.details["reason"] == reason


@pytest.mark.parametrize(
    ("column", "value", "reason"),
    [
        ("instrument_code", " ", "invalid_instrument_code"),
        ("instrument_id", 0, "invalid_instrument_id"),
        ("asset_class", " ", "invalid_instrument_definition_text"),
        ("source_snapshot_id", " ", "invalid_source_snapshot_id"),
        ("tick_size", 0.0, "invalid_instrument_definition_numeric"),
        ("lot_size", 0, "invalid_instrument_definition_numeric"),
        ("multiplier", -1.0, "invalid_instrument_definition_numeric"),
        ("settlement_cycle", -1, "invalid_trading_rule_numeric"),
        ("price_limit_pct", 1.1, "invalid_trading_rule_numeric"),
        ("commission_rate", -0.1, "invalid_fee_schedule_numeric"),
        ("stamp_duty_rate", 1.1, "invalid_fee_schedule_numeric"),
        ("min_commission", -1.0, "invalid_fee_schedule_numeric"),
        ("ipo_date", date(2027, 1, 1), "rule_outside_instrument_lifecycle"),
        ("delisting_date", date(2010, 12, 31), "invalid_instrument_lifecycle"),
    ],
)
def test_verified_artifact_rejects_invalid_domain_values(
    column: str,
    value: object,
    reason: str,
) -> None:
    poisoned = _replace_row_value(
        _frame(),
        row_index=0,
        column=column,
        value=value,
    )

    with pytest.raises(AppProcessError) as exc_info:
        _artifact(poisoned)

    assert exc_info.value.details["code"] == "REPRODUCIBILITY_FAILED"
    assert exc_info.value.details["reason"] == reason


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("order_types_supported", []),
        ("order_types_supported", ["market", "market"]),
        ("order_types_supported", ["market", " "]),
        ("call_auction_sessions", ["open", "open"]),
        ("call_auction_sessions", [" "]),
    ],
)
def test_verified_artifact_rejects_invalid_rule_collections(
    column: str,
    value: list[str],
) -> None:
    poisoned = _replace_row_value(
        _frame(),
        row_index=0,
        column=column,
        value=value,
    )

    with pytest.raises(AppProcessError) as exc_info:
        _artifact(poisoned)

    assert exc_info.value.details["code"] == "REPRODUCIBILITY_FAILED"
    assert exc_info.value.details["reason"] == "invalid_trading_rule_collection"


@pytest.mark.parametrize(
    ("evidence_change", "artifact_bytes", "reason"),
    [
        (
            {"content_hash": "0" * 64},
            None,
            "instrument_rules_content_hash_mismatch",
        ),
        (
            {"schema_hash": "0" * 64},
            None,
            "instrument_rules_schema_hash_mismatch",
        ),
        (
            {"artifact_kind": "bars"},
            None,
            "instrument_rules_kind_mismatch",
        ),
        ({}, b"", "invalid_instrument_rules_artifact_bytes"),
    ],
)
def test_verified_artifact_rejects_poisoned_attestation(
    evidence_change: dict[str, str],
    artifact_bytes: bytes | None,
    reason: str,
) -> None:
    valid = _artifact()
    evidence = replace(valid.input_evidence, **evidence_change)

    with pytest.raises(AppProcessError) as exc_info:
        VerifiedInstrumentRulesArtifact(
            input_evidence=evidence,
            artifact_bytes=(
                valid.artifact_bytes if artifact_bytes is None else artifact_bytes
            ),
        )

    assert exc_info.value.details["code"] == "REPRODUCIBILITY_FAILED"
    assert exc_info.value.details["reason"] == reason


def test_verified_artifact_rejects_non_parquet_exact_bytes() -> None:
    artifact_bytes = b"not-parquet"
    evidence = ContentAddressedResearchInput(
        input_id="instrument_rules.parquet",
        artifact_kind="instrument_rules",
        content_hash=hashlib.sha256(artifact_bytes).hexdigest(),
        schema_hash="0" * 64,
    )

    with pytest.raises(AppProcessError) as exc_info:
        VerifiedInstrumentRulesArtifact(
            input_evidence=evidence,
            artifact_bytes=artifact_bytes,
        )

    assert exc_info.value.details["reason"] == "invalid_instrument_rules_parquet"


@pytest.mark.parametrize(
    "poisoned",
    [
        _frame().select(reversed(_frame().columns)),
        _frame().with_columns(pl.lit("extra").alias("unexpected")),
        _frame().with_columns(pl.col("instrument_id").cast(pl.Int32)),
    ],
)
def test_verified_artifact_requires_exact_ordered_schema_v1(
    poisoned: pl.DataFrame,
) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        _artifact(poisoned)

    assert exc_info.value.details["reason"] == "invalid_instrument_rules_schema_v1"


def test_resolution_and_provider_never_fall_back_for_missing_identity() -> None:
    artifact = _artifact()

    with pytest.raises(AppProcessError) as exc_info:
        artifact.resolve_instrument_id("000001.SZ")

    assert exc_info.value.details == {
        "code": "REPRODUCIBILITY_FAILED",
        "reason": "instrument_code_not_found",
        "instrument_code": "000001.SZ",
    }
    provider = artifact.build_rule_provider()
    assert provider.get_definition(InstrumentId(999_999)) is None
    assert provider.get_trading_rule(InstrumentId(2_000_001), "2025-12-31") is None
    assert provider.get_fee_schedule(InstrumentId(999_999), "2026-02-15") is None
