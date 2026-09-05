"""Q4/PAP-09 exact approval, PIT, restart, and signed-chain tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import polars as pl
import pytest
from ditto_apps.scripts.q4_live_account_acceptance import (
    approved_acceptance_request,
    bootstrap_approved_acceptance,
    build_acceptance_proposal,
    record_next_paper_day,
    select_next_eligible_trade_date,
    verify_soak_progress,
)
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_execution.storage.sqlite.account_journal import (
    SqliteAccountEventJournal,
)
from ditto_portfolio.account_projection import AccountLedgerRebuilder

_GENERATED_AT = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)
_APPROVED_AT = datetime(2026, 9, 2, 8, 30, tzinfo=UTC)
_SAME_DAY_EXECUTION_AT = datetime(2026, 9, 2, 9, 53, tzinfo=UTC)
_FIRST_EXECUTION_AT = datetime(2026, 9, 4, 0, 30, tzinfo=UTC)
_SECOND_EXECUTION_AT = datetime(2026, 9, 8, 0, 30, tzinfo=UTC)
_CLOSED_DAY_AUTHORIZATION = (
    "operator explicitly requested same-day post-close acceptance"
)


def _bar(trade_date: str, *, close: float = 9.118) -> dict[str, object]:
    return {
        "source_ticker": "518880.SH",
        "trade_date": trade_date,
        "open": close - 0.01,
        "high": close + 0.02,
        "low": close - 0.03,
        "close": close,
        "pre_close": close - 0.005,
        "volume": 4_510_448.54,
        "amount": 4_118_875.882,
    }


def _proposal(tmp_path: Path) -> dict[str, object]:
    return build_acceptance_proposal(
        data_root=tmp_path / "acceptance",
        evidence_root=tmp_path / "tracked-evidence",
        generated_at=_GENERATED_AT,
        latest_published_bar=_bar("2026-09-01"),
        forecast_open_dates=(
            "2026-09-03",
            "2026-09-04",
            "2026-09-07",
            "2026-09-08",
            "2026-09-09",
            "2026-09-10",
            "2026-09-11",
            "2026-09-14",
            "2026-09-15",
            "2026-09-16",
            "2026-09-17",
            "2026-09-18",
            "2026-09-21",
            "2026-09-22",
            "2026-09-23",
            "2026-09-24",
            "2026-09-28",
            "2026-09-29",
            "2026-09-30",
            "2026-10-08",
        ),
    )


def _record(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    assert all(isinstance(key, str) for key in value)
    return value


def _approval_hash(proposal: dict[str, object]) -> str:
    request = _record(proposal["exact_acceptance_request"])
    return cast("str", request["approval_hash"])


class _Source:
    def __init__(self, bars: dict[str, dict[str, object]]) -> None:
        self._bars = bars

    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        del start_date, end_date
        return pl.DataFrame(
            {
                "trade_date": [
                    datetime(2026, 9, 2).date(),
                    datetime(2026, 9, 3).date(),
                    datetime(2026, 9, 4).date(),
                    datetime(2026, 9, 5).date(),
                    datetime(2026, 9, 7).date(),
                    datetime(2026, 9, 8).date(),
                ],
                "is_open": [True, True, True, False, True, True],
            }
        )

    def fetch_etf_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        del trade_date, source_ticker, end_date
        row = self._bars.get(cast("str", start_date))
        return pl.DataFrame([row]) if row is not None else pl.DataFrame()


def test_proposal_binds_manual_paper_provider_and_no_broker_scope(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    approved = approved_acceptance_request(
        proposal,
        approved_request_hash=_approval_hash(proposal),
    )

    assert approved.data_root == (tmp_path / "acceptance").resolve()
    assert approved.paper_target_days == 20
    assert approved.paper_order_quantity == 100
    assert approved.instrument_id == 2_001_724
    assert approved.instrument_code == "518880.SH"
    assert approved.manual_original_deposit == "5000"
    assert approved.manual_corrected_deposit == "500"
    assert proposal["safety"] == {
        "broker_connections": 0,
        "real_orders": 0,
        "publishes_strategy": False,
        "paper_only": True,
        "manual_scope": "dedicated_synthetic_acceptance_account",
    }


def test_wrong_approval_hash_and_post_proposal_tamper_fail_closed(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    with pytest.raises(ValueError, match="approval hash"):
        approved_acceptance_request(proposal, approved_request_hash="f" * 64)

    request = cast("dict[str, object]", proposal["exact_acceptance_request"])
    arguments = cast("dict[str, object]", request["arguments"])
    paper = cast("dict[str, object]", arguments["paper"])
    paper["order_quantity"] = 200
    with pytest.raises(ValueError, match="approval hash"):
        approved_acceptance_request(
            proposal,
            approved_request_hash=_approval_hash(_proposal(tmp_path)),
        )


@pytest.mark.pit
def test_next_day_is_strictly_after_approval_and_execution_date() -> None:
    assert (
        select_next_eligible_trade_date(
            open_dates=("2026-09-02", "2026-09-03", "2026-09-04"),
            completed_dates=(),
            approval_at=_APPROVED_AT,
            now=_FIRST_EXECUTION_AT,
            target_days=20,
        )
        == "2026-09-03"
    )


@pytest.mark.pit
def test_approval_day_requires_explicit_override_and_elapsed_market_close() -> None:
    open_dates = ("2026-09-02", "2026-09-03")

    assert (
        select_next_eligible_trade_date(
            open_dates=open_dates,
            completed_dates=(),
            approval_at=_APPROVED_AT,
            now=_SAME_DAY_EXECUTION_AT,
            target_days=20,
        )
        is None
    )
    assert (
        select_next_eligible_trade_date(
            open_dates=open_dates,
            completed_dates=(),
            approval_at=_APPROVED_AT,
            now=_SAME_DAY_EXECUTION_AT,
            target_days=20,
            allow_current_closed_day=True,
        )
        == "2026-09-02"
    )
    assert (
        select_next_eligible_trade_date(
            open_dates=open_dates,
            completed_dates=(),
            approval_at=datetime(2026, 9, 2, 6, 0, tzinfo=UTC),
            now=datetime(2026, 9, 2, 6, 59, tzinfo=UTC),
            target_days=20,
            allow_current_closed_day=True,
        )
        is None
    )
    assert (
        select_next_eligible_trade_date(
            open_dates=("2026-09-03", "2026-09-04"),
            completed_dates=("2026-09-03",),
            approval_at=_APPROVED_AT,
            now=_FIRST_EXECUTION_AT,
            target_days=20,
        )
        is None
    )


@pytest.mark.pit
def test_soak_chain_rejects_a_gap_or_future_completion() -> None:
    with pytest.raises(ValueError, match="prefix"):
        select_next_eligible_trade_date(
            open_dates=("2026-09-03", "2026-09-04", "2026-09-07"),
            completed_dates=("2026-09-03", "2026-09-07"),
            approval_at=_APPROVED_AT,
            now=_SECOND_EXECUTION_AT,
            target_days=20,
        )
    with pytest.raises(ValueError, match="future"):
        select_next_eligible_trade_date(
            open_dates=("2026-09-03", "2026-09-04"),
            completed_dates=("2026-09-04",),
            approval_at=_APPROVED_AT,
            now=_FIRST_EXECUTION_AT,
            target_days=20,
        )


def test_bootstrap_writes_real_manual_rebuild_but_no_paper_trade(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    approval_hash = _approval_hash(proposal)
    receipt = bootstrap_approved_acceptance(
        proposal,
        approved_request_hash=approval_hash,
        approved_at=_APPROVED_AT,
        operator_id="workspace-user",
    )
    root = tmp_path / "acceptance"
    database = root / "state" / "q4-account-acceptance.sqlite3"

    assert receipt["status"] == "passed"
    assert receipt["request_hash"] == approval_hash
    manual = _record(receipt["manual"])
    paper = _record(receipt["paper"])
    assert manual["event_count"] == 4
    assert manual["cash"] == "100500.00"
    assert manual["position_quantity"] == "100"
    assert paper["session_count"] == 0
    assert paper["execution_count"] == 0
    assert (root / "state" / "evidence-signing.key").stat().st_mode & 0o777 == 0o600

    with (
        SqliteAccountEventJournal(str(database)) as journal,
        SqlitePaperSessionStore(str(database)) as store,
    ):
        account = journal.get_account("manual-q4-owner-acceptance")
        assert account is not None
        events = journal.list_events(account.account_id)
        rebuilt = AccountLedgerRebuilder().rebuild(
            account=account,
            events=events,
            as_of="2026-09-02",
        )
        assert rebuilt.ledger_hash == manual["ledger_hash"]
        assert store.get_session("pap09-session-2026-09-03") is None


def test_bootstrap_recovers_accounts_when_receipt_write_was_interrupted(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    approval_hash = _approval_hash(proposal)
    first = bootstrap_approved_acceptance(
        proposal,
        approved_request_hash=approval_hash,
        approved_at=_APPROVED_AT,
        operator_id="workspace-user",
    )
    (tmp_path / "acceptance" / "evidence" / "bootstrap.json").unlink()
    (tmp_path / "tracked-evidence" / "bootstrap.json").unlink()

    recovered = bootstrap_approved_acceptance(
        proposal,
        approved_request_hash=approval_hash,
        approved_at=_APPROVED_AT + timedelta(minutes=5),
        operator_id="workspace-user",
    )

    assert recovered["approved_at"] == first["approved_at"]
    assert _record(recovered["manual"])["event_count"] == 4
    assert _record(recovered["paper"])["execution_count"] == 0


def test_one_real_day_is_signed_reconciled_restartable_and_idempotent(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    approval_hash = _approval_hash(proposal)
    bootstrap_approved_acceptance(
        proposal,
        approved_request_hash=approval_hash,
        approved_at=_APPROVED_AT,
        operator_id="workspace-user",
    )
    source = _Source(
        {
            "2026-09-03": _bar("2026-09-03", close=9.2),
            "2026-09-04": _bar("2026-09-04", close=9.3),
        }
    )
    evidence_root = tmp_path / "tracked-evidence"

    first = record_next_paper_day(
        proposal,
        approved_request_hash=approval_hash,
        operator_id="workspace-user",
        source=source,
        now=_FIRST_EXECUTION_AT,
        evidence_root=evidence_root,
    )
    replay = record_next_paper_day(
        proposal,
        approved_request_hash=approval_hash,
        operator_id="workspace-user",
        source=source,
        now=_FIRST_EXECUTION_AT,
        evidence_root=evidence_root,
    )
    second = record_next_paper_day(
        proposal,
        approved_request_hash=approval_hash,
        operator_id="workspace-user",
        source=source,
        now=_SECOND_EXECUTION_AT,
        evidence_root=evidence_root,
    )

    assert first["status"] == "recorded"
    assert first["trade_date"] == "2026-09-03"
    first_execution = _record(first["execution"])
    first_pit = _record(first["pit"])
    second_execution = _record(second["execution"])
    assert first_execution["fill_count"] == 1
    assert first_execution["ledger_fill_count"] == 1
    assert first_execution["balanced"] is True
    assert first_execution["session_status"] == "paused"
    assert first_pit["decision_precedes_execution"] is True
    assert replay["status"] == "waiting_for_next_published_day"
    assert replay["completed_days"] == 1
    assert second["trade_date"] == "2026-09-04"
    assert second["real_trading_day_ordinal"] == 2
    assert second_execution["pre_trade_position_quantity"] == 100
    assert (evidence_root / "days" / "2026-09-03.json").is_file()
    assert (evidence_root / "days" / "2026-09-04.json").is_file()

    progress = verify_soak_progress(
        data_root=tmp_path / "acceptance",
        evidence_root=evidence_root,
        expected_approval_hash=approval_hash,
    )
    assert progress["real_trading_day_count"] == 2
    assert progress["signature_chain_valid"] is True
    assert progress["q4_five_day_ready"] is False
    assert progress["pap09_twenty_day_complete"] is False

    database = tmp_path / "acceptance" / "state" / "q4-account-acceptance.sqlite3"
    with SqlitePaperSessionStore(str(database)) as store:
        assert len(store.list_executions("pap09-session-2026-09-03")) == 1
        assert len(store.list_executions("pap09-session-2026-09-04")) == 1


@pytest.mark.pit
def test_explicit_closed_day_override_records_published_approval_day(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    approval_hash = _approval_hash(proposal)
    bootstrap_approved_acceptance(
        proposal,
        approved_request_hash=approval_hash,
        approved_at=_APPROVED_AT,
        operator_id="workspace-user",
    )

    receipt = record_next_paper_day(
        proposal,
        approved_request_hash=approval_hash,
        operator_id="workspace-user",
        source=_Source({"2026-09-02": _bar("2026-09-02", close=9.15)}),
        now=_SAME_DAY_EXECUTION_AT,
        closed_day_authorization=_CLOSED_DAY_AUTHORIZATION,
    )

    assert receipt["trade_date"] == "2026-09-02"
    pit = _record(receipt["pit"])
    assert pit["trade_day_precedes_execution_local_date"] is False
    assert pit["market_close_precedes_recording"] is True
    assert receipt["eligibility_override"] == {
        "kind": "approval_day_after_market_close",
        "operator_authorization": _CLOSED_DAY_AUTHORIZATION,
        "supersedes_first_day_policy": True,
    }


@pytest.mark.pit
def test_later_trading_day_can_be_recorded_after_close_without_reusing_override(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    approval_hash = _approval_hash(proposal)
    bootstrap_approved_acceptance(
        proposal,
        approved_request_hash=approval_hash,
        approved_at=_APPROVED_AT,
        operator_id="workspace-user",
    )
    source = _Source(
        {
            "2026-09-02": _bar("2026-09-02", close=9.15),
            "2026-09-03": _bar("2026-09-03", close=9.2),
        }
    )
    record_next_paper_day(
        proposal,
        approved_request_hash=approval_hash,
        operator_id="workspace-user",
        source=source,
        now=_SAME_DAY_EXECUTION_AT,
        closed_day_authorization=_CLOSED_DAY_AUTHORIZATION,
    )

    receipt = record_next_paper_day(
        proposal,
        approved_request_hash=approval_hash,
        operator_id="workspace-user",
        source=source,
        now=datetime(2026, 9, 3, 9, 0, tzinfo=UTC),
    )

    assert receipt["trade_date"] == "2026-09-03"
    assert _record(receipt["pit"])["market_close_precedes_recording"] is True
    assert "eligibility_override" not in receipt


@pytest.mark.pit
def test_closed_day_override_cannot_backfill_approval_day_later(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    approval_hash = _approval_hash(proposal)
    bootstrap_approved_acceptance(
        proposal,
        approved_request_hash=approval_hash,
        approved_at=_APPROVED_AT,
        operator_id="workspace-user",
    )

    with pytest.raises(ValueError, match="approval local date"):
        record_next_paper_day(
            proposal,
            approved_request_hash=approval_hash,
            operator_id="workspace-user",
            source=_Source({"2026-09-02": _bar("2026-09-02", close=9.15)}),
            now=datetime(2026, 9, 3, 8, 0, tzinfo=UTC),
            closed_day_authorization=_CLOSED_DAY_AUTHORIZATION,
        )


def test_completed_database_day_without_evidence_is_recovered_exactly(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    approval_hash = _approval_hash(proposal)
    bootstrap_approved_acceptance(
        proposal,
        approved_request_hash=approval_hash,
        approved_at=_APPROVED_AT,
        operator_id="workspace-user",
    )
    source = _Source({"2026-09-03": _bar("2026-09-03", close=9.2)})
    first = record_next_paper_day(
        proposal,
        approved_request_hash=approval_hash,
        operator_id="workspace-user",
        source=source,
        now=_FIRST_EXECUTION_AT,
    )
    (tmp_path / "acceptance" / "evidence" / "days" / "2026-09-03.json").unlink()
    (tmp_path / "tracked-evidence" / "days" / "2026-09-03.json").unlink()

    recovered = record_next_paper_day(
        proposal,
        approved_request_hash=approval_hash,
        operator_id="workspace-user",
        source=source,
        now=_FIRST_EXECUTION_AT + timedelta(minutes=5),
    )

    assert recovered["status"] == "recorded"
    assert recovered["trade_date"] == "2026-09-03"
    recovered_pit = _record(recovered["pit"])
    first_pit = _record(first["pit"])
    recovered_signature = _record(recovered["signature"])
    first_signature = _record(first["signature"])
    assert recovered_pit["execution_at"] == first_pit["execution_at"]
    assert recovered_signature["value"] != first_signature["value"]
    progress = verify_soak_progress(
        data_root=tmp_path / "acceptance",
        evidence_root=tmp_path / "tracked-evidence",
        expected_approval_hash=approval_hash,
    )
    assert progress["real_trading_day_count"] == 1


def test_completed_database_day_rejects_revised_provider_bar_on_recovery(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    approval_hash = _approval_hash(proposal)
    bootstrap_approved_acceptance(
        proposal,
        approved_request_hash=approval_hash,
        approved_at=_APPROVED_AT,
        operator_id="workspace-user",
    )
    record_next_paper_day(
        proposal,
        approved_request_hash=approval_hash,
        operator_id="workspace-user",
        source=_Source({"2026-09-03": _bar("2026-09-03", close=9.2)}),
        now=_FIRST_EXECUTION_AT,
    )
    (tmp_path / "acceptance" / "evidence" / "days" / "2026-09-03.json").unlink()
    (tmp_path / "tracked-evidence" / "days" / "2026-09-03.json").unlink()

    with pytest.raises(ValueError, match="provider bar drifted"):
        record_next_paper_day(
            proposal,
            approved_request_hash=approval_hash,
            operator_id="workspace-user",
            source=_Source({"2026-09-03": _bar("2026-09-03", close=9.25)}),
            now=_FIRST_EXECUTION_AT + timedelta(minutes=5),
        )


def test_missing_public_day_mirror_fails_status_and_is_healed_on_replay(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    approval_hash = _approval_hash(proposal)
    bootstrap_approved_acceptance(
        proposal,
        approved_request_hash=approval_hash,
        approved_at=_APPROVED_AT,
        operator_id="workspace-user",
    )
    source = _Source({"2026-09-03": _bar("2026-09-03", close=9.2)})
    record_next_paper_day(
        proposal,
        approved_request_hash=approval_hash,
        operator_id="workspace-user",
        source=source,
        now=_FIRST_EXECUTION_AT,
    )
    public_day = tmp_path / "tracked-evidence" / "days" / "2026-09-03.json"
    public_day.unlink()

    with pytest.raises(ValueError, match="public day evidence is missing"):
        verify_soak_progress(
            data_root=tmp_path / "acceptance",
            evidence_root=tmp_path / "tracked-evidence",
            expected_approval_hash=approval_hash,
        )

    replay = record_next_paper_day(
        proposal,
        approved_request_hash=approval_hash,
        operator_id="workspace-user",
        source=source,
        now=_FIRST_EXECUTION_AT + timedelta(minutes=5),
    )
    assert replay["status"] == "waiting_for_next_published_day"
    assert public_day.is_file()


@pytest.mark.pit
def test_missing_provider_bar_fails_without_counting_the_day(tmp_path: Path) -> None:
    proposal = _proposal(tmp_path)
    approval_hash = _approval_hash(proposal)
    bootstrap_approved_acceptance(
        proposal,
        approved_request_hash=approval_hash,
        approved_at=_APPROVED_AT,
        operator_id="workspace-user",
    )

    with pytest.raises(ValueError, match="published ETF bar"):
        record_next_paper_day(
            proposal,
            approved_request_hash=approval_hash,
            operator_id="workspace-user",
            source=_Source({}),
            now=_FIRST_EXECUTION_AT,
            evidence_root=tmp_path / "tracked-evidence",
        )

    progress = verify_soak_progress(
        data_root=tmp_path / "acceptance",
        evidence_root=tmp_path / "tracked-evidence",
        expected_approval_hash=approval_hash,
    )
    assert progress["real_trading_day_count"] == 0
