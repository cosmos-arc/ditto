"""StrategyRuntimeBuilder 单元测试。"""

from __future__ import annotations

from dataclasses import asdict
from inspect import Parameter, signature
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

    def test_published_runtime_requires_canonical_spec_hash(self) -> None:
        """运行时值对象不得以空 hash 作为隐式 fallback。"""
        runtime_signature = signature(strategy_services.PublishedStrategyRuntime)

        assert runtime_signature.parameters["spec_hash"].default is Parameter.empty

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
        from ditto_strategy.alpha.spec_codec import (
            adapt_legacy_strategy_spec,
            canonical_spec_hash,
        )

        assert runtime.spec_hash == canonical_spec_hash(
            adapt_legacy_strategy_spec(runtime.spec),
        )
        assert len(runtime.spec_hash) == 64
        catalog_service.get_spec.assert_called_once_with("momentum-etf", 7)

    def test_build_published_runtime_defaults_to_latest_published_version(
        self,
    ) -> None:
        """未指定版本时应忽略更新的 draft。"""
        spec = _make_rotation_spec()
        published_v1 = _make_spec_record(spec, version=1)
        draft_v2 = _make_spec_record(spec, version=2, status="draft")
        catalog_service = MagicMock(spec=StrategyCatalogService)
        catalog_service.get_spec.return_value = draft_v2
        catalog_service.get_latest_published.return_value = published_v1
        builder = strategy_services.StrategyRuntimeBuilder(
            catalog_service=catalog_service,
        )

        runtime = builder.build_published_runtime("momentum-etf")

        assert runtime.record is published_v1
        catalog_service.get_latest_published.assert_called_once_with("momentum-etf")
        catalog_service.get_spec.assert_not_called()

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

    def test_default_slippage_bps_is_1(self) -> None:
        """反序列化时若 spec_json 缺失 slippage_bps，默认值应为 1.0 bps。"""
        spec = _make_rotation_spec()
        record = _make_spec_record(spec)
        # 从 spec_json 中移除 slippage_bps，模拟旧数据无此字段
        spec_json: dict[str, object] = dict(record.spec_json)
        exec_payload: dict[str, object] = dict(
            spec_json.get("execution", {})  # type: ignore[arg-type]
        )
        cost_payload: dict[str, object] = dict(
            exec_payload.get("cost_model", {})  # type: ignore[arg-type]
        )
        cost_payload.pop("slippage_bps", None)
        exec_payload["cost_model"] = cost_payload
        spec_json["execution"] = exec_payload
        record = StrategySpecRecord(
            strategy_id=record.strategy_id,
            name=record.name,
            spec_json=spec_json,
            version=record.version,
            status=record.status,
            tags=record.tags,
        )

        catalog_service = MagicMock(spec=StrategyCatalogService)
        catalog_service.get_latest_published.return_value = record
        builder = strategy_services.StrategyRuntimeBuilder(
            catalog_service=catalog_service,
        )

        runtime = builder.build_published_runtime("momentum-etf")
        assert runtime.spec.execution.cost_model.slippage_bps == 1.0
