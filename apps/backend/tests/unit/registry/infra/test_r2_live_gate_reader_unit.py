"""Composition-root tests for explicit R2 live-gate evidence injection."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from ditto_application.processes.experiments.r2_live_gate_evidence import (
    FileR2LiveGateEvidenceReader,
    NullR2LiveGateEvidenceReader,
    R2LiveGateEvidenceSource,
)
from ditto_apps.registry.infra.protocol_adapters import (
    r2_live_gate_reader_from_environment,
)


def test_r2_live_gate_reader_defaults_to_fail_closed_null() -> None:
    loader = MagicMock()

    reader = r2_live_gate_reader_from_environment({}, source_loader=loader)

    assert isinstance(reader, NullR2LiveGateEvidenceReader)
    loader.assert_not_called()


def test_r2_live_gate_reader_rejects_partial_or_invalid_source() -> None:
    loader = MagicMock(return_value=None)

    partial = r2_live_gate_reader_from_environment(
        {"DITTO_R2_LIVE_REPORT_PATH": "/tmp/report.json"},
        source_loader=loader,
    )
    invalid = r2_live_gate_reader_from_environment(
        {
            "DITTO_R2_LIVE_REPORT_PATH": "/tmp/report.json",
            "DITTO_R2_LIVE_SOURCE_MANIFEST_PATH": "/tmp/report.manifest.json",
        },
        source_loader=loader,
    )

    assert isinstance(partial, NullR2LiveGateEvidenceReader)
    assert isinstance(invalid, NullR2LiveGateEvidenceReader)
    loader.assert_called_once_with(
        report_path=Path("/tmp/report.json"),
        source_manifest=Path("/tmp/report.manifest.json"),
    )


def test_r2_live_gate_reader_uses_explicit_verified_source() -> None:
    source = MagicMock(spec=R2LiveGateEvidenceSource)
    loader = MagicMock(return_value=source)

    reader = r2_live_gate_reader_from_environment(
        {
            "DITTO_R2_LIVE_REPORT_PATH": "/tmp/report.json",
            "DITTO_R2_LIVE_SOURCE_MANIFEST_PATH": "/tmp/report.manifest.json",
        },
        source_loader=loader,
    )

    assert isinstance(reader, FileR2LiveGateEvidenceReader)
    assert reader.source is source
