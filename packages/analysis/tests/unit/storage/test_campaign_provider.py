"""Campaign storage provider wiring tests."""

from pathlib import Path

from ditto_analysis.di.storage import AnalysisStorageProvider
from ditto_analysis.experiments.campaign_persistence import (
    CampaignReaderProtocol,
    CampaignWriterProtocol,
)
from ditto_analysis.storage.sqlite.experiments import ResearchExperimentDatabase


def test_analysis_provider_exposes_campaign_storage_ports(tmp_path: Path) -> None:
    database = ResearchExperimentDatabase(tmp_path)
    database.initialize()
    provider = AnalysisStorageProvider()

    reader = provider.research_campaign_reader(database)
    writer = provider.research_campaign_writer(database)
    reader_port: CampaignReaderProtocol = provider.research_campaign_reader_port(reader)
    writer_port: CampaignWriterProtocol = provider.research_campaign_writer_port(writer)

    assert reader_port is reader
    assert writer_port is writer
