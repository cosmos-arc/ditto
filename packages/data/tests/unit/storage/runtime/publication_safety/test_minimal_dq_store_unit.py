"""Tests for publication safety minimal DQ stores."""

from pathlib import Path

from ditto_data.storage.runtime.publication_safety import (
    MinimalDQReader,
    MinimalDQWriter,
)
from ditto_kernel.publication_safety import DerivedMinimalDQSummaryRecord


class TestMinimalDQStore:
    """Tests for minimal DQ summary reader/writer."""

    def test_minimal_dq_roundtrip(self, tmp_path: Path) -> None:
        """Minimal DQ summary should round-trip by derived/version/run."""
        writer = MinimalDQWriter(base_path=tmp_path)
        reader = MinimalDQReader(base_path=tmp_path)
        record = DerivedMinimalDQSummaryRecord(
            derived_id="factor.momentum_20d",
            version=3,
            run_id="drv-001",
            passed=True,
            error_count=0,
            payload={
                "row_count": 100,
                "null_value_count": 2,
                "nan_value_count": 0,
                "computable_value_count": 98,
                "failed_checks": [],
            },
            created_at="2026-03-14T12:00:00+08:00",
        )

        writer.write_summary(record)
        loaded = reader.read_summary("factor.momentum_20d", 3, "drv-001")

        assert loaded == record

    def test_latest_summary_returns_most_recent_record(self, tmp_path: Path) -> None:
        """Latest minimal DQ lookup should return the newest record by created_at."""
        writer = MinimalDQWriter(base_path=tmp_path)
        reader = MinimalDQReader(base_path=tmp_path)
        older = DerivedMinimalDQSummaryRecord(
            derived_id="factor.momentum_20d",
            version=3,
            run_id="drv-001",
            passed=False,
            error_count=1,
            payload={"failed_checks": ["row_count_positive"]},
            created_at="2026-03-14T12:00:00+08:00",
        )
        newer = DerivedMinimalDQSummaryRecord(
            derived_id="factor.momentum_20d",
            version=3,
            run_id="drv-002",
            passed=True,
            error_count=0,
            payload={"failed_checks": []},
            created_at="2026-03-14T12:05:00+08:00",
        )

        writer.write_summary(older)
        writer.write_summary(newer)

        latest = reader.get_latest_summary("factor.momentum_20d", 3)

        assert latest == newer
