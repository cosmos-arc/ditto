"""Unit tests for derived publication helper hydration."""

from __future__ import annotations

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.materialization.publication_helpers import (
    hydrate_manifest,
)
from ditto_features.publication_safety_records import CompatibilityManifestRecord
from ditto_platform.foundation.json_types import JsonDict


def _manifest_record(payload: JsonDict) -> CompatibilityManifestRecord:
    return CompatibilityManifestRecord(
        derived_id="alpha.momentum",
        version=1,
        manifest_hash="manifest-hash",
        payload=payload,
        created_at="2026-01-01T00:00:00Z",
    )


def test_hydrate_manifest_rejects_non_string_manifest_field_with_app_error() -> None:
    record = _manifest_record({"engine_codegen_version": 123})

    with pytest.raises(AppProcessError, match="engine_codegen_version"):
        hydrate_manifest(record)


def test_hydrate_manifest_rejects_non_object_compile_flags_with_app_error() -> None:
    record = _manifest_record({"global_compile_flags": ["grain"]})

    with pytest.raises(AppProcessError, match="global_compile_flags"):
        hydrate_manifest(record)


def test_hydrate_manifest_rejects_non_primitive_compile_flag_with_app_error() -> None:
    record = _manifest_record({"global_compile_flags": {"grain": ["1d"]}})

    with pytest.raises(AppProcessError, match="global_compile_flags"):
        hydrate_manifest(record)
