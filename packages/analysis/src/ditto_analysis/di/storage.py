"""Analysis storage DI Provider — 研究 SQLite 存储装配."""

from dishka import Provider, Scope, provide
from ditto_data.storage.sqlite_client import SQLiteClient

from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_analysis.storage.sqlite.research import (
    SQLiteResearchCatalogReader,
    SQLiteResearchCatalogWriter,
)

__all__ = ["AnalysisStorageProvider"]


class AnalysisStorageProvider(Provider):
    """研究存储 Provider — SQLite catalog 读写与域服务."""

    scope = Scope.APP

    @provide
    def research_catalog_reader(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteResearchCatalogReader:
        """Research 控制面读取器."""
        return SQLiteResearchCatalogReader(sqlite_client)

    @provide
    def research_catalog_writer(
        self,
        sqlite_client: SQLiteClient,
    ) -> SQLiteResearchCatalogWriter:
        """Research 控制面写入器."""
        return SQLiteResearchCatalogWriter(sqlite_client)

    @provide
    def research_catalog_service(
        self,
        research_catalog_reader: SQLiteResearchCatalogReader,
        research_catalog_writer: SQLiteResearchCatalogWriter,
    ) -> ResearchCatalogService:
        """Research 控制面元数据服务."""
        return ResearchCatalogService(
            catalog_reader=research_catalog_reader,
            catalog_writer=research_catalog_writer,
        )
