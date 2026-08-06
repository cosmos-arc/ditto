"""StrategySpec v2 严格反序列化边界测试。"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace

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


def _persisted_v2_payload(spec: object) -> dict[str, object]:
    from ditto_strategy.alpha.spec_codec import canonical_spec_payload
    from ditto_strategy.alpha.specs import StrategySpecV2

    assert isinstance(spec, StrategySpecV2)
    payload = canonical_spec_payload(spec)
    payload.update(
        name=spec.name,
        metadata={"description": "UI-only round-trip field"},
        tags=["research", "round-trip"],
    )
    return payload


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

    @pytest.mark.parametrize(
        "numeric_values",
        [
            pytest.param((10, 20, 5), id="integer-inputs"),
            pytest.param((10.0, 20.0, 5.0), id="float-inputs"),
        ],
    )
    def test_direct_v2_payload_and_hash_survive_strict_round_trip(
        self,
        numeric_values: tuple[int | float, int | float, int | float],
    ) -> None:
        from ditto_application.builders.deserialization import (
            deserialize_strategy_spec_v2,
        )
        from ditto_strategy.alpha.spec_codec import (
            canonical_spec_hash,
            canonical_spec_payload,
        )
        from ditto_strategy.alpha.specs import ParamConstraint

        scaffold = deserialize_strategy_spec_v2(_record(_v2_payload()))
        minimum, maximum, step = numeric_values
        direct = replace(
            scaffold,
            parameter_schema=(
                ParamConstraint(
                    name="pipeline.nodes.factors.config.lookback",
                    dtype="int",
                    min_value=minimum,
                    max_value=maximum,
                    step=step,
                ),
            ),
        )
        payload_before = canonical_spec_payload(direct)
        hash_before = canonical_spec_hash(direct)

        restored = deserialize_strategy_spec_v2(
            _record(_persisted_v2_payload(direct)),
        )

        assert canonical_spec_payload(restored) == payload_before
        assert canonical_spec_hash(restored) == hash_before

    @pytest.mark.parametrize("field_name", ["min_value", "max_value", "step"])
    def test_negative_zero_round_trip_uses_positive_zero_identity(
        self,
        field_name: str,
    ) -> None:
        from ditto_application.builders.deserialization import (
            deserialize_strategy_spec_v2,
        )
        from ditto_strategy.alpha.spec_codec import (
            canonical_spec_bytes,
            canonical_spec_hash,
        )

        scaffold = deserialize_strategy_spec_v2(_record(_v2_payload()))
        negative_parameter = replace(
            scaffold.parameter_schema[0],
            **{field_name: -0.0},
        )
        direct = replace(
            scaffold,
            parameter_schema=(negative_parameter,),
        )
        positive_parameter = replace(
            scaffold.parameter_schema[0],
            **{field_name: 0.0},
        )
        canonical = replace(
            scaffold,
            parameter_schema=(positive_parameter,),
        )

        restored = deserialize_strategy_spec_v2(
            _record(_persisted_v2_payload(direct)),
        )
        restored_value = getattr(restored.parameter_schema[0], field_name)

        assert math.copysign(1.0, restored_value) == 1.0
        assert canonical_spec_bytes(restored) == canonical_spec_bytes(canonical)
        assert canonical_spec_hash(restored) == canonical_spec_hash(canonical)

    def test_nested_node_config_round_trip_uses_positive_zero_identity(
        self,
    ) -> None:
        from ditto_application.builders.deserialization import (
            deserialize_strategy_spec_v2,
        )
        from ditto_strategy.alpha.spec_codec import (
            canonical_spec_bytes,
            canonical_spec_hash,
        )

        scaffold = deserialize_strategy_spec_v2(_record(_v2_payload()))
        negative_factor = next(
            node for node in scaffold.pipeline.nodes if node.node_id == "factors"
        )
        negative_factor = replace(
            negative_factor,
            config={"outer": [{"inner": (-0.0, {"values": [-0.0, -5.0]})}]},
        )
        direct = replace(
            scaffold,
            pipeline=replace(
                scaffold.pipeline,
                nodes=tuple(
                    negative_factor if node.node_id == "factors" else node
                    for node in scaffold.pipeline.nodes
                ),
            ),
        )
        positive_factor = replace(
            negative_factor,
            config={"outer": [{"inner": (0.0, {"values": [0.0, -5.0]})}]},
        )
        canonical = replace(
            scaffold,
            pipeline=replace(
                scaffold.pipeline,
                nodes=tuple(
                    positive_factor if node.node_id == "factors" else node
                    for node in scaffold.pipeline.nodes
                ),
            ),
        )

        restored = deserialize_strategy_spec_v2(
            _record(_persisted_v2_payload(direct)),
        )
        restored_factor = next(
            node for node in restored.pipeline.nodes if node.node_id == "factors"
        )
        outer = restored_factor.config["outer"]
        assert isinstance(outer, tuple)
        inner = outer[0]["inner"]
        values = inner[1]["values"]

        assert math.copysign(1.0, inner[0]) == 1.0
        assert math.copysign(1.0, values[0]) == 1.0
        assert math.copysign(1.0, values[1]) == -1.0
        assert canonical_spec_bytes(restored) == canonical_spec_bytes(canonical)
        assert canonical_spec_hash(restored) == canonical_spec_hash(canonical)

    @pytest.mark.parametrize(
        "numeric_values",
        [
            pytest.param((10, 20, 5), id="integer-inputs"),
            pytest.param((10.0, 20.0, 5.0), id="float-inputs"),
        ],
    )
    def test_legacy_adapter_payload_and_hash_survive_strict_round_trip(
        self,
        numeric_values: tuple[int | float, int | float, int | float],
    ) -> None:
        from ditto_application.builders.deserialization import (
            deserialize_strategy_spec_v2,
        )
        from ditto_strategy.alpha.spec_codec import (
            adapt_legacy_strategy_spec,
            canonical_spec_hash,
            canonical_spec_payload,
        )
        from ditto_strategy.alpha.specs import ParamConstraint, StrategySpec

        minimum, maximum, step = numeric_values
        legacy = StrategySpec(
            strategy_id="legacy-etf-alpha",
            name="Legacy ETF Alpha",
            template="etf_rotation",
            universe="csi_etf_broad",
            asset_class="etf",
            param_constraints=(
                ParamConstraint(
                    name="lookback",
                    dtype="int",
                    min_value=minimum,
                    max_value=maximum,
                    step=step,
                ),
            ),
        )
        adapted = adapt_legacy_strategy_spec(legacy)
        payload_before = canonical_spec_payload(adapted)
        hash_before = canonical_spec_hash(adapted)

        restored = deserialize_strategy_spec_v2(
            _record(_persisted_v2_payload(adapted)),
        )

        assert canonical_spec_payload(restored) == payload_before
        assert canonical_spec_hash(restored) == hash_before

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

    @pytest.mark.parametrize("field_name", ["min_value", "max_value", "step"])
    def test_huge_parameter_number_maps_float_overflow_to_application_error(
        self,
        field_name: str,
    ) -> None:
        from ditto_application.builders.deserialization import (
            deserialize_strategy_spec_v2,
        )

        payload = _v2_payload()
        parameter_schema = payload.get("parameter_schema")
        assert isinstance(parameter_schema, list)
        parameter = parameter_schema[0]
        assert isinstance(parameter, dict)
        parameter[field_name] = 1 << 20_000

        with pytest.raises(AppBuilderError) as exc_info:
            deserialize_strategy_spec_v2(_record(payload))

        expected_field = f"parameter_schema[0].{field_name}"
        assert expected_field in str(exc_info.value)
        assert exc_info.value.details["field_name"] == expected_field
        assert exc_info.value.details["reason"] == "numeric_overflow"
        assert isinstance(exc_info.value.__cause__, OverflowError)

    @pytest.mark.parametrize("field_name", ["min_value", "max_value", "step"])
    def test_parameter_integer_that_would_collapse_in_float_fails_closed(
        self,
        field_name: str,
    ) -> None:
        from ditto_application.builders.deserialization import (
            deserialize_strategy_spec_v2,
        )

        exact_integer = 2**53
        lossy_integer = exact_integer + 1
        assert float(exact_integer) == float(lossy_integer)

        exact_payload = _v2_payload()
        exact_schema = exact_payload.get("parameter_schema")
        assert isinstance(exact_schema, list)
        exact_parameter = exact_schema[0]
        assert isinstance(exact_parameter, dict)
        exact_parameter[field_name] = exact_integer
        exact_spec = deserialize_strategy_spec_v2(_record(exact_payload))
        assert getattr(exact_spec.parameter_schema[0], field_name) == float(
            exact_integer,
        )

        lossy_payload = _v2_payload()
        lossy_schema = lossy_payload.get("parameter_schema")
        assert isinstance(lossy_schema, list)
        lossy_parameter = lossy_schema[0]
        assert isinstance(lossy_parameter, dict)
        lossy_parameter[field_name] = lossy_integer

        with pytest.raises(AppBuilderError) as exc_info:
            deserialize_strategy_spec_v2(_record(lossy_payload))

        expected_field = f"parameter_schema[0].{field_name}"
        assert exc_info.value.details["field_name"] == expected_field
        assert exc_info.value.details["reason"] == "numeric_precision_loss"

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
