"""Exact approval contract for the live Model/Paper/Manual closure."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from types import MappingProxyType
from typing import cast

import orjson
import polars as pl
from ditto_platform.foundation import ChecksumCompute

from ditto_apps.operations.q4_live_account_acceptance import (
    SHANGHAI,
    canonical_bar,
    canonical_hash,
    canonical_text,
    load_json,
    parse_timestamp,
    rfc3339,
)

__all__ = [
    "ApprovedLivePortfolioAcceptance",
    "LivePortfolioAcceptanceProposalInput",
    "approved_live_portfolio_acceptance_request",
    "build_live_portfolio_acceptance_proposal",
    "canonical_provider_rows",
    "provider_payload_frame",
]

_SCHEMA = "ditto.q5-live-portfolio-acceptance-proposal.v1"
_HASH = re.compile(r"[0-9a-f]{64}")
_STRATEGY_ID = "seed_etf_industry_rotation"
_STRATEGY_VERSION = 1
_SIGNAL_DATE = "2026-09-02"
_INTENDED_TRADE_DATE = "2026-09-03"
_INSTRUMENT_ID = 2_001_724
_INSTRUMENT_CODE = "518880.SH"
_MAX_TARGET_POSITIONS = 5
_MAX_TARGET_WEIGHT = 0.3
_LICENSE_RECORD_ID = (
    "license:tushare:etf_daily:sha256:"
    "c0f1403a9924d2cc71ad440c08ab743369721661a61d54ecb36637661bbcf6fc"
)
_DATASET_SCHEMA = "etf.daily.v1"
_PAYLOAD_SORT_KEYS = ("trade_date", "instrument_id")
_SAFETY = {
    "broker_connections": 0,
    "real_orders": 0,
    "paper_or_manual_journal_mutations": 0,
    "strategy_governance_mutations": 0,
    "agent_write_tools": 0,
}
_WRITES = {
    "provider_payload_and_snapshot": True,
    "derived_manual_execution_baseline": True,
    "recommendation_run_and_signal_package": True,
    "acceptance_evidence": True,
}
_ROW_FIELDS = (
    "instrument_id",
    "source_ticker",
    "trade_date",
    "knowledge_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "volume",
    "amount",
    "pct_change",
)


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


def _file_hash(path: Path) -> str:
    return canonical_hash(orjson.loads(path.read_bytes()))


def _approved_path(value: object, *, field: str) -> Path:
    text = canonical_text(value, field=field)
    path = Path(text).expanduser()
    resolved = path.resolve(strict=False)
    if not path.is_absolute() or path.is_symlink() or str(resolved) != text:
        raise ValueError(f"{field} path changed after approval")
    return resolved


def _approved_paths(arguments: Mapping[str, object]) -> tuple[Path, Path, Path]:
    data_root = _approved_path(arguments.get("data_root"), field="data_root")
    trading_database = _approved_path(
        arguments.get("trading_database"), field="trading_database"
    )
    evidence_root = _approved_path(
        arguments.get("evidence_root"), field="evidence_root"
    )
    if (
        data_root == evidence_root
        or data_root in evidence_root.parents
        or evidence_root in data_root.parents
    ):
        raise ValueError("approved data_root and evidence_root must remain independent")
    return data_root, trading_database, evidence_root


def _float(value: object, *, field: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{field} is invalid")
    return result


def _canonical_rows(
    provider_rows: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    identities: set[tuple[int, str]] = set()
    for raw in provider_rows:
        missing = tuple(field for field in _ROW_FIELDS if field not in raw)
        if missing:
            raise ValueError(f"provider row fields are missing: {missing}")
        instrument_id = raw["instrument_id"]
        if type(instrument_id) is not int or instrument_id <= 0:
            raise ValueError("provider instrument_id is invalid")
        ticker = canonical_text(raw["source_ticker"], field="source_ticker")
        trade_date = canonical_text(raw["trade_date"], field="trade_date")
        knowledge_date = canonical_text(raw["knowledge_date"], field="knowledge_date")
        date.fromisoformat(trade_date)
        date.fromisoformat(knowledge_date)
        if trade_date != _SIGNAL_DATE:
            raise ValueError("provider row is outside the exact signal date")
        identity = (instrument_id, ticker)
        if identity in identities:
            raise ValueError("provider rows contain a duplicate instrument")
        identities.add(identity)
        row: dict[str, object] = {
            "instrument_id": instrument_id,
            "source_ticker": ticker,
            "trade_date": trade_date,
            "knowledge_date": knowledge_date,
        }
        for field in _ROW_FIELDS[4:]:
            row[field] = _float(
                raw[field],
                field=f"provider.{field}",
                positive=field in {"open", "high", "low", "close", "pre_close"},
            )
        rows.append(row)
    if not rows:
        raise ValueError("provider rows cannot be empty")
    return tuple(sorted(rows, key=lambda item: cast(int, item["instrument_id"])))


def canonical_provider_rows(
    provider_rows: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Normalize exact provider rows for proposal and execution drift checks."""
    return _canonical_rows(provider_rows)


def provider_payload_frame(
    rows: Sequence[Mapping[str, object]], *, observed_at: datetime
) -> pl.DataFrame:
    """Build the exact normalized provider payload used by strategy and PIT reads."""
    canonical = _canonical_rows(rows)
    observed = parse_timestamp(rfc3339(observed_at), field="observed_at")
    return pl.DataFrame(canonical).with_columns(
        pl.col("instrument_id").cast(pl.Int64),
        pl.col("source_ticker").cast(pl.String),
        pl.col("trade_date").str.to_date(),
        pl.col("knowledge_date").str.to_date(),
        pl.lit(observed).alias("published_at"),
        pl.lit(observed).alias("available_at"),
    )


@dataclass(frozen=True, slots=True)
class _ProviderSnapshotIdentity:
    snapshot_id: str
    checksum: str
    payload_uri: str
    schema_version: str
    license_record_id: str


def _provider_snapshot(
    rows: Sequence[Mapping[str, object]],
    *,
    observed_at: datetime,
) -> _ProviderSnapshotIdentity:
    frame = provider_payload_frame(rows, observed_at=observed_at)
    checksum = ChecksumCompute.from_dataframe(frame, _PAYLOAD_SORT_KEYS)
    identity_payload = orjson.dumps(
        [
            "etf_daily",
            "tushare",
            _SIGNAL_DATE,
            _SIGNAL_DATE,
            _DATASET_SCHEMA,
            checksum,
        ]
    )
    return _ProviderSnapshotIdentity(
        snapshot_id=(
            "snapshot:tushare:etf_daily:sha256:"
            f"{hashlib.sha256(identity_payload).hexdigest()}"
        ),
        checksum=checksum,
        payload_uri=f"provider_payloads/tushare/etf_daily/{checksum}.parquet",
        schema_version=_DATASET_SCHEMA,
        license_record_id=_LICENSE_RECORD_ID,
    )


def _validated_targets(
    positions: Mapping[int, float],
    factors: Mapping[int, Mapping[str, float]],
    *,
    provider_ids: set[int],
    cash_target: float,
) -> tuple[dict[str, float], dict[str, dict[str, float]], float]:
    if (
        not 1 <= len(positions) <= _MAX_TARGET_POSITIONS
        or set(positions) - provider_ids
    ):
        raise ValueError(
            "strategy output must contain one to five provider-backed targets"
        )
    normalized_cash = _float(cash_target, field="cash target")
    if normalized_cash < 0 or normalized_cash >= 1:
        raise ValueError("strategy cash target is invalid")
    normalized: dict[str, float] = {}
    for instrument_id, raw_weight in positions.items():
        if type(instrument_id) is not int or instrument_id <= 0:
            raise ValueError("strategy target instrument is invalid")
        weight = _float(raw_weight, field="target weight", positive=True)
        if weight > _MAX_TARGET_WEIGHT:
            raise ValueError("strategy target exceeds the published max weight")
        normalized[str(instrument_id)] = weight
    if sum(normalized.values()) + normalized_cash > 1.0 + 1e-9:
        raise ValueError("strategy target weights and cash exceed one")
    normalized_factors: dict[str, dict[str, float]] = {}
    if set(factors) != set(positions):
        raise ValueError("strategy factor evidence must match selected targets")
    for instrument_id, values in factors.items():
        if set(values) != {"signal_value"}:
            raise ValueError("strategy factor evidence must contain signal_value")
        normalized_factors[str(instrument_id)] = {
            "signal_value": _float(values["signal_value"], field="factor signal_value")
        }
    return (
        dict(sorted(normalized.items())),
        dict(sorted(normalized_factors.items())),
        normalized_cash,
    )


def _validated_evidence(
    *, q3_path: Path, account_path: Path, rows: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    q3 = load_json(q3_path, field="Q3 evidence")
    account = load_json(account_path, field="account evidence")
    selection = _mapping(q3.get("etf_selection"), field="etf_selection")
    candidates = _sequence(selection.get("candidates"), field="etf candidates")
    top = _mapping(candidates[0] if candidates else None, field="top ETF candidate")
    if (
        q3.get("schema") != "ditto.q3-live-discovery.v1"
        or q3.get("passed") is not True
        or top.get("rank") != 1
        or top.get("instrument_id") != _INSTRUMENT_ID
    ):
        raise ValueError("Q3 evidence does not contain the exact passing ETF lineage")
    identity = _mapping(account.get("evidence_identity"), field="account identity")
    step_items = tuple(
        _mapping(cast("Mapping[object, object]", value), field="account step")
        for value in _sequence(account.get("steps"), field="account steps")
        if isinstance(value, Mapping)
    )
    steps = {item.get("step"): item.get("state") for item in step_items}
    safety = _mapping(account.get("safety"), field="account safety")
    if (
        account.get("schema") != "ditto.personal-workstation.ui08-account-acceptance.v1"
        or account.get("status") != "partial_pass"
        or steps.get(7) != "passed"
        or steps.get(8) != "passed"
        or safety.get("broker_connections") != 0
        or safety.get("real_orders") != 0
        or identity.get("trade_date") != _SIGNAL_DATE
        or identity.get("paper_account_id") != "paper-pap09-owner-acceptance"
        or identity.get("paper_session_id") != "pap09-session-2026-09-02"
        or identity.get("manual_account_id") != "manual-q4-owner-acceptance"
        or identity.get("strategy_id") != _STRATEGY_ID
        or identity.get("instrument_id") != _INSTRUMENT_ID
    ):
        raise ValueError("account evidence does not contain the exact safe Day 1 state")
    gold = next(
        (item for item in rows if item.get("instrument_id") == _INSTRUMENT_ID),
        None,
    )
    if gold is None:
        raise ValueError("provider rows lack the Day 1 Paper instrument")
    expected_alias = (
        f"snapshot:tushare:etf_daily:sha256:{canonical_hash(canonical_bar(gold))}"
    )
    if identity.get("provider_snapshot_id") != expected_alias:
        raise ValueError("Paper snapshot alias does not match the exact provider bar")
    return {
        "q3_evidence_path": str(q3_path),
        "q3_evidence_hash": _file_hash(q3_path),
        "selection_run_id": selection.get("run_id"),
        "selection_as_of": selection.get("as_of"),
        "account_evidence_path": str(account_path),
        "account_evidence_hash": _file_hash(account_path),
        "paper_snapshot_alias": expected_alias,
        "paper_ledger_hash": identity.get("paper_ledger_hash"),
        "manual_ledger_hash": identity.get("manual_ledger_hash"),
    }


@dataclass(frozen=True, slots=True)
class ApprovedLivePortfolioAcceptance:
    """Host-revalidated immutable scope for the Q5 portfolio closure."""

    request_hash: str
    data_root: Path
    trading_database: Path
    evidence_root: Path
    observed_at: datetime
    signal_date: str
    intended_trade_date: str
    provider_rows: tuple[Mapping[str, object], ...]
    raw_provider_row_count: int
    provider_snapshot_id: str
    provider_payload_checksum: str
    paper_snapshot_alias: str
    target_positions: Mapping[int, float]
    cash_target: float
    factor_values: Mapping[int, Mapping[str, float]]
    strategy_spec_hash: str
    strategy_universe: str
    q3_evidence_path: Path
    account_evidence_path: Path


@dataclass(frozen=True, slots=True)
class LivePortfolioAcceptanceProposalInput:
    """Complete immutable input used to freeze the exact Q5 write request."""

    data_root: Path
    trading_database: Path
    evidence_root: Path
    generated_at: datetime
    q3_evidence_path: Path
    account_evidence_path: Path
    provider_rows: Sequence[Mapping[str, object]]
    raw_provider_row_count: int
    strategy_spec_hash: str
    strategy_universe: str
    target_positions: Mapping[int, float]
    factor_values: Mapping[int, Mapping[str, float]]
    cash_target: float


def build_live_portfolio_acceptance_proposal(
    request: LivePortfolioAcceptanceProposalInput,
) -> dict[str, object]:
    """Freeze a read-only real-provider strategy preview into an approval request."""
    observed = parse_timestamp(rfc3339(request.generated_at), field="generated_at")
    if observed.astimezone(SHANGHAI).time() < time(15, 0):
        raise ValueError("live portfolio proposal requires a closed signal day")
    rows = _canonical_rows(request.provider_rows)
    raw_count = request.raw_provider_row_count
    if type(raw_count) is not int or raw_count < len(rows):
        raise ValueError("raw provider row count is invalid")
    spec_hash = _hash(request.strategy_spec_hash, field="strategy_spec_hash")
    universe = canonical_text(request.strategy_universe, field="strategy_universe")
    normalized_targets, normalized_factors, normalized_cash = _validated_targets(
        request.target_positions,
        request.factor_values,
        provider_ids={cast(int, item["instrument_id"]) for item in rows},
        cash_target=request.cash_target,
    )
    q3_path = request.q3_evidence_path.expanduser().resolve(strict=True)
    account_path = request.account_evidence_path.expanduser().resolve(strict=True)
    evidence = _validated_evidence(
        q3_path=q3_path,
        account_path=account_path,
        rows=rows,
    )
    root = request.data_root.expanduser().resolve(strict=False)
    trading = request.trading_database.expanduser().resolve(strict=False)
    public = request.evidence_root.expanduser().resolve(strict=False)
    if root == public or root in public.parents or public in root.parents:
        raise ValueError("data_root and evidence_root must be independent trees")
    snapshot = _provider_snapshot(
        rows,
        observed_at=observed,
    )
    arguments: dict[str, object] = {
        "operation": "close-live-model-paper-manual-portfolio-v1",
        "data_root": str(root),
        "trading_database": str(trading),
        "evidence_root": str(public),
        "observed_at": rfc3339(observed),
        "strategy": {
            "strategy_id": _STRATEGY_ID,
            "strategy_version": _STRATEGY_VERSION,
            "spec_hash": spec_hash,
            "universe": universe,
        },
        "decision": {
            "signal_date": _SIGNAL_DATE,
            "intended_trade_date": _INTENDED_TRADE_DATE,
            "account_id": "manual-q4-owner-acceptance",
            "paper_account_id": "paper-pap09-owner-acceptance",
            "paper_session_id": "pap09-session-2026-09-02",
        },
        "provider": {
            "source": "tushare",
            "dataset_id": "etf_daily",
            "raw_provider_row_count": raw_count,
            "provider_rows": list(rows),
            "provider_rows_hash": canonical_hash(rows),
            "snapshot_id": snapshot.snapshot_id,
            "payload_checksum": snapshot.checksum,
            "payload_uri": snapshot.payload_uri,
            "schema_version": snapshot.schema_version,
            "license_record_id": snapshot.license_record_id,
            "paper_snapshot_alias": evidence["paper_snapshot_alias"],
        },
        "expected_strategy_output": {
            "positions": normalized_targets,
            "cash_target": normalized_cash,
            "factor_values": normalized_factors,
        },
        "lineage": evidence,
        "writes": dict(_WRITES),
        "prohibitions": {
            "broker_connection": True,
            "real_order": True,
            "paper_or_manual_journal_write": True,
            "strategy_governance_write": True,
            "agent_write_tool": True,
            "latest_snapshot_fallback": True,
        },
    }
    approval_hash = canonical_hash(arguments)
    return {
        "schema": _SCHEMA,
        "generated_at": rfc3339(observed),
        "status": "pending_operator_approval",
        "safety": dict(_SAFETY),
        "exact_acceptance_request": {
            "arguments": arguments,
            "approval_hash": approval_hash,
            "requires_exact_approval": True,
            "approval_phrase": f"批准组合闭环 {approval_hash}",
        },
    }


def approved_live_portfolio_acceptance_request(  # noqa: C901 - exact approval audit
    proposal: Mapping[str, object], *, approved_request_hash: str
) -> ApprovedLivePortfolioAcceptance:
    """Revalidate the approved scope and reject any evidence or argument drift."""
    if (
        proposal.get("schema") != _SCHEMA
        or proposal.get("status") != "pending_operator_approval"
        or _mapping(proposal.get("safety"), field="safety") != _SAFETY
    ):
        raise ValueError("live portfolio acceptance proposal boundary is invalid")
    request = _mapping(
        proposal.get("exact_acceptance_request"), field="exact_acceptance_request"
    )
    arguments = _mapping(request.get("arguments"), field="arguments")
    expected = _hash(request.get("approval_hash"), field="approval_hash")
    supplied = _hash(approved_request_hash, field="approved_request_hash")
    if (
        request.get("requires_exact_approval") is not True
        or supplied != expected
        or canonical_hash(arguments) != supplied
    ):
        raise ValueError("operator approval hash does not match the exact request")
    if _mapping(arguments.get("writes"), field="writes") != _WRITES:
        raise ValueError("live portfolio acceptance write scope drifted")
    prohibitions = _mapping(arguments.get("prohibitions"), field="prohibitions")
    if any(value is not True for value in prohibitions.values()):
        raise ValueError("live portfolio acceptance prohibitions drifted")
    strategy = _mapping(arguments.get("strategy"), field="strategy")
    decision = _mapping(arguments.get("decision"), field="decision")
    provider = _mapping(arguments.get("provider"), field="provider")
    output = _mapping(
        arguments.get("expected_strategy_output"),
        field="expected_strategy_output",
    )
    if (
        arguments.get("operation") != "close-live-model-paper-manual-portfolio-v1"
        or strategy.get("strategy_id") != _STRATEGY_ID
        or strategy.get("strategy_version") != _STRATEGY_VERSION
        or decision.get("signal_date") != _SIGNAL_DATE
        or decision.get("intended_trade_date") != _INTENDED_TRADE_DATE
        or decision.get("account_id") != "manual-q4-owner-acceptance"
        or decision.get("paper_account_id") != "paper-pap09-owner-acceptance"
        or decision.get("paper_session_id") != "pap09-session-2026-09-02"
        or provider.get("source") != "tushare"
        or provider.get("dataset_id") != "etf_daily"
    ):
        raise ValueError("live portfolio acceptance identity drifted")
    raw_rows = _sequence(provider.get("provider_rows"), field="provider_rows")
    if not all(isinstance(item, Mapping) for item in raw_rows):
        raise ValueError("provider_rows are invalid")
    rows = _canonical_rows(tuple(cast("Sequence[Mapping[str, object]]", raw_rows)))
    if provider.get("provider_rows_hash") != canonical_hash(rows):
        raise ValueError("provider rows hash drifted")
    raw_count = provider.get("raw_provider_row_count")
    if type(raw_count) is not int or raw_count < len(rows):
        raise ValueError("raw provider row count is invalid")
    observed = parse_timestamp(arguments.get("observed_at"), field="observed_at")
    universe = canonical_text(strategy.get("universe"), field="strategy_universe")
    snapshot = _provider_snapshot(
        rows,
        observed_at=observed,
    )
    if (
        provider.get("snapshot_id") != snapshot.snapshot_id
        or provider.get("payload_checksum") != snapshot.checksum
        or provider.get("payload_uri") != snapshot.payload_uri
        or provider.get("schema_version") != snapshot.schema_version
        or provider.get("license_record_id") != snapshot.license_record_id
    ):
        raise ValueError("provider snapshot identity drifted")
    raw_positions = _mapping(output.get("positions"), field="target positions")
    raw_factors = _mapping(output.get("factor_values"), field="factor values")
    positions = {int(key): cast(float, value) for key, value in raw_positions.items()}
    factors = {
        int(key): cast("Mapping[str, float]", _mapping(value, field="factor values"))
        for key, value in raw_factors.items()
    }
    normalized_positions, normalized_factors, normalized_cash = _validated_targets(
        positions,
        factors,
        provider_ids={cast(int, item["instrument_id"]) for item in rows},
        cash_target=cast(float, output.get("cash_target")),
    )
    if (
        raw_positions != normalized_positions
        or raw_factors != normalized_factors
        or output.get("cash_target") != normalized_cash
    ):
        raise ValueError("expected strategy output drifted")
    lineage = _mapping(arguments.get("lineage"), field="lineage")
    q3_path = Path(canonical_text(lineage.get("q3_evidence_path"), field="q3 path"))
    account_path = Path(
        canonical_text(lineage.get("account_evidence_path"), field="account path")
    )
    if _file_hash(q3_path.resolve(strict=True)) != _hash(
        lineage.get("q3_evidence_hash"), field="q3 hash"
    ) or _file_hash(account_path.resolve(strict=True)) != _hash(
        lineage.get("account_evidence_hash"), field="account hash"
    ):
        raise ValueError("source evidence drifted after approval")
    paper_alias = canonical_text(
        provider.get("paper_snapshot_alias"), field="paper_snapshot_alias"
    )
    if lineage.get("paper_snapshot_alias") != paper_alias:
        raise ValueError("Paper snapshot alias lineage drifted")
    data_root, trading_database, evidence_root = _approved_paths(arguments)
    return ApprovedLivePortfolioAcceptance(
        request_hash=supplied,
        data_root=data_root,
        trading_database=trading_database,
        evidence_root=evidence_root,
        observed_at=observed,
        signal_date=_SIGNAL_DATE,
        intended_trade_date=_INTENDED_TRADE_DATE,
        provider_rows=tuple(MappingProxyType(dict(item)) for item in rows),
        raw_provider_row_count=raw_count,
        provider_snapshot_id=snapshot.snapshot_id,
        provider_payload_checksum=snapshot.checksum,
        paper_snapshot_alias=paper_alias,
        target_positions=MappingProxyType(
            {int(key): value for key, value in normalized_positions.items()}
        ),
        cash_target=normalized_cash,
        factor_values=MappingProxyType(
            {
                int(key): MappingProxyType(dict(value))
                for key, value in normalized_factors.items()
            }
        ),
        strategy_spec_hash=_hash(strategy.get("spec_hash"), field="strategy_spec_hash"),
        strategy_universe=universe,
        q3_evidence_path=q3_path.resolve(),
        account_evidence_path=account_path.resolve(),
    )
