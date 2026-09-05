"""Greenfield runtime bootstrap integration contract."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from ditto_apps.registry.fresh_runtime import (
    FreshRuntimeNotEmptyError,
    create_fresh_runtime,
)

pytestmark = [pytest.mark.integration, pytest.mark.serial]


def _marker(path: Path) -> tuple[int, int]:
    with sqlite3.connect(path) as connection:
        return (
            int(connection.execute("PRAGMA application_id").fetchone()[0]),
            int(connection.execute("PRAGMA user_version").fetchone()[0]),
        )


def test_fresh_runtime_creates_all_isolated_current_schemas(tmp_path: Path) -> None:
    data_root = tmp_path / "fresh-runtime"

    manifest = create_fresh_runtime(data_root)

    assert manifest.data_root == data_root.resolve()
    assert manifest.schema_version == 1
    assert {item.relative_path for item in manifest.schemas} == {
        "metadata/metadata.sqlite",
        "research/research.sqlite",
        "trading/trading.sqlite",
        "agent/agent.sqlite",
        "agent/agent-presentation.sqlite3",
        "agent-shadow/decision-opinion.sqlite",
    }
    assert _marker(data_root / "research" / "research.sqlite")[1] == 2
    assert _marker(data_root / "agent" / "agent.sqlite")[1] == 1
    assert _marker(data_root / "agent" / "agent-presentation.sqlite3")[1] == 1
    assert _marker(data_root / "agent-shadow" / "decision-opinion.sqlite")[1] == 3
    with sqlite3.connect(data_root / "trading" / "trading.sqlite") as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }
    assert {
        "account_journal_events",
        "execution_audit",
        "trade_intents",
        "paper_sessions",
    } <= tables
    assert (data_root / "features" / "technical" / "price").is_dir()
    assert (data_root / "factors" / "factors_narrow").is_dir()


def test_fresh_runtime_refuses_any_preexisting_payload(tmp_path: Path) -> None:
    data_root = tmp_path / "not-empty"
    data_root.mkdir()
    sentinel = data_root / "user-file.txt"
    sentinel.write_text("preserve me", encoding="utf-8")

    with pytest.raises(FreshRuntimeNotEmptyError):
        create_fresh_runtime(data_root)

    assert sentinel.read_text(encoding="utf-8") == "preserve me"


def test_fresh_runtime_can_enter_and_exit_the_real_app_lifespan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root = tmp_path / "fresh-runtime"
    create_fresh_runtime(data_root)
    monkeypatch.setenv("DITTO_STATE_ROOT", str(data_root))
    monkeypatch.setenv("TUSHARE_TOKEN", "fresh-bootstrap-test-token")

    from ditto_apps.main import lifespan
    from ditto_apps.registry.container import make_async_app_container
    from ditto_platform.foundation import reset_for_testing
    from fastapi import FastAPI

    async def probe() -> None:
        # Model a fresh server process instead of reusing the session fixture's
        # process-global test provider with a different temporary log root.
        reset_for_testing()
        runtime_app = FastAPI()
        runtime_app.state.dishka_container = make_async_app_container()
        async with lifespan(runtime_app):
            assert runtime_app.state.settings is not None

    asyncio.run(probe())
