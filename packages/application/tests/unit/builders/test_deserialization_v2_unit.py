"""StrategySpec v2 严格反序列化边界测试。"""

from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy

import pytest
from ditto_application.exceptions import AppBuilderError
from ditto_strategy.models import StrategySpecRecord


def _v2_payload() -> dict[str, object]:
    return {
        "schema_version": 2,
        "strategy_family_id": "family-etf-alpha",
        "strategy_kind": "etf_rotation",
        "name": "ETF Alpha",
        "pipeline": {
            "nodes": [
                {
                    "node_id": "universe",
                    "node_type": "builtin.universe",
                    "node_version": "1",
                    "category": "universe",
                    "config": {"universe_id": "csi_etf_broad"},
                    "enabled": True,
                },
                {
                    "node_id": "factors",
                    "node_type": "builtin.factor_set",
                    "node_version": "2",
                    "category": "factor_set",
                    "config": {"factor_ids": ["momentum_1m", "volatility_factor"]},
                    "enabled": True,
                },
            ],
            "sequence": ["universe", "factors"],
        },
        "parameter_schema": [
            {
                "name": "pipeline.nodes.factors.config.lookback",
                "dtype": "int",
                "min_value": 20,
                "max_value": 120,
                "step": 20,
                "allowed_values": [],
            },
        ],
        "metadata": {"description": "UI only"},
        "tags": ["research"],
    }


def _record(payload: dict[str, object]) -> StrategySpecRecord:
    return StrategySpecRecord(
        strategy_id="family-etf-alpha",
        name="ETF Alpha",
        spec_json=payload,
        version=1,
        status="draft",
    )


def _add_unknown_node_field(payload: dict[str, object]) -> None:
    pipeline = payload.get("pipeline")
    assert isinstance(pipeline, dict)
    nodes = pipeline.get("nodes")
    assert isinstance(nodes, list)
    node = nodes[0]
    assert isinstance(node, dict)
    node["unexpected"] = "value"


def _remove_node_field(payload: dict[str, object], field_name: str) -> None:
    pipeline = payload.get("pipeline")
    assert isinstance(pipeline, dict)
    nodes = pipeline.get("nodes")
    assert isinstance(nodes, list)
    node = nodes[0]
    assert isinstance(node, dict)
    node.pop(field_name)


def _replace_node_field(
    payload: dict[str, object],
    field_name: str,
    value: object,
) -> None:
    pipeline = payload.get("pipeline")
    assert isinstance(pipeline, dict)
    nodes = pipeline.get("nodes")
    assert isinstance(nodes, list)
    node = nodes[0]
    assert isinstance(node, dict)
    node[field_name] = value


def _replace_pipeline_field(
    payload: dict[str, object],
    field_name: str,
    value: object,
) -> None:
    pipeline = payload.get("pipeline")
    assert isinstance(pipeline, dict)
    pipeline[field_name] = value


class TestDeserializeStrategySpecV2:
    """新入口只接受 schema_version=2 的完整、类型化 payload。"""

    def test_deserializes_each_v2_field_to_domain_value_objects(self) -> None:
        from ditto_application.builders.deserialization import (
            deserialize_strategy_spec_v2,
        )
        from ditto_strategy.alpha.nodes import NodeCategory
        from ditto_strategy.alpha.specs import StrategyKind, StrategySpecV2

        spec = deserialize_strategy_spec_v2(_record(_v2_payload()))

        assert isinstance(spec, StrategySpecV2)
        assert spec.schema_version == 2
        assert spec.strategy_family_id == "family-etf-alpha"
        assert spec.strategy_kind is StrategyKind.ETF_ROTATION
        assert spec.pipeline.sequence == ("universe", "factors")
        assert spec.pipeline.nodes[0].category is NodeCategory.UNIVERSE
        assert spec.pipeline.nodes[1].ref.identity == "builtin.factor_set@2"
        assert spec.parameter_schema[0].dtype == "int"
        assert spec.metadata == {"description": "UI only"}
        assert spec.tags == ("research",)

    def test_rejects_legacy_payload_without_using_implicit_adapter(self) -> None:
        from ditto_application.builders.deserialization import (
            deserialize_strategy_spec_v2,
        )

        legacy = _record(
            {
                "template": "etf_rotation",
                "universe": "csi_etf_broad",
                "asset_class": "etf",
            },
        )

        with pytest.raises(AppBuilderError, match="schema_version"):
            deserialize_strategy_spec_v2(legacy)

    @pytest.mark.parametrize(
        "field_name",
        [
            "schema_version",
            "strategy_family_id",
            "strategy_kind",
            "name",
            "pipeline",
            "parameter_schema",
            "metadata",
            "tags",
        ],
    )
    def test_requires_every_canonical_top_level_field(self, field_name: str) -> None:
        from ditto_application.builders.deserialization import (
            deserialize_strategy_spec_v2,
        )

        payload = _v2_payload()
        payload.pop(field_name)

        with pytest.raises(AppBuilderError, match=field_name):
            deserialize_strategy_spec_v2(_record(payload))

    @pytest.mark.parametrize(
        "field_name",
        [
            "node_id",
            "node_type",
            "node_version",
            "category",
            "config",
            "enabled",
        ],
    )
    def test_requires_every_canonical_node_field(self, field_name: str) -> None:
        from ditto_application.builders.deserialization import (
            deserialize_strategy_spec_v2,
        )

        payload = _v2_payload()
        _remove_node_field(payload, field_name)

        with pytest.raises(AppBuilderError, match=field_name):
            deserialize_strategy_spec_v2(_record(payload))

    @pytest.mark.parametrize("field_name", ["nodes", "sequence"])
    def test_rejects_null_canonical_pipeline_collections(
        self,
        field_name: str,
    ) -> None:
        from ditto_application.builders.deserialization import (
            deserialize_strategy_spec_v2,
        )

        payload = _v2_payload()
        _replace_pipeline_field(payload, field_name, None)

        with pytest.raises(AppBuilderError, match=rf"pipeline\.{field_name}"):
            deserialize_strategy_spec_v2(_record(payload))

    def test_accepts_explicit_empty_canonical_pipeline_collections(self) -> None:
        from ditto_application.builders.deserialization import (
            deserialize_strategy_spec_v2,
        )

        payload = _v2_payload()
        _replace_pipeline_field(payload, "nodes", [])
        _replace_pipeline_field(payload, "sequence", [])

        spec = deserialize_strategy_spec_v2(_record(payload))

        assert spec.pipeline.nodes == ()
        assert spec.pipeline.sequence == ()

    @pytest.mark.parametrize(
        ("field_name", "mutate"),
        [
            pytest.param(
                "parameter_schema",
                lambda payload: payload.update(parameter_schema=None),
                id="null-parameter-schema",
            ),
            pytest.param(
                "metadata",
                lambda payload: payload.update(metadata=None),
                id="null-metadata",
            ),
            pytest.param(
                "tags",
                lambda payload: payload.update(tags=None),
                id="null-tags",
            ),
            pytest.param(
                "pipeline.nodes[0].config",
                lambda payload: _replace_node_field(payload, "config", None),
                id="null-node-config",
            ),
            pytest.param(
                "pipeline.nodes[0].config",
                lambda payload: _replace_node_field(
                    payload,
                    "config",
                    {1: "non-string-key"},
                ),
                id="non-string-config-key",
            ),
            pytest.param(
                "config.opaque",
                lambda payload: _replace_node_field(
                    payload,
                    "config",
                    {"opaque": object()},
                ),
                id="opaque-config-value",
            ),
        ],
    )
    def test_invalid_canonical_values_map_to_application_error(
        self,
        field_name: str,
        mutate: Callable[[dict[str, object]], None],
    ) -> None:
        from ditto_application.builders.deserialization import (
            deserialize_strategy_spec_v2,
        )

        payload = _v2_payload()
        mutate(payload)

        with pytest.raises(AppBuilderError, match=re.escape(field_name)):
            deserialize_strategy_spec_v2(_record(payload))

    @pytest.mark.parametrize(
        ("field_name", "mutate"),
        [
            pytest.param(
                "schema_version",
                lambda payload: payload.update(schema_version=True),
                id="bool-is-not-version",
            ),
            pytest.param(
                "strategy_kind",
                lambda payload: payload.update(strategy_kind="arbitrary_python"),
                id="unknown-strategy-kind",
            ),
            pytest.param(
                "pipeline.nodes[0]",
                _add_unknown_node_field,
                id="unknown-node-field",
            ),
            pytest.param(
                "spec_json",
                lambda payload: payload.update(unexpected="value"),
                id="unknown-top-level-field",
            ),
        ],
    )
    def test_rejects_wrong_types_unknown_values_and_extra_fields(
        self,
        field_name: str,
        mutate: Callable[[dict[str, object]], None],
    ) -> None:
        from ditto_application.builders.deserialization import (
            deserialize_strategy_spec_v2,
        )

        payload = deepcopy(_v2_payload())
        mutate(payload)

        with pytest.raises(AppBuilderError, match=re.escape(field_name)):
            deserialize_strategy_spec_v2(_record(payload))
