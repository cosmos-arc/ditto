"""Standalone exports preserve actual file schema, rows and immutable targets."""

import sqlite3
from pathlib import Path

import polars as pl
import pytest
from ditto_analysis.errors import ExperimentConflictError
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.storage.sqlite.research.export import sqlite_dataset_bytes


@pytest.mark.parametrize("empty", [False, True])
def test_sqlite_schema_and_replay(tmp_path: Path, empty: bool) -> None:
    artifacts = ResearchArtifactService(
        artifact_root=tmp_path, sqlite_export=sqlite_dataset_bytes
    )
    frame = pl.DataFrame(
        {"select": [10, 20], 'a"b': ["x", "y"], "price x": [1.5, None]}
    )
    if empty:
        frame = frame.head(0)
    receipt = artifacts.export_dataset(
        "out.sqlite", frame, fmt="sqlite", table_name="test.dataset"
    )
    first = (tmp_path / "out.sqlite").read_bytes()
    assert (
        artifacts.export_dataset(
            "out.sqlite", frame, fmt="sqlite", table_name="test.dataset"
        )
        == receipt
    )
    assert (tmp_path / "out.sqlite").read_bytes() == first
    with sqlite3.connect(tmp_path / "out.sqlite") as connection:
        assert connection.execute('SELECT * FROM "test.dataset"').fetchall() == (
            [] if empty else [(10, "x", 1.5), (20, "y", None)]
        )
        schema = connection.execute('PRAGMA table_info("test.dataset")').fetchall()
        assert [(row[1], row[2]) for row in schema] == [
            ("select", "INTEGER"),
            ('a"b', "TEXT"),
            ("price x", "REAL"),
        ]
    with pytest.raises(ExperimentConflictError):
        artifacts.export_dataset(
            "out.sqlite",
            pl.DataFrame({"other": [99]}),
            fmt="sqlite",
            table_name="test.dataset",
        )
    assert (tmp_path / "out.sqlite").read_bytes() == first


def test_sqlite_preserves_nanosecond_timestamps(tmp_path: Path) -> None:
    frame = pl.DataFrame({"time": [1770000000000000123]}).with_columns(
        pl.col("time").cast(pl.Datetime("ns"))
    )
    ResearchArtifactService(
        artifact_root=tmp_path, sqlite_export=sqlite_dataset_bytes
    ).export_dataset("out.sqlite", frame, fmt="sqlite")
    with sqlite3.connect(tmp_path / "out.sqlite") as connection:
        assert connection.execute("SELECT time FROM dataset").fetchone() == (
            "2026-02-02 02:40:00.000000123",
        )


def test_sqlite_refuses_nan_instead_of_silently_exporting_null(tmp_path: Path) -> None:
    from ditto_analysis.errors import ResearchDatasetError

    with pytest.raises(ResearchDatasetError):
        ResearchArtifactService(
            artifact_root=tmp_path, sqlite_export=sqlite_dataset_bytes
        ).export_dataset(
            "out.sqlite", pl.DataFrame({"value": [float("nan")]}), fmt="sqlite"
        )
    assert not (tmp_path / "out.sqlite").exists()
