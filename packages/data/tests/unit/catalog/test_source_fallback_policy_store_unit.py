"""Unit tests for persistent catalog source fallback policy state."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from ditto_data.catalog.fallback_policy import (
    CatalogSourceFallbackPolicy,
    CatalogSourceFallbackPolicyEvent,
    CatalogSourceFallbackPolicyReader,
    CatalogSourceFallbackPolicyWriter,
)
from ditto_data.catalog.fallback_policy_store import (
    SQLiteCatalogSourceFallbackPolicyStore,
)
from ditto_platform.foundation import SQLiteClient, SQLitePool


def _client(db_path: Path) -> tuple[SQLiteClient, SQLitePool]:
    pool = SQLitePool(str(db_path))
    return SQLiteClient(pool), pool


def _policy(
    policy_id: str = "fallback-policy-001",
    *,
    status: str = "draft",
) -> CatalogSourceFallbackPolicy:
    return CatalogSourceFallbackPolicy(
        policy_id=policy_id,
        dataset_id="stock_daily",
        namespace="market",
        trade_date="2026-06-01",
        default_source="tushare",
        selected_source="fred",
        recommended_source="fred",
        status=status,
        created_by="architecture-review",
        created_at=datetime(2026, 6, 10, 9, 0, tzinfo=UTC),
        recommended_actions=(
            "review_source_failover",
            "repair_catalog_source_coverage",
        ),
        reason_codes=("selected_source_stale",),
        fallback_sources=("fred",),
        unsupported_sources=("tdx",),
        source_selection_status="ready",
        source_selection_blockers=(),
        approval_required=True,
        execution_allowed=True,
        notes="persist dry-run fallback decision before any automation",
    )


class TestSQLiteCatalogSourceFallbackPolicyStore:
    """Fallback policy state must be durable and auditable."""

    def test_policy_state_survives_reopened_sqlite_connection(
        self,
        tmp_path: Path,
    ) -> None:
        db_path = tmp_path / "catalog.sqlite"
        policy = _policy()
        drafted = CatalogSourceFallbackPolicyEvent(
            policy_id="fallback-policy-001",
            action="drafted",
            actor="architecture-review",
            action_at=datetime(2026, 6, 10, 9, 0, tzinfo=UTC),
            status="draft",
            notes="persist dry-run fallback decision before any automation",
        )

        writer_client, writer_pool = _client(db_path)
        try:
            writer = SQLiteCatalogSourceFallbackPolicyStore(writer_client)
            writer.upsert_source_fallback_policy(policy)
            writer.append_source_fallback_policy_event(drafted)
        finally:
            writer_pool.close()

        reader_client, reader_pool = _client(db_path)
        try:
            reader = SQLiteCatalogSourceFallbackPolicyStore(reader_client)

            assert reader.get_source_fallback_policy("fallback-policy-001") == policy
            assert reader.list_source_fallback_policies(dataset_id="stock_daily") == (
                policy,
            )
            assert reader.list_source_fallback_policies(status="draft") == (policy,)
            assert reader.list_source_fallback_policy_events("fallback-policy-001") == (
                drafted,
            )
        finally:
            reader_pool.close()

    def test_policy_status_update_preserves_audit_order(
        self,
        tmp_path: Path,
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        store = SQLiteCatalogSourceFallbackPolicyStore(client)
        policy = _policy()
        approved = replace(
            policy,
            status="approved",
            decided_by="lead-reviewer",
            decided_at=datetime(2026, 6, 10, 9, 5, tzinfo=UTC),
            decision_notes="fallback policy is approved for activation",
        )
        drafted = CatalogSourceFallbackPolicyEvent(
            policy_id="fallback-policy-001",
            action="drafted",
            actor="architecture-review",
            action_at=datetime(2026, 6, 10, 9, 0, tzinfo=UTC),
            status="draft",
        )
        approved_event = CatalogSourceFallbackPolicyEvent(
            policy_id="fallback-policy-001",
            action="approved",
            actor="lead-reviewer",
            action_at=datetime(2026, 6, 10, 9, 5, tzinfo=UTC),
            status="approved",
            notes="fallback policy is approved for activation",
        )

        try:
            store.upsert_source_fallback_policy(policy)
            store.append_source_fallback_policy_event(drafted)
            store.upsert_source_fallback_policy(approved)
            store.append_source_fallback_policy_event(approved_event)

            assert store.get_source_fallback_policy("fallback-policy-001") == approved
            assert store.list_source_fallback_policies(status="draft") == ()
            assert store.list_source_fallback_policies(status="approved") == (approved,)
            assert store.list_source_fallback_policy_events("fallback-policy-001") == (
                drafted,
                approved_event,
            )
        finally:
            pool.close()

    def test_satisfies_source_fallback_policy_reader_and_writer_protocols(
        self,
        tmp_path: Path,
    ) -> None:
        client, pool = _client(tmp_path / "catalog.sqlite")
        try:
            store = SQLiteCatalogSourceFallbackPolicyStore(client)

            assert isinstance(store, CatalogSourceFallbackPolicyReader)
            assert isinstance(store, CatalogSourceFallbackPolicyWriter)
        finally:
            pool.close()
