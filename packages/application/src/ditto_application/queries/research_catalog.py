"""
Research catalog query facade — static R3 node + factor registry projection.

The facade projects the immutable strategy node registry and the features
core-factor catalog into application-owned read models so API routes never
import capability packages directly. The registries are static and
content-addressed, so the facade holds no I/O and no mutation authority.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ditto_features.factors.core_daily_catalog import R3_CORE_FACTOR_CATALOG
from ditto_features.factors.core_daily_contracts import CoreFactorCatalog
from ditto_strategy.alpha.node_registry import (
    NodeDescriptor,
    NodeRegistry,
    default_node_registry,
)

__all__ = [
    "FactorDescriptorInfo",
    "NodeDescriptorInfo",
    "ResearchCatalogQueryFacade",
    "default_research_catalog_facade",
]


@dataclass(frozen=True, slots=True)
class NodeDescriptorInfo:
    """Application projection of one immutable node descriptor."""

    node_type: str
    version: str
    category: str
    display_name: str
    implementation_key: str
    config_schema: Mapping[str, str]
    default_config: Mapping[str, object]
    required_datasets: tuple[str, ...]
    capability_tags: tuple[str, ...]
    deterministic: bool


@dataclass(frozen=True, slots=True)
class FactorDescriptorInfo:
    """Application projection of one governed core-factor descriptor."""

    factor_id: str
    resolved_payload: Mapping[str, object]


def _to_node_info(descriptor: NodeDescriptor) -> NodeDescriptorInfo:
    """Project a capability descriptor into an application read model."""
    return NodeDescriptorInfo(
        node_type=descriptor.node_type,
        version=descriptor.version,
        category=descriptor.category.value,
        display_name=descriptor.display_name,
        implementation_key=descriptor.implementation_key,
        config_schema={
            key: str(value) for key, value in descriptor.config_schema.items()
        },
        default_config=dict(descriptor.default_config),
        required_datasets=descriptor.required_datasets,
        capability_tags=descriptor.capability_tags,
        deterministic=descriptor.deterministic,
    )


class ResearchCatalogQueryFacade:
    """Project the static R3 node + factor registries into read models."""

    def __init__(
        self,
        node_registry: NodeRegistry,
        factor_catalog: CoreFactorCatalog,
    ) -> None:
        self._node_registry = node_registry
        self._factor_catalog = factor_catalog

    def list_node_descriptors(self) -> tuple[NodeDescriptorInfo, ...]:
        """Project every builtin node descriptor in registry order."""
        return tuple(
            _to_node_info(descriptor) for descriptor in self._node_registry.descriptors
        )

    def list_factors(self) -> tuple[FactorDescriptorInfo, ...]:
        """Project every governed core-factor descriptor in catalog order."""
        return tuple(
            FactorDescriptorInfo(
                factor_id=descriptor.factor_id,
                resolved_payload=dict(descriptor.resolved_payload),
            )
            for descriptor in self._factor_catalog.descriptors
        )

    @property
    def node_manifest_hash(self) -> str:
        """Stable manifest hash of the builtin node registry."""
        return self._node_registry.manifest_hash

    @property
    def factor_catalog_version(self) -> str:
        """Stable version label of the governed core-factor catalog."""
        return self._factor_catalog.version


def default_research_catalog_facade() -> ResearchCatalogQueryFacade:
    """Build the default facade over the builtin R3 registries."""
    return ResearchCatalogQueryFacade(
        node_registry=default_node_registry(),
        factor_catalog=R3_CORE_FACTOR_CATALOG,
    )
