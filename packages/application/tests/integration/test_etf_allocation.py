"""ETF allocation drafts retain exact weights, revision lineage and retry identity."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from ditto_application.exceptions import AppCommandError, AppConflictError
from ditto_application.processes.portfolio.etf_allocation import (
    ETFAllocationCommand,
    ETFAllocationRequest,
)
from ditto_application.queries.etf_candidates import ETFCandidate, ETFField
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_platform.foundation import SQLitePool
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.strategy_artifact_store import (
    SQLiteStrategyArtifactReader,
    SQLiteStrategyArtifactWriter,
)


def _candidate(instrument_id: int) -> ETFCandidate:
    tracking = ETFField(
        value="CSI300",
        unit=None,
        observed_on="2026-09-01",
        published_at="2026-09-01T07:00:00Z",
        source="recorded",
        source_snapshot_id="snapshot:recorded:etf",
        eligibility="RECORDED_REFERENCE_ONLY",
        missing_reason=None,
    )
    return ETFCandidate(
        instrument_id=instrument_id,
        ticker=f"51030{instrument_id}.SH",
        name=f"ETF {instrument_id}",
        exchange="SH",
        is_active=True,
        fields={"tracking_index": tracking},
    )


def _request() -> ETFAllocationRequest:
    return ETFAllocationRequest(
        allocation_id="demo",
        idempotency_key="one",
        parent_version_id=None,
        asof="2026-09-01",
        knowledge_cutoff="2026-09-01T09:00:00+00:00",
        source_snapshot_id="snapshot:recorded:etf",
        instrument_ids=(1, 2),
        mode="equal",
        cash_weight=Decimal("0.2"),
        max_position_weight=Decimal("0.5"),
        manual_weights={},
        reason="broad exposure",
    )


def test_save_revise_restore_and_reject_invalid_weights(tmp_path: Path) -> None:
    pool = SQLitePool(str(tmp_path / "allocation.sqlite"))
    writer = SQLiteStrategyArtifactWriter(pool)
    writer.init_schema()
    metadata = MagicMock(spec=MetadataQueryFacade)
    metadata.list_etf_candidates.return_value = [_candidate(1), _candidate(2)]
    service = ETFAllocationCommand(
        metadata, StrategyArtifactService(SQLiteStrategyArtifactReader(pool), writer)
    )
    try:
        first = service.save(_request())
        assert first.weights == {1: "0.40000000", 2: "0.40000000"}
        assert first.tracking_exposure == {"CSI300": "0.80000000"}
        assert first.paper_status == "research_only"
        assert service.save(_request()) == first
        assert len(service.list_versions("demo")) == 1
        manual = replace(
            _request(),
            idempotency_key="two",
            parent_version_id=first.version_id,
            mode="manual",
            manual_weights={1: Decimal("0.3"), 2: Decimal("0.5")},
        )
        second = service.save(manual)
        assert second.parent_version_id == first.version_id
        assert second.weights == {1: "0.3", 2: "0.5"}
        assert len(service.list_versions("demo")) == 2
        with pytest.raises(AppConflictError):
            service.save(replace(manual, reason="different"))
        with pytest.raises(AppCommandError, match="must equal one"):
            service.save(
                replace(
                    manual,
                    idempotency_key="three",
                    manual_weights={1: Decimal("0.2"), 2: Decimal("0.5")},
                )
            )
        assert len(service.list_versions("demo")) == 2
    finally:
        pool.close_all()
