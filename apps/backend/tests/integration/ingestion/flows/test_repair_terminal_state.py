"""真实 SQLite 最终账本驱动真实 Prefect 状态，不以返回字典代替 Failed。"""

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ditto_application.processes.ingestion.retry_manager import RetryManager
from ditto_apps.jobs.flows import repair
from ditto_data.ingestion.ingestion_log_store import IngestionLogStore
from ditto_data.models.ingestion import IngestionLog, IngestionResult, IngestionStatus
from ditto_data.storage.runtime.ingestion.ingestion_log_reader import IngestionLogReader
from ditto_data.storage.runtime.ingestion.ingestion_log_writer import IngestionLogWriter
from ditto_platform.foundation import SQLiteClient, SQLitePool


@pytest.mark.usefixtures("prefect_test_session")
@pytest.mark.parametrize("daily", [False, True])
@pytest.mark.parametrize("case", ["current", "healed", "accepted", "permanent"])
def test_final_ledger_controls_prefect_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str, daily: bool
) -> None:
    client = SQLiteClient(SQLitePool(str(tmp_path / "ledger.sqlite")))
    logs = IngestionLogStore(IngestionLogReader(client), IngestionLogWriter(client))
    for day in range(1, 26):
        logs.save_log(
            IngestionLog(
                dataset="etf_nav",
                source="tushare",
                trade_date=f"2014-01-{day:02}",
                status=IngestionStatus.FAIL,
                error_code="SOURCE_MISSING",
                attempts=20,
            )
        )
    if case != "accepted":
        logs.save_log(
            IngestionLog(
                dataset="etf_nav",
                source="tushare",
                trade_date="2026-11-05",
                status=IngestionStatus.FAIL,
                error_code="UNKNOWN_ERROR" if case == "permanent" else "FETCH_ERROR",
                attempts=20 if case == "permanent" else 1,
            )
        )
    coordinator = MagicMock()

    def heal(*, dataset: str, trade_date: str, force: bool) -> IngestionResult:
        assert force
        logs.save_log(
            IngestionLog(
                dataset=dataset,
                source="tushare",
                trade_date=trade_date,
                status=IngestionStatus.SUCCESS,
                rows=1,
            )
        )
        return IngestionResult(
            dataset=dataset, trade_date=trade_date, status="success", row_count=1
        )

    coordinator.ingest_date.side_effect = heal
    manager = RetryManager(coordinator, logs)
    backfill = MagicMock()

    def repair_sibling(**kwargs: object) -> SimpleNamespace:
        if case == "healed":
            heal(dataset="etf_nav", trade_date="2026-11-05", force=True)
        return SimpleNamespace(
            dataset="etf_nav", total_dates=1, success_count=1, failed_count=0
        )

    backfill.backfill_missing.side_effect = repair_sibling
    monkeypatch.setattr(
        repair,
        "create_ingestion_bundle",
        lambda **kwargs: nullcontext(
            SimpleNamespace(
                retry_manager=manager,
                backfill_manager=backfill,
                metadata_facade=SimpleNamespace(
                    list_trading_days=lambda *args: ["2026-11-05"]
                ),
            )
        ),
    )
    accepted = [
        {
            "dataset": "etf_nav",
            "source": "tushare",
            "start": "2014-01-01",
            "end": "2014-01-25",
            "error_code": "SOURCE_MISSING",
            "evidence": "fixture:decision",
        }
    ]
    if daily:
        state = repair.daily_repair_flow(
            datasets=["etf_nav"],
            retry_limit=0,
            required_dates=("2026-11-05", "2026-11-05"),
            accepted_gaps=accepted,
            return_state=True,
        )
    else:
        state = repair.retry_failed_flow(
            dataset="etf_nav",
            limit=1 if case == "healed" else 0,
            required_start="2026-11-05",
            required_end="2026-11-05",
            accepted_gaps=accepted,
            return_state=True,
        )
    assert state.is_completed() == (case in {"healed", "accepted"})
    assert state.is_failed() == (case in {"current", "permanent"})
    if case == "accepted" and not daily:
        normal = repair.retry_failed_flow(
            dataset="etf_nav", limit=0, accepted_gaps=accepted, return_state=True
        )
        assert normal.is_completed()
        research = repair.retry_failed_flow(
            dataset="etf_nav",
            limit=0,
            required_start="2014-01-01",
            required_end="2014-01-25",
            accepted_gaps=accepted,
            return_state=True,
        )
        assert research.is_failed()
    assert len(logs.list_unresolved_failures(limit=-1)) >= 25
    client.conn.close()
