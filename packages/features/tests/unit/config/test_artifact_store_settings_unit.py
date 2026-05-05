"""FeatureArtifactStoreSettings 单元测试."""

from pathlib import Path

from ditto_features.config import FeatureArtifactStoreSettings


def test_feature_artifact_store_settings_owns_feature_and_factor_paths() -> None:
    """Features 层拥有特征和因子产物路径."""
    settings = FeatureArtifactStoreSettings(data_root=Path("data"))

    assert settings.features_technical_price_path == Path(
        "data/features/technical/price"
    )
    assert settings.features_technical_indicators_narrow_path == Path(
        "data/features/technical/indicators_narrow"
    )
    assert settings.features_technical_indicators_wide_path == Path(
        "data/features/technical/indicators_wide"
    )
    assert settings.factors_narrow_style_path == Path("data/factors/narrow/style")
    assert settings.factors_wide_style_path == Path("data/factors/wide/style")
    assert settings.factors_narrow_path == Path("data/factors/factors_narrow")
    assert settings.factors_wide_path == Path("data/factors/factors_wide")


def test_feature_artifact_store_settings_lists_owned_directories() -> None:
    """all_directories() 返回 Features 层拥有的产物目录."""
    settings = FeatureArtifactStoreSettings()

    assert settings.all_directories() == [
        "features/technical/price",
        "features/technical/indicators_narrow",
        "features/technical/indicators_wide",
        "factors/narrow/style",
        "factors/wide/style",
        "factors/factors_narrow",
        "factors/factors_wide",
    ]
