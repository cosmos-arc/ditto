"""Accelerated real-provider Paper acceptance approval and PIT tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast

import orjson
import polars as pl
import pytest
from ditto_apps.operations.q4_live_account_acceptance import canonical_hash
from ditto_apps.scripts.q4_accelerated_paper_acceptance import (
    approved_accelerated_acceptance_request,
    build_accelerated_acceptance_proposal,
    run_accelerated_paper_acceptance,
    verify_accelerated_acceptance,
)
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore

_GENERATED_AT = datetime(2026, 9, 2, 10, 0, tzinfo=UTC)
_APPROVED_AT = datetime(2026, 9, 2, 10, 5, tzinfo=UTC)


def _open_dates() -> tuple[str, ...]:
    start = date(2026, 8, 5)
    dates: list[str] = []
    cursor = start
    while len(dates) < 21:
        if cursor.weekday() < 5:
            dates.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return tuple(dates)


def _bar(trade_date: str, *, ordinal: int) -> dict[str, object]:
    close = 8.5 + ordinal / 100
    return {
        "source_ticker": "518880.SH",
        "trade_date": trade_date,
        "open": close - 0.01,
        "high": close + 0.02,
        "low": close - 0.03,
        "close": close,
        "pre_close": close - 0.005,
        "volume": 4_510_448.54 + ordinal,
        "amount": 4_118_875.882 + ordinal,
    }


def _bars() -> tuple[dict[str, object], ...]:
    return tuple(
        _bar(trade_date, ordinal=index)
        for index, trade_date in enumerate(_open_dates()[:20], start=1)
    )


def _proposal(tmp_path: Path) -> dict[str, object]:
    return build_accelerated_acceptance_proposal(
        data_root=tmp_path / "accelerated-state",
        evidence_root=tmp_path / "accelerated-evidence",
        generated_at=_GENERATED_AT,
        open_dates=_open_dates(),
        provider_bars=_bars(),
        live_day_approval_hash="8" * 64,
        live_day_evidence_hash="5" * 64,
    )


def _approval_hash(proposal: dict[str, object]) -> str:
    request = cast("dict[str, object]", proposal["exact_acceptance_request"])
    return cast("str", request["approval_hash"])


class _Source:
    def __init__(self, bars: tuple[dict[str, object], ...]) -> None:
        self._bars = {cast("str", item["trade_date"]): dict(item) for item in bars}

    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        del start_date, end_date
        return pl.DataFrame(
            {
                "trade_date": [date.fromisoformat(item) for item in _open_dates()],
                "is_open": [True] * len(_open_dates()),
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


def test_proposal_binds_twenty_closed_provider_days_without_claiming_wall_clock(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    approved = approved_accelerated_acceptance_request(
        proposal,
        approved_request_hash=_approval_hash(proposal),
    )

    assert approved.trade_dates == _open_dates()[:20]
    assert approved.settlement_dates == _open_dates()[1:21]
    assert len(approved.provider_bars) == 20
    assert proposal["acceptance"] == {
        "mode": "accelerated_real_provider_replay",
        "qualifies_as_wall_clock_soak": False,
        "qualifies_as_release_acceptance": True,
        "requires_current_live_day_anchor": True,
    }
    assert proposal["safety"] == {
        "paper_only": True,
        "broker_connections": 0,
        "real_orders": 0,
        "strategy_publishes": 0,
    }


def test_wrong_hash_tamper_and_unclosed_current_day_fail_closed(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    with pytest.raises(ValueError, match="approval hash"):
        approved_accelerated_acceptance_request(
            proposal,
            approved_request_hash="f" * 64,
        )


def test_empty_settlement_calendar_fails_with_contract_error(tmp_path: Path) -> None:
    proposal = _proposal(tmp_path)
    request = cast("dict[str, object]", proposal["exact_acceptance_request"])
    arguments = cast("dict[str, object]", request["arguments"])
    replay = cast("dict[str, object]", arguments["replay"])
    replay["settlement_dates"] = []
    approval_hash = canonical_hash(arguments)
    request["approval_hash"] = approval_hash

    with pytest.raises(ValueError, match="settlement calendar"):
        approved_accelerated_acceptance_request(
            proposal,
            approved_request_hash=approval_hash,
        )

    request = cast("dict[str, object]", proposal["exact_acceptance_request"])
    arguments = cast("dict[str, object]", request["arguments"])
    replay = cast("dict[str, object]", arguments["replay"])
    replay["target_days"] = 19
    with pytest.raises(ValueError, match="approval hash"):
        approved_accelerated_acceptance_request(
            proposal,
            approved_request_hash=_approval_hash(_proposal(tmp_path)),
        )

    bars = list(_bars())
    bars[-1] = _bar("2026-09-02", ordinal=20)
    with pytest.raises(ValueError, match="market close"):
        build_accelerated_acceptance_proposal(
            data_root=tmp_path / "future-state",
            evidence_root=tmp_path / "future-evidence",
            generated_at=datetime(2026, 9, 2, 6, 59, tzinfo=UTC),
            open_dates=(*_open_dates()[:19], "2026-09-02", "2026-09-03"),
            provider_bars=bars,
            live_day_approval_hash="8" * 64,
            live_day_evidence_hash="5" * 64,
        )


@pytest.mark.pit
def test_twenty_day_accelerated_run_is_signed_balanced_and_idempotent(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    approval_hash = _approval_hash(proposal)
    source = _Source(_bars())

    first = run_accelerated_paper_acceptance(
        proposal,
        approved_request_hash=approval_hash,
        operator_id="workspace-user",
        source=source,
        approved_at=_APPROVED_AT,
    )
    replay = run_accelerated_paper_acceptance(
        proposal,
        approved_request_hash=approval_hash,
        operator_id="workspace-user",
        source=source,
        approved_at=_APPROVED_AT + timedelta(minutes=5),
    )

    assert first["accelerated_trading_day_count"] == 20
    assert first["q4_five_day_ready"] is True
    assert first["pap09_twenty_day_release_ready"] is True
    assert first["qualifies_as_wall_clock_soak"] is False
    assert first["qualifies_as_release_acceptance"] is True
    assert first["signature_chain_valid"] is True
    assert replay == first
    assert all(cast("list[bool]", first["daily_reconciliations_balanced"]))

    first_day = orjson.loads(
        (
            tmp_path / "accelerated-evidence" / "days" / f"{_open_dates()[0]}.json"
        ).read_bytes()
    )
    pit = cast("dict[str, object]", first_day["pit"])
    assert pit["decision_uses_same_day_close"] is False
    assert pit["fill_uses_bar_after_observation"] is True
    assert cast(str, pit["decision_at"]) < cast(str, pit["bar_observed_at"])
    assert cast(str, pit["bar_observed_at"]) <= cast(str, pit["execution_at"])

    verified = verify_accelerated_acceptance(
        data_root=tmp_path / "accelerated-state",
        evidence_root=tmp_path / "accelerated-evidence",
        expected_approval_hash=approval_hash,
    )
    assert verified == first

    database = (
        tmp_path / "accelerated-state" / "state" / "q4-account-acceptance.sqlite3"
    )
    with SqlitePaperSessionStore(str(database)) as store:
        assert (
            sum(
                len(store.list_executions(f"pap09-accelerated-session-{trade_date}"))
                for trade_date in _open_dates()[:20]
            )
            == 20
        )


@pytest.mark.pit
def test_live_provider_drift_fails_before_any_accelerated_day_is_counted(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    drifted = list(_bars())
    drifted[0] = _bar(_open_dates()[0], ordinal=99)

    with pytest.raises(ValueError, match="provider bar drifted"):
        run_accelerated_paper_acceptance(
            proposal,
            approved_request_hash=_approval_hash(proposal),
            operator_id="workspace-user",
            source=_Source(tuple(drifted)),
            approved_at=_APPROVED_AT,
        )

    assert not (tmp_path / "accelerated-evidence" / "days").exists()


@pytest.mark.pit
def test_accelerated_run_rejects_contaminated_fresh_root_before_bootstrap(
    tmp_path: Path,
) -> None:
    proposal = _proposal(tmp_path)
    contaminated = tmp_path / "accelerated-state" / "foreign-runtime.sqlite3"
    contaminated.parent.mkdir(parents=True)
    contaminated.write_bytes(b"not part of the approved acceptance runtime")

    with pytest.raises(ValueError, match="fresh data root"):
        run_accelerated_paper_acceptance(
            proposal,
            approved_request_hash=_approval_hash(proposal),
            operator_id="workspace-user",
            source=_Source(_bars()),
            approved_at=_APPROVED_AT,
        )

    assert not (tmp_path / "accelerated-evidence" / "bootstrap.json").exists()
    assert not (tmp_path / "accelerated-evidence" / "days").exists()
