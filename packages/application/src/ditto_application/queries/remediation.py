"""Catalog remediation backlog query facade."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ditto_application.exceptions import AppQueryError
from ditto_application.queries._remediation_evidence import (
    evidence_requirements_for_item as _evidence_requirements_for_item,
)
from ditto_application.queries.catalog import (
    CatalogQueryFacade,
    CatalogSourceHealthAttentionItem,
    CatalogSourceHealthSummaryReport,
)
from ditto_application.queries.ingestion_status import (
    DatasetMaturityGovernanceAttentionItem,
    DatasetMaturityGovernanceReport,
    IngestionStatusQueryFacade,
)
from ditto_application.queries.lineage import (
    DataLineageCatalogRunReport,
    LineageQueryFacade,
)
from ditto_application.queries.remediation_models import (
    CatalogRemediationApprovalIntent,
    CatalogRemediationBacklogReport,
    CatalogRemediationEvidenceRequirement,
    CatalogRemediationItem,
    CatalogRemediationItemDetail,
    CatalogRemediationReasonCount,
    CatalogRemediationSeverity,
    CatalogRemediationSeverityCount,
    CatalogRemediationSource,
    CatalogRemediationSourceCount,
    CatalogRemediationSourceFallbackPolicyEffectCount,
)

__all__ = [
    "CatalogRemediationApprovalIntent",
    "CatalogRemediationBacklogReport",
    "CatalogRemediationEvidenceRequirement",
    "CatalogRemediationItem",
    "CatalogRemediationItemDetail",
    "CatalogRemediationQueryFacade",
    "CatalogRemediationReasonCount",
    "CatalogRemediationSeverity",
    "CatalogRemediationSeverityCount",
    "CatalogRemediationSource",
    "CatalogRemediationSourceCount",
    "CatalogRemediationSourceFallbackPolicyEffectCount",
]

_ACTIONS_BY_REASON: dict[
    tuple[CatalogRemediationSource, str],
    tuple[str, ...],
] = {
    ("source_health", "selected_source_missing"): ("repair_catalog_source_coverage",),
    ("source_health", "selected_source_stale"): ("repair_catalog_source_coverage",),
    ("source_health", "selected_source_not_applicable"): (
        "repair_catalog_source_coverage",
    ),
    ("source_health", "default_source_failover"): ("review_source_failover",),
    ("source_health", "no_fallback_source"): ("configure_fallback_source",),
    ("source_health", "unsupported_sources_present"): ("review_source_request",),
    ("source_health", "latest_maturity_promotion_revoked"): (
        "review_maturity_promotion_revocation",
    ),
    ("maturity_governance", "maturity_warning"): ("review_dataset_maturity",),
    ("maturity_governance", "catalog_missing"): ("repair_catalog_freshness",),
    ("maturity_governance", "catalog_stale"): ("repair_catalog_freshness",),
    ("maturity_governance", "promotion_ready"): ("approve_maturity_promotion",),
    ("maturity_governance", "promotion_blocked"): ("submit_or_fix_promotion_evidence",),
    ("maturity_governance", "promotion_revoked"): (
        "review_maturity_promotion_revocation",
    ),
    ("lineage_catalog", "catalog_missing"): ("repair_lineage_catalog_asset",),
    ("lineage_catalog", "catalog_not_configured"): ("repair_lineage_catalog_asset",),
    ("lineage_catalog", "catalog_stale"): ("repair_lineage_catalog_asset",),
}

_MANUAL_ACTION_REQUIRED_INPUTS: dict[str, tuple[str, ...]] = {
    "approve_maturity_promotion": ("approved_by", "approval_notes"),
    "configure_fallback_source": ("fallback_source", "reviewed_by"),
    "review_dataset_maturity": ("reviewed_by", "decision_notes"),
    "review_maturity_promotion_revocation": ("reviewed_by", "decision_notes"),
    "review_source_failover": ("reviewed_by", "decision_notes"),
    "review_source_request": ("reviewed_by", "decision_notes"),
}

_MANUAL_ACTION_NOTES: dict[str, str] = {
    "approve_maturity_promotion": "Manual governance intent; no executor.",
    "configure_fallback_source": "Manual source configuration intent only.",
    "review_dataset_maturity": "Manual maturity governance review intent only.",
    "review_maturity_promotion_revocation": "Manual revocation review intent only.",
    "review_source_failover": "Manual source failover review intent only.",
    "review_source_request": "Manual source request review intent only.",
}


@dataclass(frozen=True, slots=True)
class _CatalogRemediationReportContext:
    dataset_ids: tuple[str, ...]
    trade_dates: tuple[str, ...]
    available_sources: tuple[str, ...]
    source_health: CatalogSourceHealthSummaryReport
    maturity: DatasetMaturityGovernanceReport
    lineage_report: DataLineageCatalogRunReport | None


class CatalogRemediationQueryFacade:
    """Compose existing backend governance reports into remediation backlog."""

    def __init__(
        self,
        *,
        catalog_facade: CatalogQueryFacade,
        ingestion_status_facade: IngestionStatusQueryFacade,
        lineage_facade: LineageQueryFacade | None = None,
        generated_at: Callable[[], datetime] | None = None,
    ) -> None:
        self._catalog_facade = catalog_facade
        self._ingestion_status_facade = ingestion_status_facade
        self._lineage_facade = lineage_facade
        self._generated_at = generated_at or _utcnow

    def get_remediation_backlog(
        self,
        *,
        dataset_ids: tuple[str, ...],
        trade_dates: tuple[str, ...],
        available_sources: tuple[str, ...],
        run_id: str | None = None,
    ) -> CatalogRemediationBacklogReport:
        """Return one backend-owned remediation backlog for governance reports."""
        context = self._build_report_context(
            dataset_ids=dataset_ids,
            trade_dates=trade_dates,
            available_sources=available_sources,
            run_id=run_id,
        )
        items = _items_from_context(context)
        return CatalogRemediationBacklogReport(
            generated_at=self._generated_at(),
            dataset_ids=context.dataset_ids,
            trade_dates=context.trade_dates,
            available_sources=context.available_sources,
            run_id=run_id,
            total_items=len(items),
            severity_counts=_severity_counts(items),
            source_counts=_source_counts(items),
            reason_counts=_reason_counts(items),
            items=items,
            source_fallback_policy_effect_counts=(
                _source_fallback_policy_effect_counts(items)
            ),
        )

    def get_remediation_item_detail(
        self,
        *,
        item_id: str,
        dataset_ids: tuple[str, ...],
        trade_dates: tuple[str, ...],
        available_sources: tuple[str, ...],
        run_id: str | None = None,
    ) -> CatalogRemediationItemDetail:
        """Return detail and approval-intent contract for one backlog item."""
        context = self._build_report_context(
            dataset_ids=dataset_ids,
            trade_dates=trade_dates,
            available_sources=available_sources,
            run_id=run_id,
        )
        item = _find_item(_items_from_context(context), item_id)
        evidence_requirements = _evidence_requirements_for_item(item, context.maturity)
        return CatalogRemediationItemDetail(
            generated_at=self._generated_at(),
            item=item,
            summary=_item_summary(item),
            evidence_requirements=evidence_requirements,
            approval_intents=_approval_intents_for_item(
                item,
                evidence_requirements,
            ),
        )

    def _build_report_context(
        self,
        *,
        dataset_ids: tuple[str, ...],
        trade_dates: tuple[str, ...],
        available_sources: tuple[str, ...],
        run_id: str | None,
    ) -> _CatalogRemediationReportContext:
        normalized_dataset_ids = _dedupe_tuple(dataset_ids)
        normalized_trade_dates = _dedupe_tuple(trade_dates)
        normalized_sources = _dedupe_tuple(
            tuple(source.lower() for source in available_sources)
        )
        source_health = self._catalog_facade.get_source_health_summary(
            dataset_ids=normalized_dataset_ids,
            trade_dates=normalized_trade_dates,
            available_sources=normalized_sources,
        )
        maturity = self._ingestion_status_facade.get_maturity_governance_report(
            list(normalized_dataset_ids),
            trade_dates=normalized_trade_dates,
            available_sources=normalized_sources,
        )
        lineage_report = (
            self._lineage_facade.get_data_lineage_catalog_report_for_run(
                run_id,
                trade_dates=normalized_trade_dates,
                available_sources=normalized_sources,
            )
            if run_id is not None and self._lineage_facade is not None
            else None
        )
        return _CatalogRemediationReportContext(
            dataset_ids=normalized_dataset_ids,
            trade_dates=normalized_trade_dates,
            available_sources=normalized_sources,
            source_health=source_health,
            maturity=maturity,
            lineage_report=lineage_report,
        )


def _items_from_context(
    context: _CatalogRemediationReportContext,
) -> tuple[CatalogRemediationItem, ...]:
    return _sort_items(
        (
            *(
                _source_health_item(item)
                for item in context.source_health.attention_required
            ),
            *(
                _maturity_governance_item(item)
                for item in context.maturity.attention_required
            ),
            *_lineage_catalog_items(context.lineage_report),
        )
    )


def _find_item(
    items: tuple[CatalogRemediationItem, ...],
    item_id: str,
) -> CatalogRemediationItem:
    for item in items:
        if item.item_id == item_id:
            return item
    raise AppQueryError(f"Catalog remediation item not found: {item_id}")


def _source_health_item(
    item: CatalogSourceHealthAttentionItem,
) -> CatalogRemediationItem:
    reasons = tuple(item.attention_reasons)
    return CatalogRemediationItem(
        item_id=f"source_health:{item.dataset_id}:{item.trade_date}",
        source="source_health",
        dataset_id=item.dataset_id,
        namespace=item.namespace,
        trade_date=item.trade_date,
        severity=item.attention_severity,
        reasons=reasons,
        suggested_actions=_source_health_suggested_actions(item, reasons),
        default_source=item.default_source,
        selected_source=item.selected_source,
        fallback_sources=item.fallback_sources,
        source_fallback_policy_effect=item.source_fallback_policy_effect,
        source_selection_status=item.source_selection_status,
        source_selection_blockers=item.source_selection_blockers,
        freshness_status=item.selected_freshness_status,
    )


def _maturity_governance_item(
    item: DatasetMaturityGovernanceAttentionItem,
) -> CatalogRemediationItem:
    reasons = tuple(item.attention_reasons)
    return CatalogRemediationItem(
        item_id=f"maturity_governance:{item.dataset_id}",
        source="maturity_governance",
        dataset_id=item.dataset_id,
        namespace="catalog",
        severity=item.attention_severity,
        reasons=reasons,
        suggested_actions=_suggested_actions("maturity_governance", reasons),
        current_maturity=item.dataset.current_maturity,
        promotion_status=item.dataset.promotion_status,
        freshness_status=item.dataset.catalog_freshness_status,
    )


def _lineage_catalog_items(
    report: DataLineageCatalogRunReport | None,
) -> tuple[CatalogRemediationItem, ...]:
    if report is None:
        return ()
    return tuple(
        CatalogRemediationItem(
            item_id=_lineage_item_id(
                run_id=report.run_id,
                side=item.side,
                namespace=item.asset.asset.namespace,
                dataset_id=item.asset.asset.dataset_id,
                partition_keys=item.asset.asset.partition_keys,
            ),
            source="lineage_catalog",
            dataset_id=item.asset.asset.dataset_id,
            namespace=item.asset.asset.namespace,
            trade_date=_trade_date_from_partition_keys(item.asset.asset.partition_keys),
            run_id=report.run_id,
            side=item.side,
            partition_keys=item.asset.asset.partition_keys,
            severity=item.attention_severity,
            reasons=tuple(item.attention_reasons),
            suggested_actions=_suggested_actions(
                "lineage_catalog",
                tuple(item.attention_reasons),
            ),
            catalog_status=item.asset.catalog_status,
            freshness_status=item.asset.freshness_status,
        )
        for item in report.attention_required
    )


def _approval_intents_for_item(
    item: CatalogRemediationItem,
    evidence_requirements: tuple[CatalogRemediationEvidenceRequirement, ...],
) -> tuple[CatalogRemediationApprovalIntent, ...]:
    intents: list[CatalogRemediationApprovalIntent] = []
    for action in item.suggested_actions:
        intents.extend(
            _approval_intents_for_action(
                action=action,
                item=item,
                evidence_requirements=evidence_requirements,
            )
        )
    return tuple(intents)


def _approval_intents_for_action(
    *,
    action: str,
    item: CatalogRemediationItem,
    evidence_requirements: tuple[CatalogRemediationEvidenceRequirement, ...],
) -> tuple[CatalogRemediationApprovalIntent, ...]:
    if action == "repair_catalog_source_coverage" and item.trade_date is not None:
        return (
            _source_coverage_repair_intent(
                dataset_id=item.dataset_id,
                trade_date=item.trade_date,
            ),
        )
    if action == "repair_lineage_catalog_asset" and item.trade_date is not None:
        return (_lineage_catalog_asset_repair_intent(item),)
    if action == "repair_catalog_freshness":
        return (_catalog_freshness_repair_intent(item),)
    if action == "submit_or_fix_promotion_evidence":
        return tuple(
            _promotion_evidence_intent(
                dataset_id=item.dataset_id,
                criterion=requirement.description,
            )
            for requirement in evidence_requirements
            if requirement.source == "promotion_criterion"
        )
    if action in _MANUAL_ACTION_REQUIRED_INPUTS:
        return (_manual_remediation_intent(item=item, action=action),)
    return ()


def _source_coverage_repair_intent(
    *,
    dataset_id: str,
    trade_date: str,
) -> CatalogRemediationApprovalIntent:
    return CatalogRemediationApprovalIntent(
        action="repair_catalog_source_coverage",
        intent_type="write",
        method="POST",
        path=f"/ingestion/{dataset_id}/{trade_date}",
        request_template={
            "dataset_id": dataset_id,
            "trade_date": trade_date,
            "force": True,
            "source": "auto",
        },
        required_operator_inputs=(),
        notes=(
            "Executes approved source-aware one-day ingestion with force=true; "
            "the application executor delegates to the existing ingest-date path."
        ),
    )


def _catalog_freshness_repair_intent(
    item: CatalogRemediationItem,
) -> CatalogRemediationApprovalIntent:
    trade_date = item.trade_date or "<trade-date>"
    required_inputs: tuple[str, ...] = (
        () if item.trade_date is not None else ("trade_date",)
    )
    return CatalogRemediationApprovalIntent(
        action="repair_catalog_freshness",
        intent_type="write",
        method="POST",
        path=f"/ingestion/{item.dataset_id}/{trade_date}",
        request_template={
            "dataset_id": item.dataset_id,
            "trade_date": trade_date,
            "force": True,
            "source": "auto",
        },
        required_operator_inputs=required_inputs,
        notes=(
            "Executes approved source-aware one-day ingestion for the operator "
            "selected trade_date to refresh catalog freshness evidence."
        ),
    )


def _lineage_catalog_asset_repair_intent(
    item: CatalogRemediationItem,
) -> CatalogRemediationApprovalIntent:
    return CatalogRemediationApprovalIntent(
        action="repair_lineage_catalog_asset",
        intent_type="write",
        method="POST",
        path=f"/ingestion/{item.dataset_id}/{item.trade_date}",
        request_template={
            "dataset_id": item.dataset_id,
            "namespace": item.namespace,
            "trade_date": item.trade_date,
            "run_id": item.run_id,
            "side": item.side,
            "partition_keys": list(item.partition_keys),
            "force": True,
            "source": "auto",
        },
        required_operator_inputs=(),
        notes=(
            "Executes approved source-aware one-day ingestion to rebuild the "
            "lineage catalog asset evidence for this run asset."
        ),
    )


def _promotion_evidence_intent(
    *,
    dataset_id: str,
    criterion: str,
) -> CatalogRemediationApprovalIntent:
    return CatalogRemediationApprovalIntent(
        action="submit_or_fix_promotion_evidence",
        intent_type="write",
        method="POST",
        path="/ingestion/catalog/promotion/evidence",
        request_template={
            "dataset_id": dataset_id,
            "criterion": criterion,
            "evidence_uri": "<evidence-uri>",
            "reviewed_by": "<reviewer>",
            "passed": True,
            "notes": None,
        },
        required_operator_inputs=("evidence_uri", "reviewed_by"),
        notes=(
            "Persists reviewer evidence; it may promote maturity when all "
            "criteria pass."
        ),
    )


def _manual_remediation_intent(
    *,
    item: CatalogRemediationItem,
    action: str,
) -> CatalogRemediationApprovalIntent:
    template: dict[str, object] = {
        "action": action,
        "dataset_id": item.dataset_id,
        "namespace": item.namespace,
    }
    if item.trade_date is not None:
        template["trade_date"] = item.trade_date
    template.update(_source_context_template(item))
    if item.current_maturity is not None:
        template["current_maturity"] = item.current_maturity
    if item.promotion_status is not None:
        template["promotion_status"] = item.promotion_status
    if action == "configure_fallback_source":
        template["fallback_source"] = "<fallback-source>"
    if action == "approve_maturity_promotion":
        template["target_maturity"] = "<target-maturity>"

    return CatalogRemediationApprovalIntent(
        action=action,
        intent_type="manual",
        method=None,
        path=None,
        request_template=template,
        required_operator_inputs=_MANUAL_ACTION_REQUIRED_INPUTS[action],
        notes=_MANUAL_ACTION_NOTES[action],
    )


def _source_context_template(item: CatalogRemediationItem) -> dict[str, object]:
    template: dict[str, object] = {}
    if item.default_source is not None:
        template["default_source"] = item.default_source
    if item.selected_source is not None:
        template["selected_source"] = item.selected_source
    if item.fallback_sources:
        template["fallback_sources"] = list(item.fallback_sources)
    if item.source_fallback_policy_effect is not None:
        template["source_fallback_policy_effect"] = {
            "policy_id": item.source_fallback_policy_effect.policy_id,
            "policy_status": item.source_fallback_policy_effect.policy_status,
            "catalog_selected_source": (
                item.source_fallback_policy_effect.catalog_selected_source
            ),
            "effective_selected_source": (
                item.source_fallback_policy_effect.effective_selected_source
            ),
            "reason_codes": list(item.source_fallback_policy_effect.reason_codes),
            "recommended_actions": list(
                item.source_fallback_policy_effect.recommended_actions
            ),
        }
    if item.source_selection_status == "blocked":
        template["source_selection_status"] = item.source_selection_status
    if item.source_selection_blockers:
        template["source_selection_blockers"] = list(item.source_selection_blockers)
    return template


def _item_summary(item: CatalogRemediationItem) -> str:
    reasons = ", ".join(item.reasons)
    source = item.source.replace("_", " ")
    return f"{item.dataset_id} requires {source} attention ({reasons})."


def _lineage_item_id(
    *,
    run_id: str,
    side: str,
    namespace: str,
    dataset_id: str,
    partition_keys: tuple[str, ...],
) -> str:
    partition_suffix = ":".join(partition_keys)
    return (
        f"lineage_catalog:{run_id}:{side}:{namespace}:{dataset_id}:{partition_suffix}"
    )


def _trade_date_from_partition_keys(partition_keys: tuple[str, ...]) -> str | None:
    for key in partition_keys:
        if key.startswith("trade_date="):
            return key.removeprefix("trade_date=")
    return None


def _suggested_actions(
    source: CatalogRemediationSource,
    reasons: tuple[str, ...],
) -> tuple[str, ...]:
    actions: list[str] = []
    for reason in reasons:
        actions.extend(_actions_for_reason(source, reason))
    return _dedupe_tuple(tuple(actions))


def _source_health_suggested_actions(
    item: CatalogSourceHealthAttentionItem,
    reasons: tuple[str, ...],
) -> tuple[str, ...]:
    actions = _suggested_actions("source_health", reasons)
    if item.source_selection_status != "blocked":
        return actions
    manual_actions = tuple(
        action for action in actions if action != "repair_catalog_source_coverage"
    )
    if manual_actions:
        return manual_actions
    return ("review_source_request",)


def _actions_for_reason(
    source: CatalogRemediationSource,
    reason: str,
) -> tuple[str, ...]:
    return _ACTIONS_BY_REASON.get(
        (source, reason),
        ("review_catalog_governance_evidence",),
    )


def _severity_counts(
    items: tuple[CatalogRemediationItem, ...],
) -> tuple[CatalogRemediationSeverityCount, ...]:
    counts: dict[CatalogRemediationSeverity, int] = {
        "critical": 0,
        "warning": 0,
        "info": 0,
    }
    for item in items:
        counts[item.severity] += 1
    return tuple(
        CatalogRemediationSeverityCount(severity=severity, count=count)
        for severity, count in counts.items()
    )


def _source_counts(
    items: tuple[CatalogRemediationItem, ...],
) -> tuple[CatalogRemediationSourceCount, ...]:
    counts: dict[CatalogRemediationSource, int] = {
        "source_health": 0,
        "maturity_governance": 0,
        "lineage_catalog": 0,
    }
    for item in items:
        counts[item.source] += 1
    return tuple(
        CatalogRemediationSourceCount(source=source, count=count)
        for source, count in counts.items()
        if count > 0
    )


def _reason_counts(
    items: tuple[CatalogRemediationItem, ...],
) -> tuple[CatalogRemediationReasonCount, ...]:
    counts: dict[tuple[CatalogRemediationSource, str], int] = {}
    for item in items:
        for reason in item.reasons:
            key = (item.source, reason)
            counts[key] = counts.get(key, 0) + 1
    source_order = {
        "source_health": 0,
        "maturity_governance": 1,
        "lineage_catalog": 2,
    }
    return tuple(
        CatalogRemediationReasonCount(source=source, reason=reason, count=count)
        for (source, reason), count in sorted(
            counts.items(),
            key=lambda entry: (source_order[entry[0][0]], entry[0][1]),
        )
    )


def _source_fallback_policy_effect_counts(
    items: tuple[CatalogRemediationItem, ...],
) -> tuple[CatalogRemediationSourceFallbackPolicyEffectCount, ...]:
    counts: dict[tuple[str, str, str, str], int] = {}
    for item in items:
        effect = item.source_fallback_policy_effect
        if effect is None:
            continue
        key = (
            effect.policy_id,
            effect.policy_status,
            effect.catalog_selected_source,
            effect.effective_selected_source,
        )
        counts[key] = counts.get(key, 0) + 1
    return tuple(
        CatalogRemediationSourceFallbackPolicyEffectCount(
            policy_id=policy_id,
            policy_status=policy_status,
            catalog_selected_source=catalog_selected_source,
            effective_selected_source=effective_selected_source,
            count=counts[key],
        )
        for key in sorted(counts)
        for (
            policy_id,
            policy_status,
            catalog_selected_source,
            effective_selected_source,
        ) in (key,)
    )


def _sort_items(
    items: tuple[CatalogRemediationItem, ...],
) -> tuple[CatalogRemediationItem, ...]:
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    source_order = {
        "source_health": 0,
        "maturity_governance": 1,
        "lineage_catalog": 2,
    }
    return tuple(
        sorted(
            items,
            key=lambda item: (
                severity_order[item.severity],
                source_order[item.source],
                item.dataset_id,
                item.trade_date or "",
                item.run_id or "",
                item.side or "",
                item.namespace,
                item.partition_keys,
            ),
        )
    )


def _dedupe_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _utcnow() -> datetime:
    return datetime.now(UTC)
