"""Tests for ResearchCatalogQueryFacade — static R3 registry projection.

The facade projects the immutable strategy node registry and the features
core-factor catalog into application-owned read models so API routes never
import capability packages directly.
"""

from __future__ import annotations

from ditto_application.queries.research_catalog import (
    FactorDescriptorInfo,
    NodeDescriptorInfo,
    ResearchCatalogQueryFacade,
)
from ditto_features.factors.core_daily_catalog import R3_CORE_FACTOR_CATALOG
from ditto_strategy.alpha.node_registry import default_node_registry


def _facade() -> ResearchCatalogQueryFacade:
    return ResearchCatalogQueryFacade(
        node_registry=default_node_registry(),
        factor_catalog=R3_CORE_FACTOR_CATALOG,
    )


class TestListNodeDescriptors:
    """list_node_descriptors projects every registry descriptor in order."""

    def test_returns_one_info_per_registry_descriptor(self) -> None:
        registry = default_node_registry()
        facade = _facade()

        result = facade.list_node_descriptors()

        assert len(result) == len(registry.descriptors)
        assert all(isinstance(item, NodeDescriptorInfo) for item in result)

    def test_projection_carries_identity_fields(self) -> None:
        facade = _facade()
        registry = default_node_registry()
        first_registry = registry.descriptors[0]

        first_info = facade.list_node_descriptors()[0]

        assert first_info.node_type == first_registry.node_type
        assert first_info.version == first_registry.version
        assert first_info.category == first_registry.category.value
        assert first_info.display_name == first_registry.display_name
        assert first_info.implementation_key == first_registry.implementation_key
        assert first_info.deterministic == first_registry.deterministic
        assert first_info.required_datasets == first_registry.required_datasets


class TestListFactors:
    """list_factors projects the governed catalog order and payload hash."""

    def test_returns_factor_ids_in_catalog_order(self) -> None:
        facade = _facade()

        result = facade.list_factors()

        expected_ids = R3_CORE_FACTOR_CATALOG.factor_ids
        assert tuple(item.factor_id for item in result) == expected_ids
        assert all(isinstance(item, FactorDescriptorInfo) for item in result)

    def test_factor_payload_is_non_empty_snapshot(self) -> None:
        facade = _facade()

        result = facade.list_factors()

        assert len(result) > 0
        assert result[0].resolved_payload


class TestCatalogIdentity:
    """manifest hash / version expose stable registry identity."""

    def test_node_manifest_hash_matches_registry(self) -> None:
        registry = default_node_registry()
        facade = _facade()

        assert facade.node_manifest_hash == registry.manifest_hash

    def test_factor_catalog_version_matches(self) -> None:
        facade = _facade()

        assert facade.factor_catalog_version == R3_CORE_FACTOR_CATALOG.version
