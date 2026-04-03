"""Tests for SQLiteFeeScheduleReader / SQLiteFeeScheduleWriter."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from ditto_data.storage.metadata.fee_schedule_reader import (
    FeeScheduleRecord,
    SQLiteFeeScheduleReader,
)
from ditto_data.storage.metadata.fee_schedule_writer import (
    SQLiteFeeScheduleWriter,
)
from ditto_infra.foundation import SQLitePool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pool(tmp_path: object) -> Generator[SQLitePool, None, None]:
    """Create a SQLitePool with fee_schedule schema initialized."""
    p = SQLitePool(str(tmp_path / "test_fee_schedule.db"))
    reader = SQLiteFeeScheduleReader(p)
    reader.init_schema()
    yield p
    p.close()


@pytest.fixture
def reader(pool: SQLitePool) -> SQLiteFeeScheduleReader:
    """Create a SQLiteFeeScheduleReader."""
    return SQLiteFeeScheduleReader(pool)


@pytest.fixture
def writer(pool: SQLitePool) -> SQLiteFeeScheduleWriter:
    """Create a SQLiteFeeScheduleWriter."""
    return SQLiteFeeScheduleWriter(pool)


# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Tests: init_schema
# ---------------------------------------------------------------------------


class TestInitSchema:
    def test_init_schema_creates_table(self, pool: SQLitePool) -> None:
        """init_schema should create fee_schedule table."""
        conn = pool.get_connection()
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fee_schedule'"
        ).fetchone()
        assert result is not None

    def test_init_schema_idempotent(self, pool: SQLitePool) -> None:
        """Calling init_schema twice should not raise."""
        reader = SQLiteFeeScheduleReader(pool)
        reader.init_schema()
        reader.init_schema()  # second call should be fine


# ---------------------------------------------------------------------------
# Tests: Writer
# ---------------------------------------------------------------------------


class TestSQLiteFeeScheduleWriter:
    def test_write_single_record(self, writer: SQLiteFeeScheduleWriter) -> None:
        """write() should persist a single record."""
        record = _make()
        writer.write(record)
        records = writer.get_records()
        assert len(records) == 1
        assert records[0].instrument_id == 1

    def test_write_multiple_records(self, writer: SQLiteFeeScheduleWriter) -> None:
        """write() should accumulate records."""
        writer.write(_make(instrument_id=1))
        writer.write(_make(instrument_id=2))
        assert len(writer.get_records()) == 2

    def test_write_upserts_on_conflict(
        self, writer: SQLiteFeeScheduleWriter, reader: SQLiteFeeScheduleReader
    ) -> None:
        """Writing with same PK (instrument_id, effective_from) should replace."""
        record_v1 = _make(commission_rate=0.0003)
        record_v2 = _make(commission_rate=0.0005)
        writer.write(record_v1)
        writer.write(record_v2)
        records = writer.get_records()
        assert len(records) == 1
        assert records[0].commission_rate == pytest.approx(0.0005)


# ---------------------------------------------------------------------------
# Tests: Reader
# ---------------------------------------------------------------------------


class TestSQLiteFeeScheduleReader:
    def test_get_returns_matching_record(
        self, writer: SQLiteFeeScheduleWriter, reader: SQLiteFeeScheduleReader
    ) -> None:
        """get() should return the record matching instrument_id and PIT condition."""
        writer.write(_make())
        result = reader.get(1, "2026-03-01")
        assert result is not None
        assert result.commission_rate == pytest.approx(0.0003)

    def test_get_returns_none_when_no_match(
        self, reader: SQLiteFeeScheduleReader
    ) -> None:
        """get() should return None when no record matches."""
        assert reader.get(999, "2026-01-01") is None

    def test_get_returns_none_for_empty_db(
        self, reader: SQLiteFeeScheduleReader
    ) -> None:
        """get() on an empty database should return None."""
        assert reader.get(1, "2026-01-01") is None

    def test_pit_effective_from_boundary(
        self, writer: SQLiteFeeScheduleWriter, reader: SQLiteFeeScheduleReader
    ) -> None:
        """effective_from <= as_of_date: boundary should be inclusive."""
        writer.write(
            _make(
                effective_from="2026-02-01",
                effective_to=None,
            )
        )
        assert reader.get(1, "2026-02-01") is not None
        assert reader.get(1, "2026-01-31") is None

    def test_pit_effective_to_boundary(
        self, writer: SQLiteFeeScheduleWriter, reader: SQLiteFeeScheduleReader
    ) -> None:
        """effective_to > as_of_date: boundary should be exclusive."""
        writer.write(
            _make(
                effective_from="2026-01-01",
                effective_to="2026-02-15",
            )
        )
        assert reader.get(1, "2026-02-14") is not None
        assert reader.get(1, "2026-02-15") is None

    def test_pit_selects_latest_version(
        self, writer: SQLiteFeeScheduleWriter, reader: SQLiteFeeScheduleReader
    ) -> None:
        """Multiple versions match -> return the one with max effective_from."""
        writer.write(
            _make(
                effective_from="2023-01-01",
                effective_to="2023-08-27",
                stamp_duty_rate=0.0005,
                transfer_fee_rate=0.00001,
            )
        )
        writer.write(
            _make(
                effective_from="2023-08-28",
                effective_to=None,
                stamp_duty_rate=0.00025,
                transfer_fee_rate=0.00001,
            )
        )
        # Historical version
        result_old = reader.get(1, "2023-01-15")
        assert result_old is not None
        assert result_old.stamp_duty_rate == pytest.approx(0.0005)

        # Current version
        result_new = reader.get(1, "2026-01-01")
        assert result_new is not None
        assert result_new.stamp_duty_rate == pytest.approx(0.00025)

    def test_pit_null_effective_to_means_current(
        self, writer: SQLiteFeeScheduleWriter, reader: SQLiteFeeScheduleReader
    ) -> None:
        """effective_to IS NULL means the version is still valid."""
        writer.write(_make())
        assert reader.get(1, "2099-12-31") is not None

    def test_pit_multiple_instruments(
        self, writer: SQLiteFeeScheduleWriter, reader: SQLiteFeeScheduleReader
    ) -> None:
        """get() should isolate queries by instrument_id."""
        writer.write(_make(instrument_id=1, commission_rate=0.0003))
        writer.write(_make(instrument_id=2, commission_rate=0.0005))
        assert reader.get(1, "2026-03-01").commission_rate == pytest.approx(0.0003)
        assert reader.get(2, "2026-03-01").commission_rate == pytest.approx(0.0005)

    def test_pit_gap_between_versions(
        self, writer: SQLiteFeeScheduleWriter, reader: SQLiteFeeScheduleReader
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
        assert reader.get(1, "2026-02-15") is None

    def test_float_precision_round_trip(
        self, writer: SQLiteFeeScheduleWriter, reader: SQLiteFeeScheduleReader
    ) -> None:
        """Float fee fields should round-trip with acceptable precision."""
        record = _make(
            commission_rate=0.00025,
            min_commission=5.0,
            stamp_duty_rate=0.0005,
            transfer_fee_rate=0.00001,
        )
        writer.write(record)
        result = reader.get(1, "2026-03-01")
        assert result is not None
        assert result.commission_rate == pytest.approx(0.00025)
        assert result.min_commission == pytest.approx(5.0)
        assert result.stamp_duty_rate == pytest.approx(0.0005)
        assert result.transfer_fee_rate == pytest.approx(0.00001)


# ---------------------------------------------------------------------------
# Tests: load + read integration
# ---------------------------------------------------------------------------


class TestLoadAndRead:
    def test_load_persists_records(self, reader: SQLiteFeeScheduleReader) -> None:
        """load() should persist records via INSERT OR REPLACE."""
        records = [
            _make(instrument_id=1),
            _make(instrument_id=2),
        ]
        reader.load(records)
        assert reader.get(1, "2026-03-01") is not None
        assert reader.get(2, "2026-03-01") is not None

    def test_load_replaces_existing(self, reader: SQLiteFeeScheduleReader) -> None:
        """load() with same PK should replace existing records."""
        reader.load([_make(commission_rate=0.0003)])
        assert reader.get(1, "2026-03-01").commission_rate == pytest.approx(0.0003)
        reader.load([_make(commission_rate=0.0008)])
        assert reader.get(1, "2026-03-01").commission_rate == pytest.approx(0.0008)
