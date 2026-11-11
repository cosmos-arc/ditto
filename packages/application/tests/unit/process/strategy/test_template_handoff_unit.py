"""SelectionRun-to-strategy-template handoff proposal orchestration."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from ditto_analysis.research.cases import ResearchCase
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.strategy.template_handoff import (
    ProposeStrategyTemplateDraft,
    StrategyTemplateHandoffRequest,
)
from ditto_application.research_case_contracts import (
    ResearchCaseMaterial,
    ResearchCaseView,
)
from ditto_kernel.identity import InstrumentId
from ditto_strategy.selection.contracts import (
    EtfSelectionSpec,
    SelectionConditionOperator,
    SelectionFactorCondition,
    SelectionFactorValue,
    SelectionFactorWeight,
    SelectionInputBundle,
    SelectionInstrumentInput,
    SelectionLimitState,
    SelectionRun,
    SelectionRunStatus,
    StockSelectionSpec,
)
from ditto_strategy.selection.identity import canonical_selection_run_hash
from ditto_strategy.selection.pipeline import SelectionPipeline


class _RunReader:
    def __init__(self, run: SelectionRun | None) -> None:
        self._run = run

    def get(self, run_id: str) -> SelectionRun | None:
        if self._run is not None and self._run.run_id == run_id:
            return self._run
        return None

    def list_by_spec(self, spec_id: str, *, limit: int = 100) -> list[SelectionRun]:
        del spec_id, limit
        return []


class _PolicyReader:
    def __init__(self, policies: dict[str, object]) -> None:
        self._policies = policies

    def policy_by_hash(
        self, spec_hash: str
    ) -> StockSelectionSpec | EtfSelectionSpec | None:
        value = self._policies.get(spec_hash)
        return cast("StockSelectionSpec | EtfSelectionSpec | None", value)


class _CaseReader:
    def __init__(self, cases: dict[str, ResearchCaseView]) -> None:
        self._cases = cases

    def get(self, case_id: str) -> ResearchCaseView | None:
        return self._cases.get(case_id)

    def list_recent(self, *, limit: int = 20) -> tuple[ResearchCaseView, ...]:
        del limit
        return ()

    def list_by_run(
        self, selection_run_id: str, *, limit: int = 20
    ) -> tuple[ResearchCaseView, ...]:
        del selection_run_id, limit
        return ()


_AS_OF = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)


def _stock_run() -> SelectionRun:
    return SelectionPipeline().run(
        SelectionInputBundle(
            as_of=_AS_OF,
            knowledge_cutoff=_AS_OF,
            publication_cutoff=_AS_OF,
            universe_snapshot_id="universe:sha256:abc",
            industry_rotation_snapshot_id=None,
            source_snapshot_ids=("market-a",),
            spec=StockSelectionSpec(
                spec_id="stock-core",
                spec_version="1",
                top_k=5,
                min_average_turnover=20_000_000.0,
                min_listing_days=120,
                factor_weights=(
                    SelectionFactorWeight("momentum_1m", 0.6),
                    SelectionFactorWeight("value_pe", 0.4),
                ),
                filter_groups=(
                    (
                        SelectionFactorCondition(
                            "momentum_1m", SelectionConditionOperator.GTE, 0.5
                        ),
                    ),
                ),
            ),
            seed=17,
            instruments=tuple(
                SelectionInstrumentInput(
                    instrument_id=instrument_id,
                    instrument_name=f"Instrument {instrument_id}",
                    industry_id="801010",
                    factor_values=(
                        SelectionFactorValue("momentum_1m", momentum),
                        SelectionFactorValue("value_pe", value),
                    ),
                    average_turnover=100_000_000.0,
                    is_st=False,
                    is_suspended=False,
                    listing_days=500,
                    limit_state=SelectionLimitState.NORMAL,
                    tracking_error=None,
                )
                for instrument_id, momentum, value in (
                    (InstrumentId(600001), 1.0, 0.2),
                    (InstrumentId(600002), 0.5, 0.6),
                )
            ),
        )
    )


def _etf_run() -> SelectionRun:
    return SelectionPipeline().run(
        SelectionInputBundle(
            as_of=_AS_OF,
            knowledge_cutoff=_AS_OF,
            publication_cutoff=_AS_OF,
            universe_snapshot_id="universe:sha256:etf",
            industry_rotation_snapshot_id=None,
            source_snapshot_ids=("etf-market-a",),
            spec=EtfSelectionSpec(
                spec_id="etf-core",
                spec_version="1",
                top_k=3,
                min_average_turnover=10_000_000.0,
                min_listing_days=60,
                factor_weights=(SelectionFactorWeight("momentum_1m", 1.0),),
                max_tracking_error=0.02,
            ),
            seed=23,
            instruments=tuple(
                SelectionInstrumentInput(
                    instrument_id=instrument_id,
                    instrument_name=f"ETF {instrument_id}",
                    industry_id=None,
                    factor_values=(SelectionFactorValue("momentum_1m", momentum),),
                    average_turnover=50_000_000.0,
                    is_st=False,
                    is_suspended=False,
                    listing_days=900,
                    limit_state=SelectionLimitState.NORMAL,
                    tracking_error=0.01,
                )
                for instrument_id, momentum in (
                    (InstrumentId(510300), 1.0),
                    (InstrumentId(510500), 0.4),
                )
            ),
        )
    )


def _process(
    *,
    run: SelectionRun | None,
    policy: StockSelectionSpec | EtfSelectionSpec | None,
    cases: dict[str, ResearchCaseView] | None = None,
) -> ProposeStrategyTemplateDraft:
    return ProposeStrategyTemplateDraft(
        run_reader=_RunReader(run),
        policy_reader=_PolicyReader(
            {run.spec_hash: policy} if run is not None and policy is not None else {}
        ),
        case_reader=_CaseReader(cases or {}),
    )


def _case(run: SelectionRun, *, case_id: str = "case-1") -> ResearchCaseView:
    material = ResearchCaseMaterial(
        selection_run_id=run.run_id,
        selection_run_hash=canonical_selection_run_hash(run),
        selection_input_hash=run.input_hash,
        selection_spec_hash=run.spec_hash,
        objective="验证动量与价值因子在月度调仓下的表现",
        asset_kind=run.asset_kind.value,
        as_of=run.as_of,
        knowledge_cutoff=run.knowledge_cutoff,
        publication_cutoff=run.publication_cutoff,
        universe_snapshot_id=run.universe_snapshot_id,
        industry_rotation_snapshot_id=run.industry_rotation_snapshot_id,
        source_snapshot_ids=run.source_snapshot_ids,
        candidate_instrument_ids=tuple(item.instrument_id for item in run.candidates),
        selection_status=run.status.value,
        missing_inputs=run.missing_inputs,
    )
    return ResearchCase(**asdict(material))


def test_stock_handoff_converts_weights_and_top_k_and_explains_the_rest() -> None:
    run = _stock_run()
    policy = replace(
        cast("StockSelectionSpec", _stock_policy(run)),
    )
    proposal = _process(run=run, policy=policy).propose(
        StrategyTemplateHandoffRequest(
            selection_run_id=run.run_id,
            template_id="stock_selection",
        )
    )

    spec = proposal.spec_json
    assert spec["template"] == "stock_selection"
    assert spec["signal_expressions"] == ["momentum_1m", "value_pe"]
    assert spec["signal_weights"] == [0.6, 0.4]
    assert spec["asset_class"] == "stock"
    selector = spec["selector"]
    assert isinstance(selector, dict)
    selector_params = selector["params"]
    assert isinstance(selector_params, dict)
    assert selector_params["k"] == 5
    assert spec["universe"] == "csi_a_share"

    converted_sources = {item.source for item in proposal.converted}
    assert "factor_weights" in converted_sources
    assert "top_k" in converted_sources

    unconverted = {item.source: item for item in proposal.unconverted}
    assert set(unconverted) == {
        "filter_groups",
        "min_average_turnover",
        "min_listing_days",
        "excluded_limit_states",
    }
    # 每条不可转换条件都有可读解释与原因码，不静默丢弃。
    for item in proposal.unconverted:
        assert item.reason_code
        assert item.explanation

    assert proposal.lineage["selection_run_id"] == run.run_id
    assert proposal.lineage["selection_spec_hash"] == run.spec_hash
    assert proposal.lineage["asset_kind"] == "stock"
    assert proposal.lineage["as_of"] == run.as_of


def _stock_policy(run: SelectionRun) -> StockSelectionSpec:
    return StockSelectionSpec(
        spec_id=run.spec_id,
        spec_version=run.spec_version,
        top_k=5,
        min_average_turnover=20_000_000.0,
        min_listing_days=120,
        factor_weights=(
            SelectionFactorWeight("momentum_1m", 0.6),
            SelectionFactorWeight("value_pe", 0.4),
        ),
        filter_groups=(
            (
                SelectionFactorCondition(
                    "momentum_1m", SelectionConditionOperator.GTE, 0.5
                ),
            ),
        ),
    )


def test_etf_handoff_targets_etf_rotation_template() -> None:
    run = _etf_run()
    policy = EtfSelectionSpec(
        spec_id=run.spec_id,
        spec_version=run.spec_version,
        top_k=3,
        min_average_turnover=10_000_000.0,
        min_listing_days=60,
        factor_weights=(SelectionFactorWeight("momentum_1m", 1.0),),
        max_tracking_error=0.02,
    )
    proposal = _process(run=run, policy=policy).propose(
        StrategyTemplateHandoffRequest(
            selection_run_id=run.run_id,
            template_id="etf_rotation",
        )
    )

    assert proposal.spec_json["template"] == "etf_rotation"
    assert proposal.spec_json["universe"] == "csi_etf_broad"
    assert proposal.spec_json["signal_expressions"] == ["momentum_1m"]
    unconverted_sources = {item.source for item in proposal.unconverted}
    assert "max_tracking_error" in unconverted_sources


def test_handoff_rejects_template_asset_class_mismatch() -> None:
    run = _stock_run()
    policy = _stock_policy(run)

    with pytest.raises(AppProcessError) as error:
        _process(run=run, policy=policy).propose(
            StrategyTemplateHandoffRequest(
                selection_run_id=run.run_id,
                template_id="etf_rotation",
            )
        )
    assert error.value.details["reason"] == "template_asset_class_mismatch"


def test_handoff_rejects_unknown_template_and_missing_run_or_policy() -> None:
    run = _stock_run()
    policy = _stock_policy(run)

    with pytest.raises(AppProcessError) as unknown_template:
        _process(run=run, policy=policy).propose(
            StrategyTemplateHandoffRequest(
                selection_run_id=run.run_id,
                template_id="stock_sector_rotation",
            )
        )
    assert unknown_template.value.details["reason"] == "unknown_strategy_template"

    with pytest.raises(AppProcessError) as missing_run:
        _process(run=None, policy=None).propose(
            StrategyTemplateHandoffRequest(
                selection_run_id=run.run_id,
                template_id="stock_selection",
            )
        )
    assert missing_run.value.details["reason"] == "selection_run_not_found"

    with pytest.raises(AppProcessError) as missing_policy:
        _process(run=run, policy=None).propose(
            StrategyTemplateHandoffRequest(
                selection_run_id=run.run_id,
                template_id="stock_selection",
            )
        )
    assert missing_policy.value.details["reason"] == "selection_policy_snapshot_missing"


def test_handoff_from_research_case_keeps_objective_and_case_lineage() -> None:
    run = _stock_run()
    policy = _stock_policy(run)
    case = _case(run, case_id="case-1")
    proposal = _process(
        run=run,
        policy=policy,
        cases={case.case_id: case},
    ).propose(
        StrategyTemplateHandoffRequest(
            selection_run_id=run.run_id,
            template_id="stock_selection",
            research_case_id=case.case_id,
        )
    )

    assert proposal.spec_json["name"] == "研究: 验证动量与价值因子在月度调仓下的表现"
    assert proposal.lineage["research_case_id"] == case.case_id
    tags = proposal.spec_json["tags"]
    assert isinstance(tags, list)
    assert f"research-case:{case.case_id.rsplit(':', 1)[-1][:12]}" in list(tags)

    # 用例属于另一条运行时明确拒绝，不把目标错绑到当前运行。
    foreign = _case(_etf_run())
    with pytest.raises(AppProcessError) as error:
        _process(run=run, policy=policy, cases={foreign.case_id: foreign}).propose(
            StrategyTemplateHandoffRequest(
                selection_run_id=run.run_id,
                template_id="stock_selection",
                research_case_id=foreign.case_id,
            )
        )
    assert error.value.details["reason"] == "research_case_run_mismatch"


def test_proposed_spec_round_trips_through_persisted_legacy_deserialization() -> None:
    run = _stock_run()
    policy = _stock_policy(run)
    proposal = _process(run=run, policy=policy).propose(
        StrategyTemplateHandoffRequest(
            selection_run_id=run.run_id,
            template_id="stock_selection",
        )
    )

    from ditto_application.strategy_spec_legacy_deserialization import (
        deserialize_strategy_spec,
    )
    from ditto_strategy.models import StrategySpecRecord

    record = StrategySpecRecord(
        strategy_id="handoff-momentum-value",
        name=str(proposal.spec_json["name"]),
        spec_json=dict(proposal.spec_json),
    )
    spec = deserialize_strategy_spec(record)
    assert spec.signal_expressions == ("momentum_1m", "value_pe")
    assert spec.signal_weights == (0.6, 0.4)
    assert spec.template == "stock_selection"


def test_handoff_without_case_names_spec_from_run_spec_family() -> None:
    run = _stock_run()
    policy = _stock_policy(run)
    proposal = _process(run=run, policy=policy).propose(
        StrategyTemplateHandoffRequest(
            selection_run_id=run.run_id,
            template_id="stock_selection",
        )
    )

    assert proposal.spec_json["name"] == "研究: stock-core"


def test_handoff_rejects_blocked_runs() -> None:
    run = replace(
        _stock_run(),
        status=SelectionRunStatus.BLOCKED,
        candidates=(),
        missing_inputs=("bars",),
    )
    policy = _stock_policy(run)

    with pytest.raises(AppProcessError) as error:
        _process(run=run, policy=policy).propose(
            StrategyTemplateHandoffRequest(
                selection_run_id=run.run_id,
                template_id="stock_selection",
            )
        )
    assert error.value.details["reason"] == "selection_run_blocked"


def test_handoff_live_lane_knowledge_cutoff_after_as_of_is_accepted() -> None:
    run = replace(_stock_run(), knowledge_cutoff=_AS_OF + timedelta(days=1))
    policy = _stock_policy(run)
    proposal = _process(run=run, policy=policy).propose(
        StrategyTemplateHandoffRequest(
            selection_run_id=run.run_id,
            template_id="stock_selection",
        )
    )

    assert proposal.lineage["knowledge_cutoff"] == run.knowledge_cutoff
