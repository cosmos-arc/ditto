"""Shared strict codecs for canonical experiment planning document nodes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from ditto_strategy.alpha.parameters import ParameterValue

from ditto_application.processes.experiments._planning_values import (
    BaselineInputValue,
)
from ditto_application.processes.experiments._preflight_decode_values import (
    decode_boolean,
    decode_date,
    decode_integer,
    decode_list,
    decode_mapping,
    decode_string,
)
from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)
from ditto_application.processes.experiments.planning import (
    BaselineDescriptor,
    CandidateMatrixSpec,
    ParameterAxis,
)
from ditto_application.processes.experiments.planning_probes import (
    ResearchDatasetRequirement,
)

__all__ = [
    "candidate_matrix_spec_payload",
    "decode_candidate_matrix_spec",
    "decode_dataset_requirements",
    "planning_parameter_type",
]


def planning_parameter_type(value: object) -> str:
    """Return the canonical explicit type tag for one matrix scalar."""
    if type(value) is bool:
        return "bool"
    if type(value) is int:
        return "int"
    if type(value) is float:
        return "float"
    if type(value) is str:
        return "string"
    raise experiment_process_error("candidate parameter has an unsupported JSON type")


def _typed_parameter(value: object, declared_type: object) -> ParameterValue:
    if planning_parameter_type(value) != decode_string(
        declared_type,
        "candidate_parameter.type",
    ):
        raise experiment_process_error(
            "candidate parameter type tag does not match its value"
        )
    return cast("ParameterValue", value)


def decode_candidate_matrix_spec(value: object) -> CandidateMatrixSpec:
    """Decode one exact canonical candidate-matrix preimage."""
    payload = decode_mapping(value, "work.matrix_spec")
    baseline = decode_mapping(payload.get("baseline"), "work.matrix_spec.baseline")
    axes = tuple(
        ParameterAxis(
            name=decode_string(axis.get("name"), "work.matrix_spec.axis.name"),
            values=tuple(
                _typed_parameter(item.get("value"), item.get("type"))
                for raw_item in decode_list(
                    axis.get("values"),
                    "work.matrix_spec.axis.values",
                )
                for item in (decode_mapping(raw_item, "work.matrix_spec.axis.value"),)
            ),
        )
        for raw_axis in decode_list(payload.get("axes"), "work.matrix_spec.axes")
        for axis in (decode_mapping(raw_axis, "work.matrix_spec.axis"),)
    )
    return CandidateMatrixSpec(
        baseline=BaselineDescriptor(
            descriptor_type=decode_string(
                baseline.get("descriptor_type"),
                "work.matrix_spec.baseline.descriptor_type",
            ),
            payload=cast(
                "Mapping[str, BaselineInputValue]",
                decode_mapping(
                    baseline.get("payload"),
                    "work.matrix_spec.baseline.payload",
                ),
            ),
            schema_version=decode_integer(
                baseline.get("schema_version"),
                "work.matrix_spec.baseline.schema_version",
            ),
        ),
        axes=axes,
        candidate_limit=decode_integer(
            payload.get("candidate_limit"),
            "work.matrix_spec.candidate_limit",
        ),
    )


def candidate_matrix_spec_payload(
    matrix: CandidateMatrixSpec,
) -> Mapping[str, object]:
    """Project one matrix into the canonical planning-document shape."""
    return {
        "baseline": {
            "descriptor_type": matrix.baseline.descriptor_type,
            "payload": matrix.baseline.payload,
            "schema_version": matrix.baseline.schema_version,
        },
        "axes": [
            {
                "name": axis.name,
                "values": [
                    {"type": planning_parameter_type(value), "value": value}
                    for value in axis.values
                ],
            }
            for axis in matrix.axes
        ],
        "candidate_limit": matrix.candidate_limit,
    }


def decode_dataset_requirements(
    value: object,
) -> tuple[ResearchDatasetRequirement, ...]:
    """Decode exact dataset/snapshot bindings from canonical JSON values."""
    return tuple(
        ResearchDatasetRequirement(
            dataset_id=decode_string(item.get("dataset_id"), "binding.dataset_id"),
            expected_snapshot_ids=tuple(
                decode_string(snapshot_id, "binding.expected_snapshot_id")
                for snapshot_id in decode_list(
                    item.get("expected_snapshot_ids"),
                    "binding.expected_snapshot_ids",
                )
            ),
            requires_pit_universe=decode_boolean(
                item.get("requires_pit_universe"),
                "binding.requires_pit_universe",
            ),
            certified_from=decode_date(
                item.get("certified_from"),
                "binding.certified_from",
            ),
        )
        for raw_item in decode_list(value, "authority.dataset_bindings")
        for item in (decode_mapping(raw_item, "authority.dataset_binding"),)
    )
