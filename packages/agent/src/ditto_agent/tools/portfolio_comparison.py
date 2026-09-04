"""Read-only three-portfolio comparison and deterministic scenario tools."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Literal, cast

from ditto_application.queries.portfolio_comparison_evidence_contracts import (
    PortfolioComparisonEvidenceIdentity,
    PortfolioComparisonEvidenceQueryPort,
    PortfolioScenarioEvidenceQueryPort,
    PortfolioScenarioEvidenceRequest,
)

from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext
from ditto_agent.models.port import ModelToolSpec
from ditto_agent.tools._common import (
    Arguments,
    application_context,
    function_spec,
    seal_portfolio_comparison_evidence,
    seal_portfolio_scenario_evidence,
)

_TEXT = {"type": "string", "minLength": 1}
_IDENTITY_PROPERTIES = {
    "strategy_id": _TEXT,
    "model_portfolio_id": _TEXT,
    "paper_account_id": _TEXT,
    "manual_account_id": _TEXT,
    "paper_session_id": _TEXT,
}
_IDENTITY_FIELDS = tuple(_IDENTITY_PROPERTIES)


def _identity(parsed: Arguments) -> PortfolioComparisonEvidenceIdentity:
    return PortfolioComparisonEvidenceIdentity(
        strategy_id=parsed.text("strategy_id"),
        model_portfolio_id=parsed.text("model_portfolio_id"),
        paper_account_id=parsed.text("paper_account_id"),
        manual_account_id=parsed.text("manual_account_id"),
        paper_session_id=parsed.text("paper_session_id"),
    )


def _decimal(arguments: Mapping[str, object], field: str) -> Decimal:
    value = arguments[field]
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be a canonical decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be a canonical decimal string") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def _number(arguments: Mapping[str, object], field: str) -> float:
    value = arguments.get(field, 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number")
    return result


def _instrument_ids(arguments: Mapping[str, object]) -> frozenset[int]:
    raw = arguments["excluded_instrument_ids"]
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise ValueError("excluded_instrument_ids must be an array")
    values = tuple(cast("Sequence[object]", raw))
    if any(
        isinstance(item, bool) or not isinstance(item, int) or item <= 0
        for item in values
    ):
        raise ValueError("excluded_instrument_ids must contain positive integers")
    integers = cast("tuple[int, ...]", values)
    if len(set(integers)) != len(integers):
        raise ValueError("excluded_instrument_ids must be unique")
    return frozenset(integers)


def _industry_shocks(arguments: Mapping[str, object]) -> Mapping[str, float]:
    raw = arguments.get("industry_shocks", {})
    if not isinstance(raw, Mapping):
        raise ValueError("industry_shocks must be an object")
    result: dict[str, float] = {}
    for key, value in cast("Mapping[object, object]", raw).items():
        if not isinstance(key, str) or not key or key.strip() != key:
            raise ValueError("industry_shocks keys must be canonical strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("industry_shocks values must be finite numbers")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("industry_shocks values must be finite numbers")
        result[key] = number
    return dict(sorted(result.items()))


def _baseline_kind(value: str) -> Literal["model", "paper", "manual"]:
    if value not in {"model", "paper", "manual"}:
        raise ValueError("baseline_kind is invalid")
    return cast("Literal['model', 'paper', 'manual']", value)


class PortfolioComparisonEvidenceTool:
    """Read exact Model/Paper/Manual values under host snapshot authority."""

    spec: ModelToolSpec = function_spec(
        name="portfolio_comparison_evidence",
        description=(
            "Read host-computed Model, Paper, and Manual valuation, drift, and "
            "attribution facts for one exact Signal Package and Paper session."
        ),
        properties=_IDENTITY_PROPERTIES,
        required=_IDENTITY_FIELDS,
    )

    def __init__(self, *, facade: PortfolioComparisonEvidenceQueryPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Read comparison facts without model-controlled temporal identities."""
        parsed = Arguments(arguments, required=_IDENTITY_FIELDS)
        result = self._facade.get_comparison_evidence(
            identity=_identity(parsed),
            context=application_context(context),
        )
        return seal_portfolio_comparison_evidence(
            tool_name=self.spec.name,
            read_model=result,
            context=context,
        )


class PortfolioScenarioPreviewTool:
    """Preview constraints and shocks without accepting or applying target weights."""

    spec: ModelToolSpec = function_spec(
        name="portfolio_scenario_preview",
        description=(
            "Ask deterministic Portfolio and Risk services to preview user-selected "
            "constraints and shocks; this tool cannot apply a target or write a ledger."
        ),
        properties={
            **_IDENTITY_PROPERTIES,
            "baseline_kind": {"type": "string", "enum": ["model", "paper", "manual"]},
            "excluded_instrument_ids": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1},
                "uniqueItems": True,
            },
            "max_position_weight": {
                "type": "string",
                "pattern": r"^(?:0(?:\.\d+)?|1(?:\.0+)?)$",
            },
            "cash_reserve_weight": {
                "type": "string",
                "pattern": r"^0(?:\.\d+)?$",
            },
            "market_shock": {"type": "number"},
            "industry_shocks": {
                "type": "object",
                "additionalProperties": {"type": "number"},
            },
        },
        required=(
            *_IDENTITY_FIELDS,
            "baseline_kind",
            "excluded_instrument_ids",
            "max_position_weight",
            "cash_reserve_weight",
        ),
    )

    def __init__(self, *, facade: PortfolioScenarioEvidenceQueryPort) -> None:
        self._facade = facade

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        """Return only the deterministic preview and its authenticated provenance."""
        required = cast("tuple[str, ...]", self.spec.input_schema["required"])
        parsed = Arguments(
            arguments,
            required=required,
            optional=("market_shock", "industry_shocks"),
        )
        baseline_kind = _baseline_kind(parsed.text("baseline_kind"))
        result = self._facade.preview_scenario(
            request=PortfolioScenarioEvidenceRequest(
                identity=_identity(parsed),
                baseline_kind=baseline_kind,
                excluded_instrument_ids=_instrument_ids(arguments),
                max_position_weight=_decimal(arguments, "max_position_weight"),
                cash_reserve_weight=_decimal(arguments, "cash_reserve_weight"),
                market_shock=_number(arguments, "market_shock"),
                industry_shocks=_industry_shocks(arguments),
            ),
            context=application_context(context),
        )
        return seal_portfolio_scenario_evidence(
            tool_name=self.spec.name,
            read_model=result,
            context=context,
        )


__all__ = ["PortfolioComparisonEvidenceTool", "PortfolioScenarioPreviewTool"]
