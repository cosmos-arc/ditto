"""ConfigProvider init coordinator wiring tests."""

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
