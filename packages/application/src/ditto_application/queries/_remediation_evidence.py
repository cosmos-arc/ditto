"""Evidence requirements for catalog remediation detail reports."""

from __future__ import annotations

from ditto_application.queries.ingestion_status import (
    DatasetMaturityGovernanceItem,
    DatasetMaturityGovernanceReport,
)
from ditto_application.queries.remediation_models import (
    CatalogRemediationEvidenceRequirement,
    CatalogRemediationItem,
)


def evidence_requirements_for_item(
    item: CatalogRemediationItem,
    maturity: DatasetMaturityGovernanceReport,
) -> tuple[CatalogRemediationEvidenceRequirement, ...]:
    """Return backend-readable evidence requirements for one remediation item."""
    if item.source == "maturity_governance":
        dataset = _maturity_dataset(maturity, item.dataset_id)
        if dataset is not None:
            return _promotion_evidence_requirements(dataset)
    if item.source == "source_health":
        return _source_health_evidence_requirements(item)
    return tuple(
        CatalogRemediationEvidenceRequirement(
            requirement_id=f"{item.source}:{reason}",
            source=item.source,
            status="attention_required",
            description=reason,
        )
        for reason in item.reasons
    )


def _maturity_dataset(
    maturity: DatasetMaturityGovernanceReport,
    dataset_id: str,
) -> DatasetMaturityGovernanceItem | None:
    for dataset in maturity.datasets:
        if dataset.dataset_id == dataset_id:
            return dataset
    return None


def _promotion_evidence_requirements(
    dataset: DatasetMaturityGovernanceItem,
) -> tuple[CatalogRemediationEvidenceRequirement, ...]:
    requirements: list[CatalogRemediationEvidenceRequirement] = []
    for criterion in dataset.missing_criteria:
        requirements.append(
            CatalogRemediationEvidenceRequirement(
                requirement_id=f"promotion_criterion:{criterion}",
                source="promotion_criterion",
                status="missing",
                description=criterion,
            )
        )
    for criterion in dataset.rejected_criteria:
        requirements.append(
            CatalogRemediationEvidenceRequirement(
                requirement_id=f"promotion_criterion:{criterion}",
                source="promotion_criterion",
                status="rejected",
                description=criterion,
            )
        )
    return tuple(requirements)


def _source_health_evidence_requirements(
    item: CatalogRemediationItem,
) -> tuple[CatalogRemediationEvidenceRequirement, ...]:
    requirements: list[CatalogRemediationEvidenceRequirement] = [
        CatalogRemediationEvidenceRequirement(
            requirement_id=_source_health_requirement_id(item, reason),
            source="source_health",
            status="attention_required",
            description=_source_health_reason_description(item, reason),
        )
        for reason in item.reasons
    ]
    requirements.extend(_fallback_candidate_requirements(item))
    requirements.extend(_source_selection_blocker_requirements(item))
    return _dedupe_requirements(tuple(requirements))


def _source_health_requirement_id(item: CatalogRemediationItem, reason: str) -> str:
    return f"source_health:{item.dataset_id}:{_item_trade_date(item)}:{reason}"


def _source_health_reason_description(
    item: CatalogRemediationItem,
    reason: str,
) -> str:
    selected_source = item.selected_source or "<selected-source>"
    default_source = item.default_source or "<default-source>"
    trade_date = _item_trade_date(item)
    descriptions = {
        "selected_source_missing": (
            f"Selected source {selected_source} is missing catalog freshness "
            f"evidence for {item.dataset_id} on {trade_date}."
        ),
        "selected_source_stale": (
            f"Selected source {selected_source} has stale catalog freshness "
            f"evidence for {item.dataset_id} on {trade_date}."
        ),
        "selected_source_not_applicable": (
            f"Selected source {selected_source} has no applicable catalog freshness "
            f"policy for {item.dataset_id} on {trade_date}."
        ),
        "default_source_failover": (
            f"Selected source {selected_source} differs from default source "
            f"{default_source} for {item.dataset_id} on {trade_date}; review "
            "fallback policy before changing source preferences."
        ),
        "no_fallback_source": (
            f"No candidate fallback source is available for {item.dataset_id} "
            f"on {trade_date}; define or review fallback policy manually."
        ),
        "unsupported_sources_present": (
            f"One or more requested sources are unsupported for {item.dataset_id} "
            f"on {trade_date}; review source capability metadata before retrying."
        ),
        "latest_maturity_promotion_revoked": (
            f"Latest maturity promotion for {item.dataset_id} was revoked; review "
            "maturity governance before relying on source fallback evidence."
        ),
    }
    return descriptions.get(reason, reason)


def _fallback_candidate_requirements(
    item: CatalogRemediationItem,
) -> tuple[CatalogRemediationEvidenceRequirement, ...]:
    trade_date = _item_trade_date(item)
    return tuple(
        CatalogRemediationEvidenceRequirement(
            requirement_id=(
                f"source_fallback_candidate:{item.dataset_id}:{trade_date}:{source}"
            ),
            source="source_fallback_candidate",
            status="attention_required",
            description=(
                f"Candidate fallback source {source} is available for "
                f"{item.dataset_id} on {trade_date}; review suitability before "
                "changing fallback policy."
            ),
        )
        for source in item.fallback_sources
    )


def _source_selection_blocker_requirements(
    item: CatalogRemediationItem,
) -> tuple[CatalogRemediationEvidenceRequirement, ...]:
    trade_date = _item_trade_date(item)
    return tuple(
        CatalogRemediationEvidenceRequirement(
            requirement_id=(
                f"source_selection_blocker:{item.dataset_id}:{trade_date}:{blocker}"
            ),
            source="source_selection_blocker",
            status="attention_required",
            description=(
                f"Source selection blocker {blocker} prevents source=auto for "
                f"{item.dataset_id} on {trade_date}; resolve policy or capability "
                "metadata before exposing executable repair."
            ),
        )
        for blocker in item.source_selection_blockers
    )


def _dedupe_requirements(
    requirements: tuple[CatalogRemediationEvidenceRequirement, ...],
) -> tuple[CatalogRemediationEvidenceRequirement, ...]:
    seen: set[str] = set()
    deduped: list[CatalogRemediationEvidenceRequirement] = []
    for requirement in requirements:
        if requirement.requirement_id in seen:
            continue
        seen.add(requirement.requirement_id)
        deduped.append(requirement)
    return tuple(deduped)


def _item_trade_date(item: CatalogRemediationItem) -> str:
    return item.trade_date or "<trade-date>"
