"""Dedicated trading recovery-unit composition contract."""

from __future__ import annotations

from pathlib import Path

from ditto_apps.registry.container import make_app_container
from ditto_execution.di import ExecutionDatabase, ExecutionSQLiteClient
from ditto_platform.foundation import SQLiteClient


def test_app_container_binds_execution_database_to_trading_store(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DITTO_DATA_ROOT", str(tmp_path))

    with make_app_container() as container:
        database = container.get(ExecutionDatabase)
        location = (
            database.pool.get_connection().execute("PRAGMA database_list").fetchone()[2]
        )

    assert Path(location).resolve() == (tmp_path / "trading/trading.sqlite").resolve()


def test_app_container_honors_explicit_trading_sqlite_override(
    monkeypatch,
    tmp_path: Path,
) -> None:
    override = tmp_path / "acceptance" / "q4-account-acceptance.sqlite3"
    monkeypatch.setenv("DITTO_DATA_ROOT", str(tmp_path / "default-data"))
    monkeypatch.setenv("DITTO_TRADING_SQLITE_PATH", str(override))

    with make_app_container() as container:
        database = container.get(ExecutionDatabase)
        location = (
            database.pool.get_connection().execute("PRAGMA database_list").fetchone()[2]
        )

    assert Path(location).resolve() == override.resolve()


def test_app_container_keeps_data_and_execution_sqlite_clients_distinct(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DITTO_DATA_ROOT", str(tmp_path))

    with make_app_container() as container:
        data_client = container.get(SQLiteClient)
        execution_client = container.get(ExecutionSQLiteClient)
        data_location = data_client.conn.execute("PRAGMA database_list").fetchone()[2]
        execution_location = execution_client.conn.execute(
            "PRAGMA database_list"
        ).fetchone()[2]

    assert (
        Path(data_location).resolve()
        == (tmp_path / "metadata/metadata.sqlite").resolve()
    )
    assert (
        Path(execution_location).resolve()
        == (tmp_path / "trading/trading.sqlite").resolve()
    )
