"""Analysis public contract tests."""

from __future__ import annotations


def test_research_catalog_protocols_have_canonical_contract_module() -> None:
    from ditto_analysis.contracts import (
        ResearchCatalogReaderProtocol,
        ResearchCatalogWriterProtocol,
    )

    # Protocols 定义在 research.protocols 以避免循环依赖，contracts 仅重导出
    _expected = "ditto_analysis.research.protocols"
    assert ResearchCatalogReaderProtocol.__module__ == _expected
    assert ResearchCatalogWriterProtocol.__module__ == _expected
