"""Tests for DerivedArtifactReader — pruning, schema evolution, memory management."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import polars as pl
from ditto_features.services.derived._pruning import prune_parquet_paths

# ---------------------------------------------------------------------------
# Partition pruning tests
# ---------------------------------------------------------------------------


class TestPruneParquetPaths:
    """Tests for prune_parquet_paths() pure function."""

    def test_prune_paths_with_both_start_end(self, tmp_path: Path) -> None:
        """Date range filters to only relevant year files."""
        # Create year partition files for 2023, 2024, 2025
        for year in (2023, 2024, 2025):
            (tmp_path / f"{year}.parquet").touch()

        result = prune_parquet_paths(tmp_path, start="2024-06-01", end="2025-03-15")

        assert len(result) == 2
        expected_names = {f"{y}.parquet" for y in (2024, 2025)}
        assert {p.name for p in result} == expected_names
        assert result == sorted(result)

    def test_prune_paths_with_single_year_range(self, tmp_path: Path) -> None:
        """Date range within a single year returns only that file."""
        for year in (2023, 2024, 2025):
            (tmp_path / f"{year}.parquet").touch()

        result = prune_parquet_paths(tmp_path, start="2024-01-01", end="2024-12-31")

        assert len(result) == 1
        assert result[0].name == "2024.parquet"

    def test_prune_paths_without_filters_returns_all(self, tmp_path: Path) -> None:
        """No start/end filters → glob returns all parquet files."""
        for year in (2023, 2024, 2025):
            (tmp_path / f"{year}.parquet").touch()

        result = prune_parquet_paths(tmp_path, start=None, end=None)

        assert len(result) == 3
        expected_names = {f"{y}.parquet" for y in (2023, 2024, 2025)}
        assert {p.name for p in result} == expected_names

    def test_prune_paths_with_only_start_returns_all(self, tmp_path: Path) -> None:
        """Only start provided (no end) → fallback to glob."""
        for year in (2023, 2024, 2025):
            (tmp_path / f"{year}.parquet").touch()

        result = prune_parquet_paths(tmp_path, start="2024-01-01", end=None)

        assert len(result) == 3

    def test_prune_paths_excludes_non_partition_files(self, tmp_path: Path) -> None:
        """Non-year parquet files (e.g. _ephemeral/) should not be returned."""
        (tmp_path / "2024.parquet").touch()
        (tmp_path / "2025.parquet").touch()
        # Directories and non-year files should be excluded
        (tmp_path / "_ephemeral").mkdir()
        (tmp_path / "_runs").mkdir()

        # When filtering, only year-named files in the root are returned
        result = prune_parquet_paths(tmp_path, start="2024-01-01", end="2025-12-31")

        assert len(result) == 2
        assert {p.name for p in result} == {"2024.parquet", "2025.parquet"}

    def test_prune_paths_excludes_nonexistent_years(self, tmp_path: Path) -> None:
        """Year files that don't exist are silently skipped."""
        (tmp_path / "2023.parquet").touch()
        # 2024 and 2025 don't exist
        result = prune_parquet_paths(tmp_path, start="2023-01-01", end="2025-12-31")

        assert len(result) == 1
        assert result[0].name == "2023.parquet"

    def test_prune_paths_empty_directory(self, tmp_path: Path) -> None:
        """Empty directory with date range returns empty list."""
        result = prune_parquet_paths(tmp_path, start="2024-01-01", end="2024-12-31")
        assert result == []

    def test_prune_paths_empty_directory_no_filters(self, tmp_path: Path) -> None:
        """Empty directory with no filters returns empty list."""
        result = prune_parquet_paths(tmp_path, start=None, end=None)
        assert result == []


# ---------------------------------------------------------------------------
# Schema evolution tests
# ---------------------------------------------------------------------------


class TestSchemaEvolution:
    """Tests for schema evolution handling across year partitions.

    Exercises the production ``_scan_with_schema_evolution`` function which
    uses ``pl.concat(how='diagonal_relaxed')`` to merge per-file LazyFrames
    so that column additions and type widenings (int -> float) are handled.
    """

    def test_schema_evolution_new_column_in_later_year(self, tmp_path: Path) -> None:
        """2024 lacks extra_col, 2025 has it → merge succeeds."""
        from ditto_features.services.derived.artifact_reader import (
            _scan_with_schema_evolution,
        )

        df_2024 = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": ["2024-01-02", "2024-01-03"],
                "value": [10.0, 20.0],
            }
        )
        df_2025 = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": ["2025-01-02", "2025-01-03"],
                "value": [30.0, 40.0],
                "extra_col": ["a", "b"],
            }
        )

        df_2024.write_parquet(tmp_path / "2024.parquet")
        df_2025.write_parquet(tmp_path / "2025.parquet")

        paths = prune_parquet_paths(tmp_path, start="2024-01-01", end="2025-12-31")
        result = _scan_with_schema_evolution(paths)

        collected = result.collect().sort("instrument_id", "trade_date")

        assert "extra_col" in collected.columns
        assert collected.shape == (4, 4)
        # 2024 rows should have null for extra_col
        row_2024 = collected.filter(pl.col("trade_date") == "2024-01-02")
        assert row_2024["extra_col"][0] is None

    def test_schema_evolution_type_widen(self, tmp_path: Path) -> None:
        """int in 2023 → float in 2025 → diagonal_relaxed handles widening."""
        from ditto_features.services.derived.artifact_reader import (
            _scan_with_schema_evolution,
        )

        df_2023 = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": ["2023-06-01", "2023-06-02"],
                "value": [10, 20],  # int
            }
        )
        df_2025 = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": ["2025-01-02", "2025-01-03"],
                "value": [30.5, 40.7],  # float
            }
        )

        df_2023.write_parquet(tmp_path / "2023.parquet")
        df_2025.write_parquet(tmp_path / "2025.parquet")

        paths = prune_parquet_paths(tmp_path, start="2023-01-01", end="2025-12-31")
        result = _scan_with_schema_evolution(paths)

        collected = result.collect().sort("instrument_id", "trade_date")

        assert collected.shape == (4, 3)
        # value should be widened to float
        assert collected["value"].dtype == pl.Float64
        assert collected["value"][0] == 10.0
        # After sort by [instrument_id, trade_date]:
        # idx 0: (1, 2023-06-01, 10.0), idx 1: (1, 2025-01-02, 30.5)
        assert collected["value"][1] == 30.5

    def test_scan_with_schema_evolution_single_file(self, tmp_path: Path) -> None:
        """Single parquet file is scanned directly without concat."""
        from ditto_features.services.derived.artifact_reader import (
            _scan_with_schema_evolution,
        )

        pl.DataFrame({"a": [1, 2]}).write_parquet(tmp_path / "2024.parquet")
        result = _scan_with_schema_evolution([tmp_path / "2024.parquet"])
        assert result.collect().shape == (2, 1)


# ---------------------------------------------------------------------------
# Memory management tests (MAT-M-4)
# ---------------------------------------------------------------------------


def _make_catalog_service(sqlite_client):
    """Create a real DerivedCatalogService backed by in-memory SQLite."""
    from ditto_features.services.derived_catalog_service import DerivedCatalogService
    from ditto_features.storage.sqlite.derived import (
        SQLiteDerivedCatalogReader,
        SQLiteDerivedCatalogWriter,
    )

    return DerivedCatalogService(
        catalog_reader=SQLiteDerivedCatalogReader(sqlite_client),
        catalog_writer=SQLiteDerivedCatalogWriter(sqlite_client),
    )


def _seed_reader_catalog(
    catalog_service,
    *,
    derived_id: str = "factor.test_factor",
    version: int = 1,
) -> None:
    """Seed catalog with a minimal spec + version record for read_frame tests."""
    from ditto_features.models.derived import DerivedSpecRecord, DerivedVersionRecord
    from ditto_kernel.strategy import (
        DerivedRole,
        DerivedSpec,
        MaterializationProfile,
    )

    spec = DerivedSpec(
        id=derived_id,
        version=version,
        role=DerivedRole.FACTOR,
        materialization_profile=MaterializationProfile.SERIES,
        expression="close_20",
    )

    catalog_service.save_spec(
        DerivedSpecRecord(
            derived_id=derived_id,
            version=version,
            role=spec.role.value,
            materialization_profile=spec.materialization_profile.value,
            spec_hash=f"hash:{derived_id}:v{version}",
            spec_json=asdict(spec),
            created_at="2026-03-19T12:00:00+08:00",
        )
    )
    catalog_service.save_version(
        DerivedVersionRecord(
            derived_id=derived_id,
            version=version,
            status="published",
            engine_version="expr-v1",
            is_online=True,
            is_primary=True,
            created_at="2026-03-19T12:00:00+08:00",
            updated_at=None,
        )
    )


def _make_reader(
    catalog_service,
    artifact_root: Path,
):
    from ditto_features.services.derived import DerivedArtifactReader

    return DerivedArtifactReader(
        catalog_service=catalog_service,
        artifact_root=artifact_root,
    )


class TestReadFrameAsLazy:
    """Tests for read_frame(as_lazy=True) returning pl.LazyFrame."""

    def test_read_frame_as_lazy_returns_lazyframe(
        self, tmp_path: Path, sqlite_client
    ) -> None:
        """When as_lazy=True, read_frame should return a pl.LazyFrame."""
        catalog_service = _make_catalog_service(sqlite_client)
        derived_id = "factor.lazy_test"
        _seed_reader_catalog(catalog_service, derived_id=derived_id)

        # Write a parquet file under the expected version root
        version_root = tmp_path / "derived" / "artifacts" / "series" / derived_id / "v1"
        version_root.mkdir(parents=True, exist_ok=True)
        df = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": ["2024-01-02", "2024-01-03"],
                "value": [10.0, 20.0],
            }
        )
        df.write_parquet(version_root / "2024.parquet")

        reader = _make_reader(catalog_service, tmp_path)
        result = reader.read_frame(
            derived_id=derived_id,
            version=1,
            as_lazy=True,
        )

        assert isinstance(result, pl.LazyFrame)


class TestReadFrameStreaming:
    """Tests for read_frame(streaming=True) collecting with streaming engine."""

    def test_read_frame_streaming_mode(self, tmp_path: Path, sqlite_client) -> None:
        """When streaming=True, collect() should receive engine='streaming'."""
        from unittest.mock import patch

        catalog_service = _make_catalog_service(sqlite_client)
        derived_id = "factor.streaming_test"
        _seed_reader_catalog(catalog_service, derived_id=derived_id)

        version_root = tmp_path / "derived" / "artifacts" / "series" / derived_id / "v1"
        version_root.mkdir(parents=True, exist_ok=True)
        df = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "trade_date": ["2024-01-02", "2024-01-03"],
                "value": [10.0, 20.0],
            }
        )
        df.write_parquet(version_root / "2024.parquet")

        reader = _make_reader(catalog_service, tmp_path)

        # Wrap the real LazyFrame.collect to capture kwargs
        collect_kwargs: dict[str, object] = {}
        original_collect = pl.LazyFrame.collect

        def spy_collect(self, **kwargs):  # type: ignore[no-untyped-def]
            collect_kwargs.update(kwargs)
            return original_collect(self, **kwargs)

        with patch.object(pl.LazyFrame, "collect", spy_collect):
            reader.read_frame(
                derived_id=derived_id,
                version=1,
                streaming=True,
            )

        assert collect_kwargs.get("engine") == "streaming"


class TestReadFrameMaxRows:
    """Tests for read_frame(max_rows=N) limiting collected rows."""

    def test_read_frame_max_rows_limit(self, tmp_path: Path, sqlite_client) -> None:
        """max_rows should limit the number of rows returned."""
        catalog_service = _make_catalog_service(sqlite_client)
        derived_id = "factor.maxrows_test"
        _seed_reader_catalog(catalog_service, derived_id=derived_id)

        version_root = tmp_path / "derived" / "artifacts" / "series" / derived_id / "v1"
        version_root.mkdir(parents=True, exist_ok=True)
        df = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3, 4, 5],
                "trade_date": [
                    "2024-01-02",
                    "2024-01-03",
                    "2024-01-04",
                    "2024-01-05",
                    "2024-01-06",
                ],
                "value": [10.0, 20.0, 30.0, 40.0, 50.0],
            }
        )
        df.write_parquet(version_root / "2024.parquet")

        reader = _make_reader(catalog_service, tmp_path)
        result = reader.read_frame(
            derived_id=derived_id,
            version=1,
            max_rows=3,
        )

        assert isinstance(result, pl.DataFrame)
        assert result.height <= 3
