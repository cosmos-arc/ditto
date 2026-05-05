"""DataRootInitProvider directory repair behavior tests."""

from pathlib import Path

from ditto_platform.foundation.config.providers import DataRootInitProvider


def test_data_root_provider_check_requires_missing_configured_directories(
    tmp_path: Path,
) -> None:
    """Existing data roots still need init when a configured directory is absent."""
    data_root = tmp_path / "data"
    (data_root / "raw").mkdir(parents=True)
    provider = DataRootInitProvider(["raw", "features/technical/price"])

    assert provider.check(data_root)


def test_data_root_provider_check_skips_when_all_configured_directories_exist(
    tmp_path: Path,
) -> None:
    """Fully initialized data roots do not need init."""
    data_root = tmp_path / "data"
    (data_root / "raw").mkdir(parents=True)
    (data_root / "features" / "technical" / "price").mkdir(parents=True)
    provider = DataRootInitProvider(["raw", "features/technical/price"])

    assert not provider.check(data_root)
