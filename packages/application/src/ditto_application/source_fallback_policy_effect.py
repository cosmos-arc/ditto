"""Shared source fallback policy effect resolution."""

from __future__ import annotations

from dataclasses import dataclass

from ditto_data.catalog.fallback_policy import (
    CatalogSourceFallbackPolicy,
    CatalogSourceFallbackPolicyReader,
)

from ditto_application.exceptions import AppProcessError

__all__ = [
    "SourceFallbackPolicyEffect",
    "ensure_source_fallback_policy_effect_executable",
    "resolve_active_source_fallback_policy_effect",
    "source_fallback_policy_details",
]


@dataclass(frozen=True, slots=True)
class SourceFallbackPolicyEffect:
    """Resolved active policy effect for one catalog source-selection decision."""

    policy: CatalogSourceFallbackPolicy
    catalog_selected_source: str
    effective_source: str

    @property
    def executable(self) -> bool:
        """Return whether the active policy can be applied by ingestion execution."""
        return self.policy.source_selection_status == "ready" and (
            self.policy.execution_allowed
        )


def resolve_active_source_fallback_policy_effect(
    policy_reader: CatalogSourceFallbackPolicyReader | None,
    *,
    dataset: str,
    trade_date: str,
    catalog_selected_source: str,
) -> SourceFallbackPolicyEffect | None:
    """Return the active source fallback policy effect for an exact dataset/date."""
    policy = _active_source_fallback_policy(
        policy_reader,
        dataset=dataset,
        trade_date=trade_date,
    )
    if policy is None:
        return None
    return SourceFallbackPolicyEffect(
        policy=policy,
        catalog_selected_source=catalog_selected_source.lower(),
        effective_source=_policy_effect_source(policy),
    )


def ensure_source_fallback_policy_effect_executable(
    effect: SourceFallbackPolicyEffect,
) -> str:
    """Return the effective source or fail closed with policy diagnostics."""
    if effect.executable:
        return effect.effective_source
    raise AppProcessError(
        "Active source fallback policy is not executable",
        details={
            "source_selection_status": effect.policy.source_selection_status,
            "execution_allowed": effect.policy.execution_allowed,
            **source_fallback_policy_details(effect),
        },
    )


def source_fallback_policy_details(
    effect: SourceFallbackPolicyEffect | CatalogSourceFallbackPolicy | None,
) -> dict[str, object]:
    """Return stable diagnostics for policy-driven source-selection failures."""
    if effect is None:
        return {}
    policy = effect.policy if isinstance(effect, SourceFallbackPolicyEffect) else effect
    return {
        "source_fallback_policy_id": policy.policy_id,
        "source_fallback_policy_status": policy.status,
    }


def _active_source_fallback_policy(
    policy_reader: CatalogSourceFallbackPolicyReader | None,
    *,
    dataset: str,
    trade_date: str,
) -> CatalogSourceFallbackPolicy | None:
    if policy_reader is None:
        return None
    policies = tuple(
        policy
        for policy in policy_reader.list_source_fallback_policies(
            dataset_id=dataset,
            status="active",
        )
        if policy.trade_date == trade_date
    )
    if not policies:
        return None
    return max(
        policies,
        key=lambda policy: (
            policy.decided_at or policy.created_at,
            policy.created_at,
            policy.policy_id,
        ),
    )


def _policy_effect_source(policy: CatalogSourceFallbackPolicy) -> str:
    source = policy.recommended_source or policy.selected_source
    return source.lower()
