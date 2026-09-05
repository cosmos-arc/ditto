"""Fail-closed boundaries for the Q5 live Author support helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import orjson
import pytest
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext
from ditto_agent.tools.author import AuthorDraftStrategyTool
from ditto_apps.scripts import q5_live_agent_author_support as support


def _inputs() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
]:
    timestamp = "2026-09-01T16:21:00Z"
    selection = {
        "run_id": "selection-run:sha256:selection",
        "status": "ready",
        "as_of": timestamp,
        "source_snapshot_ids": ["snapshot:selection"],
        "candidates": [
            {
                "rank": 1,
                "instrument_id": 2_001_724,
                "instrument_name": "gold-etf",
                "industry_id": "gold",
                "score": 0.8,
                "factor_contributions": [],
            }
        ],
    }
    research_case = {
        "case_id": "research-case:sha256:case",
        "selection_run_id": selection["run_id"],
        "candidate_instrument_ids": [2_001_724],
        "asset_kind": "etf",
        "objective": "PIT ETF research",
        "content_hash": "a" * 64,
        "source_snapshot_ids": ["snapshot:selection"],
    }
    market = {
        "feature_set_id": "market-regime:sha256:market",
        "status": "ready",
        "regime_label": "risk_on",
        "regime_score": 0.2,
        "as_of": timestamp,
        "knowledge_cutoff": timestamp,
        "publication_cutoff": timestamp,
        "metrics": [],
        "drivers": [],
        "impacts": [],
        "missing_inputs": [],
        "uncertainties": [],
        "source_snapshot_set_id": "snapshot-set:market",
        "source_snapshot_ids": ["snapshot:market"],
    }
    technical = {
        "snapshot_id": "technical-analysis:sha256:technical",
        "status": "ready",
        "instrument_id": 2_001_724,
        "instrument_name": "gold-etf",
        "selection_run_id": selection["run_id"],
        "research_case_id": research_case["case_id"],
        "as_of": timestamp,
        "knowledge_cutoff": timestamp,
        "publication_cutoff": timestamp,
        "last_visible_bar_at": timestamp,
        "timeframe_summaries": [],
        "levels": [],
        "conflicts": [],
        "missing_inputs": [],
        "readings": [{"timeframe": "daily", "name": "rsi", "value": 55.0}],
        "source_snapshot_ids": ["snapshot:technical"],
    }
    return selection, research_case, market, technical


def _payload() -> dict[str, object]:
    selection, research_case, market, technical = _inputs()
    return support.minimal_author_context(
        selection=selection,
        research_case=research_case,
        market=market,
        technical=technical,
    )


def _decision_time() -> datetime:
    return datetime(2026, 9, 1, 16, 21, tzinfo=UTC)


def _context() -> TemporalToolContext:
    return support._context(payload=_payload(), decision_time=_decision_time())


def _spec(**overrides: object) -> dict[str, object]:
    spec = support._plain_mapping(support._AUTHOR_SPEC_TEMPLATE)
    spec.update(overrides)
    return spec


def _shape_value(kind: str, value: object) -> object:
    if kind == "mapping":
        return support._mapping(value, field="value")
    if kind == "sequence":
        return support._sequence(value, field="value")
    if kind == "text":
        return support._text(value, field="value")
    return support._snapshot_ids(value, field="value")


@pytest.mark.parametrize(
    ("kind", "value", "message"),
    [
        ("mapping", [], "string-keyed object"),
        ("mapping", {1: "value"}, "string-keyed object"),
        ("sequence", 1, "must be an array"),
        ("sequence", "items", "must be an array"),
        ("text", None, "canonical text"),
        ("text", "", "canonical text"),
        ("text", " padded ", "canonical text"),
        ("snapshots", [], "snapshot identities"),
        ("snapshots", [""], "snapshot identities"),
        ("snapshots", [1], "snapshot identities"),
    ],
)
def test_shape_helpers_reject_ambiguous_host_values(
    kind: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _shape_value(kind, value)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("case_lineage", "research_case_id lineage"),
        ("empty_candidates", "no candidates"),
        ("invalid_top", "no instrument identity"),
        ("case_candidate", "not bound to the top"),
        ("technical_candidate", "not bound to the top"),
    ],
)
def test_minimal_context_rejects_unbound_evidence(case: str, message: str) -> None:
    selection, research_case, market, technical = _inputs()
    if case == "case_lineage":
        technical["research_case_id"] = "research-case:sha256:other"
    elif case == "empty_candidates":
        selection["candidates"] = []
    elif case == "invalid_top":
        selection["candidates"] = [{"instrument_id": True}]
    elif case == "case_candidate":
        research_case["candidate_instrument_ids"] = [2_001_725]
    else:
        technical["instrument_id"] = 2_001_725

    with pytest.raises(ValueError, match=message):
        support.minimal_author_context(
            selection=selection,
            research_case=research_case,
            market=market,
            technical=technical,
        )


def test_minimal_context_rejects_nested_holdout_material() -> None:
    selection, research_case, market, technical = _inputs()
    market["metrics"] = [{"series": [{"holdout_return": 0.99}]}]

    with pytest.raises(ValueError, match="egress contains holdout"):
        support.minimal_author_context(
            selection=selection,
            research_case=research_case,
            market=market,
            technical=technical,
        )


def test_datetime_parser_normalizes_offsets_and_rejects_naive_values() -> None:
    assert (
        support._parse_datetime(
            "2026-09-02T00:21:00+08:00",
            field="decision_time",
        )
        == _decision_time()
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        support._parse_datetime("2026-09-01T16:21:00", field="decision_time")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("strategy_id", "outside", "strategy_id escaped"),
        ("name", "outside", "name escaped"),
        ("asset_class", "stock", "approved ETF template"),
        ("universe", "outside", "universe escaped"),
        ("required_datasets", ["daily"], "unapproved dataset"),
        ("signal_expressions", ["momentum_1m"], "unapproved signal"),
        ("signal_weights", [1.0, 0.0, 0.0], "weights escaped"),
        ("params", {"lookback": 63, "vol_window": 60}, "parameters escaped"),
        (
            "selector",
            {"method": "all", "params": {"k": 1}},
            "selector escaped",
        ),
        ("constraints", [], "constraints escaped"),
    ],
)
def test_author_spec_rejects_values_outside_host_scope(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        support._validate_author_spec(_spec(**{field: value}))


def test_author_spec_rejects_constraint_holdout_and_frozen_field_drift() -> None:
    constraint_spec = _spec()
    constraints = cast("list[dict[str, object]]", constraint_spec["constraints"])
    first_params = cast("dict[str, object]", constraints[0]["params"])
    first_params["max_weight"] = 0.9
    with pytest.raises(ValueError, match="max-weight constraint drifted"):
        support._validate_author_spec(constraint_spec)

    with pytest.raises(ValueError, match="contains holdout"):
        support._validate_author_spec(_spec(holdout_report={"return": 1.0}))

    with pytest.raises(ValueError, match="changed a frozen field"):
        support._validate_author_spec(_spec(benchmark="000905.SH"))

    assert support._safe_author_rejection_reason(ValueError("unknown")) == (
        "host_rejected_author_proposal:malformed_or_incomplete_strategy_spec"
    )


def test_artifact_helpers_return_exact_payloads_and_content_hashes(
    tmp_path: Path,
) -> None:
    api_path = tmp_path / "api.json"
    api_content = orjson.dumps({"data": {"status": "ready"}})
    api_path.write_bytes(api_content)
    q3_path = tmp_path / "q3.json"
    q3_content = orjson.dumps(
        {"passed": True, "etf_selection": {"run_id": "selection-run"}}
    )
    q3_path.write_bytes(q3_content)

    api_data, api_hash = support._api_data(api_path)
    selection, q3_hash = support._q3_selection(q3_path)

    assert api_data == {"status": "ready"}
    assert api_hash == hashlib.sha256(api_content).hexdigest()
    assert selection == {"run_id": "selection-run"}
    assert q3_hash == hashlib.sha256(q3_content).hexdigest()


def test_q3_artifact_must_contain_passing_evidence(tmp_path: Path) -> None:
    path = tmp_path / "q3-failed.json"
    path.write_bytes(orjson.dumps({"passed": False, "etf_selection": {}}))

    with pytest.raises(ValueError, match="not passing"):
        support._q3_selection(path)


def test_context_and_seal_bind_snapshot_authority_and_artifacts() -> None:
    payload = _payload()
    context = support._context(payload=payload, decision_time=_decision_time())

    first = support._seal_section(
        tool_name="get_q5_context",
        kind="q5_author_context",
        payload=payload,
        context=context,
        source_hashes=("a" * 64, "b" * 64),
        lineage=("selection-run", "research-case"),
    )
    second = support._seal_section(
        tool_name="get_q5_context",
        kind="q5_author_context",
        payload=payload,
        context=context,
        source_hashes=("a" * 64, "b" * 64),
        lineage=("selection-run", "research-case"),
    )

    assert first == second
    assert first.verify_integrity() is True
    assert first.evidence_id.startswith("evidence-")
    assert first.artifact_refs == (
        f"source-artifact:sha256:{'a' * 64}",
        f"source-artifact:sha256:{'b' * 64}",
    )
    assert first.lineage[-2:] == (
        "redaction:approved-research-minimal-v1",
        "holdout:excluded",
    )
    assert context.allowed_universe == ("518880.SH",)
    assert context.source_snapshot_id.startswith("snapshot-set:sha256:")


def test_context_fails_closed_without_aggregate_snapshot_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _missing_authority(snapshot_ids: tuple[str, ...]) -> None:
        assert snapshot_ids

    monkeypatch.setattr(support, "aggregate_source_snapshot_ids", _missing_authority)

    with pytest.raises(ValueError, match="no source snapshot authority"):
        support._context(payload=_payload(), decision_time=_decision_time())


def test_bound_context_tool_requires_exact_arguments_and_authority() -> None:
    context = _context()
    envelope = support._seal_section(
        tool_name="get_q5_context",
        kind="q5_author_context",
        payload={"status": "ready"},
        context=context,
        source_hashes=("a" * 64,),
        lineage=("selection-run",),
    )
    spec = support._CapturingAuthorDraftTool().spec
    tool = support._BoundContextTool(
        spec=spec,
        envelope=envelope,
        expected_arguments={"section": "market"},
    )

    assert tool.spec is spec
    assert tool.invoke(arguments={"section": "market"}, context=context) is envelope
    with pytest.raises(ValueError, match="arguments escaped"):
        tool.invoke(arguments={"section": "technical"}, context=context)
    later_context = support._context(
        payload=_payload(),
        decision_time=_decision_time() + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="temporal authority drifted"):
        tool.invoke(arguments={"section": "market"}, context=later_context)


def test_no_base_catalog_is_empty_for_every_read_contract() -> None:
    catalog = support._NoBaseCatalog()

    assert catalog.get_spec("strategy", 1) is None
    assert catalog.list_specs() == []
    assert catalog.list_versions("strategy") == []
    assert catalog.get_active_published("strategy") is None


def test_capturing_author_tool_balanced_success_and_single_call_contract() -> None:
    tool = support._CapturingAuthorDraftTool()
    context = _context()
    evidence = tool.invoke(
        arguments={
            "lookback": 252,
            "vol_window": 60,
            "signal_weights_choice": "balanced",
        },
        context=context,
    )

    assert evidence.result["valid"] is True
    assert tool.evidence is evidence
    assert tool.arguments is not None
    spec = cast("Mapping[str, object]", tool.arguments["spec_json"])
    assert spec["signal_weights"] == [0.5, 0.3, 0.2]
    with pytest.raises(ValueError, match="only once"):
        tool.invoke(
            arguments={
                "lookback": 252,
                "vol_window": 60,
                "signal_weights_choice": "balanced",
            },
            context=context,
        )


@pytest.mark.parametrize(
    "arguments",
    [
        {"lookback": 252, "vol_window": 60},
        {
            "lookback": True,
            "vol_window": 60,
            "signal_weights_choice": "balanced",
        },
    ],
)
def test_capturing_author_tool_rejects_unfrozen_arguments(
    arguments: Mapping[str, object],
) -> None:
    tool = support._CapturingAuthorDraftTool()

    with pytest.raises(ValueError, match="parameters escaped"):
        tool.invoke(arguments=arguments, context=_context())

    assert tool.rejection_reason == (
        "host_rejected_author_proposal:parameters_outside_frozen_choices"
    )
    assert tool.arguments is None


@pytest.mark.parametrize(
    ("diagnostics", "expected_code"),
    [
        ((), "UNKNOWN"),
        (({"code": "SPEC_INVALID"},), "SPEC_INVALID"),
        (({"code": "bad-code"},), "UNKNOWN"),
    ],
)
def test_capturing_author_tool_rejects_invalid_preview_evidence(
    monkeypatch: pytest.MonkeyPatch,
    diagnostics: tuple[Mapping[str, object], ...],
    expected_code: str,
) -> None:
    def _invalid_preview(
        tool: AuthorDraftStrategyTool,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        del tool, arguments
        return EvidenceEnvelope.seal(
            evidence_id="evidence-invalid-preview",
            tool_name="author_draft_strategy",
            result={
                "valid": False,
                "payload": {"diagnostics": diagnostics},
            },
            artifact_refs=("artifact:invalid-preview",),
            temporal_context=context,
            lineage=("author-preview:invalid",),
        )

    monkeypatch.setattr(AuthorDraftStrategyTool, "invoke", _invalid_preview)
    tool = support._CapturingAuthorDraftTool()

    with pytest.raises(ValueError, match="preview is invalid"):
        tool.invoke(
            arguments={
                "lookback": 126,
                "vol_window": 20,
                "signal_weights_choice": "momentum_tilt",
            },
            context=_context(),
        )

    assert tool.rejection_reason == f"author_preview_invalid:{expected_code}"
    assert tool.arguments is None
    assert tool.evidence is None
