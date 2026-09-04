"""Canonical transport-neutral experiment planning request builder tests."""

from __future__ import annotations

from collections import UserDict
from collections.abc import Callable, Iterator, Mapping
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from types import MappingProxyType
from typing import cast

import orjson
import pytest
from ditto_analysis.experiments import (
    ResearchMetricDirection,
    ResearchMetricId,
    ResearchMetricValue,
)
from ditto_analysis.experiments.preflight_authority import (
    canonical_research_cycle_hash,
)
from ditto_analysis.experiments.promotion_objective import (
    promotion_objective_payload,
)
from ditto_analysis.experiments.specs import ExperimentFailurePolicy
from ditto_analysis.experiments.trial_ledger import (
    ConstraintOperator,
    MetricConstraint,
    ObjectiveMetric,
    PromotionObjective,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments import _planning_request_identity
from ditto_application.processes.experiments._planning_request_identity import (
    plain_planning_value,
    planning_request_hash,
    validate_planning_request_graph,
)
from ditto_application.processes.experiments.planning import (
    BaselineDescriptor,
    CandidateMatrixSpec,
    ParameterAxis,
)
from ditto_application.processes.experiments.planning_contracts import (
    declare_trial_family,
    decode_canonical_promotion_objective,
    decode_experiment_failure_policy,
    derive_canonical_research_cycle_hash,
)
from ditto_application.processes.experiments.planning_request_builder import (
    build_experiment_planning_request,
)
from ditto_application.research_validation_protocol import (
    CalendarMonth,
    CoverageEligibility,
    InstrumentEligibilityEvidence,
    IsolationSemantics,
    MonthCoverageDecision,
    PitUniverseMembershipInterval,
    TradingCalendarEvidence,
    TradingCalendarMonthClosure,
    TradingCalendarSourceIdentity,
    UniverseCoveragePolicy,
    UniverseMembershipSource,
    ValidationProtocolRequest,
    canonical_validation_protocol_payload,
    compile_validation_protocol,
)
from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
    canonical_spec_payload_for_record,
    deserialize_strategy_spec,
)
from ditto_backtest.context_inputs import ContextInputKind, ReplayContextInputRef
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.models import StrategySpecRecord

_NOW = datetime(2026, 7, 30, tzinfo=UTC)
_EXPERIMENT_ID = "exp-canonical-builder-1"
_STRATEGY_ID = "seed_etf_trend_swing"
_SNAPSHOT_HASH = "d" * 64

type PlanningDocument = dict[str, object]
type DocumentMutation = Callable[[PlanningDocument], None]


class _ReadOnlyMapping(Mapping[str, object]):
    def __init__(self, values: Mapping[str, object]) -> None:
        self._values = values

    def __getitem__(self, key: str) -> object:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


class _MutatingMapping(Mapping[str, object]):
    def __init__(self, values: Mapping[str, object]) -> None:
        self._values = dict(values)

    def __getitem__(self, key: str) -> object:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        for index, key in enumerate(tuple(self._values)):
            yield key
            if index == 0:
                self._values["injected_during_iteration"] = True

    def __len__(self) -> int:
        return len(self._values)


class _SameSizeMutatingMapping(Mapping[str, object]):
    def __init__(self, values: Mapping[str, object]) -> None:
        self._values = dict(values)

    def __getitem__(self, key: str) -> object:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        for index, key in enumerate(tuple(self._values)):
            yield key
            if index == 0:
                self._values["seed"] = 99

    def __len__(self) -> int:
        return len(self._values)


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if type(value) in {list, tuple}:
        items = cast("list[object] | tuple[object, ...]", value)
        return [_plain_json(item) for item in items]
    return value


def _javascript_json_number_round_trip(value: object) -> object:
    """Model JSON.parse/stringify's loss of an integral float lexical suffix."""
    if type(value) is dict:
        source = cast("dict[str, object]", value)
        return {
            key: _javascript_json_number_round_trip(item)
            for key, item in source.items()
        }
    if type(value) is list:
        return [
            _javascript_json_number_round_trip(item)
            for item in cast("list[object]", value)
        ]
    if type(value) is float and value.is_integer():
        return int(value)
    return value


def _next_month(month: CalendarMonth) -> CalendarMonth:
    if month.month == 12:
        return CalendarMonth(month.year + 1, 1)
    return CalendarMonth(month.year, month.month + 1)


def _validation_request() -> ValidationProtocolRequest:
    months: list[CalendarMonth] = []
    sessions: list[date] = []
    month_sessions: list[tuple[date, ...]] = []
    month = CalendarMonth(2016, 1)
    for _ in range(97):
        months.append(month)
        current_month_sessions: list[date] = []
        current = date(month.year, month.month, 1)
        following = _next_month(month)
        stop = date(following.year, following.month, 1)
        while current < stop:
            if current.weekday() < 5:
                sessions.append(current)
                current_month_sessions.append(current)
            current += timedelta(days=1)
        month_sessions.append(tuple(current_month_sessions))
        month = following
    instrument_ids = ("ETF-0001",)
    eligible_from = sessions[21]
    membership = (PitUniverseMembershipInterval(months[0], months[-1]),)
    cutoff = date(month.year, month.month, 1) - timedelta(days=1)
    return ValidationProtocolRequest(
        trading_sessions=tuple(sessions),
        strategy_eligible_start=eligible_from,
        last_complete_month=months[-1],
        coverage_policy=UniverseCoveragePolicy("a-share-core", 1),
        coverage_decisions=tuple(
            MonthCoverageDecision.create(
                month=item,
                eligibility=CoverageEligibility.ELIGIBLE,
                universe_instrument_ids=instrument_ids,
                eligible_instrument_ids=instrument_ids,
            )
            for item in months[1:]
        ),
        isolation=IsolationSemantics(2, 5, 1),
        trading_calendar=TradingCalendarEvidence.create(
            calendar_id="sse-szse",
            version=1,
            source=TradingCalendarSourceIdentity(
                dataset_id="etf_daily",
                snapshot_id="provider-snapshot-1",
                manifest_hash=_SNAPSHOT_HASH,
                certified_through=cutoff,
                authority_as_of=cutoff,
            ),
            month_closures=tuple(
                TradingCalendarMonthClosure.create(
                    month=item,
                    open_sessions=open_sessions,
                )
                for item, open_sessions in zip(months, month_sessions, strict=True)
            ),
        ),
        instrument_eligibility=(
            InstrumentEligibilityEvidence(
                instrument_id=instrument_ids[0],
                listing_date=sessions[0],
                base_data_eligible_start=sessions[0],
                warmup_sessions=21,
                eligible_from=eligible_from,
                membership_intervals=membership,
            ),
        ),
        required_input_start=sessions[0],
        membership_source=UniverseMembershipSource(
            universe_id="csi_etf_broad",
            dataset_id="etf_daily",
            snapshot_id="provider-snapshot-1",
            manifest_hash=_SNAPSHOT_HASH,
        ),
        planning_decision_date=_NOW.date(),
    )


def _matrix_spec() -> CandidateMatrixSpec:
    return CandidateMatrixSpec(
        baseline=BaselineDescriptor(
            descriptor_type="etf-current-active",
            payload={
                "strategy_id": _STRATEGY_ID,
                "version": 2,
                "spec_hash": "f" * 64,
            },
        ),
        axes=(
            ParameterAxis(
                "selector.top_k",
                (10, 20),
            ),
        ),
        candidate_limit=4,
    )


def _matrix_document(matrix: CandidateMatrixSpec) -> dict[str, object]:
    return {
        "baseline": {
            "descriptor_type": matrix.baseline.descriptor_type,
            "payload": dict(matrix.baseline.payload),
            "schema_version": matrix.baseline.schema_version,
        },
        "axes": [
            {
                "name": axis.name,
                "values": [
                    {
                        "type": (
                            "bool"
                            if type(value) is bool
                            else "int"
                            if type(value) is int
                            else "float"
                            if type(value) is float
                            else "string"
                        ),
                        "value": value,
                    }
                    for value in axis.values
                ],
            }
            for axis in matrix.axes
        ],
        "candidate_limit": matrix.candidate_limit,
    }


def _promotion_objective(
    matrix: CandidateMatrixSpec,
) -> PromotionObjective:
    family = declare_trial_family(
        experiment_id=_EXPERIMENT_ID,
        matrix_spec=matrix,
        family_id="stock-selection-r3-v1",
    )
    return PromotionObjective(
        primary=ObjectiveMetric(
            ResearchMetricId.NET_RETURN,
            ResearchMetricDirection.MAXIMIZE,
        ),
        hard_constraints=(
            MetricConstraint(
                ResearchMetricValue(ResearchMetricId.MAX_DRAWDOWN, -20.0),
                ConstraintOperator.GREATER_THAN_OR_EQUAL,
            ),
        ),
        tie_break_order=(
            ObjectiveMetric(
                ResearchMetricId.TURNOVER,
                ResearchMetricDirection.MINIMIZE,
            ),
        ),
        baseline_candidate_id=family.current_members[0].candidate_id,
        economic_rationale="Capture durable returns after costs.",
        trial_family=family,
    )


def _plain_seed_spec() -> dict[str, object]:
    return cast(
        "dict[str, object]",
        orjson.loads(orjson.dumps(asdict(SEED_STRATEGY_SPECS[_STRATEGY_ID]))),
    )


def _default_injected_seed_spec() -> dict[str, object]:
    persisted = _plain_seed_spec()
    seed = SEED_STRATEGY_SPECS[_STRATEGY_ID]
    record = StrategySpecRecord(
        strategy_id=seed.strategy_id,
        name=seed.name,
        spec_json=persisted,
        version=2,
        created_at="2026-07-30T00:00:00Z",
        tags=seed.tags,
    )
    return cast(
        "dict[str, object]",
        orjson.loads(orjson.dumps(asdict(deserialize_strategy_spec(record)))),
    )


def _planning_document() -> PlanningDocument:
    matrix = _matrix_spec()
    validation = _validation_request()
    validation_plan = compile_validation_protocol(validation)
    assert validation_plan.reserved_holdout is not None
    holdout = validation_plan.reserved_holdout.test_window
    spec_json = _plain_seed_spec()
    record = StrategySpecRecord(
        strategy_id=_STRATEGY_ID,
        name=cast("str", spec_json["name"]),
        spec_json=spec_json,
        version=2,
        created_at="2026-07-30T00:00:00Z",
        tags=cast("tuple[str, ...]", tuple(spec_json["tags"])),
    )
    return {
        "experiment_id": _EXPERIMENT_ID,
        "research_cycle_id": "cycle-canonical-builder-1",
        "research_cycle_hash": str(
            canonical_research_cycle_hash(
                strategy_family_id=_STRATEGY_ID,
                certified_data_cutoff=holdout.end,
                oos_window=holdout,
            )
        ),
        "strategy": {
            "strategy_id": _STRATEGY_ID,
            "version": 2,
            "spec_hash": canonical_spec_hash_for_record(record),
            "spec_json": spec_json,
        },
        "snapshot": {
            "snapshot_id": "certified-snapshot-1",
            "manifest_hash": _SNAPSHOT_HASH,
        },
        "validation": dict(canonical_validation_protocol_payload(validation)),
        "matrix": _matrix_document(matrix),
        "promotion_objective": dict(
            promotion_objective_payload(_promotion_objective(matrix))
        ),
        "dataset_requirements": [
            {
                "dataset_id": "etf_daily",
                "expected_snapshot_ids": ["provider-snapshot-1"],
                "requires_pit_universe": True,
                "certified_from": "2016-01-01",
            },
        ],
        "cost_model": {
            "bytes_per_run": 100,
            "bytes_per_trading_session": 2,
        },
        "budget": {
            "candidate_limit": 4,
            "fold_run_limit": 1_000,
            "trading_session_limit": 1_000_000,
            "disk_byte_limit": 100_000_000,
        },
        "seed": 42,
        "worker_count": 2,
        "failure_policy": "fail_fast",
        "created_at": "2026-07-30T00:00:00Z",
    }


def _mapping_at(document: PlanningDocument, key: str) -> dict[str, object]:
    return cast("dict[str, object]", document[key])


def _list_at(document: PlanningDocument, key: str) -> list[object]:
    return cast("list[object]", document[key])


def _assert_spec_invalid(document: PlanningDocument) -> None:
    with pytest.raises(AppProcessError) as caught:
        build_experiment_planning_request(document)
    assert caught.value.details["code"] == "SPEC_INVALID"
    assert isinstance(caught.value.details["reason"], str)


def test_planning_contract_wrappers_preserve_authoritative_codecs() -> None:
    document = _planning_document()
    validation = _validation_request()

    objective = decode_canonical_promotion_objective(document["promotion_objective"])

    assert (
        dict(promotion_objective_payload(objective))
        == (document["promotion_objective"])
    )
    assert (
        derive_canonical_research_cycle_hash(
            strategy_family_id=_STRATEGY_ID,
            validation_request=validation,
        )
        == document["research_cycle_hash"]
    )
    assert (
        decode_experiment_failure_policy(document["failure_policy"])
        is ExperimentFailurePolicy.FAIL_FAST
    )


def test_builder_decodes_every_field_into_the_exact_planning_contract() -> None:
    document = _planning_document()

    request = build_experiment_planning_request(document)

    strategy = _mapping_at(document, "strategy")
    assert request.experiment_id == document["experiment_id"]
    assert request.research_cycle_id == document["research_cycle_id"]
    assert request.research_cycle_hash == document["research_cycle_hash"]
    assert request.strategy_record.strategy_id == strategy["strategy_id"]
    assert request.strategy_record.version == strategy["version"]
    assert request.strategy_record.spec_hash == strategy["spec_hash"]
    assert _plain_json(request.strategy_record.spec_json) == strategy["spec_json"]
    assert request.snapshot_identity.snapshot_id == "certified-snapshot-1"
    assert request.snapshot_identity.manifest_hash == _SNAPSHOT_HASH
    assert (
        dict(canonical_validation_protocol_payload(request.validation_request))
        == (document["validation"])
    )
    assert request.matrix_spec == _matrix_spec()
    assert (
        dict(promotion_objective_payload(request.promotion_objective))
        == (document["promotion_objective"])
    )
    assert [item.as_payload() for item in request.dataset_requirements] == (
        document["dataset_requirements"]
    )
    assert request.cost_model.bytes_per_run == 100
    assert request.cost_model.bytes_per_trading_session == 2
    assert request.budget.candidate_limit == 4
    assert request.budget.fold_run_limit == 1_000
    assert request.budget.trading_session_limit == 1_000_000
    assert request.budget.disk_byte_limit == 100_000_000
    assert request.seed == 42
    assert request.worker_count == 2
    assert request.failure_policy is ExperimentFailurePolicy.FAIL_FAST
    assert request.created_at == _NOW


def test_builder_accepts_semantically_identical_browser_json_numbers() -> None:
    original = _planning_document()
    browser_round_trip = cast(
        "PlanningDocument",
        _javascript_json_number_round_trip(original),
    )

    request = build_experiment_planning_request(browser_round_trip)

    assert (
        request.strategy_record.spec_hash
        == _mapping_at(original, "strategy")["spec_hash"]
    )
    assert planning_request_hash(request) == planning_request_hash(
        build_experiment_planning_request(original)
    )


def test_stock_strategy_hash_survives_browser_integral_float_round_trip() -> None:
    seed = SEED_STRATEGY_SPECS["seed_stock_selection_rotation"]
    original_spec = cast(
        "dict[str, object]",
        orjson.loads(orjson.dumps(asdict(seed))),
    )
    browser_spec = cast(
        "dict[str, object]",
        _javascript_json_number_round_trip(original_spec),
    )

    def record(spec_json: dict[str, object]) -> StrategySpecRecord:
        return StrategySpecRecord(
            strategy_id=seed.strategy_id,
            name=seed.name,
            spec_json=spec_json,
            version=2,
            created_at="2026-07-30T00:00:00Z",
            tags=seed.tags,
        )

    assert canonical_spec_hash_for_record(record(browser_spec)) == (
        canonical_spec_hash_for_record(record(original_spec))
    )


def test_builder_freezes_replay_context_inputs_into_request_identity() -> None:
    without_context = _planning_document()
    document = _planning_document()
    document["context_input_refs"] = [
        {
            "context_kind": "market_context",
            "context_id": "market-regime:sha256:q5",
            "content_hash": "a" * 64,
            "as_of": "2026-07-30T00:00:00Z",
            "knowledge_cutoff": "2026-07-30T00:00:00Z",
            "publication_cutoff": "2026-07-30T00:00:00Z",
            "source_snapshot_ids": ["snapshot:tushare:index_daily:sha256:q5"],
        }
    ]

    request = build_experiment_planning_request(document)

    assert request.context_input_refs[0].context_id == "market-regime:sha256:q5"
    assert planning_request_hash(request) != planning_request_hash(
        build_experiment_planning_request(without_context)
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda document: document.update({"unknown": True}),
        lambda document: document.pop("seed"),
        lambda document: _mapping_at(document, "strategy").update({"unknown": True}),
        lambda document: _mapping_at(document, "strategy").pop("version"),
        lambda document: _mapping_at(document, "snapshot").update({"unknown": True}),
        lambda document: _mapping_at(document, "snapshot").pop("snapshot_id"),
        lambda document: _mapping_at(document, "cost_model").update({"unknown": 1}),
        lambda document: cast(
            "dict[str, object]",
            _list_at(document, "dataset_requirements")[0],
        ).pop("dataset_id"),
    ],
)
def test_builder_rejects_unknown_or_missing_keys(mutate: DocumentMutation) -> None:
    document = _planning_document()
    mutate(document)

    _assert_spec_invalid(document)


def _drift_strategy_hash(document: PlanningDocument) -> None:
    _mapping_at(document, "strategy")["spec_hash"] = "0" * 64


def _drift_research_cycle_hash(document: PlanningDocument) -> None:
    document["research_cycle_hash"] = "0" * 64


def _drift_snapshot_identity(document: PlanningDocument) -> None:
    _mapping_at(document, "snapshot")["manifest_hash"] = "D" * 64


def _drift_matrix(document: PlanningDocument) -> None:
    matrix = _mapping_at(document, "matrix")
    axes = cast("list[object]", matrix["axes"])
    axis = cast("dict[str, object]", axes[0])
    values = cast("list[object]", axis["values"])
    cast("dict[str, object]", values[0])["type"] = "string"


def _drift_validation(document: PlanningDocument) -> None:
    validation = _mapping_at(document, "validation")
    calendar = cast("dict[str, object]", validation["trading_calendar"])
    calendar["payload_hash"] = "0" * 64


def _drift_objective(document: PlanningDocument) -> None:
    objective = _mapping_at(document, "promotion_objective")
    family = cast("dict[str, object]", objective["trial_family"])
    members = cast("list[object]", family["members"])
    cast("dict[str, object]", members[0])["parameter_hash"] = "0" * 64


@pytest.mark.parametrize(
    "mutate",
    [
        _drift_strategy_hash,
        _drift_research_cycle_hash,
        _drift_snapshot_identity,
        _drift_matrix,
        _drift_validation,
        _drift_objective,
    ],
)
def test_builder_rejects_canonical_identity_drift(
    mutate: DocumentMutation,
) -> None:
    document = _planning_document()
    mutate(document)

    _assert_spec_invalid(document)


@pytest.mark.parametrize(
    ("container_name", "field_name"),
    [
        (None, "seed"),
        (None, "worker_count"),
        ("strategy", "version"),
        ("matrix", "candidate_limit"),
        ("budget", "candidate_limit"),
        ("cost_model", "bytes_per_run"),
    ],
)
def test_builder_rejects_bool_impersonating_integer(
    container_name: str | None,
    field_name: str,
) -> None:
    document = _planning_document()
    container = (
        document if container_name is None else _mapping_at(document, container_name)
    )
    container[field_name] = True

    _assert_spec_invalid(document)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_builder_rejects_non_finite_json_values(value: float) -> None:
    document = _planning_document()
    strategy = _mapping_at(document, "strategy")
    spec_json = cast("dict[str, object]", strategy["spec_json"])
    params = cast("dict[str, object]", spec_json["params"])
    params["unsafe"] = value

    _assert_spec_invalid(document)


def test_builder_rejects_unordered_and_non_string_mapping_values() -> None:
    unordered = _planning_document()
    strategy = _mapping_at(unordered, "strategy")
    cast("dict[str, object]", strategy["spec_json"])["unsafe"] = {"a", "b"}
    _assert_spec_invalid(unordered)

    non_string_key = _planning_document()
    strategy = _mapping_at(non_string_key, "strategy")
    spec_json = cast("dict[object, object]", strategy["spec_json"])
    spec_json[1] = "not-a-string-key"
    _assert_spec_invalid(non_string_key)


def test_builder_detaches_every_nested_value_from_caller_mutation() -> None:
    document = _planning_document()

    request = build_experiment_planning_request(document)
    strategy = _mapping_at(document, "strategy")
    spec_json = cast("dict[str, object]", strategy["spec_json"])
    spec_json["name"] = "mutated"
    snapshot = _mapping_at(document, "snapshot")
    snapshot["snapshot_id"] = "mutated"
    validation = _mapping_at(document, "validation")
    cast("list[object]", validation["trading_sessions"]).clear()
    matrix = _mapping_at(document, "matrix")
    cast("list[object]", matrix["axes"]).clear()
    requirements = _list_at(document, "dataset_requirements")
    requirements.clear()

    assert request.strategy_record.spec_json["name"] != "mutated"
    assert request.snapshot_identity.snapshot_id == "certified-snapshot-1"
    assert request.validation_request.trading_sessions
    assert request.matrix_spec.axes
    assert request.dataset_requirements


@pytest.mark.parametrize(
    "wrapper_name",
    ["user_dict", "read_only"],
)
def test_builder_snapshots_arbitrary_mapping_inputs_once(
    wrapper_name: str,
) -> None:
    document = _planning_document()
    wrapped = (
        UserDict(document)
        if wrapper_name == "user_dict"
        else _ReadOnlyMapping(document)
    )

    request = build_experiment_planning_request(wrapped)
    _mapping_at(document, "strategy")["spec_json"] = {"name": "mutated"}

    assert request.strategy_record.name == "ETF 趋势追踪"
    assert request.strategy_record.spec_json["name"] == "ETF 趋势追踪"


def test_builder_rejects_mapping_that_mutates_while_being_snapshotted() -> None:
    document = _MutatingMapping(_planning_document())

    with pytest.raises(AppProcessError) as caught:
        build_experiment_planning_request(document)

    assert caught.value.details == {
        "code": "SPEC_INVALID",
        "reason": "planning_document_changed_during_snapshot",
    }


def test_builder_rejects_same_size_value_replacement_during_snapshot() -> None:
    source = _planning_document()
    strategy = _mapping_at(source, "strategy")
    strategy["spec_json"] = _default_injected_seed_spec()
    document = _SameSizeMutatingMapping(source)

    with pytest.raises(AppProcessError) as caught:
        build_experiment_planning_request(document)

    assert caught.value.details == {
        "code": "SPEC_INVALID",
        "reason": "planning_document_changed_during_snapshot",
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda spec_json: spec_json.update({"unknown_spec_field": True}),
        lambda spec_json: cast(
            "dict[str, object]",
            spec_json["execution"],
        ).pop("default_order_type"),
    ],
)
def test_builder_rejects_noncanonical_legacy_strategy_payload_aliases(
    mutate: Callable[[dict[str, object]], object],
) -> None:
    document = _planning_document()
    strategy = _mapping_at(document, "strategy")
    spec_json = cast("dict[str, object]", strategy["spec_json"])
    mutate(spec_json)

    _assert_spec_invalid(document)


def test_builder_deep_freezes_strategy_spec_without_breaking_identity_codecs() -> None:
    request = build_experiment_planning_request(_planning_document())
    spec_json = request.strategy_record.spec_json
    execution = cast("dict[str, object]", spec_json["execution"])
    cost_model = cast("dict[str, object]", execution["cost_model"])

    assert type(spec_json) is MappingProxyType
    assert type(execution) is MappingProxyType
    assert type(cost_model) is MappingProxyType
    with pytest.raises(TypeError):
        spec_json["name"] = "mutated"
    with pytest.raises(TypeError):
        execution["frequency"] = "D"
    with pytest.raises(TypeError):
        cost_model["slippage_bps"] = 999.0

    assert planning_request_hash(request)
    assert canonical_spec_payload_for_record(request.strategy_record)


def _expect_request_identity_invalid(
    reason: str,
    factory: Callable[[], object],
) -> None:
    with pytest.raises(AppProcessError) as exc_info:
        factory()
    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == reason


class TestPlanningRequestIdentityEdges:
    pytestmark = pytest.mark.pit

    def test_plain_value_supports_exact_json_scalars_and_containers(self) -> None:
        source = MappingProxyType(
            {
                "none": None,
                "bool": True,
                "int": 1,
                "float": 1.5,
                "text": "value",
                "nested": (1, [2]),
            }
        )

        copied = plain_planning_value(source)

        assert copied == {
            "none": None,
            "bool": True,
            "int": 1,
            "float": 1.5,
            "text": "value",
            "nested": [1, [2]],
        }

    def test_plain_value_rejects_nonfinite_cycles_keys_and_foreign_types(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            _expect_request_identity_invalid(
                "non_finite_planning_request_value",
                lambda value=value: plain_planning_value(value),
            )

        cyclic_mapping: dict[str, object] = {}
        cyclic_mapping["self"] = cyclic_mapping
        _expect_request_identity_invalid(
            "cyclic_planning_request_value",
            lambda: plain_planning_value(cyclic_mapping),
        )

        cyclic_list: list[object] = []
        cyclic_list.append(cyclic_list)
        _expect_request_identity_invalid(
            "cyclic_planning_request_value",
            lambda: plain_planning_value(cyclic_list),
        )

        _expect_request_identity_invalid(
            "invalid_planning_request_mapping_key",
            lambda: plain_planning_value({1: "value"}),
        )
        _expect_request_identity_invalid(
            "invalid_planning_request_value_type",
            lambda: plain_planning_value({"not", "json"}),
        )

    def test_parameter_types_are_bound_into_the_matrix_identity(self) -> None:
        request = build_experiment_planning_request(_planning_document())
        matrix = CandidateMatrixSpec(
            baseline=request.matrix_spec.baseline,
            axes=(ParameterAxis("mixed", (True, 1, 1.5, "value")),),
            candidate_limit=5,
        )
        changed = replace(
            request,
            matrix_spec=matrix,
            promotion_objective=_promotion_objective(matrix),
            budget=replace(request.budget, candidate_limit=5),
        )

        assert planning_request_hash(changed)

    def test_matrix_graph_rejects_mutated_baseline_axes_and_derived_json(self) -> None:
        request = build_experiment_planning_request(_planning_document())

        matrix = replace(request.matrix_spec)
        object.__setattr__(matrix.baseline, "payload", dict(matrix.baseline.payload))
        _expect_request_identity_invalid(
            "invalid_planning_request_matrix_graph",
            lambda: validate_planning_request_graph(
                replace(request, matrix_spec=matrix)
            ),
        )

        request = build_experiment_planning_request(_planning_document())
        matrix = replace(request.matrix_spec)
        object.__setattr__(matrix, "axes", [*matrix.axes])
        _expect_request_identity_invalid(
            "invalid_planning_request_matrix_graph",
            lambda: validate_planning_request_graph(
                replace(request, matrix_spec=matrix)
            ),
        )

        request = build_experiment_planning_request(_planning_document())
        matrix = replace(request.matrix_spec)
        object.__setattr__(matrix, "axes", (object(),))
        _expect_request_identity_invalid(
            "invalid_planning_request_matrix_graph",
            lambda: validate_planning_request_graph(
                replace(request, matrix_spec=matrix)
            ),
        )

        request = build_experiment_planning_request(_planning_document())
        matrix = replace(request.matrix_spec)
        axis = matrix.axes[0]
        object.__setattr__(axis, "values", [*axis.values])
        _expect_request_identity_invalid(
            "invalid_planning_request_matrix_graph",
            lambda: validate_planning_request_graph(
                replace(request, matrix_spec=matrix)
            ),
        )

        request = build_experiment_planning_request(_planning_document())
        matrix = replace(request.matrix_spec)
        object.__setattr__(matrix.baseline, "canonical_json", "{}")
        _expect_request_identity_invalid(
            "noncanonical_planning_request_matrix_graph",
            lambda: validate_planning_request_graph(
                replace(request, matrix_spec=matrix)
            ),
        )

    def test_context_input_refs_require_exact_unique_canonical_order(self) -> None:
        request = build_experiment_planning_request(_planning_document())
        object.__setattr__(request, "context_input_refs", [])
        _expect_request_identity_invalid(
            "invalid_planning_request_graph",
            lambda: validate_planning_request_graph(request),
        )

        request = build_experiment_planning_request(_planning_document())
        object.__setattr__(request, "context_input_refs", (object(),))
        _expect_request_identity_invalid(
            "invalid_planning_request_graph",
            lambda: validate_planning_request_graph(request),
        )

        first = ReplayContextInputRef(
            context_kind=ContextInputKind.TECHNICAL_ANALYSIS,
            context_id="technical:1",
            content_hash="a" * 64,
            as_of="2026-07-30T00:00:00Z",
            knowledge_cutoff="2026-07-30T00:00:00Z",
            publication_cutoff="2026-07-30T00:00:00Z",
            source_snapshot_ids=("snapshot:technical",),
        )
        second = ReplayContextInputRef(
            context_kind=ContextInputKind.MARKET_CONTEXT,
            context_id="market:1",
            content_hash="b" * 64,
            as_of="2026-07-30T00:00:00Z",
            knowledge_cutoff="2026-07-30T00:00:00Z",
            publication_cutoff="2026-07-30T00:00:00Z",
            source_snapshot_ids=("snapshot:market",),
        )
        request = build_experiment_planning_request(_planning_document())
        object.__setattr__(request, "context_input_refs", (first, first))
        _expect_request_identity_invalid(
            "invalid_planning_request_context_inputs",
            lambda: validate_planning_request_graph(request),
        )

        request = build_experiment_planning_request(_planning_document())
        object.__setattr__(request, "context_input_refs", (first, second))
        _expect_request_identity_invalid(
            "noncanonical_planning_request_context_inputs",
            lambda: validate_planning_request_graph(request),
        )

    def test_rebuilt_requirements_and_candidate_limit_must_remain_exact(self) -> None:
        request = build_experiment_planning_request(_planning_document())
        requirement = request.dataset_requirements[0]
        object.__setattr__(
            requirement,
            "expected_snapshot_ids",
            ("snapshot-z", "snapshot-a"),
        )
        _expect_request_identity_invalid(
            "noncanonical_planning_request_dataset_requirement",
            lambda: validate_planning_request_graph(request),
        )

        request = build_experiment_planning_request(_planning_document())
        object.__setattr__(
            request.matrix_spec,
            "candidate_limit",
            request.budget.candidate_limit + 1,
        )
        _expect_request_identity_invalid(
            "planning_request_candidate_limit_mismatch",
            lambda: validate_planning_request_graph(request),
        )

    def test_hash_detects_request_payload_drift_between_identity_reads(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        request = build_experiment_planning_request(_planning_document())
        calls = 0

        def changing_payload(_: object) -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {"revision": calls}

        monkeypatch.setattr(
            _planning_request_identity,
            "_request_payload",
            changing_payload,
        )

        with pytest.raises(AppProcessError) as exc_info:
            planning_request_hash(request)
        assert exc_info.value.details == {
            "code": "REPRODUCIBILITY_FAILED",
            "reason": "planning_request_identity_mutated",
        }
