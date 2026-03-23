"""Tests for TradingRuleReader / TradingRuleWriter (PIT versioned)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest
from ditto_datahub.stores.metadata.trading_rule_reader import (
    TradingRuleReader,
    TradingRuleRecord,
)
from ditto_datahub.stores.metadata.trading_rule_writer import TradingRuleWriter

_DEFAULTS: dict[str, object] = {
    "instrument_id": "159915.SZ",
    "as_of_date": "2026-01-01",
    "settlement_cycle": 1,
    "fund_settlement_cycle": 1,
    "price_limit_pct": 0.10,
    "order_types_supported": ("market", "limit"),
    "call_auction_sessions": ("open", "close"),
    "effective_from": "2026-01-01",
    "effective_to": None,
}


def _make(**overrides: object) -> TradingRuleRecord:
    return TradingRuleRecord(**{**_DEFAULTS, **overrides})


def _check_effective_from_boundary(
    reader: TradingRuleReader,
    *,
    effective_from: str = "2026-02-01",
    match_date: str = "2026-02-01",
    miss_date: str = "2026-01-31",
    instrument_id: str = "159915.SZ",
) -> None:
    """effective_from <= as_of_date: as_of_date == effective_from 应匹配."""
    reader.load([_make(effective_from=effective_from)])
    assert reader.get(instrument_id, match_date) is not None
    assert reader.get(instrument_id, miss_date) is None


def _check_effective_to_boundary(
    reader: TradingRuleReader,
    *,
    effective_to: str = "2026-02-15",
    match_date: str = "2026-02-14",
    miss_date: str = "2026-02-15",
    instrument_id: str = "159915.SZ",
) -> None:
    """effective_to > as_of_date: boundary 是 exclusive, == 应不匹配."""
    reader.load([_make(effective_to=effective_to)])
    assert reader.get(instrument_id, match_date) is not None
    assert reader.get(instrument_id, miss_date) is None


def _check_latest_version(
    reader: TradingRuleReader,
    *,
    old_attrs: dict[str, Any],
    new_attrs: dict[str, Any],
    check_field: str,
    old_value: Any,
    new_value: Any,
    old_date: str,
    new_date: str,
    instrument_id: str = "159915.SZ",
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
    reader: TradingRuleReader,
    *,
    far_future_date: str = "2099-12-31",
    instrument_id: str = "159915.SZ",
) -> None:
    """effective_to IS NULL 表示版本仍然有效."""
    reader.load([_make()])
    assert reader.get(instrument_id, far_future_date) is not None


class TestTradingRuleRecord:
    """Tests for TradingRuleRecord frozen dataclass."""

    def test_create_record(self) -> None:
        record = _make()
        assert record.settlement_cycle == 1
        assert record.effective_to is None

    def test_record_is_frozen(self) -> None:
        record = _make()
        with pytest.raises(FrozenInstanceError):
            record.settlement_cycle = 0  # type: ignore[misc]

    def test_record_fields_accessible(self) -> None:
        record = _make()
        assert record.instrument_id == "159915.SZ"
        assert record.order_types_supported == ("market", "limit")
        assert record.call_auction_sessions == ("open", "close")


class TestTradingRuleReader:
    """Tests for TradingRuleReader PIT queries."""

    def test_get_returns_matching_record(self) -> None:
        reader = TradingRuleReader()
        reader.load([_make()])
        result = reader.get("159915.SZ", "2026-03-01")
        assert result is not None
        assert result.settlement_cycle == 1

    def test_get_returns_none_when_no_match(self) -> None:
        reader = TradingRuleReader()
        result = reader.get("999999.SZ", "2026-01-01")
        assert result is None

    def test_pit_effective_from_boundary(self) -> None:
        _check_effective_from_boundary(TradingRuleReader())

    def test_pit_effective_to_boundary(self) -> None:
        _check_effective_to_boundary(TradingRuleReader())

    def test_pit_selects_latest_version(self) -> None:
        _check_latest_version(
            TradingRuleReader(),
            old_attrs={
                "effective_from": "2026-01-01",
                "effective_to": "2026-06-01",
                "order_types_supported": ("market",),
                "call_auction_sessions": ("open",),
            },
            new_attrs={"effective_from": "2026-06-01", "price_limit_pct": 0.20},
            check_field="price_limit_pct",
            old_value=0.10,
            new_value=0.20,
            old_date="2026-05-15",
            new_date="2026-06-01",
        )

    def test_pit_null_effective_to_means_current(self) -> None:
        _check_null_effective_to(TradingRuleReader())


class TestTradingRuleWriter:
    """Tests for TradingRuleWriter."""

    def test_write_and_retrieve(self) -> None:
        writer = TradingRuleWriter()
        record = _make()
        writer.write(record)
        records = writer.get_records()
        assert len(records) == 1
        assert records[0].instrument_id == "159915.SZ"

    def test_write_multiple_records(self) -> None:
        writer = TradingRuleWriter()
        writer.write(_make(instrument_id="159915.SZ"))
        writer.write(_make(instrument_id="510300.SH"))
        assert len(writer.get_records()) == 2
