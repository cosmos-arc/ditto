"""Exact-approval contract and authenticated evidence for Q4/PAP-09."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Protocol, cast
from zoneinfo import ZoneInfo

import orjson
import polars as pl

__all__ = [
    "BOOTSTRAP_SCHEMA",
    "DAY_SCHEMA",
    "INSTRUMENT_CODE",
    "SHANGHAI",
    "AcceptanceDayRequest",
    "AcceptanceMarketSource",
    "ApprovedAcceptance",
    "acceptance_state_paths",
    "approved_acceptance_request",
    "atomic_write_json",
    "build_acceptance_proposal",
    "calendar_dates",
    "canonical_bar",
    "canonical_hash",
    "canonical_text",
    "load_json",
    "load_signing_key",
    "parse_iso_date",
    "parse_timestamp",
    "positive_number",
    "reconcile_completed_dates",
    "restore_public_evidence_mirrors",
    "rfc3339",
    "select_next_eligible_trade_date",
    "sign_payload",
    "verify_signed_payload",
    "verify_soak_progress",
]

_SCHEMA = "ditto.q4-live-account-acceptance-proposal.v1"
BOOTSTRAP_SCHEMA = "ditto.q4-live-account-acceptance-bootstrap.v1"
DAY_SCHEMA = "ditto.pap09-real-trading-day.v1"
_PROGRESS_SCHEMA = "ditto.pap09-real-soak-progress.v1"
_HASH = re.compile(r"[0-9a-f]{64}")
SHANGHAI = ZoneInfo("Asia/Shanghai")
_INSTRUMENT_ID = 2_001_724
INSTRUMENT_CODE = "518880.SH"
_MANUAL_ACCOUNT_ID = "manual-q4-owner-acceptance"
_PAPER_ACCOUNT_ID = "paper-pap09-owner-acceptance"
_STRATEGY_ID = "seed_etf_industry_rotation"
_TARGET_DAYS = 20
_Q4_DAYS = 5
_ORDER_QUANTITY = 100
_MANUAL_OPENING_CASH = "100000"
_PAPER_OPENING_CASH = "1000000"
_ORIGINAL_DEPOSIT = "5000"
_CORRECTED_DEPOSIT = "500"
_SIGNING_KEY_BYTES = 32
_MARKET_CLOSE_LOCAL = time(15, 0)


class AcceptanceMarketSource(Protocol):
    """Narrow source seam used only by the apps acceptance entrypoint."""

    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        """Fetch provider trading-calendar rows."""
        ...

    def fetch_etf_daily(
        self,
        trade_date: str | None = None,
        source_ticker: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        """Fetch provider ETF daily bars."""
        ...


@dataclass(frozen=True, slots=True)
class AcceptanceDayRequest:
    """All identities required to record one acceptance trading day."""

    approved: ApprovedAcceptance
    database: Path
    source: AcceptanceMarketSource
    trade_date: str
    settlement_date: str
    now: datetime
    operator_id: str
    session_prefix: str = "pap09-session"
    pause_reason: str = "PAP-09 provider-published EOD complete"


@dataclass(frozen=True, slots=True, kw_only=True)
class ApprovedAcceptance:
    """Validated exact scope for the two state-changing acceptance lanes."""

    request_hash: str
    data_root: Path
    evidence_root: Path
    generated_at: datetime
    instrument_id: int
    instrument_code: str
    strategy_id: str
    manual_account_id: str
    manual_opening_cash: str
    manual_opening_position_quantity: int
    manual_opening_position_price: str
    manual_opening_trade_date: str
    manual_original_deposit: str
    manual_corrected_deposit: str
    paper_account_id: str
    paper_opening_cash: str
    paper_target_days: int
    paper_order_quantity: int


def _canonical_bytes(value: object) -> bytes:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS)


def canonical_hash(value: object) -> str:
    """Return the canonical SHA-256 digest for a JSON-compatible value."""
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    raw = cast("Mapping[object, object]", value)
    if not all(type(key) is str for key in raw):
        raise ValueError(f"{field} must have string keys")
    return cast("Mapping[str, object]", raw)


def canonical_text(value: object, *, field: str) -> str:
    """Validate and return one non-empty canonical text field."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be a non-empty canonical string")
    return value


def _integer(value: object, *, field: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{field} must be an integer")
    return value


def _hash(value: object, *, field: str) -> str:
    text = canonical_text(value, field=field)
    if _HASH.fullmatch(text) is None:
        raise ValueError(f"{field} must be a lowercase sha256 digest")
    return text


def parse_timestamp(value: object, *, field: str) -> datetime:
    """Parse one timezone-aware timestamp and normalize it to UTC."""
    text = canonical_text(value, field=field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an RFC3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def rfc3339(value: datetime) -> str:
    """Render one timezone-aware timestamp in canonical UTC form."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_iso_date(value: object, *, field: str) -> str:
    """Validate and return one canonical ISO calendar date."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    text = canonical_text(value, field=field)
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def positive_number(value: object, *, field: str) -> float:
    """Validate and return one positive finite numeric field."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    number = float(value)
    if number <= 0:
        raise ValueError(f"{field} must be positive")
    return number


def _decimal_text(value: object, *, field: str) -> str:
    text = canonical_text(value, field=field)
    try:
        number = Decimal(text)
    except Exception as exc:
        raise ValueError(f"{field} must be decimal text") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(f"{field} must be a positive finite decimal")
    return format(number, "f")


def canonical_bar(raw: Mapping[str, object]) -> dict[str, object]:
    """Validate and canonicalize the exact acceptance instrument bar."""
    ticker = canonical_text(raw.get("source_ticker"), field="bar.source_ticker")
    if ticker != INSTRUMENT_CODE:
        raise ValueError("provider bar instrument drifted")
    trade_date = parse_iso_date(raw.get("trade_date"), field="bar.trade_date")
    values = {
        field: positive_number(raw.get(field), field=f"bar.{field}")
        for field in (
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "volume",
            "amount",
        )
    }
    if values["high"] < max(values["open"], values["close"]):
        raise ValueError("provider bar high is inconsistent")
    if values["low"] > min(values["open"], values["close"]):
        raise ValueError("provider bar low is inconsistent")
    return {
        "source_ticker": ticker,
        "trade_date": trade_date,
        **values,
    }


def calendar_dates(frame: pl.DataFrame) -> tuple[str, ...]:
    """Return sorted provider-confirmed open dates from a calendar frame."""
    if "trade_date" not in frame.columns or "is_open" not in frame.columns:
        raise ValueError("provider calendar schema is incomplete")
    dates: list[str] = []
    for row in frame.iter_rows(named=True):
        if bool(row["is_open"]):
            raw = row["trade_date"]
            dates.append(
                raw.isoformat()
                if isinstance(raw, date)
                else parse_iso_date(raw, field="calendar.trade_date")
            )
    return tuple(sorted(set(dates)))


def build_acceptance_proposal(
    *,
    data_root: Path,
    evidence_root: Path,
    generated_at: datetime,
    latest_published_bar: Mapping[str, object],
    forecast_open_dates: Sequence[str],
) -> dict[str, object]:
    """Build one read-only proposal that freezes every permitted mutation."""
    generated = parse_timestamp(rfc3339(generated_at), field="generated_at")
    root = data_root.expanduser().resolve()
    public_root = evidence_root.expanduser().resolve()
    if (
        root == public_root
        or root in public_root.parents
        or public_root in root.parents
    ):
        raise ValueError("data_root and evidence_root must be independent trees")
    bar = canonical_bar(latest_published_bar)
    if (
        date.fromisoformat(cast("str", bar["trade_date"]))
        >= generated.astimezone(SHANGHAI).date()
    ):
        raise ValueError("manual opening bar must predate the proposal")
    forecast = tuple(
        sorted(
            {
                parse_iso_date(item, field="forecast_open_dates")
                for item in forecast_open_dates
            }
        )
    )
    if len(forecast) < _TARGET_DAYS:
        raise ValueError("proposal requires at least twenty forecast open dates")
    manual_position_price = format(Decimal(str(bar["close"])), "f")
    arguments: dict[str, object] = {
        "operation": "bootstrap-manual-and-authorize-paper-soak-v1",
        "data_root": str(root),
        "evidence_root": str(public_root),
        "generated_at": rfc3339(generated),
        "operator_authority": "exact_user_approval",
        "manual": {
            "account_id": _MANUAL_ACCOUNT_ID,
            "account_kind": "manual",
            "scope": "dedicated_synthetic_acceptance_account",
            "opening_cash": _MANUAL_OPENING_CASH,
            "opening_position": {
                "instrument_id": _INSTRUMENT_ID,
                "instrument_code": INSTRUMENT_CODE,
                "quantity": 100,
                "price": manual_position_price,
                "trade_date": bar["trade_date"],
                "provider_snapshot_hash": canonical_hash(bar),
            },
            "deposit_correction": {
                "original_amount": _ORIGINAL_DEPOSIT,
                "corrected_amount": _CORRECTED_DEPOSIT,
            },
        },
        "paper": {
            "account_id": _PAPER_ACCOUNT_ID,
            "account_kind": "paper",
            "opening_cash": _PAPER_OPENING_CASH,
            "strategy_id": _STRATEGY_ID,
            "target_real_trading_days": _TARGET_DAYS,
            "q4_minimum_days": _Q4_DAYS,
            "first_day_policy": "first_tushare_open_day_after_approval_local_date",
            "daily_limit": 1,
            "order_side": "buy",
            "order_type": "market",
            "order_quantity": _ORDER_QUANTITY,
            "instrument_id": _INSTRUMENT_ID,
            "instrument_code": INSTRUMENT_CODE,
            "decision_local_time": "08:55:00 Asia/Shanghai",
            "execution_policy": "only_after_trade_day_and_provider_bar_publication",
            "fill_assumption": {
                "assumption_id": "pap09-real-close-v1",
                "version": 1,
                "reference_price_field": "close",
                "slippage_bps": 1.0,
            },
            "rules": {
                "asset_class": "etf",
                "exchange": "XSHG",
                "tick_size": 0.001,
                "lot_size": 100,
                "settlement_cycle": 1,
                "commission_rate": 0.0003,
                "min_commission": 5.0,
                "stamp_duty_rate": 0.0,
                "transfer_fee_rate": 0.00001,
            },
        },
        "provider": {
            "name": "tushare",
            "calendar_dataset": "trade_calendar",
            "market_dataset": "etf_daily",
            "latest_published_bar": bar,
            "latest_published_bar_hash": canonical_hash(bar),
        },
        "evidence_signing": {
            "algorithm": "hmac-sha256",
            "key_bytes": _SIGNING_KEY_BYTES,
            "private_key_storage": "data_root/state/evidence-signing.key",
            "private_key_mode": "0600",
            "private_key_exported": False,
        },
        "prohibitions": {
            "broker_connection": True,
            "real_order": True,
            "strategy_publish_or_activation": True,
            "agent_paper_start": True,
            "agent_manual_write": True,
            "current_or_future_day_backfill": True,
            "more_than_one_day_per_run": True,
        },
    }
    approval_hash = canonical_hash(arguments)
    return {
        "schema": _SCHEMA,
        "generated_at": rfc3339(generated),
        "status": "pending_operator_approval",
        "exact_acceptance_request": {
            "arguments": arguments,
            "approval_hash": approval_hash,
            "requires_exact_approval": True,
            "approval_phrase": f"批准账户验收 {approval_hash}",
        },
        "forecast": {
            "source": "tushare",
            "informational_only": True,
            "first_twenty_open_dates": list(forecast[:_TARGET_DAYS]),
            "runtime_calendar_remains_authoritative": True,
        },
        "safety": {
            "broker_connections": 0,
            "real_orders": 0,
            "publishes_strategy": False,
            "paper_only": True,
            "manual_scope": "dedicated_synthetic_acceptance_account",
        },
    }


def approved_acceptance_request(
    proposal: Mapping[str, object], *, approved_request_hash: str
) -> ApprovedAcceptance:
    """Validate exact operator approval and reject any proposal drift."""
    if proposal.get("schema") != _SCHEMA:
        raise ValueError("Q4 acceptance proposal schema is invalid")
    request = _mapping(
        proposal.get("exact_acceptance_request"), field="exact_acceptance_request"
    )
    arguments = _mapping(request.get("arguments"), field="arguments")
    expected_hash = _hash(request.get("approval_hash"), field="approval_hash")
    supplied_hash = _hash(approved_request_hash, field="approved_request_hash")
    if expected_hash != supplied_hash or canonical_hash(arguments) != supplied_hash:
        raise ValueError(
            "operator approval hash does not match exact acceptance request"
        )
    if request.get("requires_exact_approval") is not True:
        raise ValueError("exact approval requirement is missing")
    prohibitions = _mapping(arguments.get("prohibitions"), field="prohibitions")
    if any(value is not True for value in prohibitions.values()):
        raise ValueError("acceptance safety prohibitions drifted")
    manual = _mapping(arguments.get("manual"), field="manual")
    opening = _mapping(manual.get("opening_position"), field="opening_position")
    correction = _mapping(manual.get("deposit_correction"), field="deposit_correction")
    paper = _mapping(arguments.get("paper"), field="paper")
    provider = _mapping(arguments.get("provider"), field="provider")
    signing = _mapping(arguments.get("evidence_signing"), field="evidence_signing")
    if (
        manual.get("scope") != "dedicated_synthetic_acceptance_account"
        or paper.get("account_kind") != "paper"
        or provider.get("name") != "tushare"
        or signing.get("algorithm") != "hmac-sha256"
        or signing.get("private_key_exported") is not False
    ):
        raise ValueError("acceptance scope drifted")
    return ApprovedAcceptance(
        request_hash=supplied_hash,
        data_root=Path(
            canonical_text(arguments.get("data_root"), field="data_root")
        ).resolve(),
        evidence_root=Path(
            canonical_text(arguments.get("evidence_root"), field="evidence_root")
        ).resolve(),
        generated_at=parse_timestamp(
            arguments.get("generated_at"), field="generated_at"
        ),
        instrument_id=_integer(opening.get("instrument_id"), field="instrument_id"),
        instrument_code=canonical_text(
            opening.get("instrument_code"), field="instrument_code"
        ),
        strategy_id=canonical_text(paper.get("strategy_id"), field="strategy_id"),
        manual_account_id=canonical_text(
            manual.get("account_id"), field="manual.account_id"
        ),
        manual_opening_cash=_decimal_text(
            manual.get("opening_cash"), field="manual.opening_cash"
        ),
        manual_opening_position_quantity=_integer(
            opening.get("quantity"), field="opening.quantity"
        ),
        manual_opening_position_price=_decimal_text(
            opening.get("price"), field="opening.price"
        ),
        manual_opening_trade_date=parse_iso_date(
            opening.get("trade_date"), field="opening.trade_date"
        ),
        manual_original_deposit=_decimal_text(
            correction.get("original_amount"), field="original_amount"
        ),
        manual_corrected_deposit=_decimal_text(
            correction.get("corrected_amount"), field="corrected_amount"
        ),
        paper_account_id=canonical_text(
            paper.get("account_id"), field="paper.account_id"
        ),
        paper_opening_cash=_decimal_text(
            paper.get("opening_cash"), field="paper.opening_cash"
        ),
        paper_target_days=_integer(
            paper.get("target_real_trading_days"), field="target_real_trading_days"
        ),
        paper_order_quantity=_integer(
            paper.get("order_quantity"), field="order_quantity"
        ),
    )


def select_next_eligible_trade_date(
    *,
    open_dates: Sequence[str],
    completed_dates: Sequence[str],
    approval_at: datetime,
    now: datetime,
    target_days: int,
    allow_current_closed_day: bool = False,
) -> str | None:
    """Return the next provider-calendar prefix member after its market close."""
    approved = parse_timestamp(rfc3339(approval_at), field="approval_at")
    observed = parse_timestamp(rfc3339(now), field="now")
    if observed < approved:
        raise ValueError("execution time cannot precede approval")
    approval_day = approved.astimezone(SHANGHAI).date()
    execution_day = observed.astimezone(SHANGHAI).date()
    market_close = datetime.combine(
        execution_day,
        _MARKET_CLOSE_LOCAL,
        tzinfo=SHANGHAI,
    ).astimezone(UTC)
    current_day_is_closed = observed >= market_close
    ordered_open = tuple(
        sorted({parse_iso_date(item, field="open_dates") for item in open_dates})
    )
    eligible = tuple(
        item
        for item in ordered_open
        if date.fromisoformat(item)
        >= (
            approval_day
            if allow_current_closed_day
            else approval_day + timedelta(days=1)
        )
        and (
            date.fromisoformat(item) < execution_day
            or (
                allow_current_closed_day
                and date.fromisoformat(item) == execution_day
                and current_day_is_closed
            )
        )
    )
    completed = tuple(
        parse_iso_date(item, field="completed_dates") for item in completed_dates
    )
    if any(
        date.fromisoformat(item) > execution_day
        or (
            date.fromisoformat(item) == execution_day
            and not (allow_current_closed_day and current_day_is_closed)
        )
        for item in completed
    ):
        raise ValueError("completed soak evidence contains a current or future day")
    if completed != eligible[: len(completed)]:
        raise ValueError(
            "completed soak dates must be a strict provider-calendar prefix"
        )
    if len(completed) >= target_days:
        return None
    return eligible[len(completed)] if len(completed) < len(eligible) else None


def reconcile_completed_dates(
    progress: Mapping[str, object],
    *,
    database_completed: Sequence[str],
) -> tuple[str, ...]:
    """Trust signed evidence as the count and admit one recoverable DB-only day."""
    completed = _progress_dates(progress)
    persisted = tuple(database_completed)
    if persisted[: len(completed)] != completed:
        raise ValueError("signed evidence and Paper database prefix drifted")
    if len(persisted) > len(completed) + 1:
        raise ValueError("more than one Paper database day lacks signed evidence")
    return completed


def _progress_dates(progress: Mapping[str, object]) -> tuple[str, ...]:
    raw_completed = progress.get("trade_dates")
    if not isinstance(raw_completed, list):
        raise ValueError("signed soak progress trade dates are invalid")
    completed_items = cast("list[object]", raw_completed)
    if not all(isinstance(item, str) for item in completed_items):
        raise ValueError("signed soak progress trade dates are invalid")
    return tuple(cast("list[str]", completed_items))


def acceptance_state_paths(approved: ApprovedAcceptance) -> tuple[Path, Path, Path]:
    """Return the approved database, signing-key, and bootstrap paths."""
    state = approved.data_root / "state"
    return (
        state / "q4-account-acceptance.sqlite3",
        state / "evidence-signing.key",
        approved.data_root / "evidence" / "bootstrap.json",
    )


def atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    """Write canonical JSON atomically with private default permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (
        orjson.dumps(payload, option=orjson.OPT_SORT_KEYS | orjson.OPT_INDENT_2) + b"\n"
    )
    descriptor, temporary = (
        os.open(
            path.parent / f".{path.name}.{os.getpid()}.tmp",
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        ),
        path.parent / f".{path.name}.{os.getpid()}.tmp",
    )
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    temporary.replace(path)


def load_json(path: Path, *, field: str) -> dict[str, object]:
    """Load one required JSON object from disk."""
    try:
        decoded: object = orjson.loads(path.read_bytes())
    except FileNotFoundError as exc:
        raise ValueError(f"{field} is missing") from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"{field} must be an object")
    return cast("dict[str, object]", decoded)


def load_signing_key(path: Path, *, create: bool) -> bytes:
    """Create or load the private acceptance evidence signing key."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        if not create:
            raise ValueError("acceptance evidence signing key is missing")
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(descriptor, os.urandom(_SIGNING_KEY_BYTES))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    path.chmod(0o600)
    key = path.read_bytes()
    if len(key) != _SIGNING_KEY_BYTES:
        raise ValueError("acceptance evidence signing key is invalid")
    return key


def sign_payload(
    payload: Mapping[str, object],
    *,
    key: bytes,
    approval_hash: str,
    previous_signature: str | None,
) -> dict[str, object]:
    """Attach an approval-bound chained HMAC signature to one payload."""
    payload_hash = canonical_hash(payload)
    signed_message = {
        "approval_hash": approval_hash,
        "payload_hash": payload_hash,
        "previous_signature": previous_signature,
    }
    signature = hmac.new(
        key, _canonical_bytes(signed_message), hashlib.sha256
    ).hexdigest()
    return {
        **payload,
        "signature": {
            "algorithm": "hmac-sha256",
            "approval_hash": approval_hash,
            "payload_hash": payload_hash,
            "previous_signature": previous_signature,
            "value": signature,
        },
    }


def verify_signed_payload(
    payload: Mapping[str, object],
    *,
    key: bytes,
    approval_hash: str,
    previous_signature: str | None,
) -> str:
    """Verify one approval-bound chained payload and return its signature."""
    signature = _mapping(payload.get("signature"), field="signature")
    unsigned = {key_: value for key_, value in payload.items() if key_ != "signature"}
    payload_hash = canonical_hash(unsigned)
    if (
        signature.get("algorithm") != "hmac-sha256"
        or signature.get("approval_hash") != approval_hash
        or signature.get("payload_hash") != payload_hash
        or signature.get("previous_signature") != previous_signature
    ):
        raise ValueError("acceptance evidence signature metadata is invalid")
    expected = hmac.new(
        key,
        _canonical_bytes(
            {
                "approval_hash": approval_hash,
                "payload_hash": payload_hash,
                "previous_signature": previous_signature,
            }
        ),
        hashlib.sha256,
    ).hexdigest()
    actual = _hash(signature.get("value"), field="signature.value")
    if not hmac.compare_digest(expected, actual):
        raise ValueError("acceptance evidence signature is invalid")
    return actual


def verify_soak_progress(
    *,
    data_root: Path,
    evidence_root: Path,
    expected_approval_hash: str,
    require_public: bool = True,
) -> dict[str, object]:
    """Verify the private HMAC chain and return a public progress projection."""
    approval_hash = _hash(expected_approval_hash, field="expected_approval_hash")
    root = data_root.expanduser().resolve()
    public_root = evidence_root.expanduser().resolve()
    key = load_signing_key(root / "state" / "evidence-signing.key", create=False)
    bootstrap = load_json(root / "evidence" / "bootstrap.json", field="bootstrap")
    signature = verify_signed_payload(
        bootstrap,
        key=key,
        approval_hash=approval_hash,
        previous_signature=None,
    )
    durable_bootstrap = root / "evidence" / "bootstrap.json"
    public_bootstrap = public_root / "bootstrap.json"
    if require_public and not public_bootstrap.exists():
        raise ValueError("public bootstrap evidence is missing")
    if public_bootstrap.exists() and public_bootstrap.read_bytes() != (
        durable_bootstrap.read_bytes()
    ):
        raise ValueError("public and durable bootstrap evidence drifted")
    day_root = root / "evidence" / "days"
    day_paths = sorted(day_root.glob("*.json")) if day_root.exists() else []
    dates: list[str] = []
    public_hashes: list[str] = []
    for path in day_paths:
        payload = load_json(path, field=f"day evidence {path.name}")
        trade_date = parse_iso_date(payload.get("trade_date"), field="trade_date")
        if path.stem != trade_date:
            raise ValueError("day evidence filename does not match trade_date")
        signature = verify_signed_payload(
            payload,
            key=key,
            approval_hash=approval_hash,
            previous_signature=signature,
        )
        public = public_root / "days" / path.name
        if require_public and not public.exists():
            raise ValueError(f"public day evidence is missing: {trade_date}")
        if public.exists() and public.read_bytes() != path.read_bytes():
            raise ValueError("public and durable day evidence drifted")
        dates.append(trade_date)
        public_hashes.append(canonical_hash(payload))
    if dates != sorted(set(dates)):
        raise ValueError("day evidence dates are not unique and ordered")
    count = len(dates)
    return {
        "schema": _PROGRESS_SCHEMA,
        "status": "passed",
        "approval_hash": approval_hash,
        "real_trading_day_count": count,
        "trade_dates": dates,
        "day_evidence_hashes": public_hashes,
        "signature_chain_valid": True,
        "signature_chain_head": signature,
        "q4_five_day_ready": count >= _Q4_DAYS,
        "pap09_twenty_day_complete": count >= _TARGET_DAYS,
        "remaining_real_trading_days": max(0, _TARGET_DAYS - count),
        "safety": {
            "paper_only": True,
            "broker_connections": 0,
            "real_orders": 0,
        },
    }


def restore_public_evidence_mirrors(
    *,
    data_root: Path,
    evidence_root: Path,
    progress: Mapping[str, object],
) -> None:
    """Heal missing public mirrors after durable signatures have been verified."""
    root = data_root.expanduser().resolve()
    public_root = evidence_root.expanduser().resolve()
    bootstrap = load_json(root / "evidence" / "bootstrap.json", field="bootstrap")
    atomic_write_json(public_root / "bootstrap.json", bootstrap)
    for trade_date in _progress_dates(progress):
        payload = load_json(
            root / "evidence" / "days" / f"{trade_date}.json",
            field=f"day evidence {trade_date}",
        )
        atomic_write_json(public_root / "days" / f"{trade_date}.json", payload)
