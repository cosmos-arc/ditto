"""ConfigProvider init coordinator wiring tests."""

import sqlite3
from contextlib import closing
from pathlib import Path

from ditto_apps.registry.infra.config import ConfigProvider
from ditto_data.config import DataSourceSettings
from ditto_data.config.data_store import DataStoreSettings
from ditto_features.config import FeatureArtifactStoreSettings
from ditto_platform.foundation import InitScope


def test_config_provider_init_coordinator_creates_feature_artifact_dirs(
    tmp_path: Path,
) -> None:
    """Startup data-root init includes features-owned artifact directories."""
    data_root = tmp_path / "data"
    coordinator = ConfigProvider().init_coordinator(
        DataStoreSettings(data_root=data_root),
        FeatureArtifactStoreSettings(data_root=data_root),
        DataSourceSettings(tushare_token="resolved-test-token"),
    )

    results = coordinator.initialize(
        scope=InitScope.STARTUP,
        data_root=data_root,
        fail_fast=False,
    )

    assert results["data_root"].success
    assert (data_root / "features" / "technical" / "price").is_dir()
    assert (data_root / "factors" / "factors_narrow").is_dir()
    assert results["data_source_validation"].success
    assert results["r4_risk_schema"].success

    database = data_root / "metadata" / "metadata.sqlite"
    with closing(sqlite3.connect(database)) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "risk_events",
        "risk_state_snapshots",
        "daily_risk_reports",
    } <= tables
