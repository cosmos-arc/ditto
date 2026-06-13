"""Tests for metadata DI provider dependency grouping."""

from unittest.mock import MagicMock

import pytest
from ditto_data.di.metadata import MetadataProvider
from ditto_data.services.metadata_service import MetadataService


@pytest.mark.unit
def test_metadata_service_uses_grouped_provider_dependencies() -> None:
    """MetadataProvider should assemble the facade from named dependency bundles."""
    provider = MetadataProvider()

    instrument_reader = MagicMock()
    instrument_writer = MagicMock()
    name_history_reader = MagicMock()
    name_history_writer = MagicMock()
    calendar_reader = MagicMock()
    calendar_writer = MagicMock()
    industry_reader = MagicMock()
    industry_writer = MagicMock()
    industry_mapping_reader = MagicMock()
    industry_mapping_writer = MagicMock()
    universe_reader = MagicMock()
    universe_writer = MagicMock()
    rebalance_reader = MagicMock()
    rebalance_writer = MagicMock()
    instrument_id_allocator = MagicMock()
    index_composition_reader = MagicMock()
    exchange_transformers = MagicMock()

    instrument_deps = provider.metadata_instrument_dependencies(
        instrument_reader,
        instrument_writer,
        name_history_reader,
        name_history_writer,
    )
    calendar_deps = provider.metadata_calendar_dependencies(
        calendar_reader,
        calendar_writer,
    )
    industry_deps = provider.metadata_industry_dependencies(
        industry_reader,
        industry_writer,
        industry_mapping_reader,
        industry_mapping_writer,
    )
    universe_deps = provider.metadata_universe_dependencies(
        universe_reader,
        universe_writer,
        rebalance_reader,
        rebalance_writer,
    )
    domain_deps = provider.metadata_domain_dependencies(
        instrument_deps,
        calendar_deps,
        industry_deps,
        universe_deps,
    )
    runtime_deps = provider.metadata_runtime_dependencies(
        instrument_id_allocator,
        index_composition_reader,
        exchange_transformers,
    )

    service = provider.metadata_service(domain_deps, runtime_deps)

    assert isinstance(service, MetadataService)
    assert service.instrument._instrument_reader is instrument_reader
    assert service.calendar._calendar_reader is calendar_reader
    assert service.universe._universe_reader is universe_reader
