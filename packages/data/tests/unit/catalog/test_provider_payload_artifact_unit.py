"""Pure contract tests for immutable provider payload identities."""

from dataclasses import replace

import pytest
from ditto_data.catalog.provider_payload import ProviderPayloadArtifact

pytestmark = pytest.mark.unit

_CHECKSUM = "a" * 32


def _artifact() -> ProviderPayloadArtifact:
    return ProviderPayloadArtifact(
        dataset_id="stock_daily",
        source="tushare",
        checksum=_CHECKSUM,
        row_count=42,
        uri=f"provider_payloads/tushare/stock_daily/{_CHECKSUM}.parquet",
    )


def test_provider_payload_artifact_rejects_noncanonical_checksum() -> None:
    with pytest.raises(ValueError, match="invalid provider payload checksum"):
        replace(_artifact(), checksum="A" * 32)


def test_provider_payload_artifact_rejects_negative_row_count() -> None:
    with pytest.raises(ValueError, match="row_count must be non-negative"):
        replace(_artifact(), row_count=-1)


def test_provider_payload_artifact_rejects_uri_identity_mismatch() -> None:
    with pytest.raises(ValueError, match="uri does not match its identity"):
        replace(
            _artifact(),
            uri=f"provider_payloads/other/stock_daily/{_CHECKSUM}.parquet",
        )
