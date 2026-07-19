"""Migration and isolation tests for the dedicated research experiment database."""

# Imports inside _api are intentionally reflected into a SimpleNamespace.
# ruff: noqa: F401

from __future__ import annotations

import hashlib
import importlib.resources
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from types import SimpleNamespace
from typing import Any

import pytest

APP_ID = 1_146_376_755
USER_VERSION = 1
DDL_SHA256 = "697d10854fb12e324ddcff349bad55b9b442425b244cb5f1852d7192cfb7a8fd"
SCHEMA_FINGERPRINT = "b4e0c52b7ef2f844987ecd65cc96ece5c5f75a3d19dc15e380c4ffdf10adc39a"


def _api() -> SimpleNamespace:
    from ditto_analysis.errors import (
        ExperimentDatabaseClosedError,
        ExperimentSchemaError,
    )
    from ditto_analysis.storage.sqlite.experiments import ResearchExperimentDatabase
    from ditto_analysis.storage.sqlite.experiments.schema import (
        schema_fingerprint,
        schema_rows,
    )

    return SimpleNamespace(**locals())


def _logical_snapshot(
    path: Path,
) -> tuple[
    int, int, tuple[tuple[Any, ...], ...], dict[str, tuple[tuple[Any, ...], ...]]
]:
    with sqlite3.connect(path) as connection:
        app_id = connection.execute("PRAGMA application_id").fetchone()[0]
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        objects = tuple(
            tuple(row)
            for row in connection.execute(
                """
                SELECT type, name, tbl_name, sql
                FROM sqlite_schema
                WHERE name NOT LIKE 'sqlite_%'
                ORDER BY type, name
                """
            )
        )
        tables = tuple(row[1] for row in objects if row[0] == "table")
        rows = {
            table: tuple(
                tuple(row) for row in connection.execute(f'SELECT * FROM "{table}"')
            )
            for table in tables
        }
    return app_id, version, objects, rows


def _metadata_snapshot(root: Path) -> dict[str, Any]:
    metadata_dir = root / "metadata"
    database_path = metadata_dir / "metadata.sqlite"
    files: dict[str, tuple[str, int, int]] = {}
    for path in sorted(metadata_dir.glob("metadata.sqlite*")):
        payload = path.read_bytes()
        stat = path.stat()
        files[path.name] = (
            hashlib.sha256(payload).hexdigest(),
            stat.st_size,
            stat.st_mtime_ns,
        )
    with sqlite3.connect(
        f"file:{database_path}?mode=ro&immutable=1", uri=True
    ) as connection:
        schema = tuple(
            tuple(row)
            for row in connection.execute(
                """
                SELECT type, name, tbl_name, sql
                FROM sqlite_schema ORDER BY type, name
                """
            )
        )
        rows = tuple(tuple(row) for row in connection.execute("SELECT * FROM sentinel"))
        counts = {
            row[0]: connection.execute(f'SELECT count(*) FROM "{row[0]}"').fetchone()[0]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_schema
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """
            )
        }
    return {"files": files, "schema": schema, "rows": rows, "counts": counts}


def _create_metadata_sentinel(root: Path) -> Path:
    path = root / "metadata" / "metadata.sqlite"
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE sentinel(key TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO sentinel VALUES ('identity', 'metadata-must-not-change')"
        )
        connection.commit()
    return path


def test_runtime_schema_resource_matches_the_approved_ddl_byte_for_byte() -> None:
    resource = importlib.resources.files(
        "ditto_analysis.storage.sqlite.experiments"
    ).joinpath("schema_v1.sql")
    payload = resource.read_bytes()
    approved = Path(
        "docs/plans/2026-07-19-r3-task7-research-schema-v1.sql"
    ).read_bytes()

    assert payload == approved
    assert hashlib.sha256(payload).hexdigest() == DDL_SHA256


def test_fresh_and_repeat_initialize_create_exact_approved_schema(
    tmp_path: Path,
) -> None:
    api = _api()
    database = api.ResearchExperimentDatabase(tmp_path)

    database.initialize()
    before = _logical_snapshot(database.path)
    database.initialize()
    after = _logical_snapshot(database.path)

    assert database.path == tmp_path / "research" / "research.sqlite"
    assert before == after
    app_id, version, objects, _rows = after
    assert (app_id, version) == (APP_ID, USER_VERSION)
    assert len(objects) == 50
    assert sum(row[0] == "table" for row in objects) == 9
    assert sum(row[0] == "index" for row in objects) == 14
    assert sum(row[0] == "trigger" for row in objects) == 27
    with database.connection() as connection:
        assert api.schema_fingerprint(api.schema_rows(connection)) == SCHEMA_FINGERPRINT
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_two_wrappers_initialize_the_same_empty_database_safely(tmp_path: Path) -> None:
    api = _api()
    first = api.ResearchExperimentDatabase(tmp_path)
    second = api.ResearchExperimentDatabase(tmp_path)
    barrier = Barrier(2)

    def initialize(database: Any) -> None:
        barrier.wait()
        database.initialize()

    with ThreadPoolExecutor(max_workers=2) as executor:
        tuple(executor.map(initialize, (first, second)))

    assert _logical_snapshot(first.path) == _logical_snapshot(second.path)
    assert _logical_snapshot(first.path)[0:2] == (APP_ID, USER_VERSION)


def test_initialize_uses_complete_statements_and_rolls_back_partial_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    from ditto_analysis.storage.sqlite.experiments import schema

    original = schema.iter_schema_statements

    def broken(sql: str) -> tuple[str, ...]:
        statements = original(sql)
        return (*statements[:2], "CREATE TABLE broken(", *statements[-2:])

    monkeypatch.setattr(schema, "iter_schema_statements", broken)
    database = api.ResearchExperimentDatabase(tmp_path)

    with pytest.raises(api.ExperimentSchemaError):
        database.initialize()

    assert _logical_snapshot(database.path) == (0, 0, (), {})


@pytest.mark.parametrize(
    ("application_id", "user_version", "setup_sql"),
    [
        (0, 0, "CREATE TABLE foreign_table(value TEXT)"),
        (1234, 1, "CREATE TABLE foreign_table(value TEXT)"),
        (APP_ID, 99, "CREATE TABLE foreign_table(value TEXT)"),
        (APP_ID, 0, ""),
        (0, USER_VERSION, ""),
    ],
)
def test_fail_closed_marker_cases_do_not_mutate_logical_state(
    tmp_path: Path,
    application_id: int,
    user_version: int,
    setup_sql: str,
) -> None:
    api = _api()
    path = tmp_path / "research" / "research.sqlite"
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as connection:
        if setup_sql:
            connection.execute(setup_sql)
        connection.execute(f"PRAGMA application_id={application_id}")
        connection.execute(f"PRAGMA user_version={user_version}")
        connection.commit()
    before = _logical_snapshot(path)

    with pytest.raises(api.ExperimentSchemaError):
        api.ResearchExperimentDatabase(tmp_path).initialize()

    assert _logical_snapshot(path) == before


def test_current_marker_with_schema_drift_fails_closed(tmp_path: Path) -> None:
    api = _api()
    database = api.ResearchExperimentDatabase(tmp_path)
    database.initialize()
    with sqlite3.connect(database.path) as connection:
        connection.execute("DROP INDEX ix_experiment_dispatch_queue")
        connection.commit()
    before = _logical_snapshot(database.path)

    with pytest.raises(api.ExperimentSchemaError) as exc_info:
        api.ResearchExperimentDatabase(tmp_path).initialize()

    assert exc_info.value.details["reason_code"] == "research_schema_drift"
    assert _logical_snapshot(database.path) == before


def test_every_worker_connection_forces_required_pragmas(tmp_path: Path) -> None:
    api = _api()
    database = api.ResearchExperimentDatabase(tmp_path)
    database.initialize()
    barrier = Barrier(8)

    def pragmas(_index: int) -> tuple[int, int]:
        barrier.wait()
        connection = database.get_connection()
        return (
            connection.execute("PRAGMA foreign_keys").fetchone()[0],
            connection.execute("PRAGMA recursive_triggers").fetchone()[0],
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = tuple(executor.map(pragmas, range(8)))

    assert results == ((1, 1),) * 8


def test_sqlite_path_is_ignored_and_metadata_is_byte_for_byte_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = _api()
    metadata_path = _create_metadata_sentinel(tmp_path)
    before = _metadata_snapshot(tmp_path)
    override = tmp_path / "wrong" / "metadata-override.sqlite"
    monkeypatch.setenv("SQLITE_PATH", os.fspath(override))

    database = api.ResearchExperimentDatabase(tmp_path)
    database.initialize()
    database.initialize()

    assert database.path == tmp_path / "research" / "research.sqlite"
    assert not override.exists()
    assert _metadata_snapshot(tmp_path) == before
    with sqlite3.connect(metadata_path) as metadata:
        task7_tables = metadata.execute(
            """
            SELECT name FROM sqlite_schema
            WHERE type='table' AND name LIKE 'experiment%'
            """
        ).fetchall()
        assert task7_tables == []
    with database.connection() as research:
        assert (
            research.execute(
                "SELECT name FROM sqlite_schema WHERE name='sentinel'"
            ).fetchone()
            is None
        )
        database_list = research.execute("PRAGMA database_list").fetchall()
        assert [(row[1], Path(row[2])) for row in database_list] == [
            ("main", database.path)
        ]


def test_close_all_closes_worker_connections_and_prevents_resurrection(
    tmp_path: Path,
) -> None:
    api = _api()
    database = api.ResearchExperimentDatabase(tmp_path)
    database.initialize()
    connection_ready = Event()
    close_finished = Event()

    def worker() -> str:
        connection = database.get_connection()
        connection_ready.set()
        assert close_finished.wait(timeout=5)
        with pytest.raises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")
        return "closed"

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(worker)
        assert connection_ready.wait(timeout=5)
        database.close_all()
        close_finished.set()
        assert future.result() == "closed"

    with pytest.raises(api.ExperimentDatabaseClosedError):
        database.get_connection()
