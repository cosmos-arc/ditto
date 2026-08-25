"""Unit tests for source fallback policy application contracts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from ditto_application.commands.source_fallback_policy import (
    ActivateCatalogSourceFallbackPolicyHandler,
    ApproveCatalogSourceFallbackPolicyHandler,
    CatalogSourceFallbackPolicyDraftCommand,
    CatalogSourceFallbackPolicyLifecycleCommand,
    DraftCatalogSourceFallbackPolicyHandler,
    RetireCatalogSourceFallbackPolicyHandler,
)
from ditto_application.exceptions import AppCommandError, AppQueryError
from ditto_application.queries.source_fallback_policy_state import (
    CatalogSourceFallbackPolicyQueryFacade,
)
from ditto_application.source_fallback_policy_state import (
    CatalogSourceFallbackPolicy as AppCatalogSourceFallbackPolicy,
)
from ditto_application.source_fallback_policy_state import (
    CatalogSourceFallbackPolicyEvent as AppCatalogSourceFallbackPolicyEvent,
)
from ditto_application.source_fallback_policy_state import (
    to_catalog_source_fallback_policy,
)
from ditto_data.catalog.fallback_policy import (
    CatalogSourceFallbackPolicy as DataCatalogSourceFallbackPolicy,
)
from ditto_data.catalog.fallback_policy import (
    CatalogSourceFallbackPolicyEvent as DataCatalogSourceFallbackPolicyEvent,
)


class _PolicyStore:
    def __init__(
        self,
        policies: dict[str, DataCatalogSourceFallbackPolicy] | None = None,
    ) -> None:
        self.policies = policies or {}
        self.events: list[DataCatalogSourceFallbackPolicyEvent] = []

    def upsert_source_fallback_policy(
        self,
        policy: DataCatalogSourceFallbackPolicy,
    ) -> None:
        self.policies[policy.policy_id] = policy

    def append_source_fallback_policy_event(
        self,
        event: DataCatalogSourceFallbackPolicyEvent,
    ) -> None:
        self.events.append(event)

    def get_source_fallback_policy(
        self,
        policy_id: str,
    ) -> DataCatalogSourceFallbackPolicy | None:
        return self.policies.get(policy_id)

    def list_source_fallback_policies(
        self,
        *,
        dataset_id: str | None = None,
        status: str | None = None,
    ) -> tuple[DataCatalogSourceFallbackPolicy, ...]:
        policies = tuple(self.policies.values())
        if dataset_id is not None:
            policies = tuple(item for item in policies if item.dataset_id == dataset_id)
        if status is not None:
            policies = tuple(item for item in policies if item.status == status)
        return tuple(sorted(policies, key=lambda item: item.created_at))

    def list_source_fallback_policy_events(
        self,
        policy_id: str,
    ) -> tuple[DataCatalogSourceFallbackPolicyEvent, ...]:
        return tuple(event for event in self.events if event.policy_id == policy_id)


def _now() -> datetime:
    return datetime(2026, 6, 10, 9, 0, tzinfo=UTC)


def _data_policy(
    policy_id: str = "fallback-policy-001",
    *,
    status: str = "draft",
) -> DataCatalogSourceFallbackPolicy:
    return DataCatalogSourceFallbackPolicy(
        policy_id=policy_id,
        dataset_id="stock_daily",
        namespace="market",
        trade_date="2026-06-01",
        default_source="tushare",
        selected_source="fred",
        recommended_source="fred",
        status=status,
        created_by="architecture-review",
        created_at=_now(),
        recommended_actions=("review_source_failover",),
        reason_codes=("default_source_stale",),
        fallback_sources=("fred",),
        unsupported_sources=("tdx",),
        source_selection_status="ready",
        source_selection_blockers=(),
        approval_required=True,
        execution_allowed=True,
        notes="persist dry-run fallback decision",
    )


def _app_policy(
    policy_id: str = "fallback-policy-001",
    *,
    status: str = "draft",
) -> AppCatalogSourceFallbackPolicy:
    return AppCatalogSourceFallbackPolicy(
        policy_id=policy_id,
        dataset_id="stock_daily",
        namespace="market",
        trade_date="2026-06-01",
        default_source="tushare",
        selected_source="fred",
        recommended_source="fred",
        status=status,
        created_by="architecture-review",
        created_at=_now(),
        recommended_actions=("review_source_failover",),
        reason_codes=("default_source_stale",),
        fallback_sources=("fred",),
        unsupported_sources=("tdx",),
        source_selection_status="ready",
        source_selection_blockers=(),
        approval_required=True,
        execution_allowed=True,
        notes="persist dry-run fallback decision",
    )


class TestDraftCatalogSourceFallbackPolicyHandler:
    """Draft handler persists policy state without activating automation."""

    def test_creates_draft_policy_and_audit_event(self) -> None:
        store = _PolicyStore()
        handler = DraftCatalogSourceFallbackPolicyHandler(
            policy_writer=store,
            now=_now,
            policy_id_factory=lambda: "fallback-policy-001",
        )

        result = handler.handle(
            CatalogSourceFallbackPolicyDraftCommand(
                dataset_id="stock_daily",
                namespace="market",
                trade_date="2026-06-01",
                default_source="tushare",
                selected_source="fred",
                recommended_source="fred",
                created_by="architecture-review",
                recommended_actions=("review_source_failover",),
                reason_codes=("default_source_stale",),
                fallback_sources=("fred",),
                unsupported_sources=("tdx",),
                source_selection_status="ready",
                source_selection_blockers=(),
                approval_required=True,
                execution_allowed=True,
                notes="persist dry-run fallback decision",
            )
        )

        assert result.policy == _app_policy()
        assert store.policies == {"fallback-policy-001": _data_policy()}
        assert store.events == [
            DataCatalogSourceFallbackPolicyEvent(
                policy_id="fallback-policy-001",
                action="drafted",
                actor="architecture-review",
                action_at=_now(),
                status="draft",
                notes="persist dry-run fallback decision",
            )
        ]
        assert len(result.policy.authority_hash) == 64
        assert result.policy.authority_payload["action"] == "approval"
        assert result.policy.authority_payload["selected_source"] == "fred"


class TestCatalogSourceFallbackPolicyLifecycleHandlers:
    """Lifecycle handlers transition policy state without source mutation."""

    def test_approve_draft_policy_appends_audit_event(self) -> None:
        store = _PolicyStore({"fallback-policy-001": _data_policy()})
        handler = ApproveCatalogSourceFallbackPolicyHandler(
            policy_reader=store,
            policy_writer=store,
            now=lambda: datetime(2026, 6, 10, 9, 5, tzinfo=UTC),
        )

        result = handler.handle(
            CatalogSourceFallbackPolicyLifecycleCommand(
                policy_id="fallback-policy-001",
                expected_authority_hash=to_catalog_source_fallback_policy(
                    store.policies["fallback-policy-001"]
                ).authority_hash,
                actor="lead-reviewer",
                notes="approved for controlled fallback activation",
            )
        )

        approved = replace(
            _data_policy(),
            status="approved",
            decided_by="lead-reviewer",
            decided_at=datetime(2026, 6, 10, 9, 5, tzinfo=UTC),
            decision_notes="approved for controlled fallback activation",
        )
        assert result.policy == replace(
            _app_policy(),
            status="approved",
            decided_by="lead-reviewer",
            decided_at=datetime(2026, 6, 10, 9, 5, tzinfo=UTC),
            decision_notes="approved for controlled fallback activation",
        )
        assert store.policies == {"fallback-policy-001": approved}
        assert store.events == [
            DataCatalogSourceFallbackPolicyEvent(
                policy_id="fallback-policy-001",
                action="approved",
                actor="lead-reviewer",
                action_at=datetime(2026, 6, 10, 9, 5, tzinfo=UTC),
                status="approved",
                notes="approved for controlled fallback activation",
            )
        ]

    def test_activate_approved_policy_without_mutating_source_metadata(self) -> None:
        approved = replace(
            _data_policy(status="approved"),
            decided_by="lead-reviewer",
            decided_at=datetime(2026, 6, 10, 9, 5, tzinfo=UTC),
            decision_notes="approved for controlled fallback activation",
        )
        store = _PolicyStore({"fallback-policy-001": approved})
        handler = ActivateCatalogSourceFallbackPolicyHandler(
            policy_reader=store,
            policy_writer=store,
            now=lambda: datetime(2026, 6, 10, 9, 10, tzinfo=UTC),
        )

        result = handler.handle(
            CatalogSourceFallbackPolicyLifecycleCommand(
                policy_id="fallback-policy-001",
                expected_authority_hash=to_catalog_source_fallback_policy(
                    store.policies["fallback-policy-001"]
                ).authority_hash,
                actor="ops-runner",
                notes="activate policy resource only",
            )
        )

        active = replace(approved, status="active")
        assert result.policy == replace(
            _app_policy(status="approved"),
            status="active",
            decided_by="lead-reviewer",
            decided_at=datetime(2026, 6, 10, 9, 5, tzinfo=UTC),
            decision_notes="approved for controlled fallback activation",
        )
        assert store.policies["fallback-policy-001"] == active
        assert store.policies["fallback-policy-001"].default_source == "tushare"
        assert store.policies["fallback-policy-001"].selected_source == "fred"
        assert store.events == [
            DataCatalogSourceFallbackPolicyEvent(
                policy_id="fallback-policy-001",
                action="activated",
                actor="ops-runner",
                action_at=datetime(2026, 6, 10, 9, 10, tzinfo=UTC),
                status="active",
                notes="activate policy resource only",
            )
        ]

    def test_retire_active_policy_appends_audit_event(self) -> None:
        active = replace(_data_policy(status="active"), decided_by="lead-reviewer")
        store = _PolicyStore({"fallback-policy-001": active})
        handler = RetireCatalogSourceFallbackPolicyHandler(
            policy_reader=store,
            policy_writer=store,
            now=lambda: datetime(2026, 6, 10, 9, 15, tzinfo=UTC),
        )

        result = handler.handle(
            CatalogSourceFallbackPolicyLifecycleCommand(
                policy_id="fallback-policy-001",
                expected_authority_hash=to_catalog_source_fallback_policy(
                    store.policies["fallback-policy-001"]
                ).authority_hash,
                actor="ops-runner",
                notes="retire policy after review",
            )
        )

        retired = replace(active, status="retired")
        assert result.policy == replace(
            _app_policy(status="active"),
            status="retired",
            decided_by="lead-reviewer",
        )
        assert store.policies == {"fallback-policy-001": retired}
        assert store.events == [
            DataCatalogSourceFallbackPolicyEvent(
                policy_id="fallback-policy-001",
                action="retired",
                actor="ops-runner",
                action_at=datetime(2026, 6, 10, 9, 15, tzinfo=UTC),
                status="retired",
                notes="retire policy after review",
            )
        ]

    def test_rejects_invalid_lifecycle_transition_without_audit_event(self) -> None:
        store = _PolicyStore({"fallback-policy-001": _data_policy()})
        handler = ActivateCatalogSourceFallbackPolicyHandler(
            policy_reader=store,
            policy_writer=store,
            now=lambda: datetime(2026, 6, 10, 9, 10, tzinfo=UTC),
        )

        with pytest.raises(
            AppCommandError,
            match="Source fallback policy is not approved",
        ):
            handler.handle(
                CatalogSourceFallbackPolicyLifecycleCommand(
                    policy_id="fallback-policy-001",
                    expected_authority_hash=to_catalog_source_fallback_policy(
                        store.policies["fallback-policy-001"]
                    ).authority_hash,
                    actor="ops-runner",
                )
            )

        assert store.policies == {"fallback-policy-001": _data_policy()}
        assert store.events == []

    def test_rejects_lifecycle_transition_for_a_different_exact_hash(self) -> None:
        store = _PolicyStore({"fallback-policy-001": _data_policy()})
        handler = ApproveCatalogSourceFallbackPolicyHandler(
            policy_reader=store,
            policy_writer=store,
            now=lambda: datetime(2026, 6, 10, 9, 5, tzinfo=UTC),
        )

        with pytest.raises(AppCommandError, match="authority hash mismatch"):
            handler.handle(
                CatalogSourceFallbackPolicyLifecycleCommand(
                    policy_id="fallback-policy-001",
                    expected_authority_hash="0" * 64,
                    actor="lead-reviewer",
                )
            )

        assert store.policies == {"fallback-policy-001": _data_policy()}
        assert store.events == []


class TestCatalogSourceFallbackPolicyQueryFacade:
    """Query facade exposes current source fallback policy state."""

    def test_lists_policies_and_audit_events(self) -> None:
        event = DataCatalogSourceFallbackPolicyEvent(
            policy_id="fallback-policy-001",
            action="drafted",
            actor="architecture-review",
            action_at=_now(),
            status="draft",
            notes="persist dry-run fallback decision",
        )
        store = _PolicyStore({"fallback-policy-001": _data_policy()})
        store.events.append(event)
        facade = CatalogSourceFallbackPolicyQueryFacade(policy_reader=store)

        assert facade.get_source_fallback_policy("fallback-policy-001") == _app_policy()
        assert facade.list_source_fallback_policies(dataset_id="stock_daily") == (
            _app_policy(),
        )
        assert facade.list_source_fallback_policies(status="draft") == (_app_policy(),)
        assert facade.list_source_fallback_policy_events("fallback-policy-001") == (
            AppCatalogSourceFallbackPolicyEvent(
                policy_id="fallback-policy-001",
                action="drafted",
                actor="architecture-review",
                action_at=_now(),
                status="draft",
                notes="persist dry-run fallback decision",
            ),
        )

    def test_get_raises_when_policy_is_missing(self) -> None:
        facade = CatalogSourceFallbackPolicyQueryFacade(policy_reader=_PolicyStore())

        with pytest.raises(
            AppQueryError,
            match="Catalog source fallback policy not found",
        ):
            facade.get_source_fallback_policy("missing-policy")
