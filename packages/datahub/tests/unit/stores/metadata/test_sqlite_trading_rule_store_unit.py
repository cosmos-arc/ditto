"""Tests for SQLiteTradingRuleReader / SQLiteTradingRuleWriter."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from ditto_datahub.stores.metadata.trading_rule_reader import (
    SQLiteTradingRuleReader,
    TradingRuleRecord,
)
from ditto_datahub.stores.metadata.trading_rule_writer import (
    SQLiteTradingRuleWriter,
)
from ditto_infra.foundation import SQLitePool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pool(tmp_path: object) -> Generator[SQLitePool, None, None]:
    """Create a SQLitePool with trading_rule schema initialized."""
    p = SQLitePool(str(tmp_path / "test_trading_rule.db"))
    reader = SQLiteTradingRuleReader(p)
    reader.init_schema()
    yield p
    p.close()


@pytest.fixture
def reader(pool: SQLitePool) -> SQLiteTradingRuleReader:
    """Create a SQLiteTradingRuleReader."""
    return SQLiteTradingRuleReader(pool)


@pytest.fixture
def writer(pool: SQLitePool) -> SQLiteTradingRuleWriter:
    """Create a SQLiteTradingRuleWriter."""
    return SQLiteTradingRuleWriter(pool)


# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, object] = {
    "instrument_id": 1,
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


# ---------------------------------------------------------------------------
# Tests: init_schema
# ---------------------------------------------------------------------------


class TestInitSchema:
    def test_init_schema_creates_table(self, pool: SQLitePool) -> None:
        """init_schema should create trading_rule table."""
        conn = pool.get_connection()
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='trading_rule'"
        ).fetchone()
        assert result is not None

    def test_init_schema_idempotent(self, pool: SQLitePool) -> None:
        """Calling init_schema twice should not raise."""
        reader = SQLiteTradingRuleReader(pool)
        reader.init_schema()
        reader.init_schema()  # second call should be fine


# ---------------------------------------------------------------------------
# Tests: Writer
# ---------------------------------------------------------------------------


class TestSQLiteTradingRuleWriter:
    def test_write_single_record(self, writer: SQLiteTradingRuleWriter) -> None:
        """write() should persist a single record."""
        record = _make()
        writer.write(record)
        records = writer.get_records()
        assert len(records) == 1
        assert records[0].instrument_id == 1

    def test_write_multiple_records(self, writer: SQLiteTradingRuleWriter) -> None:
        """write() should accumulate records."""
        writer.write(_make(instrument_id=1))
        writer.write(_make(instrument_id=2))
        assert len(writer.get_records()) == 2

    def test_write_upserts_on_conflict(
        self, writer: SQLiteTradingRuleWriter, reader: SQLiteTradingRuleReader
    ) -> None:
        """Writing with same PK (instrument_id, effective_from) should replace."""
        record_v1 = _make(price_limit_pct=0.10)
        record_v2 = _make(price_limit_pct=0.20)
        writer.write(record_v1)
        writer.write(record_v2)
        # Only one record should exist
        records = writer.get_records()
        assert len(records) == 1
        assert records[0].price_limit_pct == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# Tests: Reader
# ---------------------------------------------------------------------------


class TestSQLiteTradingRuleReader:
    def test_get_returns_matching_record(
        self, writer: SQLiteTradingRuleWriter, reader: SQLiteTradingRuleReader
    ) -> None:
        """get() should return the record matching instrument_id and PIT condition."""
        writer.write(_make())
        result = reader.get(1, "2026-03-01")
        assert result is not None
        assert result.settlement_cycle == 1

    def test_get_returns_none_when_no_match(
        self, reader: SQLiteTradingRuleReader
    ) -> None:
        """get() should return None when no record matches."""
        assert reader.get(999, "2026-01-01") is None

    def test_get_returns_none_for_empty_db(
        self, reader: SQLiteTradingRuleReader
    ) -> None:
        """get() on an empty database should return None."""
        assert reader.get(1, "2026-01-01") is None

    def test_pit_effective_from_boundary(
        self, writer: SQLiteTradingRuleWriter, reader: SQLiteTradingRuleReader
    ) -> None:
        """effective_from <= as_of_date: boundary should be inclusive."""
        writer.write(
            _make(
                effective_from="2026-02-01",
                effective_to=None,
            )
        )
        # as_of_date == effective_from -> should match
        assert reader.get(1, "2026-02-01") is not None
        # as_of_date < effective_from -> should not match
        assert reader.get(1, "2026-01-31") is None

    def test_pit_effective_to_boundary(
        self, writer: SQLiteTradingRuleWriter, reader: SQLiteTradingRuleReader
    ) -> None:
        """effective_to > as_of_date: boundary should be exclusive."""
        writer.write(
            _make(
                effective_from="2026-01-01",
                effective_to="2026-02-15",
            )
        )
        # as_of_date < effective_to -> should match
        assert reader.get(1, "2026-02-14") is not None
        # as_of_date == effective_to -> should NOT match (exclusive)
        assert reader.get(1, "2026-02-15") is None

    def test_pit_selects_latest_version(
        self, writer: SQLiteTradingRuleWriter, reader: SQLiteTradingRuleReader
    ) -> None:
        """Multiple versions match -> return the one with max effective_from."""
        writer.write(
            _make(
                effective_from="2026-01-01",
                effective_to="2026-06-01",
                price_limit_pct=0.10,
                order_types_supported=("market",),
                call_auction_sessions=("open",),
            )
        )
        writer.write(
            _make(
                effective_from="2026-06-01",
                effective_to=None,
                price_limit_pct=0.20,
            )
        )
        # Before new version takes effect -> old version
        result_old = reader.get(1, "2026-05-15")
        assert result_old is not None
        assert result_old.price_limit_pct == pytest.approx(0.10)

        # After new version takes effect -> new version
        result_new = reader.get(1, "2026-06-01")
        assert result_new is not None
        assert result_new.price_limit_pct == pytest.approx(0.20)

    def test_pit_null_effective_to_means_current(
        self, writer: SQLiteTradingRuleWriter, reader: SQLiteTradingRuleReader
    ) -> None:
        """effective_to IS NULL means the version is still valid."""
        writer.write(_make())
        assert reader.get(1, "2099-12-31") is not None

    def test_pit_multiple_instruments(
        self, writer: SQLiteTradingRuleWriter, reader: SQLiteTradingRuleReader
    ) -> None:
        """get() should isolate queries by instrument_id."""
        writer.write(_make(instrument_id=1, settlement_cycle=1))
        writer.write(_make(instrument_id=2, settlement_cycle=2))
        assert reader.get(1, "2026-03-01") is not None
        assert reader.get(1, "2026-03-01").settlement_cycle == 1
        assert reader.get(2, "2026-03-01") is not None
        assert reader.get(2, "2026-03-01").settlement_cycle == 2

    def test_pit_gap_between_versions(
        self, writer: SQLiteTradingRuleWriter, reader: SQLiteTradingRuleReader
    ) -> None:
        """If there is a gap between versions, dates in the gap should return None."""
        writer.write(
            _make(
                effective_from="2026-01-01",
                effective_to="2026-02-01",
            )
        )
        writer.write(
            _make(
                effective_from="2026-03-01",
                effective_to=None,
            )
        )
        # Date in the gap -> no version covers it
        assert reader.get(1, "2026-02-15") is None

    def test_tuple_fields_round_trip(
        self, writer: SQLiteTradingRuleWriter, reader: SQLiteTradingRuleReader
    ) -> None:
        """Tuple fields (order_types, call_auction) should round-trip correctly."""
        record = _make(
            order_types_supported=("market", "limit", "stop"),
            call_auction_sessions=("open", "close", "midday"),
        )
        writer.write(record)
        result = reader.get(1, "2026-03-01")
        assert result is not None
        assert result.order_types_supported == ("market", "limit", "stop")
        assert result.call_auction_sessions == ("open", "close", "midday")

    def test_price_limit_pct_none_round_trip(
        self, writer: SQLiteTradingRuleWriter, reader: SQLiteTradingRuleReader
    ) -> None:
        """price_limit_pct=None should round-trip correctly."""
        record = _make(price_limit_pct=None)
        writer.write(record)
        result = reader.get(1, "2026-03-01")
        assert result is not None
        assert result.price_limit_pct is None


# ---------------------------------------------------------------------------
# Tests: load + read integration
# ---------------------------------------------------------------------------


class TestLoadAndRead:
    def test_load_persists_records(self, reader: SQLiteTradingRuleReader) -> None:
        """load() should persist records via INSERT OR REPLACE."""
        records = [
            _make(instrument_id=1),
            _make(instrument_id=2),
        ]
        reader.load(records)
        assert reader.get(1, "2026-03-01") is not None
        assert reader.get(2, "2026-03-01") is not None

    def test_load_replaces_existing(self, reader: SQLiteTradingRuleReader) -> None:
        """load() with same PK should replace existing records."""
        reader.load([_make(price_limit_pct=0.10)])
        assert reader.get(1, "2026-03-01").price_limit_pct == pytest.approx(0.10)
        reader.load([_make(price_limit_pct=0.30)])
        assert reader.get(1, "2026-03-01").price_limit_pct == pytest.approx(0.30)
