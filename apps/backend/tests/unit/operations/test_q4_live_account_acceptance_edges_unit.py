# pyright: reportPrivateUsage=false
"""Fail-closed boundary tests for Q4/PAP-09 acceptance evidence."""

from __future__ import annotations

import math
from copy import deepcopy
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import orjson
import polars as pl
import pytest
from ditto_apps.operations import q4_live_account_acceptance as subject

_GENERATED_AT = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)
_APPROVED_AT = datetime(2026, 9, 2, 8, 30, tzinfo=UTC)
_APPROVAL_HASH = "a" * 64


def _bar(trade_date: str = "2026-09-01") -> dict[str, object]:
    return {
        "source_ticker": subject.INSTRUMENT_CODE,
        "trade_date": trade_date,
        "open": 9.1,
        "high": 9.2,
        "low": 9.0,
        "close": 9.15,
        "pre_close": 9.12,
        "volume": 1_000.0,
        "amount": 9_150.0,
    }


def _forecast() -> tuple[str, ...]:
    return tuple(f"2026-10-{day:02d}" for day in range(1, 21))


def _proposal(tmp_path: Path) -> dict[str, object]:
    return subject.build_acceptance_proposal(
        data_root=tmp_path / "state",
        evidence_root=tmp_path / "public",
        generated_at=_GENERATED_AT,
        latest_published_bar=_bar(),
        forecast_open_dates=_forecast(),
    )


def _record(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast("dict[str, object]", value)


def _arguments(proposal: dict[str, object]) -> dict[str, object]:
    request = _record(proposal["exact_acceptance_request"])
    return _record(request["arguments"])


def _rehash(proposal: dict[str, object]) -> str:
    request = _record(proposal["exact_acceptance_request"])
    digest = subject.canonical_hash(_record(request["arguments"]))
    request["approval_hash"] = digest
    return digest


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_positive_number_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        subject.positive_number(value, field="price")


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: subject._mapping([], field="item"), "object"),
        (lambda: subject._mapping({1: "x"}, field="item"), "string keys"),
        (lambda: subject._integer(True, field="count"), "integer"),
        (lambda: subject._hash("A" * 64, field="digest"), "lowercase sha256"),
        (lambda: subject.parse_timestamp("not-a-date", field="when"), "RFC3339"),
        (
            lambda: subject.parse_timestamp("2026-09-02T08:00:00", field="when"),
            "timezone-aware",
        ),
        (lambda: subject.rfc3339(datetime(2026, 9, 2)), "timezone-aware"),
        (lambda: subject.parse_iso_date("2026-02-30", field="day"), "ISO date"),
        (lambda: subject.positive_number(True, field="price"), "numeric"),
        (lambda: subject.positive_number(0, field="price"), "positive finite"),
        (lambda: subject._decimal_text("not-decimal", field="cash"), "decimal"),
        (lambda: subject._decimal_text("NaN", field="cash"), "positive finite"),
    ],
)
def test_scalar_validators_fail_closed(
    call: object,
    message: str,
) -> None:
    operation = cast("object", call)
    assert callable(operation)
    with pytest.raises(ValueError, match=message):
        operation()


def test_parse_iso_date_accepts_date_objects() -> None:
    assert subject.parse_iso_date(date(2026, 9, 2), field="day") == "2026-09-02"


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"source_ticker": "000001.SH"}, "instrument drifted"),
        ({"high": 9.14}, "high is inconsistent"),
        ({"low": 9.16}, "low is inconsistent"),
    ],
)
def test_canonical_bar_rejects_provider_drift(
    update: dict[str, object],
    message: str,
) -> None:
    raw = {**_bar(), **update}
    with pytest.raises(ValueError, match=message):
        subject.canonical_bar(raw)


def test_calendar_dates_requires_schema_and_canonicalizes_open_days() -> None:
    with pytest.raises(ValueError, match="schema is incomplete"):
        subject.calendar_dates(pl.DataFrame({"trade_date": [date(2026, 9, 2)]}))

    assert subject.calendar_dates(
        pl.DataFrame(
            {
                "trade_date": [date(2026, 9, 3), date(2026, 9, 2)],
                "is_open": [True, False],
            }
        )
    ) == ("2026-09-03",)


def test_proposal_requires_independent_roots(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="independent trees"):
        subject.build_acceptance_proposal(
            data_root=tmp_path,
            evidence_root=tmp_path / "evidence",
            generated_at=_GENERATED_AT,
            latest_published_bar=_bar(),
            forecast_open_dates=_forecast(),
        )


def test_proposal_rejects_current_bar_and_short_forecast(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must predate"):
        subject.build_acceptance_proposal(
            data_root=tmp_path / "state",
            evidence_root=tmp_path / "public",
            generated_at=_GENERATED_AT,
            latest_published_bar=_bar("2026-09-02"),
            forecast_open_dates=_forecast(),
        )
    with pytest.raises(ValueError, match="at least twenty"):
        subject.build_acceptance_proposal(
            data_root=tmp_path / "state",
            evidence_root=tmp_path / "public",
            generated_at=_GENERATED_AT,
            latest_published_bar=_bar(),
            forecast_open_dates=_forecast()[:19],
        )


def test_approved_request_rejects_schema_and_exact_approval_drift(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    proposal["schema"] = "wrong"
    with pytest.raises(ValueError, match="schema is invalid"):
        subject.approved_acceptance_request(
            proposal,
            approved_request_hash=_rehash(proposal),
        )

    proposal = _proposal(tmp_path)
    request = _record(proposal["exact_acceptance_request"])
    request["requires_exact_approval"] = False
    with pytest.raises(ValueError, match="exact approval requirement"):
        subject.approved_acceptance_request(
            proposal,
            approved_request_hash=_rehash(proposal),
        )


def test_approved_request_rejects_safety_and_scope_drift(tmp_path: Path) -> None:
    proposal = _proposal(tmp_path)
    prohibitions = _record(_arguments(proposal)["prohibitions"])
    prohibitions["real_order"] = False
    with pytest.raises(ValueError, match="safety prohibitions"):
        subject.approved_acceptance_request(
            proposal,
            approved_request_hash=_rehash(proposal),
        )

    proposal = _proposal(tmp_path)
    manual = _record(_arguments(proposal)["manual"])
    manual["scope"] = "real-account"
    with pytest.raises(ValueError, match="scope drifted"):
        subject.approved_acceptance_request(
            proposal,
            approved_request_hash=_rehash(proposal),
        )


def test_trade_date_selection_rejects_time_travel_and_stops_at_target() -> None:
    with pytest.raises(ValueError, match="cannot precede approval"):
        subject.select_next_eligible_trade_date(
            open_dates=("2026-09-03",),
            completed_dates=(),
            approval_at=_APPROVED_AT,
            now=datetime(2026, 9, 2, 8, 29, tzinfo=UTC),
            target_days=1,
        )

    assert (
        subject.select_next_eligible_trade_date(
            open_dates=("2026-09-03",),
            completed_dates=("2026-09-03",),
            approval_at=_APPROVED_AT,
            now=datetime(2026, 9, 4, tzinfo=UTC),
            target_days=1,
        )
        is None
    )


def test_reconcile_completed_dates_rejects_database_drift() -> None:
    progress: dict[str, object] = {"trade_dates": ["2026-09-03"]}
    with pytest.raises(ValueError, match="prefix drifted"):
        subject.reconcile_completed_dates(
            progress,
            database_completed=("2026-09-04",),
        )
    with pytest.raises(ValueError, match="more than one"):
        subject.reconcile_completed_dates(
            progress,
            database_completed=("2026-09-03", "2026-09-04", "2026-09-07"),
        )


@pytest.mark.parametrize("trade_dates", [None, ["2026-09-03", 4]])
def test_reconcile_completed_dates_rejects_invalid_progress(
    trade_dates: object,
) -> None:
    with pytest.raises(ValueError, match="trade dates are invalid"):
        subject.reconcile_completed_dates(
            {"trade_dates": trade_dates},
            database_completed=(),
        )


def test_json_and_signing_key_io_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="is missing"):
        subject.load_json(tmp_path / "missing.json", field="receipt")

    list_path = tmp_path / "list.json"
    list_path.write_bytes(orjson.dumps([1, 2]))
    with pytest.raises(ValueError, match="must be an object"):
        subject.load_json(list_path, field="receipt")

    key_path = tmp_path / "key"
    with pytest.raises(ValueError, match="key is missing"):
        subject.load_signing_key(key_path, create=False)
    key_path.write_bytes(b"short")
    with pytest.raises(ValueError, match="key is invalid"):
        subject.load_signing_key(key_path, create=False)


def test_signature_verification_rejects_metadata_and_value_drift() -> None:
    key = b"k" * 32
    signed = subject.sign_payload(
        {"schema": "evidence.v1", "value": 1},
        key=key,
        approval_hash=_APPROVAL_HASH,
        previous_signature=None,
    )

    metadata_drift = deepcopy(signed)
    _record(metadata_drift["signature"])["algorithm"] = "none"
    with pytest.raises(ValueError, match="metadata is invalid"):
        subject.verify_signed_payload(
            metadata_drift,
            key=key,
            approval_hash=_APPROVAL_HASH,
            previous_signature=None,
        )

    signature_drift = deepcopy(signed)
    _record(signature_drift["signature"])["value"] = "b" * 64
    with pytest.raises(ValueError, match="signature is invalid"):
        subject.verify_signed_payload(
            signature_drift,
            key=key,
            approval_hash=_APPROVAL_HASH,
            previous_signature=None,
        )


def _write_signed_chain(
    tmp_path: Path,
    *,
    trade_dates: tuple[str, ...] = (),
) -> tuple[Path, Path]:
    data_root = tmp_path / "state"
    public_root = tmp_path / "public"
    key = subject.load_signing_key(
        data_root / "state" / "evidence-signing.key",
        create=True,
    )
    bootstrap = subject.sign_payload(
        {"schema": subject.BOOTSTRAP_SCHEMA},
        key=key,
        approval_hash=_APPROVAL_HASH,
        previous_signature=None,
    )
    subject.atomic_write_json(data_root / "evidence" / "bootstrap.json", bootstrap)
    subject.atomic_write_json(public_root / "bootstrap.json", bootstrap)
    signature = cast("str", _record(bootstrap["signature"])["value"])
    for trade_date in trade_dates:
        payload = subject.sign_payload(
            {"schema": subject.DAY_SCHEMA, "trade_date": trade_date},
            key=key,
            approval_hash=_APPROVAL_HASH,
            previous_signature=signature,
        )
        subject.atomic_write_json(
            data_root / "evidence" / "days" / f"{trade_date}.json",
            payload,
        )
        subject.atomic_write_json(
            public_root / "days" / f"{trade_date}.json",
            payload,
        )
        signature = cast("str", _record(payload["signature"])["value"])
    return data_root, public_root


def test_soak_progress_rejects_missing_and_drifted_public_bootstrap(
    tmp_path: Path,
) -> None:
    data_root, public_root = _write_signed_chain(tmp_path)
    (public_root / "bootstrap.json").unlink()
    with pytest.raises(ValueError, match="public bootstrap evidence is missing"):
        subject.verify_soak_progress(
            data_root=data_root,
            evidence_root=public_root,
            expected_approval_hash=_APPROVAL_HASH,
        )

    subject.atomic_write_json(public_root / "bootstrap.json", {"drift": True})
    with pytest.raises(ValueError, match="bootstrap evidence drifted"):
        subject.verify_soak_progress(
            data_root=data_root,
            evidence_root=public_root,
            expected_approval_hash=_APPROVAL_HASH,
        )


def test_soak_progress_rejects_day_filename_and_public_drift(tmp_path: Path) -> None:
    data_root, public_root = _write_signed_chain(
        tmp_path,
        trade_dates=("2026-09-03",),
    )
    durable_day = data_root / "evidence" / "days" / "2026-09-03.json"
    durable_day.rename(durable_day.with_name("2026-09-04.json"))
    with pytest.raises(ValueError, match="filename does not match"):
        subject.verify_soak_progress(
            data_root=data_root,
            evidence_root=public_root,
            expected_approval_hash=_APPROVAL_HASH,
        )

    data_root, public_root = _write_signed_chain(
        tmp_path / "second",
        trade_dates=("2026-09-03",),
    )
    public_day = public_root / "days" / "2026-09-03.json"
    public_day.write_bytes(b"{}")
    with pytest.raises(ValueError, match="day evidence drifted"):
        subject.verify_soak_progress(
            data_root=data_root,
            evidence_root=public_root,
            expected_approval_hash=_APPROVAL_HASH,
        )
