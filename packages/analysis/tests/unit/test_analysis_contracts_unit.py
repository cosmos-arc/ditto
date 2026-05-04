"""Analysis public contract tests."""

from __future__ import annotations


def test_research_catalog_protocols_have_canonical_contract_module() -> None:
    from ditto_analysis.contracts import (
        ResearchCatalogReaderProtocol,
        ResearchCatalogWriterProtocol,
    )

    assert ResearchCatalogReaderProtocol.__module__ == "ditto_analysis.contracts"
    assert ResearchCatalogWriterProtocol.__module__ == "ditto_analysis.contracts"
