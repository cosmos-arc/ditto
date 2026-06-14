"""Import-boundary guards for ``ditto_application.queries`` (A4 remediation).

These tests enforce the CLAUDE.md zero-tolerance rule on production
``TYPE_CHECKING`` deferred imports: the maturity / source-fallback cycle must be
broken by extracting eager leaf modules, so the DTOs referenced across the
cycle are bound at runtime rather than only under ``TYPE_CHECKING``.
"""

from __future__ import annotations

import importlib


def test_source_fallback_policy_eagerly_binds_catalog_source_health_report() -> None:
    """A4 case 2: ``CatalogSourceHealthReport`` must be eager-imported.

    Previously a ``TYPE_CHECKING`` forward reference to
    ``ditto_application.queries.catalog`` — which left the name unbound at runtime
    and formed a real import cycle. The leaf module
    ``ditto_application.queries.catalog_source_health`` breaks the cycle, so the
    import is now eager and the name must resolve at runtime.
    """
    module = importlib.import_module("ditto_application.queries.source_fallback_policy")

    assert hasattr(module, "CatalogSourceHealthReport")
    assert module.CatalogSourceHealthReport is not None


def test_maturity_types_leaf_exposes_governance_dtos() -> None:
    """A4 case 1: governance DTOs live in eager leaf module ``_maturity_types``.

    Extracting these DTOs out of ``ingestion_status`` into a leaf breaks the
    ``ingestion_status <-> _maturity_governance`` cycle without re-export chains,
    so ``_maturity_governance`` can import them eagerly.
    """
    from ditto_application.queries import _maturity_types

    for name in (
        "DatasetStatus",
        "DatasetMaturitySummary",
        "DatasetPromotionStatusCount",
        "DatasetPromotionCriterionCount",
        "DatasetPromotionReadinessItem",
        "DatasetPromotionReadinessReport",
    ):
        assert hasattr(_maturity_types, name), name


def test_maturity_governance_drops_type_checking() -> None:
    """A4 case 1: ``_maturity_governance`` must not defer maturity DTO imports."""
    import inspect

    from ditto_application.queries import _maturity_governance

    assert "TYPE_CHECKING" not in inspect.getsource(_maturity_governance)
