"""OPS-03 isolated workstation backup and restore integration tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from ditto_agent.contracts.runtime import AgentManifest, ModelProfile, RetentionClass
from ditto_agent.runtime.service import (
    AgentRunCancelCommand,
    AgentRunCreateCommand,
    AgentSessionCreateCommand,
)
from ditto_application.commands.paper_account import (
    CreatePaperAccountCommand,
    CreatePaperAccountHandler,
)
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_apps.operations.workstation_backup import (
    WORKSTATION_DATABASES,
    WorkstationBackupError,
    backup_workstation,
    restore_workstation,
    verify_workstation_backup,
)
from ditto_apps.registry.agent.database_provider import build_agent_database
from ditto_apps.registry.agent.runtime import (
    PersistedAgentRuntime,
    PersistedAgentRuntimeOptions,
)
from ditto_apps.registry.fresh_runtime import create_fresh_runtime
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_platform.foundation import SQLiteClient, SQLitePool
from ditto_platform.foundation.storage.sqlite_backup import inspect_database

pytestmark = [pytest.mark.integration, pytest.mark.serial]


_NOW = datetime(2026, 8, 31, 7, tzinfo=UTC)


@contextmanager
def _services(
    root: Path,
) -> Iterator[tuple[SqliteAccountEventJournal, PersistedAgentRuntime]]:
    pool = SQLitePool(str(root / "trading/trading.sqlite"))
    agent = build_agent_database(root)
    try:
        manifest = AgentManifest(
            manifest_id="recovery-test",
            agent_version="r5",
            prompt_version="v1",
            prompt_hash="a" * 64,
            tool_schema_version="v1",
            tool_schema_hash="b" * 64,
            model_profile=ModelProfile.BALANCED,
            model_snapshot="offline",
        )
        agent.writer.put_manifest(manifest)
        yield (
            SqliteAccountEventJournal(SQLiteClient(pool)),
            PersistedAgentRuntime(
                reader=agent.reader,
                writer=agent.writer,
                manifest=manifest,
                clock=lambda: _NOW,
                options=PersistedAgentRuntimeOptions(
                    presentation_reader=agent.presentation_reader,
                    presentation_writer=agent.presentation_writer,
                    presentation_projector=agent.presentation_projector,
                ),
            ),
        )
    finally:
        agent.close()
        pool.close_all()


def test_backup_and_restore_all_four_domains_into_an_isolated_root(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    backup = tmp_path / "backup"
    restored = tmp_path / "restored"
    create_fresh_runtime(source)
    with _services(source) as (journal, runtime):
        CreatePaperAccountHandler(journal=journal, clock=lambda: _NOW).handle(
            CreatePaperAccountCommand(
                account_id="recovery-paper",
                name="Recovery Paper",
                opened_at=_NOW,
                trade_date="2026-08-31",
                initial_cash=Decimal("150000"),
                idempotency_key="recovery-paper-open",
            )
        )
        ledger = AccountLedgerQuery(journal=journal).get(
            account_id="recovery-paper", as_of="2026-08-31"
        )
        assert ledger.snapshot.cash.available == Decimal("150000")
        assert len(ledger.events) == 1
        session = runtime.create_session(
            AgentSessionCreateCommand(
                retention_class=RetentionClass.STANDARD,
                idempotency_key="recovery-session",
            )
        )
        queued = runtime.create_run(
            AgentRunCreateCommand(
                session_id=session.session_id,
                objective="Read recovery evidence",
                authority_hash="c" * 64,
                max_model_tokens=1024,
                max_model_spend_usd=Decimal("0.25"),
                model_profile=ModelProfile.BALANCED,
                idempotency_key="recovery-run",
            )
        )
        run = runtime.cancel_run(
            AgentRunCancelCommand(
                run_id=queued.run_id, expected_revision=queued.revision
            )
        )
        events = runtime.list_run_events(run.run_id)
        assert len(events) >= 2
        cursor = events[0].event_id
        remaining = runtime.list_run_events(run.run_id, after_event_id=cursor)
        assert remaining
    # All source writers are closed before the sequential multi-database snapshot.
    manifest = backup_workstation(source, backup)
    verified = verify_workstation_backup(backup)
    restored_manifest = restore_workstation(backup, restored)

    assert manifest == verified == restored_manifest
    assert {item.domain for item in manifest.databases} == {
        "data",
        "research",
        "trading",
        "agent",
    }
    assert tuple(item.relative_path for item in manifest.databases) == tuple(
        spec.relative_path for spec in WORKSTATION_DATABASES
    )
    assert (backup / "manifest.json").is_file()
    with _services(restored) as (journal, runtime):
        assert (
            AccountLedgerQuery(journal=journal).get(
                account_id="recovery-paper", as_of="2026-08-31"
            )
            == ledger
        )
        assert runtime.get_run(run.run_id) == run
        assert runtime.list_run_events(run.run_id) == events
        assert runtime.list_run_events(run.run_id, after_event_id=cursor) == remaining
        assert (
            runtime.list_run_events(run.run_id, after_event_id=events[-1].event_id)
            == ()
        )
        assert runtime.list_sessions(limit=10, offset=0).items == (session,)
        # Repeated reads cannot duplicate the ledger or terminal run events.
        assert (
            AccountLedgerQuery(journal=journal).get(
                account_id="recovery-paper", as_of="2026-08-31"
            )
            == ledger
        )
        assert runtime.list_run_events(run.run_id) == events
    for item in manifest.databases:
        restored_report = inspect_database(restored / item.relative_path)
        assert restored_report.integrity_check == "ok"
        assert restored_report.table_row_counts == item.table_row_counts


def test_restore_rejects_a_tampered_database_and_leaves_no_partial_root(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    backup = tmp_path / "backup"
    restored = tmp_path / "restored"
    create_fresh_runtime(source)
    backup_workstation(source, backup)
    target = backup / WORKSTATION_DATABASES[0].relative_path
    target.write_bytes(target.read_bytes() + b"tampered")

    with pytest.raises(WorkstationBackupError, match="verification failed"):
        restore_workstation(backup, restored)

    assert not restored.exists()


def test_backup_and_restore_refuse_overlapping_or_existing_targets(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    create_fresh_runtime(source)

    with pytest.raises(WorkstationBackupError, match="must not overlap"):
        backup_workstation(source, source / "backup")

    backup = tmp_path / "backup"
    backup_workstation(source, backup)
    destination = tmp_path / "existing"
    destination.mkdir()
    with pytest.raises(WorkstationBackupError, match="already exists"):
        restore_workstation(backup, destination)
