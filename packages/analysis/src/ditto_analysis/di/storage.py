"""Analysis storage DI Provider — 研究 SQLite 存储装配."""

from collections.abc import Iterator
from pathlib import Path

from dishka import Provider, Scope, provide
from ditto_platform.foundation import SQLiteClient

from ditto_analysis.experiments.campaign_persistence import (
    CampaignReaderProtocol,
    CampaignWriterProtocol,
)
from ditto_analysis.experiments.protocols import (
    ExperimentReaderProtocol,
    ExperimentWriterProtocol,
)
from ditto_analysis.research.artifact_service import ResearchArtifactService
from ditto_analysis.research.catalog_service import ResearchCatalogService
from ditto_analysis.storage.sqlite.experiments import (
    ResearchExperimentDatabase,
    SQLiteCampaignReader,
    SQLiteCampaignWriter,
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
    def research_campaign_reader(
        self,
        database: ResearchExperimentDatabase,
    ) -> SQLiteCampaignReader:
        """Provide the immutable Campaign/search ledger reader."""
        return SQLiteCampaignReader(database)

    @provide
    def research_campaign_writer(
        self,
        database: ResearchExperimentDatabase,
    ) -> SQLiteCampaignWriter:
        """Provide the append-only Campaign/search ledger writer."""
        return SQLiteCampaignWriter(database)

    @provide
    def research_campaign_reader_port(
        self,
        reader: SQLiteCampaignReader,
    ) -> CampaignReaderProtocol:
        """Expose Campaign reads through the Analysis-owned port."""
        return reader

    @provide
    def research_campaign_writer_port(
        self,
        writer: SQLiteCampaignWriter,
    ) -> CampaignWriterProtocol:
        """Expose Campaign writes through the Analysis-owned port."""
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
    def research_artifact_service(
        self,
        data_root: Path,
        database: ResearchExperimentDatabase,
        reader: SQLiteExperimentReader,
        writer: SQLiteExperimentWriter,
    ) -> ResearchArtifactService:
        """Provide legacy files plus the database-owned verified R3 namespace."""
        return ResearchArtifactService(
            artifact_root=data_root,
            indexed_artifact_root=database.artifact_root,
            artifact_reader=reader,
            artifact_writer=writer,
        )
