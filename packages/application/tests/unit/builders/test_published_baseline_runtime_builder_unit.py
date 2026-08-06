"""Published exact-baseline runtime boundary tests."""

from __future__ import annotations

from dataclasses import asdict
from inspect import signature

import pytest
from ditto_application.builders.published_baseline_runtime_builder import (
    PublishedBaselineRuntimeBuilder,
)
from ditto_application.builders.research_runtime_builder import (
    ResearchRuntimeBuilder,
    ResearchSnapshotIdentity,
)
from ditto_application.exceptions import AppBuilderError
from ditto_strategy.alpha.parameters import CandidateParameter, legacy_parameter_path
from ditto_strategy.alpha.specs import (
    ScorerSpec,
    SelectorSpec,
    StrategySpec,
)
from ditto_strategy.models import StrategySpecRecord


def _record(
    *,
    template: str = "etf_rotation",
) -> StrategySpecRecord:
    asset_class = "etf" if template == "etf_rotation" else "equity"
    universe = "csi_etf_broad" if template == "etf_rotation" else "all_a_shares"
    spec = StrategySpec(
        strategy_id="published-baseline",
        name="Published baseline",
        template=template,
        universe=universe,
        asset_class=asset_class,
        scorer=ScorerSpec(method="rank"),
        selector=SelectorSpec(method="top_k", params={"k": 3}),
        params={
            "allocation_method": "equal_weight",
            "scoring_ascending": False,
            "top_k": 3,
        },
        required_datasets=(
            "etf_daily" if template == "etf_rotation" else "stock_daily",
        ),
    )
    return StrategySpecRecord(
        strategy_id=spec.strategy_id,
        name=spec.name,
        spec_json=asdict(spec),
        version=7,
        tags=spec.tags,
    )


def _snapshot() -> ResearchSnapshotIdentity:
    return ResearchSnapshotIdentity("snapshot-v1", "a" * 64)


def test_published_baseline_builder_is_independent_and_has_no_lookup_switch() -> None:
    constructor = signature(PublishedBaselineRuntimeBuilder).parameters
    build = signature(PublishedBaselineRuntimeBuilder.build).parameters

    assert not issubclass(PublishedBaselineRuntimeBuilder, ResearchRuntimeBuilder)
    assert "catalog_service" not in constructor
    assert "allow_unpublished" not in constructor
    assert "allow_unpublished" not in build
    assert "record" in build


def test_published_baseline_builder_builds_only_exact_published_etf_record() -> None:
    record = _record()

    runtime = PublishedBaselineRuntimeBuilder().build(
        record=record,
        candidate_parameters=(),
        snapshot_identity=_snapshot(),
        version_status="published",
    )

    assert runtime.strategy_id == record.strategy_id
    assert runtime.strategy_version == record.version
    assert runtime.version_status == "published"
    assert runtime.resolved_spec.strategy_kind.value == "etf_rotation"
    assert runtime.legacy_spec.required_datasets == ("etf_daily",)


@pytest.mark.parametrize("status", ["draft", "review", "retired"])
def test_published_baseline_builder_rejects_every_non_published_status(
    status: str,
) -> None:
    with pytest.raises(AppBuilderError) as exc_info:
        PublishedBaselineRuntimeBuilder().build(
            record=_record(),
            candidate_parameters=(),
            snapshot_identity=_snapshot(),
            version_status=status,
        )

    assert exc_info.value.details == {
        "code": "SPEC_INVALID",
        "reason": "published_baseline_version_required",
        "path": "version_status",
        "strategy_id": "published-baseline",
        "strategy_version": 7,
        "version_status": status,
    }


def test_published_baseline_builder_rejects_non_etf_runtime_lane() -> None:
    with pytest.raises(AppBuilderError) as exc_info:
        PublishedBaselineRuntimeBuilder().build(
            record=_record(template="stock_selection"),
            candidate_parameters=(),
            snapshot_identity=_snapshot(),
            version_status="published",
        )

    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == "published_baseline_lane_not_supported"
    assert exc_info.value.details["actual_lane"] == "stock_selection"


def test_published_baseline_builder_forbids_candidate_parameter_binding() -> None:
    with pytest.raises(AppBuilderError) as exc_info:
        PublishedBaselineRuntimeBuilder().build(
            record=_record(),
            candidate_parameters=(
                CandidateParameter(path=legacy_parameter_path("top_k"), value=2),
            ),
            snapshot_identity=_snapshot(),
            version_status="published",
        )

    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == (
        "published_baseline_parameters_forbidden"
    )


def test_research_runtime_builder_still_rejects_the_same_published_record() -> None:
    record = _record()

    with pytest.raises(AppBuilderError) as exc_info:
        ResearchRuntimeBuilder().build(
            record=record,
            candidate_parameters=(),
            snapshot_identity=_snapshot(),
            version_status="published",
        )

    assert exc_info.value.details["reason"] == "research_version_not_buildable"
