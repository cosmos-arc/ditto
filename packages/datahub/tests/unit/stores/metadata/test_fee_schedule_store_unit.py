"""Tests for FeeScheduleReader / FeeScheduleWriter (PIT versioned)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest
from ditto_datahub.stores.metadata.fee_schedule_reader import (
    FeeScheduleReader,
    FeeScheduleRecord,
)
from ditto_datahub.stores.metadata.fee_schedule_writer import FeeScheduleWriter

_DEFAULTS: dict[str, object] = {
    "instrument_id": 1,
    "as_of_date": "2026-01-01",
    "commission_rate": 0.0003,
    "min_commission": 5.0,
    "stamp_duty_rate": 0.0,
    "transfer_fee_rate": 0.0,
    "effective_from": "2026-01-01",
    "effective_to": None,
}


def _make(**overrides: object) -> FeeScheduleRecord:
    return FeeScheduleRecord(**{**_DEFAULTS, **overrides})


def _check_effective_from_boundary(
    reader: FeeScheduleReader,
    *,
    effective_from: str = "2026-02-01",
    match_date: str = "2026-02-01",
    miss_date: str = "2026-01-31",
    instrument_id: int = 1,
) -> None:
    """effective_from <= as_of_date: as_of_date == effective_from 应匹配."""
    reader.load([_make(effective_from=effective_from)])
    assert reader.get(instrument_id, match_date) is not None
    assert reader.get(instrument_id, miss_date) is None


def _check_effective_to_boundary(
    reader: FeeScheduleReader,
    *,
    effective_to: str = "2026-02-15",
    match_date: str = "2026-02-14",
    miss_date: str = "2026-02-15",
    instrument_id: int = 1,
) -> None:
    """effective_to > as_of_date: boundary 是 exclusive, == 应不匹配."""
    reader.load([_make(effective_to=effective_to)])
    assert reader.get(instrument_id, match_date) is not None
    assert reader.get(instrument_id, miss_date) is None


def _check_latest_version(
    reader: FeeScheduleReader,
    *,
    old_attrs: dict[str, Any],
    new_attrs: dict[str, Any],
    check_field: str,
    old_value: Any,
    new_value: Any,
    old_date: str,
    new_date: str,
    instrument_id: int = 1,
) -> None:
    """多个版本匹配时, 选择 effective_from 最大的版本."""
    reader.load([_make(**old_attrs), _make(**new_attrs)])
    result_old = reader.get(instrument_id, old_date)
    assert result_old is not None
    assert getattr(result_old, check_field) == old_value
    result_new = reader.get(instrument_id, new_date)
    assert result_new is not None
    assert getattr(result_new, check_field) == new_value


def _check_null_effective_to(
    reader: FeeScheduleReader,
    *,
    far_future_date: str = "2099-12-31",
    instrument_id: int = 1,
) -> None:
    """effective_to IS NULL 表示版本仍然有效."""
    reader.load([_make()])
    assert reader.get(instrument_id, far_future_date) is not None


class TestFeeScheduleRecord:
    def test_create_record(self) -> None:
        record = _make()
        assert record.stamp_duty_rate == 0.0

    def test_record_is_frozen(self) -> None:
        record = _make()
        with pytest.raises(FrozenInstanceError):
            record.commission_rate = 0.0  # type: ignore[misc]

    def test_record_fields_accessible(self) -> None:
        record = _make(
            instrument_id=3,
            stamp_duty_rate=0.0005,
            transfer_fee_rate=0.00001,
        )
        assert record.instrument_id == 3
        assert record.stamp_duty_rate == 0.0005
        assert record.min_commission == 5.0


class TestFeeScheduleReaderPIT:
    def test_get_current_version(self) -> None:
        _check_latest_version(
            FeeScheduleReader(),
            old_attrs={
                "stamp_duty_rate": 0.0005,
                "transfer_fee_rate": 0.00001,
                "effective_from": "2023-01-01",
                "effective_to": "2023-08-27",
            },
            new_attrs={
                "stamp_duty_rate": 0.00025,
                "transfer_fee_rate": 0.00001,
                "effective_from": "2023-08-28",
            },
            check_field="stamp_duty_rate",
            old_value=0.0005,
            new_value=0.00025,
            old_date="2023-01-15",
            new_date="2026-01-01",
        )

    def test_get_historical_version(self) -> None:
        reader = FeeScheduleReader()
        reader.load(
            [
                _make(
                    as_of_date="2023-01-01",
                    stamp_duty_rate=0.0005,
                    transfer_fee_rate=0.00001,
                    effective_from="2023-01-01",
                    effective_to="2023-08-27",
                ),
                _make(
                    as_of_date="2023-08-28",
                    stamp_duty_rate=0.00025,
                    transfer_fee_rate=0.00001,
                    effective_from="2023-08-28",
                ),
            ]
        )
        result = reader.get(1, "2023-01-15")
        assert result is not None
        assert result.stamp_duty_rate == pytest.approx(0.0005)

    def test_pit_effective_to_boundary(self) -> None:
        _check_effective_to_boundary(FeeScheduleReader())

    def test_pit_null_effective_to_means_current(self) -> None:
        _check_null_effective_to(FeeScheduleReader())


class TestFeeScheduleWriter:
    def test_write_and_retrieve(self) -> None:
        writer = FeeScheduleWriter()
        record = _make()
        writer.write(record)
        assert len(writer.get_records()) == 1
        assert writer.get_records()[0] is record

    def test_get_records_returns_copy(self) -> None:
        writer = FeeScheduleWriter()
        writer.write(_make())
        records = writer.get_records()
        records.clear()
        assert len(writer.get_records()) == 1
