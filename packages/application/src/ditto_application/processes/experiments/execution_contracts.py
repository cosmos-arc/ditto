"""Frozen execution identities and fail-closed research policy contracts."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import NoReturn

import orjson

from ditto_application.exceptions import AppProcessError

__all__ = [
    "EvidenceSource",
    "ExactResearchSnapshot",
    "ExactStrategyIdentity",
    "ExactUniverseIdentity",
    "FeeAssumption",
    "MissingExecutionEvidenceAction",
    "ResearchAssetLane",
    "ResearchExecutionPolicy",
    "SettlementAssumption",
    "SlippageAssumption",
    "TradingRulesAssumption",
    "default_etf_execution_policy",
    "default_stock_execution_policy",
]

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _raise_contract_error(
    message: str,
    *,
    reason: str,
    code: str = "SPEC_INVALID",
    **details: object,
) -> NoReturn:
    payload: dict[str, object] = {"code": code, "reason": reason}
    payload.update(details)
    raise AppProcessError(message, details=payload)


def _canonical_identity(value: object, *, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        _raise_contract_error(
            f"{field_name} must be a canonical non-empty string",
            reason="invalid_canonical_identity",
            field=field_name,
        )
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        _raise_contract_error(
            f"{field_name} must have a canonical UTF-8 identity",
            reason="invalid_canonical_identity",
            field=field_name,
        )
    return value


def _positive_version(value: object, *, field_name: str, reason: str) -> int:
    if type(value) is not int or value <= 0:
        _raise_contract_error(
            f"{field_name} must be a positive integer",
            reason=reason,
            field=field_name,
        )
    return value


def _content_hash(value: object, *, field_name: str) -> str:
    if type(value) is not str or _SHA256_PATTERN.fullmatch(value) is None:
        _raise_contract_error(
            f"{field_name} must be a lowercase SHA-256 digest",
            reason="invalid_content_hash",
            field=field_name,
        )
    return value


def _canonical_hash(payload: Mapping[str, object]) -> str:
    try:
        encoded = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AppProcessError(
            "research execution contract has no canonical JSON identity",
            details={
                "code": "SPEC_INVALID",
                "reason": "invalid_execution_contract_identity",
                "codec_error": type(exc).__name__,
            },
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _contract_key(value: object, *, field_name: str) -> str:
    return _canonical_identity(value, field_name=field_name)


@dataclass(frozen=True, slots=True)
class ExactStrategyIdentity:
    """Exact strategy family, integer version, and canonical spec hash."""

    strategy_id: str
    version: int
    spec_hash: str
    canonical_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate and hash the complete exact strategy identity."""
        strategy_id = _canonical_identity(self.strategy_id, field_name="strategy_id")
        version = _positive_version(
            self.version,
            field_name="strategy_version",
            reason="invalid_exact_strategy_version",
        )
        spec_hash = _content_hash(self.spec_hash, field_name="strategy_spec_hash")
        object.__setattr__(self, "strategy_id", strategy_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "spec_hash", spec_hash)
        object.__setattr__(
            self,
            "canonical_hash",
            _canonical_hash(self.canonical_payload()),
        )

    @property
    def identity(self) -> str:
        """Return the exact catalog-independent strategy identity."""
        return f"{self.strategy_id}@{self.version}"

    def canonical_payload(self) -> dict[str, object]:
        """Return all strategy execution identity fields."""
        return {
            "spec_hash": self.spec_hash,
            "strategy_id": self.strategy_id,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class ExactResearchSnapshot:
    """Exact certified research snapshot and immutable manifest identity."""

    snapshot_id: str
    manifest_hash: str
    canonical_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate and hash the complete exact snapshot identity."""
        snapshot_id = _canonical_identity(self.snapshot_id, field_name="snapshot_id")
        manifest_hash = _content_hash(
            self.manifest_hash,
            field_name="snapshot_manifest_hash",
        )
        object.__setattr__(self, "snapshot_id", snapshot_id)
        object.__setattr__(self, "manifest_hash", manifest_hash)
        object.__setattr__(
            self,
            "canonical_hash",
            _canonical_hash(self.canonical_payload()),
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return all frozen snapshot identity fields."""
        return {
            "manifest_hash": self.manifest_hash,
            "snapshot_id": self.snapshot_id,
        }


@dataclass(frozen=True, slots=True)
class ExactUniverseIdentity:
    """Exact PIT universe projection consumed by one fold."""

    universe_id: str
    membership_hash: str
    canonical_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate and hash the complete exact universe identity."""
        universe_id = _canonical_identity(self.universe_id, field_name="universe_id")
        membership_hash = _content_hash(
            self.membership_hash,
            field_name="universe_membership_hash",
        )
        object.__setattr__(self, "universe_id", universe_id)
        object.__setattr__(self, "membership_hash", membership_hash)
        object.__setattr__(
            self,
            "canonical_hash",
            _canonical_hash(self.canonical_payload()),
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return all PIT universe identity fields."""
        return {
            "membership_hash": self.membership_hash,
            "universe_id": self.universe_id,
        }


class ResearchAssetLane(StrEnum):
    """Supported R3 A-share research execution lanes."""

    STOCK = "stock"
    ETF = "etf"


class EvidenceSource(StrEnum):
    """Permitted source of time-varying execution evidence."""

    FROZEN_PIT = "frozen_snapshot_pit"


class MissingExecutionEvidenceAction(StrEnum):
    """Stable behavior when a required rule or fee row is absent."""

    FAIL_CLOSED = "fail_closed"
    FALLBACK = "fallback"


def _require_source(value: object, *, field_name: str) -> EvidenceSource:
    if type(value) is not EvidenceSource:
        _raise_contract_error(
            f"{field_name} must be EvidenceSource",
            reason="invalid_execution_evidence_source",
            field=field_name,
        )
    return value


@dataclass(frozen=True, slots=True)
class SettlementAssumption:
    """Versioned settlement model driven only by frozen PIT rules."""

    model_key: str
    model_version: int
    cycle_source: EvidenceSource

    def __post_init__(self) -> None:
        """Reject implicit or unversioned settlement semantics."""
        _contract_key(self.model_key, field_name="settlement.model_key")
        _positive_version(
            self.model_version,
            field_name="settlement.model_version",
            reason="invalid_execution_policy_version",
        )
        _require_source(self.cycle_source, field_name="settlement.cycle_source")

    def canonical_payload(self) -> dict[str, object]:
        """Return complete settlement semantics."""
        return {
            "cycle_source": self.cycle_source.value,
            "model_key": self.model_key,
            "model_version": self.model_version,
        }


@dataclass(frozen=True, slots=True)
class FeeAssumption:
    """Versioned fee model driven only by a frozen PIT schedule."""

    model_key: str
    model_version: int
    schedule_source: EvidenceSource

    def __post_init__(self) -> None:
        """Reject implicit or unversioned fee semantics."""
        _contract_key(self.model_key, field_name="fees.model_key")
        _positive_version(
            self.model_version,
            field_name="fees.model_version",
            reason="invalid_execution_policy_version",
        )
        _require_source(self.schedule_source, field_name="fees.schedule_source")

    def canonical_payload(self) -> dict[str, object]:
        """Return complete fee semantics."""
        return {
            "model_key": self.model_key,
            "model_version": self.model_version,
            "schedule_source": self.schedule_source.value,
        }


@dataclass(frozen=True, slots=True)
class TradingRulesAssumption:
    """Versioned rule contract with no permissive runtime fallback."""

    contract_key: str
    contract_version: int
    required_asset_class: ResearchAssetLane
    instrument_definition_source: EvidenceSource
    trading_rule_source: EvidenceSource
    fee_schedule_source: EvidenceSource
    missing_evidence_action: MissingExecutionEvidenceAction

    def __post_init__(self) -> None:
        """Require typed frozen PIT evidence and fail-closed behavior."""
        _contract_key(self.contract_key, field_name="rules.contract_key")
        _positive_version(
            self.contract_version,
            field_name="rules.contract_version",
            reason="invalid_execution_policy_version",
        )
        if type(self.required_asset_class) is not ResearchAssetLane:
            _raise_contract_error(
                "rules.required_asset_class must be ResearchAssetLane",
                reason="invalid_execution_asset_lane",
            )
        for field_name in (
            "instrument_definition_source",
            "trading_rule_source",
            "fee_schedule_source",
        ):
            _require_source(
                getattr(self, field_name),
                field_name=f"rules.{field_name}",
            )
        if (
            type(self.missing_evidence_action) is not MissingExecutionEvidenceAction
            or self.missing_evidence_action
            is not MissingExecutionEvidenceAction.FAIL_CLOSED
        ):
            _raise_contract_error(
                "research execution evidence cannot use fallback defaults",
                code="REPRODUCIBILITY_FAILED",
                reason="execution_evidence_fallback_forbidden",
            )

    def canonical_payload(self) -> dict[str, object]:
        """Return complete instrument/rule evidence semantics."""
        return {
            "contract_key": self.contract_key,
            "contract_version": self.contract_version,
            "fee_schedule_source": self.fee_schedule_source.value,
            "instrument_definition_source": (self.instrument_definition_source.value),
            "missing_evidence_action": self.missing_evidence_action.value,
            "required_asset_class": self.required_asset_class.value,
            "trading_rule_source": self.trading_rule_source.value,
        }


@dataclass(frozen=True, slots=True)
class SlippageAssumption:
    """Versioned deterministic fixed-basis-point slippage contract."""

    model_key: str
    model_version: int
    basis_points: int

    def __post_init__(self) -> None:
        """Validate deterministic fixed-basis-point slippage semantics."""
        _contract_key(self.model_key, field_name="slippage.model_key")
        _positive_version(
            self.model_version,
            field_name="slippage.model_version",
            reason="invalid_execution_policy_version",
        )
        if type(self.basis_points) is not int or self.basis_points < 0:
            _raise_contract_error(
                "slippage basis_points must be a non-negative integer",
                reason="invalid_slippage_assumption",
            )

    def canonical_payload(self) -> dict[str, object]:
        """Return complete slippage semantics."""
        return {
            "basis_points": self.basis_points,
            "model_key": self.model_key,
            "model_version": self.model_version,
        }


@dataclass(frozen=True, slots=True)
class ResearchExecutionPolicy:
    """Complete versioned execution policy for one research asset lane."""

    policy_id: str
    version: int
    lane: ResearchAssetLane
    settlement: SettlementAssumption
    fees: FeeAssumption
    rules: TradingRulesAssumption
    slippage: SlippageAssumption
    canonical_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate nested contracts and derive the complete policy hash."""
        _canonical_identity(self.policy_id, field_name="execution_policy_id")
        _positive_version(
            self.version,
            field_name="execution_policy_version",
            reason="invalid_execution_policy_version",
        )
        typed_fields = (
            (self.lane, ResearchAssetLane, "lane"),
            (self.settlement, SettlementAssumption, "settlement"),
            (self.fees, FeeAssumption, "fees"),
            (self.rules, TradingRulesAssumption, "rules"),
            (self.slippage, SlippageAssumption, "slippage"),
        )
        for value, expected, field_name in typed_fields:
            if type(value) is not expected:
                _raise_contract_error(
                    f"execution policy {field_name} has the wrong type",
                    reason="invalid_execution_policy_field",
                    field=field_name,
                )
        if self.rules.required_asset_class is not self.lane:
            _raise_contract_error(
                "execution policy lane and rule asset class must match",
                reason="execution_policy_lane_mismatch",
            )
        object.__setattr__(
            self,
            "canonical_hash",
            _canonical_hash(self.canonical_payload()),
        )

    @property
    def identity(self) -> str:
        """Return the stable policy ID and version."""
        return f"{self.policy_id}.v{self.version}"

    def canonical_payload(self) -> dict[str, object]:
        """Return every field that can affect baseline execution."""
        return {
            "fees": self.fees.canonical_payload(),
            "lane": self.lane.value,
            "policy_id": self.policy_id,
            "rules": self.rules.canonical_payload(),
            "settlement": self.settlement.canonical_payload(),
            "slippage": self.slippage.canonical_payload(),
            "version": self.version,
        }


def _default_policy(lane: ResearchAssetLane) -> ResearchExecutionPolicy:
    return ResearchExecutionPolicy(
        policy_id=f"a_share_{lane.value}_daily",
        version=1,
        lane=lane,
        settlement=SettlementAssumption(
            model_key="ditto_backtest.a_share_settlement",
            model_version=1,
            cycle_source=EvidenceSource.FROZEN_PIT,
        ),
        fees=FeeAssumption(
            model_key="ditto_execution.a_share_fee",
            model_version=1,
            schedule_source=EvidenceSource.FROZEN_PIT,
        ),
        rules=TradingRulesAssumption(
            contract_key="ditto_kernel.instrument_rules",
            contract_version=1,
            required_asset_class=lane,
            instrument_definition_source=EvidenceSource.FROZEN_PIT,
            trading_rule_source=EvidenceSource.FROZEN_PIT,
            fee_schedule_source=EvidenceSource.FROZEN_PIT,
            missing_evidence_action=MissingExecutionEvidenceAction.FAIL_CLOSED,
        ),
        slippage=SlippageAssumption(
            model_key="ditto_backtest.fixed_bps_slippage",
            model_version=1,
            basis_points=1,
        ),
    )


def default_stock_execution_policy() -> ResearchExecutionPolicy:
    """Return the immutable v1 A-share stock research policy."""
    return _default_policy(ResearchAssetLane.STOCK)


def default_etf_execution_policy() -> ResearchExecutionPolicy:
    """Return the immutable v1 A-share ETF research policy."""
    return _default_policy(ResearchAssetLane.ETF)
