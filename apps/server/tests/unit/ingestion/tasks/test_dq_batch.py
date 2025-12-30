"""Tests for DQ batch tasks."""

import pathlib

import ditto_datahub
from ditto_server.ingestion.tasks.dq_batch import get_default_dq_config_path


def test_default_config_path_points_to_package():
    """Test default config path points to packages/datahub/config/dq_rules."""
    package_root = pathlib.Path(ditto_datahub.__file__).parent.parent.parent
    expected_path = package_root / "config" / "dq_rules"

    actual_path = get_default_dq_config_path()

    assert actual_path == str(expected_path)
    # Verify the path actually exists on the filesystem
    assert pathlib.Path(actual_path).exists()
