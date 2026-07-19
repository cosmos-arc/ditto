"""Analysis storage DI Provider — 研究 SQLite 存储装配."""

from collections.abc import Iterator
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_platform.foundation import SQLiteClient

from ditto_analysis.experiments.protocols import (
    ExperimentReaderProtocol,
    ExperimentWriterProtocol,
)
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteExperimentReader,
    SQLiteExperimentWriter,
)
from ditto_analysis.storage.sqlite.research import (
    SQLiteResearchCatalogReader,
    SQLiteResearchCatalogWriter,
)

__all__ = ["AnalysisStorageProvider"]


class AnalysisStorageProvider(Provider):
    """研究存储 Provider — SQLite catalog 读写与域服务."""

    scope = Scope.APP

    @provide
    def research_experiment_database(
        self,
        data_root: Path,
    ) -> Iterator[ResearchExperimentDatabase]:
        """Own the nominal research DB and close every worker connection on exit."""
        database = ResearchExperimentDatabase(data_root)
        database.initialize()
        try:
            yield database
        finally:
            database.close_all()

    @provide
    def research_experiment_reader(
        self,
        database: ResearchExperimentDatabase,
    ) -> SQLiteExperimentReader:
        """Provide the typed experiment reader without exposing its private pool."""
        return SQLiteExperimentReader(database)

    @provide
    def research_experiment_writer(
        self,
        database: ResearchExperimentDatabase,
    ) -> SQLiteExperimentWriter:
        """Provide the typed experiment command and lease writer."""
        return SQLiteExperimentWriter(database)

    @provide
    def research_experiment_reader_port(
        self,
        reader: SQLiteExperimentReader,
    ) -> ExperimentReaderProtocol:
        """Expose the experiment reader through its analysis-owned port."""
        return reader

    @provide
    def research_experiment_writer_port(
        self,
        writer: SQLiteExperimentWriter,
    ) -> ExperimentWriterProtocol:
        """Expose the experiment writer through its analysis-owned port."""
        return writer

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

    @provide
    def research_artifact_service(self, data_root: Path) -> ResearchArtifactService:
        """Research artifact file I/O service."""
        return ResearchArtifactService(artifact_root=data_root)
