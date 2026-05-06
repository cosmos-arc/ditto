"""StrategyRuntimeBuilder 单元测试。"""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

import ditto_application.builders as strategy_services
import pytest
from ditto_application.exceptions import AppBuilderError
from ditto_kernel.strategy import ImpactModel
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.specs import (
    CostModelSpec,
    ExecutionSpec,
    ScorerSpec,
    SelectorSpec,
    StrategySpec,
)
from ditto_strategy.models import StrategySpecRecord
from ditto_strategy.storage.sqlite.services.strategy_catalog_service import (
    StrategyCatalogService,
)


def _make_rotation_spec() -> StrategySpec:
    """构造测试用 etf_rotation StrategySpec。"""
    return StrategySpec(
        strategy_id="momentum-etf",
        name="Momentum ETF",
        template="etf_rotation",
        universe="cn_etf",
        asset_class="etf",
        scorer=ScorerSpec(method="rank"),
        selector=SelectorSpec(method="top_k", params={"k": 3}),
        execution=ExecutionSpec(
            frequency="M",
            method="calendar",
            cost_model=CostModelSpec(
                commission_rate=0.0005,
                slippage_bps=7.5,
                impact_model=ImpactModel.VOLUME_SHARE,
            ),
        ),
        params={
            "top_k": 3,
            "allocation_method": "score_weight",
            "cash_target": 0.05,
            "signal_column": "momentum_20d",
            "max_weight": 0.4,
            "max_positions": 3,
            "scoring_method": "rank",
            "scoring_ascending": True,
        },
        tags=("momentum", "etf"),
    )


def _make_spec_record(
    spec: StrategySpec,
    *,
    version: int = 3,
    status: str = "published",
) -> StrategySpecRecord:
    """构造测试用 StrategySpecRecord。"""
    return StrategySpecRecord(
        strategy_id=spec.strategy_id,
        name=spec.name,
        spec_json=asdict(spec),
        version=version,
        status=status,
        tags=spec.tags,
    )


class TestStrategyRuntimeBuilder:
    """Published strategy runtime 解析测试。"""

    def test_build_published_runtime_returns_spec_and_pipeline(self) -> None:
        """builder 应从 published spec 恢复 StrategySpec 并构造 Pipeline。"""
        spec = _make_rotation_spec()
        record = _make_spec_record(spec, version=7)
        catalog_service = MagicMock(spec=StrategyCatalogService)
        catalog_service.get_spec.return_value = record

        builder_cls = strategy_services.StrategyRuntimeBuilder
        builder = builder_cls(catalog_service=catalog_service)

        runtime = builder.build_published_runtime("momentum-etf", 7)

        assert runtime.record is record
        assert runtime.spec.strategy_id == "momentum-etf"
        assert runtime.spec.template == "etf_rotation"
        assert runtime.spec.execution.cost_model.commission_rate == 0.0005
        assert runtime.spec.selector.params == {"k": 3}
        assert isinstance(runtime.pipeline, StrategyPipeline)
        assert len(runtime.pipeline._stages) == 6
        catalog_service.get_spec.assert_called_once_with("momentum-etf", 7)

    def test_build_published_runtime_rejects_non_published_spec(self) -> None:
        """builder 只接受 published spec。"""
        spec = _make_rotation_spec()
        record = _make_spec_record(spec, status="draft")
        catalog_service = MagicMock(spec=StrategyCatalogService)
        catalog_service.get_spec.return_value = record

        builder_cls = strategy_services.StrategyRuntimeBuilder
        builder = builder_cls(catalog_service=catalog_service)

        with pytest.raises(AppBuilderError, match="published"):
            builder.build_published_runtime("momentum-etf", 3)
