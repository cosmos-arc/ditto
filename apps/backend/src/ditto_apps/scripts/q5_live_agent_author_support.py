"""Q5 Author context minimization, validation, and tool composition."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import orjson
from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.models.port import ModelToolSpec
from ditto_agent.tools._common import function_spec
from ditto_agent.tools.author import AuthorDraftStrategyTool
from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.queries.authoring_preview import AuthoringPreviewFacade
from ditto_strategy.models import StrategySpecRecord

from ditto_apps.registry.agent.model_provider import (
    AgentModelCredentialKind,
)

__all__ = [
    "_API_KEY_ENV",
    "_AUTHOR_SPEC_TEMPLATE",
    "_CREDENTIAL_KIND",
    "_EXPECTED_TOOL_CALL_COUNT",
    "_MAX_MODEL_TOKENS",
    "_MAX_OUTPUT_TOKENS",
    "_MODEL_SNAPSHOT",
    "_STRATEGY_ID",
    "_STRATEGY_NAME",
    "LiveAuthorValidationError",
    "_BoundContextTool",
    "_CapturingAuthorDraftTool",
    "_NoBaseCatalog",
    "_api_data",
    "_context",
    "_mapping",
    "_parse_datetime",
    "_plain_mapping",
    "_q3_selection",
    "_seal_section",
    "_validate_author_spec",
    "minimal_author_context",
]

_SELECTED_INDICATORS = frozenset(
    {"historical_volatility", "macd_histogram", "return", "rsi"}
)
_TEMPORAL_FIELDS = ("as_of", "knowledge_cutoff", "publication_cutoff")
_API_KEY_ENV = "DITTO_AGENT_GLM_VALIDATION_API_KEY"
_CREDENTIAL_KIND = AgentModelCredentialKind.GLM_CODING_PLAN_VALIDATION
_MODEL_SNAPSHOT = "glm-5.3-coding-plan-2026-09-02"
_STRATEGY_ID = "agent_etf_518880_rotation"
_STRATEGY_NAME = "518880 黄金 ETF 证据绑定策略"
_MAX_MODEL_TOKENS = 32_768
_MAX_OUTPUT_TOKENS = 8_192
_ALLOWED_SIGNAL_WEIGHTS = {(0.5, 0.3, 0.2), (0.6, 0.2, 0.2)}
_ALLOWED_SIGNALS = ("momentum_1m", "reversal_1w", "volatility_factor")
_EXPECTED_CONSTRAINT_COUNT = 2
_EXPECTED_TOOL_CALL_COUNT = 4
_VALIDATION_REASON_CODES = {
    "Author proposal contains holdout material": "holdout_material_present",
    "Author proposal strategy_id escaped the host scope": "identity_outside_host_scope",
    "Author proposal name escaped the host scope": "identity_outside_host_scope",
    "Author proposal is not the approved ETF template": "template_outside_host_scope",
    "Author proposal universe escaped the selection scope": (
        "universe_outside_host_scope"
    ),
    "Author proposal requested an unapproved dataset": "dataset_outside_host_scope",
    "Author proposal requested an unapproved signal": "signals_outside_frozen_choices",
    "Author proposal signal weights escaped the frozen choices": (
        "signal_weights_outside_frozen_choices"
    ),
    "Author proposal parameters escaped the frozen choices": (
        "parameters_outside_frozen_choices"
    ),
    "Author proposal selector escaped the top-1 scope": "selector_outside_host_scope",
    "Author proposal constraints escaped the frozen shape": (
        "constraints_outside_host_scope"
    ),
    "Author proposal max-weight constraint drifted": "constraints_outside_host_scope",
    "Author proposal changed a frozen field": "frozen_field_drift",
}
_AUTHOR_SPEC_TEMPLATE: dict[str, object] = {
    "strategy_id": _STRATEGY_ID,
    "name": _STRATEGY_NAME,
    "asset_class": "etf",
    "template": "etf_rotation",
    "universe": "csi_etf_broad",
    "benchmark": "000300.SH",
    "required_datasets": ["etf_daily"],
    "signal_expressions": list(_ALLOWED_SIGNALS),
    "signal_weights": [0.5, 0.3, 0.2],
    "scorer": {"method": "rank_then_combine", "params": {}},
    "selector": {"method": "top_k", "params": {"k": 1}},
    "constraints": [
        {
            "type": "max_weight_per_instrument",
            "params": {"max_weight": 1.0},
            "priority": 100,
        },
        {
            "type": "max_turnover",
            "params": {"max_turnover": 0.5},
            "priority": 100,
        },
    ],
    "execution": {
        "method": "calendar",
        "frequency": "M",
        "default_order_type": "market",
        "cost_model": {
            "commission_rate": 0.0003,
            "slippage_bps": 5.0,
            "impact_model": "none",
        },
    },
    "params": {"lookback": 252, "vol_window": 60},
    "param_constraints": [],
    "tags": ["agent-authored", "etf", "gold", "q5"],
}


class LiveAuthorValidationError(RuntimeError):
    """A real Author proposal did not satisfy its governed contract."""


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(
        isinstance(key, str) for key in cast("Mapping[object, object]", value)
    ):
        raise ValueError(f"{field} must be a string-keyed object")
    return cast("Mapping[str, object]", value)


def _sequence(value: object, *, field: str) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be an array")
    return tuple(cast("Sequence[object]", value))


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be non-empty canonical text")
    return value


def _project(value: Mapping[str, object], fields: tuple[str, ...]) -> dict[str, object]:
    return {field: value[field] for field in fields if field in value}


def _snapshot_ids(value: object, *, field: str) -> tuple[str, ...]:
    values = _sequence(value, field=field)
    if not values or not all(isinstance(item, str) and item for item in values):
        raise ValueError(f"{field} must contain snapshot identities")
    return cast("tuple[str, ...]", values)


def _same_temporal_boundary(
    market: Mapping[str, object], technical: Mapping[str, object]
) -> dict[str, str]:
    boundary: dict[str, str] = {}
    for field in _TEMPORAL_FIELDS:
        market_value = _text(market.get(field), field=f"market.{field}")
        technical_value = _text(technical.get(field), field=f"technical.{field}")
        if market_value != technical_value:
            raise ValueError("MarketContext and Technical temporal boundary drifted")
        boundary[field] = market_value
    return boundary


def _contains_holdout_material(value: object, *, root: bool = True) -> bool:
    if isinstance(value, Mapping):
        for key, item in cast("Mapping[object, object]", value).items():
            if (
                isinstance(key, str)
                and "holdout" in key.lower()
                and not (root and key == "holdout_excluded" and item is True)
            ):
                return True
            if _contains_holdout_material(item, root=False):
                return True
        return False
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        sequence = cast("Sequence[object]", value)
        return any(_contains_holdout_material(item, root=False) for item in sequence)
    return False


def minimal_author_context(
    *,
    selection: Mapping[str, object],
    research_case: Mapping[str, object],
    market: Mapping[str, object],
    technical: Mapping[str, object],
) -> dict[str, object]:
    """Project exact Q5 evidence while excluding holdout and raw provider data."""
    selection_run_id = _text(selection.get("run_id"), field="selection.run_id")
    case_selection_id = _text(
        research_case.get("selection_run_id"), field="research_case.selection_run_id"
    )
    technical_selection_id = _text(
        technical.get("selection_run_id"), field="technical.selection_run_id"
    )
    if len({selection_run_id, case_selection_id, technical_selection_id}) != 1:
        raise ValueError("Q5 selection_run_id lineage drifted")

    case_id = _text(research_case.get("case_id"), field="research_case.case_id")
    technical_case_id = _text(
        technical.get("research_case_id"), field="technical.research_case_id"
    )
    if case_id != technical_case_id:
        raise ValueError("Q5 research_case_id lineage drifted")

    candidates = _sequence(selection.get("candidates"), field="selection.candidates")
    if not candidates:
        raise ValueError("Q5 selection has no candidates")
    top = _mapping(candidates[0], field="selection top candidate")
    top_id = top.get("instrument_id")
    if not isinstance(top_id, int) or isinstance(top_id, bool) or top_id < 1:
        raise ValueError("Q5 top candidate has no instrument identity")
    candidate_ids = _sequence(
        research_case.get("candidate_instrument_ids"),
        field="research_case.candidate_instrument_ids",
    )
    if candidate_ids != (top_id,):
        raise ValueError("Q5 ResearchCase is not bound to the top selection candidate")
    if technical.get("instrument_id") != top_id:
        raise ValueError("Q5 Technical snapshot is not bound to the top candidate")

    temporal_boundary = _same_temporal_boundary(market, technical)
    readings = tuple(
        _mapping(item, field="technical reading")
        for item in _sequence(technical.get("readings"), field="technical.readings")
    )
    selected_readings = tuple(
        _project(
            item,
            ("timeframe", "name", "status", "value", "reason", "window"),
        )
        for item in readings
        if item.get("name") in _SELECTED_INDICATORS
    )
    feature_set_id = _text(market.get("feature_set_id"), field="market.feature_set_id")
    technical_snapshot_id = _text(
        technical.get("snapshot_id"), field="technical.snapshot_id"
    )
    payload: dict[str, object] = {
        "schema_version": 1,
        "holdout_excluded": True,
        "temporal_boundary": temporal_boundary,
        "selection": {
            "run_id": selection_run_id,
            "status": selection.get("status"),
            "as_of": selection.get("as_of"),
            "top_candidate": _project(
                top,
                (
                    "rank",
                    "instrument_id",
                    "instrument_name",
                    "industry_id",
                    "score",
                    "factor_contributions",
                ),
            ),
            "source_snapshot_ids": _snapshot_ids(
                selection.get("source_snapshot_ids"),
                field="selection.source_snapshot_ids",
            ),
        },
        "research_case": {
            "case_id": case_id,
            "asset_kind": research_case.get("asset_kind"),
            "objective": research_case.get("objective"),
            "candidate_instrument_ids": (top_id,),
            "content_hash": research_case.get("content_hash"),
            "source_snapshot_ids": _snapshot_ids(
                research_case.get("source_snapshot_ids"),
                field="research_case.source_snapshot_ids",
            ),
        },
        "market_context": {
            "feature_set_id": feature_set_id,
            "status": market.get("status"),
            "regime_label": market.get("regime_label"),
            "regime_score": market.get("regime_score"),
            "metrics": _sequence(market.get("metrics"), field="market.metrics"),
            "drivers": _sequence(market.get("drivers"), field="market.drivers"),
            "impacts": _sequence(market.get("impacts"), field="market.impacts"),
            "missing_inputs": _sequence(
                market.get("missing_inputs"), field="market.missing_inputs"
            ),
            "uncertainties": _sequence(
                market.get("uncertainties"), field="market.uncertainties"
            ),
            "source_snapshot_set_id": market.get("source_snapshot_set_id"),
            "source_snapshot_ids": _snapshot_ids(
                market.get("source_snapshot_ids"),
                field="market.source_snapshot_ids",
            ),
        },
        "technical": {
            "snapshot_id": technical_snapshot_id,
            "status": technical.get("status"),
            "instrument_id": top_id,
            "instrument_name": technical.get("instrument_name"),
            "last_visible_bar_at": technical.get("last_visible_bar_at"),
            "timeframe_summaries": _sequence(
                technical.get("timeframe_summaries"),
                field="technical.timeframe_summaries",
            ),
            "levels": _sequence(technical.get("levels"), field="technical.levels"),
            "conflicts": _sequence(
                technical.get("conflicts"), field="technical.conflicts"
            ),
            "missing_inputs": _sequence(
                technical.get("missing_inputs"), field="technical.missing_inputs"
            ),
            "selected_readings": selected_readings,
            "source_snapshot_ids": _snapshot_ids(
                technical.get("source_snapshot_ids"),
                field="technical.source_snapshot_ids",
            ),
        },
        "lineage": {
            "selection_run_id": selection_run_id,
            "research_case_id": case_id,
            "market_context_feature_set_id": feature_set_id,
            "technical_snapshot_id": technical_snapshot_id,
        },
    }
    if _contains_holdout_material(payload):
        raise ValueError("Q5 Author egress contains holdout material")
    return payload


def _parse_datetime(value: object, *, field: str) -> datetime:
    text = _text(value, field=field)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _plain_mapping(value: Mapping[str, object]) -> dict[str, object]:
    decoded: object = orjson.loads(orjson.dumps(value, option=orjson.OPT_SORT_KEYS))
    return cast("dict[str, object]", decoded)


def _validate_author_identity(spec: Mapping[str, object]) -> None:
    if spec.get("strategy_id") != _STRATEGY_ID:
        raise ValueError("Author proposal strategy_id escaped the host scope")
    if spec.get("name") != _STRATEGY_NAME:
        raise ValueError("Author proposal name escaped the host scope")
    if spec.get("asset_class") != "etf" or spec.get("template") != "etf_rotation":
        raise ValueError("Author proposal is not the approved ETF template")
    if spec.get("universe") != "csi_etf_broad":
        raise ValueError("Author proposal universe escaped the selection scope")
    if spec.get("required_datasets") != ["etf_daily"]:
        raise ValueError("Author proposal requested an unapproved dataset")


def _validate_author_signals(spec: Mapping[str, object]) -> None:
    signals = _sequence(
        spec.get("signal_expressions"), field="Author signal expressions"
    )
    if signals != _ALLOWED_SIGNALS:
        raise ValueError("Author proposal requested an unapproved signal")
    raw_weights = _sequence(spec.get("signal_weights"), field="Author signal weights")
    if raw_weights not in _ALLOWED_SIGNAL_WEIGHTS:
        raise ValueError("Author proposal signal weights escaped the frozen choices")


def _validate_author_parameters(spec: Mapping[str, object]) -> None:
    params = _mapping(spec.get("params"), field="Author proposal params")
    if params.get("lookback") not in {126, 252} or params.get("vol_window") not in {
        20,
        60,
    }:
        raise ValueError("Author proposal parameters escaped the frozen choices")
    selector = _mapping(spec.get("selector"), field="Author proposal selector")
    selector_params = _mapping(
        selector.get("params"), field="Author proposal selector params"
    )
    if selector.get("method") != "top_k" or selector_params.get("k") != 1:
        raise ValueError("Author proposal selector escaped the top-1 scope")


def _validate_author_constraints(spec: Mapping[str, object]) -> None:
    constraints = _sequence(spec.get("constraints"), field="Author constraints")
    if len(constraints) != _EXPECTED_CONSTRAINT_COUNT:
        raise ValueError("Author proposal constraints escaped the frozen shape")
    first = _mapping(constraints[0], field="Author max weight constraint")
    first_params = _mapping(first.get("params"), field="Author max weight params")
    if (
        first.get("type") != "max_weight_per_instrument"
        or first_params.get("max_weight") != 1.0
    ):
        raise ValueError("Author proposal max-weight constraint drifted")


def _validate_author_spec(value: Mapping[str, object]) -> dict[str, object]:
    spec = _plain_mapping(value)
    if _contains_holdout_material(spec):
        raise ValueError("Author proposal contains holdout material")
    _validate_author_identity(spec)
    _validate_author_signals(spec)
    _validate_author_parameters(spec)
    _validate_author_constraints(spec)
    allowed = _plain_mapping(_AUTHOR_SPEC_TEMPLATE)
    allowed["signal_weights"] = spec["signal_weights"]
    allowed["params"] = spec["params"]
    if spec != allowed:
        raise ValueError("Author proposal changed a frozen field")
    return spec


def _safe_author_rejection_reason(exc: Exception) -> str:
    code = _VALIDATION_REASON_CODES.get(
        str(exc), "malformed_or_incomplete_strategy_spec"
    )
    return f"host_rejected_author_proposal:{code}"


def _api_data(path: Path) -> tuple[Mapping[str, object], str]:
    resolved = path.expanduser().resolve(strict=True)
    content = resolved.read_bytes()
    root = _mapping(orjson.loads(content), field=f"API artifact {resolved.name}")
    return _mapping(root.get("data"), field=f"API artifact {resolved.name}.data"), (
        hashlib.sha256(content).hexdigest()
    )


def _q3_selection(path: Path) -> tuple[Mapping[str, object], str]:
    resolved = path.expanduser().resolve(strict=True)
    content = resolved.read_bytes()
    root = _mapping(orjson.loads(content), field=f"Q3 evidence {resolved.name}")
    if root.get("passed") is not True:
        raise ValueError("Q3 evidence is not passing")
    return _mapping(root.get("etf_selection"), field="Q3 ETF selection"), (
        hashlib.sha256(content).hexdigest()
    )


def _context(
    *, payload: Mapping[str, object], decision_time: datetime
) -> TemporalToolContext:
    snapshots: list[str] = []
    for section_name in ("selection", "research_case", "market_context", "technical"):
        section = _mapping(payload.get(section_name), field=section_name)
        snapshots.extend(
            _snapshot_ids(
                section.get("source_snapshot_ids"),
                field=f"{section_name}.source_snapshot_ids",
            )
        )
    snapshot_set_id = aggregate_source_snapshot_ids(tuple(dict.fromkeys(snapshots)))
    if snapshot_set_id is None:
        raise ValueError("Q5 Author context has no source snapshot authority")
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=decision_time,
            knowledge_cutoff=decision_time,
            publication_cutoff=decision_time,
            source_snapshot_id=snapshot_set_id,
            execution_eligible_at="not_applicable",
            allowed_universe=("518880.SH",),
            license_class="approved-research",
            egress_class=EgressClass.CLOUD_ALLOWED,
        )
    )


def _seal_section(
    *,
    tool_name: str,
    kind: str,
    payload: Mapping[str, object],
    context: TemporalToolContext,
    source_hashes: tuple[str, ...],
    lineage: tuple[str, ...],
) -> EvidenceEnvelope:
    result: Mapping[str, object] = {
        "schema_version": 1,
        "kind": kind,
        "redaction_profile": "approved-research-minimal-v1",
        "payload": payload,
    }
    artifact_refs = tuple(f"source-artifact:sha256:{item}" for item in source_hashes)
    sealed_lineage = (
        *lineage,
        "redaction:approved-research-minimal-v1",
        "holdout:excluded",
    )
    identity = canonical_sha256(
        {
            "tool_name": tool_name,
            "result": result,
            "artifact_refs": artifact_refs,
            "context": context.canonical_payload(),
            "lineage": sealed_lineage,
        }
    )
    return EvidenceEnvelope.seal(
        evidence_id=f"evidence-{identity}",
        tool_name=tool_name,
        result=result,
        artifact_refs=artifact_refs,
        temporal_context=context,
        lineage=sealed_lineage,
    )


class _BoundContextTool:
    def __init__(
        self,
        *,
        spec: ModelToolSpec,
        envelope: EvidenceEnvelope,
        expected_arguments: Mapping[str, object],
    ) -> None:
        self._spec = spec
        self.envelope = envelope
        self.expected_arguments = expected_arguments

    @property
    def spec(self) -> ModelToolSpec:
        return self._spec

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        if arguments != self.expected_arguments:
            raise ValueError("Q5 context tool arguments escaped the host scope")
        if context != self.envelope.temporal_context:
            raise ValueError("Q5 context temporal authority drifted")
        return self.envelope


class _NoBaseCatalog:
    def get_spec(
        self, strategy_id: str, version: int | None = None
    ) -> StrategySpecRecord | None:
        del strategy_id, version
        return None

    def list_specs(self) -> list[StrategySpecRecord]:
        return []

    def list_versions(self, strategy_id: str) -> list[StrategySpecRecord]:
        del strategy_id
        return []

    def get_active_published(self, strategy_id: str) -> StrategySpecRecord | None:
        del strategy_id
        return None


class _CapturingAuthorDraftTool:
    def __init__(self) -> None:
        self._delegate = AuthorDraftStrategyTool(
            facade=AuthoringPreviewFacade(catalog=_NoBaseCatalog())
        )
        self._spec = function_spec(
            name=self._delegate.spec.name,
            description=(
                "Choose the three research-bound parameters for a host-frozen ETF "
                "StrategySpec draft."
            ),
            properties={
                "lookback": {"type": "integer", "enum": [126, 252]},
                "vol_window": {"type": "integer", "enum": [20, 60]},
                "signal_weights_choice": {
                    "type": "string",
                    "enum": ["balanced", "momentum_tilt"],
                },
            },
            required=("lookback", "vol_window", "signal_weights_choice"),
        )
        self.arguments: dict[str, object] | None = None
        self.evidence: EvidenceEnvelope | None = None
        self.rejection_reason: str | None = None

    @property
    def spec(self) -> ModelToolSpec:
        return self._spec

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        if self.arguments is not None:
            raise ValueError("Q5 Author draft tool may be called only once")
        try:
            if set(arguments) != {
                "lookback",
                "vol_window",
                "signal_weights_choice",
            }:
                raise ValueError(
                    "Author proposal parameters escaped the frozen choices"
                )
            lookback = arguments.get("lookback")
            vol_window = arguments.get("vol_window")
            weights_choice = arguments.get("signal_weights_choice")
            if (
                not isinstance(lookback, int)
                or isinstance(lookback, bool)
                or lookback not in {126, 252}
                or not isinstance(vol_window, int)
                or isinstance(vol_window, bool)
                or vol_window not in {20, 60}
                or weights_choice not in {"balanced", "momentum_tilt"}
            ):
                raise ValueError(
                    "Author proposal parameters escaped the frozen choices"
                )
            spec = _plain_mapping(_AUTHOR_SPEC_TEMPLATE)
            spec["params"] = {
                "lookback": lookback,
                "vol_window": vol_window,
            }
            spec["signal_weights"] = (
                [0.6, 0.2, 0.2]
                if weights_choice == "momentum_tilt"
                else [0.5, 0.3, 0.2]
            )
            spec = _validate_author_spec(spec)
        except (TypeError, ValueError) as exc:
            self.rejection_reason = _safe_author_rejection_reason(exc)
            raise
        evidence = self._delegate.invoke(
            arguments={"spec_json": spec},
            context=context,
        )
        if evidence.result.get("valid") is not True:
            payload = _mapping(
                evidence.result.get("payload"), field="Author preview payload"
            )
            diagnostics = _sequence(
                payload.get("diagnostics"), field="Author preview diagnostics"
            )
            code = "UNKNOWN"
            if diagnostics:
                first = _mapping(diagnostics[0], field="Author preview diagnostic")
                raw_code = first.get("code")
                if isinstance(raw_code, str) and raw_code.replace("_", "").isalnum():
                    code = raw_code
            self.rejection_reason = f"author_preview_invalid:{code}"
            raise ValueError("Q5 Author draft preview is invalid")
        self.arguments = {"spec_json": spec}
        self.evidence = evidence
        return evidence
