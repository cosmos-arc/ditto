"""Exact approval contract for accelerated real-provider Paper acceptance."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from types import MappingProxyType
from typing import cast

from ditto_apps.operations.q4_live_account_acceptance import (
    INSTRUMENT_CODE,
    SHANGHAI,
    ApprovedAcceptance,
    canonical_bar,
    canonical_hash,
    canonical_text,
    parse_iso_date,
    parse_timestamp,
    rfc3339,
)

__all__ = [
    "ACCELERATED_DAY_SCHEMA",
    "ACCELERATED_PROGRESS_SCHEMA",
    "ApprovedAcceleratedAcceptance",
    "approved_accelerated_acceptance_request",
    "build_accelerated_acceptance_proposal",
]

_SCHEMA = "ditto.q4-accelerated-paper-acceptance-proposal.v1"
ACCELERATED_DAY_SCHEMA = "ditto.pap09-accelerated-provider-replay-day.v1"
ACCELERATED_PROGRESS_SCHEMA = "ditto.pap09-accelerated-provider-replay.v1"
_HASH = re.compile(r"[0-9a-f]{64}")
_TARGET_DAYS = 20
_INSTRUMENT_ID = 2_001_724
_STRATEGY_ID = "seed_etf_industry_rotation"
_PAPER_ACCOUNT_ID = "paper-pap09-accelerated-acceptance"
_OPENING_CASH = "1000000"
_ORDER_QUANTITY = 100
_ACCEPTANCE = {
    "mode": "accelerated_real_provider_replay",
    "qualifies_as_wall_clock_soak": False,
    "qualifies_as_release_acceptance": True,
    "requires_current_live_day_anchor": True,
}
_SAFETY = {
    "paper_only": True,
    "broker_connections": 0,
    "real_orders": 0,
    "strategy_publishes": 0,
}


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    raw = cast("Mapping[object, object]", value)
    if not all(type(key) is str for key in raw):
        raise ValueError(f"{field} must have string keys")
    return cast("Mapping[str, object]", raw)


def _sequence(value: object, *, field: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be an array")
    return cast("Sequence[object]", value)


def _hash(value: object, *, field: str) -> str:
    text = canonical_text(value, field=field)
    if _HASH.fullmatch(text) is None:
        raise ValueError(f"{field} must be a lowercase sha256 digest")
    return text


def _independent_roots(data_root: Path, evidence_root: Path) -> tuple[Path, Path]:
    root = data_root.expanduser().resolve()
    public = evidence_root.expanduser().resolve()
    if root == public or root in public.parents or public in root.parents:
        raise ValueError("data_root and evidence_root must be independent trees")
    return root, public


def _validated_dates(
    open_dates: Sequence[str], provider_bars: Sequence[Mapping[str, object]]
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[dict[str, object], ...]]:
    calendar = tuple(parse_iso_date(item, field="open_dates") for item in open_dates)
    if calendar != tuple(sorted(set(calendar))) or len(calendar) != _TARGET_DAYS + 1:
        raise ValueError(
            "accelerated acceptance requires exactly 21 ordered open dates"
        )
    bars = tuple(canonical_bar(item) for item in provider_bars)
    trade_dates = calendar[:_TARGET_DAYS]
    if (
        len(bars) != _TARGET_DAYS
        or tuple(cast("str", item["trade_date"]) for item in bars) != trade_dates
    ):
        raise ValueError(
            "provider bars must match the exact twenty-day calendar prefix"
        )
    return trade_dates, calendar[1:], bars


def _assert_closed_dates(*, generated_at: datetime, trade_dates: Sequence[str]) -> None:
    generated = parse_timestamp(rfc3339(generated_at), field="generated_at")
    local = generated.astimezone(SHANGHAI)
    local_day = local.date()
    market_close = datetime.combine(local_day, time(15, 0), tzinfo=SHANGHAI)
    for value in trade_dates:
        trade_day = date.fromisoformat(value)
        if trade_day > local_day or (trade_day == local_day and local < market_close):
            raise ValueError("accelerated replay date must be past its market close")


@dataclass(frozen=True, slots=True)
class ApprovedAcceleratedAcceptance:
    """One operator-approved, immutable accelerated replay scope."""

    request_hash: str
    data_root: Path
    evidence_root: Path
    generated_at: datetime
    trade_dates: tuple[str, ...]
    settlement_dates: tuple[str, ...]
    provider_bars: tuple[Mapping[str, object], ...]
    live_day_approval_hash: str
    live_day_evidence_hash: str

    def paper_scope(self) -> ApprovedAcceptance:
        """Project the exact replay scope into the existing Paper runtime contract."""
        first_bar = self.provider_bars[0]
        return ApprovedAcceptance(
            request_hash=self.request_hash,
            data_root=self.data_root,
            evidence_root=self.evidence_root,
            generated_at=self.generated_at,
            instrument_id=_INSTRUMENT_ID,
            instrument_code=INSTRUMENT_CODE,
            strategy_id=_STRATEGY_ID,
            manual_account_id="manual-not-used-by-accelerated-acceptance",
            manual_opening_cash="100000",
            manual_opening_position_quantity=100,
            manual_opening_position_price=format(
                float(cast(float, first_bar["close"])), ".12g"
            ),
            manual_opening_trade_date=self.trade_dates[0],
            manual_original_deposit="5000",
            manual_corrected_deposit="500",
            paper_account_id=_PAPER_ACCOUNT_ID,
            paper_opening_cash=_OPENING_CASH,
            paper_target_days=_TARGET_DAYS,
            paper_order_quantity=_ORDER_QUANTITY,
        )


def build_accelerated_acceptance_proposal(
    *,
    data_root: Path,
    evidence_root: Path,
    generated_at: datetime,
    open_dates: Sequence[str],
    provider_bars: Sequence[Mapping[str, object]],
    live_day_approval_hash: str,
    live_day_evidence_hash: str,
) -> dict[str, object]:
    """Freeze twenty closed Tushare sessions into a read-only approval proposal."""
    generated = parse_timestamp(rfc3339(generated_at), field="generated_at")
    root, public = _independent_roots(data_root, evidence_root)
    trade_dates, settlement_dates, bars = _validated_dates(open_dates, provider_bars)
    _assert_closed_dates(generated_at=generated, trade_dates=trade_dates)
    live_approval = _hash(live_day_approval_hash, field="live_day_approval_hash")
    live_evidence = _hash(live_day_evidence_hash, field="live_day_evidence_hash")
    arguments: dict[str, object] = {
        "operation": "run-accelerated-real-provider-paper-acceptance-v1",
        "data_root": str(root),
        "evidence_root": str(public),
        "generated_at": rfc3339(generated),
        "acceptance": dict(_ACCEPTANCE),
        "live_day_anchor": {
            "approval_hash": live_approval,
            "day_evidence_hash": live_evidence,
        },
        "replay": {
            "provider": "tushare",
            "calendar_dataset": "trade_calendar",
            "market_dataset": "etf_daily",
            "instrument_id": _INSTRUMENT_ID,
            "instrument_code": INSTRUMENT_CODE,
            "strategy_id": _STRATEGY_ID,
            "paper_account_id": _PAPER_ACCOUNT_ID,
            "opening_cash": _OPENING_CASH,
            "order_quantity": _ORDER_QUANTITY,
            "target_days": _TARGET_DAYS,
            "trade_dates": list(trade_dates),
            "settlement_dates": list(settlement_dates),
            "provider_bars": list(bars),
            "provider_bars_hash": canonical_hash(bars),
            "one_session_per_day": True,
            "storage_reopened_per_day": True,
            "restart_replay_required": True,
        },
        "prohibitions": {
            "broker_connection": True,
            "real_order": True,
            "strategy_publish_or_activation": True,
            "claim_wall_clock_soak": True,
            "unclosed_or_future_bar": True,
            "provider_bar_drift": True,
        },
    }
    approval_hash = canonical_hash(arguments)
    return {
        "schema": _SCHEMA,
        "generated_at": rfc3339(generated),
        "status": "pending_operator_approval",
        "acceptance": dict(_ACCEPTANCE),
        "safety": dict(_SAFETY),
        "exact_acceptance_request": {
            "arguments": arguments,
            "approval_hash": approval_hash,
            "requires_exact_approval": True,
            "approval_phrase": f"批准加速账户验收 {approval_hash}",
        },
    }


def approved_accelerated_acceptance_request(  # noqa: C901 - exact approval audit
    proposal: Mapping[str, object], *, approved_request_hash: str
) -> ApprovedAcceleratedAcceptance:
    """Validate an exact accelerated replay approval and reject all drift."""
    if (
        proposal.get("schema") != _SCHEMA
        or proposal.get("status") != "pending_operator_approval"
        or _mapping(proposal.get("acceptance"), field="acceptance") != _ACCEPTANCE
        or _mapping(proposal.get("safety"), field="safety") != _SAFETY
    ):
        raise ValueError("accelerated acceptance proposal boundary is invalid")
    request = _mapping(
        proposal.get("exact_acceptance_request"), field="exact_acceptance_request"
    )
    arguments = _mapping(request.get("arguments"), field="arguments")
    expected = _hash(request.get("approval_hash"), field="approval_hash")
    supplied = _hash(approved_request_hash, field="approved_request_hash")
    if (
        request.get("requires_exact_approval") is not True
        or expected != supplied
        or canonical_hash(arguments) != supplied
    ):
        raise ValueError("operator approval hash does not match accelerated request")
    if (
        _mapping(arguments.get("acceptance"), field="arguments.acceptance")
        != _ACCEPTANCE
    ):
        raise ValueError("accelerated acceptance semantics drifted")
    prohibitions = _mapping(arguments.get("prohibitions"), field="prohibitions")
    if any(value is not True for value in prohibitions.values()):
        raise ValueError("accelerated acceptance safety prohibitions drifted")
    replay = _mapping(arguments.get("replay"), field="replay")
    if (
        replay.get("provider") != "tushare"
        or replay.get("instrument_id") != _INSTRUMENT_ID
        or replay.get("instrument_code") != INSTRUMENT_CODE
        or replay.get("strategy_id") != _STRATEGY_ID
        or replay.get("paper_account_id") != _PAPER_ACCOUNT_ID
        or replay.get("opening_cash") != _OPENING_CASH
        or replay.get("order_quantity") != _ORDER_QUANTITY
        or replay.get("target_days") != _TARGET_DAYS
        or replay.get("one_session_per_day") is not True
        or replay.get("storage_reopened_per_day") is not True
        or replay.get("restart_replay_required") is not True
    ):
        raise ValueError("accelerated replay scope drifted")
    raw_dates = _sequence(replay.get("trade_dates"), field="trade_dates")
    raw_settlements = _sequence(
        replay.get("settlement_dates"), field="settlement_dates"
    )
    raw_bars = _sequence(replay.get("provider_bars"), field="provider_bars")
    if not all(isinstance(item, str) for item in (*raw_dates, *raw_settlements)):
        raise ValueError("accelerated replay dates are invalid")
    if not raw_settlements:
        raise ValueError("accelerated settlement calendar is empty")
    if not all(isinstance(item, Mapping) for item in raw_bars):
        raise ValueError("accelerated replay provider bars are invalid")
    trade_dates, settlement_dates, bars = _validated_dates(
        tuple(cast("Sequence[str]", (*raw_dates, raw_settlements[-1]))),
        tuple(cast("Sequence[Mapping[str, object]]", raw_bars)),
    )
    if settlement_dates != tuple(cast("Sequence[str]", raw_settlements)):
        raise ValueError("accelerated settlement calendar drifted")
    if replay.get("provider_bars_hash") != canonical_hash(bars):
        raise ValueError("accelerated provider bars hash drifted")
    generated = parse_timestamp(arguments.get("generated_at"), field="generated_at")
    _assert_closed_dates(generated_at=generated, trade_dates=trade_dates)
    root, public = _independent_roots(
        Path(canonical_text(arguments.get("data_root"), field="data_root")),
        Path(canonical_text(arguments.get("evidence_root"), field="evidence_root")),
    )
    anchor = _mapping(arguments.get("live_day_anchor"), field="live_day_anchor")
    return ApprovedAcceleratedAcceptance(
        request_hash=supplied,
        data_root=root,
        evidence_root=public,
        generated_at=generated,
        trade_dates=trade_dates,
        settlement_dates=settlement_dates,
        provider_bars=tuple(MappingProxyType(dict(item)) for item in bars),
        live_day_approval_hash=_hash(
            anchor.get("approval_hash"), field="live_day_anchor.approval_hash"
        ),
        live_day_evidence_hash=_hash(
            anchor.get("day_evidence_hash"), field="live_day_anchor.day_evidence_hash"
        ),
    )
