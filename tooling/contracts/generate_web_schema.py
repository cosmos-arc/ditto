"""Generate and verify Web OpenAPI types from the local canonical snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast
from urllib.parse import unquote

from tooling.dev.toolchain import node_executable

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SNAPSHOT = _REPO_ROOT / "contracts/openapi/v1.json"
_DEFAULT_OUTPUT = _REPO_ROOT / "apps/web/src/api/generated/schema.d.ts"
_DEFAULT_RESPONSE_OUTPUT = (
    _REPO_ROOT / "apps/web/src/api/generated/operation-contracts.ts"
)
_GENERATOR_PACKAGE = _REPO_ROOT / "node_modules/openapi-typescript/package.json"
_GENERATOR_CLI = _REPO_ROOT / "node_modules/openapi-typescript/bin/cli.js"
EXPECTED_GENERATOR_VERSION = "7.13.0"
OPERATION_CONTRACT_GENERATOR_VERSION = "4"
_HTTP_METHODS = frozenset(
    {"delete", "get", "head", "options", "patch", "post", "put", "trace"}
)
_RESPONSE_STATUS = re.compile(r"^(?:[1-5][0-9]{2}|[1-5]XX|default)$")
_MEDIA_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_INVALID_POINTER_ESCAPE = re.compile(r"~(?![01])")
_ASCII_CONTROL_LIMIT = 32
_QUOTED_VALUE_MIN_LENGTH = 2
_PARAMETER_LOCATIONS = ("cookie", "header", "path", "query")


class CodegenError(RuntimeError):
    """The local deterministic TypeScript generation contract was violated."""


class RemoteReferenceError(CodegenError):
    """A reference escaped the canonical single-file contract boundary."""


class GeneratedSchemaMismatchError(CodegenError):
    """The committed Web types differ from a fresh local generation."""


Generator = Callable[[Path, Path], None]


def generated_header(*, schema_sha256: str, generator_version: str) -> str:
    """Return the stable provenance header for the checked-in generated file."""
    return (
        "/**\n"
        " * DO NOT EDIT: generated from contracts/openapi/v1.json.\n"
        f" * Schema SHA-256: {schema_sha256}\n"
        f" * Generator: openapi-typescript {generator_version}\n"
        " */\n\n"
    )


def generated_operation_contracts_header(*, schema_sha256: str) -> str:
    """Return provenance for the runtime response-contract projection."""
    return (
        "/**\n"
        " * DO NOT EDIT: generated from contracts/openapi/v1.json.\n"
        f" * Schema SHA-256: {schema_sha256}\n"
        " * Generator: ditto-operation-response-contracts "
        f"{OPERATION_CONTRACT_GENERATOR_VERSION}\n"
        " */\n\n"
    )


def _walk_references(value: object) -> list[str]:
    references: list[str] = []
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        reference = mapping.get("$ref")
        if isinstance(reference, str):
            references.append(reference)
        for child in mapping.values():
            references.extend(_walk_references(child))
    elif isinstance(value, list):
        for child in value:
            references.extend(_walk_references(child))
    return references


def assert_local_only_references(schema: object) -> None:
    """Require every reference to stay inside the one canonical JSON file."""
    external = sorted(
        reference
        for reference in _walk_references(schema)
        if not reference.startswith("#")
    )
    if external:
        raise RemoteReferenceError(
            "OpenAPI generation is local-only and snapshot-contained; "
            + "external $ref is forbidden: "
            + ", ".join(external)
        )


def load_local_schema(snapshot_path: Path) -> tuple[dict[str, object], bytes]:
    """Read one local JSON snapshot and validate its offline input boundary."""
    snapshot_path = snapshot_path.resolve(strict=True)
    payload = snapshot_path.read_bytes()
    try:
        loaded: object = json.loads(payload)
    except json.JSONDecodeError as error:
        raise CodegenError(f"invalid OpenAPI JSON: {snapshot_path}: {error}") from error
    if not isinstance(loaded, dict):
        raise CodegenError(f"OpenAPI root must be an object: {snapshot_path}")
    schema = cast("dict[str, object]", loaded)
    assert_local_only_references(schema)
    return schema, payload


def _mapping(value: object, *, context: str) -> Mapping[object, object]:
    if not isinstance(value, Mapping):
        raise CodegenError(f"{context} must be an object")
    return cast("Mapping[object, object]", value)


def _json_pointer_value(schema: object, reference: str, *, context: str) -> object:
    if reference == "#":
        return schema
    if not reference.startswith("#/"):
        raise CodegenError(
            f"{context} has an invalid local JSON Pointer: {reference!r}"
        )
    current = schema
    for encoded_token in unquote(reference[2:]).split("/"):
        if _INVALID_POINTER_ESCAPE.search(encoded_token):
            raise CodegenError(
                f"{context} has an invalid JSON Pointer escape: {reference!r}"
            )
        token = encoded_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            mapping = cast("Mapping[object, object]", current)
            if token not in mapping:
                raise CodegenError(
                    f"{context} references a missing JSON Pointer: {reference!r}"
                )
            current = mapping[token]
            continue
        if isinstance(current, list):
            if (
                not token.isdecimal()
                or (len(token) > 1 and token.startswith("0"))
                or int(token) >= len(current)
            ):
                raise CodegenError(
                    f"{context} references an invalid array index: {reference!r}"
                )
            current = current[int(token)]
            continue
        raise CodegenError(
            f"{context} traverses a non-container JSON value: {reference!r}"
        )
    return current


def _resolved_response(
    schema: Mapping[str, object],
    response: object,
    *,
    context: str,
    references: tuple[str, ...] = (),
) -> Mapping[object, object]:
    response_mapping = _mapping(response, context=context)
    reference = response_mapping.get("$ref")
    if reference is None:
        return response_mapping
    if not isinstance(reference, str):
        raise CodegenError(f"{context} response $ref must be a string")
    unsupported_siblings = sorted(
        str(key)
        for key in response_mapping
        if key not in {"$ref", "summary", "description"}
        and not (isinstance(key, str) and key.startswith("x-"))
    )
    if unsupported_siblings:
        raise CodegenError(
            f"{context} response $ref has unsupported siblings: "
            + ", ".join(unsupported_siblings)
        )
    if reference in references:
        chain = " -> ".join((*references, reference))
        raise CodegenError(f"{context} has a cyclic response ref: {chain}")
    target = _json_pointer_value(schema, reference, context=context)
    return _resolved_response(
        schema,
        target,
        context=context,
        references=(*references, reference),
    )


def _resolved_path_item(
    schema: Mapping[str, object],
    path_item: object,
    *,
    context: str,
    references: tuple[str, ...] = (),
) -> Mapping[object, object]:
    path_mapping = _mapping(path_item, context=context)
    reference = path_mapping.get("$ref")
    if reference is None:
        return path_mapping
    if not isinstance(reference, str):
        raise CodegenError(f"{context} path item $ref must be a string")
    if reference in references:
        chain = " -> ".join((*references, reference))
        raise CodegenError(f"{context} has a cyclic path item ref: {chain}")
    resolved = dict(
        _resolved_path_item(
            schema,
            _json_pointer_value(schema, reference, context=context),
            context=context,
            references=(*references, reference),
        )
    )
    for key, value in path_mapping.items():
        if key != "$ref":
            resolved[key] = value
    return resolved


def _resolved_parameter(
    schema: Mapping[str, object],
    parameter: object,
    *,
    context: str,
    references: tuple[str, ...] = (),
) -> Mapping[object, object]:
    parameter_mapping = _mapping(parameter, context=context)
    reference = parameter_mapping.get("$ref")
    if reference is None:
        return parameter_mapping
    if not isinstance(reference, str):
        raise CodegenError(f"{context} parameter $ref must be a string")
    if reference in references:
        chain = " -> ".join((*references, reference))
        raise CodegenError(f"{context} has a cyclic parameter ref: {chain}")
    unsupported_siblings = sorted(
        str(key)
        for key in parameter_mapping
        if key not in {"$ref", "summary", "description"}
        and not (isinstance(key, str) and key.startswith("x-"))
    )
    if unsupported_siblings:
        raise CodegenError(
            f"{context} parameter $ref has unsupported siblings: "
            + ", ".join(unsupported_siblings)
        )
    return _resolved_parameter(
        schema,
        _json_pointer_value(schema, reference, context=context),
        context=context,
        references=(*references, reference),
    )


def _resolved_schema(
    schema: Mapping[str, object],
    value: object,
    *,
    context: str,
    references: tuple[str, ...] = (),
) -> Mapping[object, object]:
    """Resolve a local OpenAPI 3.1 Schema Object including legal ref siblings."""
    schema_mapping = _mapping(value, context=context)
    reference = schema_mapping.get("$ref")
    if reference is None:
        return schema_mapping
    if not isinstance(reference, str):
        raise CodegenError(f"{context} schema $ref must be a string")
    if reference in references:
        chain = " -> ".join((*references, reference))
        raise CodegenError(f"{context} has a cyclic schema ref: {chain}")
    resolved = dict(
        _resolved_schema(
            schema,
            _json_pointer_value(schema, reference, context=context),
            context=context,
            references=(*references, reference),
        )
    )
    for key, item in schema_mapping.items():
        if key != "$ref":
            resolved[key] = item
    return resolved


def _media_sections(value: str, *, context: str) -> tuple[str, ...]:
    sections: list[str] = []
    start = 0
    quoted = False
    escaped = False
    for index, character in enumerate(value):
        if ord(character) < _ASCII_CONTROL_LIMIT and character != "\t":
            raise CodegenError(f"{context} contains a control character")
        if escaped:
            escaped = False
            continue
        if quoted and character == "\\":
            escaped = True
            continue
        if character == '"':
            quoted = not quoted
            continue
        if character == ";" and not quoted:
            sections.append(value[start:index].strip())
            start = index + 1
    if quoted or escaped:
        raise CodegenError(f"{context} contains an unterminated quoted parameter")
    sections.append(value[start:].strip())
    return tuple(sections)


def _quoted_parameter(value: str, *, context: str) -> str:
    if len(value) < _QUOTED_VALUE_MIN_LENGTH or value[0] != '"' or value[-1] != '"':
        raise CodegenError(f"{context} has an invalid quoted parameter")
    decoded: list[str] = []
    escaped = False
    for character in value[1:-1]:
        if escaped:
            decoded.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"' or ord(character) < _ASCII_CONTROL_LIMIT:
            raise CodegenError(f"{context} has an invalid quoted parameter")
        else:
            decoded.append(character)
    if escaped:
        raise CodegenError(f"{context} has an invalid quoted parameter")
    escaped_value = "".join(decoded).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped_value}"'


def _normalize_media_type(value: str, *, context: str) -> str:
    sections = _media_sections(value.strip(), context=context)
    if not sections[0] or sections[0].count("/") != 1:
        raise CodegenError(f"{context} is invalid: {value!r}")
    raw_type, raw_subtype = (part.strip() for part in sections[0].split("/", 1))
    if (
        (raw_type != "*" and _MEDIA_TOKEN.fullmatch(raw_type) is None)
        or (raw_subtype != "*" and _MEDIA_TOKEN.fullmatch(raw_subtype) is None)
        or (raw_type == "*" and raw_subtype != "*")
    ):
        raise CodegenError(f"{context} is invalid: {value!r}")
    parameters: dict[str, str] = {}
    for section in sections[1:]:
        if not section or "=" not in section:
            raise CodegenError(f"{context} has an invalid parameter: {value!r}")
        raw_name, raw_parameter = (part.strip() for part in section.split("=", 1))
        name = raw_name.lower()
        if _MEDIA_TOKEN.fullmatch(name) is None or name in parameters:
            raise CodegenError(
                f"{context} has an invalid or duplicate parameter: {value!r}"
            )
        if raw_parameter.startswith('"'):
            parameter = _quoted_parameter(raw_parameter, context=context)
        elif _MEDIA_TOKEN.fullmatch(raw_parameter) is not None:
            parameter = raw_parameter
        else:
            raise CodegenError(f"{context} has an invalid parameter value: {value!r}")
        parameters[name] = parameter.lower() if name == "charset" else parameter
    essence = f"{raw_type.lower()}/{raw_subtype.lower()}"
    return essence + "".join(
        f";{name}={parameters[name]}" for name in sorted(parameters)
    )


def _response_media_types(
    schema: Mapping[str, object],
    response: object,
    *,
    operation: str,
    status: str,
) -> tuple[str, ...]:
    response_mapping = _resolved_response(
        schema,
        response,
        context=f"OpenAPI response {operation} {status}",
    )
    content = response_mapping.get("content")
    if content is None:
        return ()
    content_mapping = _mapping(
        content,
        context=f"OpenAPI response content {operation} {status}",
    )
    normalized: set[str] = set()
    for media_type in content_mapping:
        if not isinstance(media_type, str):
            raise CodegenError(
                f"OpenAPI response media type {operation} {status} must be a string"
            )
        candidate = _normalize_media_type(
            media_type,
            context=f"OpenAPI response media type {operation} {status}",
        )
        if candidate in normalized:
            raise CodegenError(
                f"OpenAPI response media type {operation} {status} is duplicated"
            )
        normalized.add(candidate)
    return tuple(sorted(normalized))


def _project_response_map(
    schema: Mapping[str, object],
    responses: Mapping[object, object],
    *,
    operation: str,
) -> dict[str, tuple[str, ...]]:
    projected: dict[str, tuple[str, ...]] = {}
    for status_value, response in responses.items():
        if isinstance(status_value, str) and status_value.startswith("x-"):
            continue
        if (
            not isinstance(status_value, str)
            or _RESPONSE_STATUS.fullmatch(status_value) is None
        ):
            raise CodegenError(
                f"OpenAPI response status is invalid for {operation}: "
                + f"{status_value!r}"
            )
        projected[status_value] = _response_media_types(
            schema,
            response,
            operation=operation,
            status=status_value,
        )
    if not projected:
        raise CodegenError(f"OpenAPI operation has no concrete responses: {operation}")
    return projected


def _schema_enum_values(
    schema: Mapping[str, object],
    value: object,
    *,
    context: str,
) -> tuple[str, ...]:
    resolved = _resolved_schema(schema, value, context=context)
    raw_values = resolved.get("enum")
    if not isinstance(raw_values, list) or not raw_values:
        raise CodegenError(f"{context} must define a non-empty string enum")
    values: list[str] = []
    for raw_value in raw_values:
        if not isinstance(raw_value, str) or not raw_value:
            raise CodegenError(f"{context} must define a non-empty string enum")
        if raw_value in values:
            raise CodegenError(f"{context} contains a duplicate enum value")
        values.append(raw_value)
    return tuple(values)


def _event_data_schema_contract(
    schema: Mapping[str, object],
    media: Mapping[object, object],
    *,
    context: str,
) -> tuple[
    str,
    Mapping[object, object],
    frozenset[str],
    int,
    tuple[str, ...],
    tuple[str, ...] | None,
]:
    raw_data_schema = _mapping(
        media.get("x-ditto-sse-data-schema"),
        context=f"{context} x-ditto-sse-data-schema",
    )
    if set(raw_data_schema) != {"$ref"}:
        raise CodegenError(
            f"{context} data schema must be one exact local component reference"
        )
    reference = raw_data_schema.get("$ref")
    if not isinstance(reference, str) or not reference.startswith(
        "#/components/schemas/"
    ):
        raise CodegenError(f"{context} data schema must reference #/components/schemas")
    data_schema = _resolved_schema(
        schema,
        raw_data_schema,
        context=f"{context} data schema",
    )
    if (
        data_schema.get("type") != "object"
        or data_schema.get("additionalProperties") is not False
    ):
        raise CodegenError(f"{context} data schema must be a closed object schema")
    properties = _mapping(
        data_schema.get("properties"),
        context=f"{context} data schema properties",
    )
    required = data_schema.get("required")
    if not isinstance(required, list) or any(
        not isinstance(item, str) for item in required
    ):
        raise CodegenError(f"{context} data schema required must be a string array")
    required_names = frozenset(cast("list[str]", required))
    if any(not isinstance(name, str) for name in properties):
        raise CodegenError(f"{context} data schema property names must be strings")
    property_names = frozenset(cast("str", name) for name in properties)
    if required_names != property_names:
        raise CodegenError(f"{context} data schema must require every declared field")
    for required_name in ("schema_version", "event_type"):
        if required_name not in required_names or required_name not in properties:
            raise CodegenError(f"{context} data schema must require {required_name}")
    version_schema = _resolved_schema(
        schema,
        properties["schema_version"],
        context=f"{context} schema_version",
    )
    schema_version = version_schema.get("const")
    if type(schema_version) is not int or schema_version != 1:
        raise CodegenError(f"{context} schema_version must be the integer constant 1")
    event_types = _schema_enum_values(
        schema,
        properties["event_type"],
        context=f"{context} event_type",
    )
    status_values = (
        _schema_enum_values(
            schema,
            properties["status"],
            context=f"{context} status",
        )
        if "status" in properties
        else None
    )
    return (
        reference,
        properties,
        required_names,
        schema_version,
        event_types,
        status_values,
    )


def _event_terminal_contract(
    schema: Mapping[str, object],
    media: Mapping[object, object],
    *,
    properties: Mapping[object, object],
    required_names: frozenset[str],
    context: str,
) -> dict[str, object]:
    raw_terminal = _mapping(
        media.get("x-ditto-sse-terminal"),
        context=f"{context} x-ditto-sse-terminal",
    )
    if set(raw_terminal) != {"field", "values"}:
        raise CodegenError(
            f"{context} terminal contract must contain only field and values"
        )
    terminal_field = raw_terminal.get("field")
    if terminal_field not in {"event_type", "status"}:
        raise CodegenError(f"{context} terminal field must be event_type or status")
    terminal_name = cast("str", terminal_field)
    if terminal_name not in required_names or terminal_name not in properties:
        raise CodegenError(
            f"{context} terminal field must be required by the data schema"
        )
    allowed_values = _schema_enum_values(
        schema,
        properties[terminal_name],
        context=f"{context} terminal field",
    )
    raw_values = raw_terminal.get("values")
    if not isinstance(raw_values, list) or not raw_values:
        raise CodegenError(f"{context} terminal values must be a non-empty array")
    if any(not isinstance(value, str) or not value for value in raw_values):
        raise CodegenError(f"{context} terminal values must be non-empty strings")
    values = tuple(cast("list[str]", raw_values))
    if len(values) != len(set(values)) or not set(values).issubset(allowed_values):
        raise CodegenError(
            f"{context} terminal values must be unique members of the data schema"
        )
    return {"field": terminal_name, "values": values}


def _event_contract_from_media(
    schema: Mapping[str, object],
    media: object,
    *,
    operation: str,
    status: str,
) -> dict[str, object]:
    context = f"OpenAPI SSE contract {operation} {status}"
    media_mapping = _mapping(media, context=context)
    raw_wire_schema = media_mapping.get("schema")
    if raw_wire_schema is None:
        raise CodegenError(f"{context} wire schema must be exactly type string")
    wire_schema = _resolved_schema(
        schema,
        raw_wire_schema,
        context=f"{context} wire schema",
    )
    if wire_schema != {"type": "string"}:
        raise CodegenError(f"{context} wire schema must be exactly type string")
    (
        reference,
        properties,
        required_names,
        schema_version,
        event_types,
        status_values,
    ) = _event_data_schema_contract(schema, media_mapping, context=context)
    terminal = _event_terminal_contract(
        schema,
        media_mapping,
        properties=properties,
        required_names=required_names,
        context=context,
    )
    projected: dict[str, object] = {
        "dataSchema": reference,
        "eventTypes": event_types,
        "fields": tuple(sorted(cast("str", name) for name in properties)),
        "mediaType": "text/event-stream",
        "responseStatus": status,
        "schemaVersion": schema_version,
        "terminal": terminal,
    }
    if status_values is not None:
        projected["statusValues"] = status_values
    return projected


def _project_event_contract(
    schema: Mapping[str, object],
    responses: Mapping[object, object],
    *,
    operation: str,
) -> dict[str, object] | None:
    projected: dict[str, object] | None = None
    for raw_status, raw_response in responses.items():
        if isinstance(raw_status, str) and raw_status.startswith("x-"):
            continue
        status = str(raw_status)
        response = _resolved_response(
            schema,
            raw_response,
            context=f"OpenAPI response {operation} {status}",
        )
        content = response.get("content")
        if content is None:
            continue
        content_mapping = _mapping(
            content,
            context=f"OpenAPI response content {operation} {status}",
        )
        for raw_media_type, media in content_mapping.items():
            if not isinstance(raw_media_type, str):
                continue
            normalized = _normalize_media_type(
                raw_media_type,
                context=f"OpenAPI response media type {operation} {status}",
            )
            if normalized != "text/event-stream":
                continue
            if projected is not None:
                raise CodegenError(
                    f"OpenAPI operation has multiple SSE contracts: {operation}"
                )
            projected = _event_contract_from_media(
                schema,
                media,
                operation=operation,
                status=status,
            )
    return projected


def _parameter_contract(
    schema: Mapping[str, object],
    parameter_groups: tuple[object, ...],
    *,
    operation: str,
) -> dict[str, tuple[str, ...]]:
    declared: dict[tuple[str, str], str] = {}
    for group_index, raw_group in enumerate(parameter_groups):
        if raw_group is None:
            continue
        if not isinstance(raw_group, list):
            raise CodegenError(f"OpenAPI parameters must be an array for {operation}")
        for parameter_index, raw_parameter in enumerate(raw_group):
            context = (
                f"OpenAPI parameter {operation} "
                f"group {group_index} index {parameter_index}"
            )
            parameter = _resolved_parameter(
                schema,
                raw_parameter,
                context=context,
            )
            name = parameter.get("name")
            location = parameter.get("in")
            if not isinstance(name, str) or not name:
                raise CodegenError(f"{context} name must be a non-empty string")
            if not isinstance(location, str) or location not in _PARAMETER_LOCATIONS:
                raise CodegenError(f"{context} has an invalid location: {location!r}")
            identity_name = name.lower() if location == "header" else name
            declared[(location, identity_name)] = name
    projected: dict[str, tuple[str, ...]] = {}
    for location in _PARAMETER_LOCATIONS:
        names = sorted(
            name
            for (candidate_location, _), name in declared.items()
            if candidate_location == location
        )
        if names:
            projected[location] = tuple(names)
    return projected


def _operation_contracts(
    schema: Mapping[str, object],
) -> tuple[
    dict[str, dict[str, tuple[str, ...]]],
    dict[str, dict[str, tuple[str, ...]]],
    dict[str, dict[str, object]],
]:
    paths = _mapping(schema.get("paths"), context="OpenAPI paths")
    response_contracts: dict[str, dict[str, tuple[str, ...]]] = {}
    request_contracts: dict[str, dict[str, tuple[str, ...]]] = {}
    event_contracts: dict[str, dict[str, object]] = {}
    for path_value, item_value in paths.items():
        if isinstance(path_value, str) and path_value.startswith("x-"):
            continue
        if not isinstance(path_value, str) or not path_value.startswith("/"):
            raise CodegenError(f"OpenAPI path is invalid: {path_value!r}")
        item = _resolved_path_item(
            schema,
            item_value,
            context=f"OpenAPI path item {path_value}",
        )
        path_parameters = item.get("parameters")
        for method_value, operation_value in item.items():
            if not isinstance(method_value, str):
                raise CodegenError(
                    f"OpenAPI path item key must be a string: {path_value}"
                )
            method = method_value.lower()
            if method not in _HTTP_METHODS:
                continue
            if method != method_value:
                raise CodegenError(
                    f"OpenAPI operation method must be lowercase: {method_value!r}"
                )
            operation = _mapping(
                operation_value,
                context=f"OpenAPI operation {method} {path_value}",
            )
            responses = _mapping(
                operation.get("responses"),
                context=f"OpenAPI responses {method} {path_value}",
            )
            if not responses:
                raise CodegenError(
                    f"OpenAPI operation has no responses: {method} {path_value}"
                )
            operation_name = f"{method} {path_value}"
            response_contracts[operation_name] = _project_response_map(
                schema,
                responses,
                operation=operation_name,
            )
            request_contracts[operation_name] = _parameter_contract(
                schema,
                (path_parameters, operation.get("parameters")),
                operation=operation_name,
            )
            event_contract = _project_event_contract(
                schema,
                responses,
                operation=operation_name,
            )
            if event_contract is not None:
                event_contracts[operation_name] = event_contract
    return response_contracts, request_contracts, event_contracts


def _operation_contracts_bytes(
    *,
    schema: Mapping[str, object],
    schema_payload: bytes,
) -> bytes:
    response_contracts, request_contracts, event_contracts = _operation_contracts(
        schema
    )
    lines = [
        generated_operation_contracts_header(
            schema_sha256=hashlib.sha256(schema_payload).hexdigest()
        ).rstrip(),
        "",
        "export const operationResponseContracts = {",
    ]
    for operation_name in sorted(response_contracts):
        lines.append(f"  {json.dumps(operation_name)}: {{")
        responses = response_contracts[operation_name]
        for status in sorted(responses):
            media_types = json.dumps(
                list(responses[status]),
                ensure_ascii=False,
                separators=(", ", ": "),
            )
            lines.append(f"    {json.dumps(status)}: {media_types},")
        lines.append("  },")
    lines.extend(("} as const;", "", "export const operationRequestContracts = {"))
    for operation_name in sorted(request_contracts):
        lines.append(f"  {json.dumps(operation_name)}: {{")
        parameters = request_contracts[operation_name]
        if parameters:
            lines.append("    parameters: {")
            for location in sorted(parameters):
                names = json.dumps(
                    list(parameters[location]),
                    ensure_ascii=False,
                    separators=(", ", ": "),
                )
                lines.append(f"      {json.dumps(location)}: {names},")
            lines.append("    },")
        lines.append("  },")
    lines.extend(("} as const;", "", "export const operationEventContracts = {"))
    for operation_name in sorted(event_contracts):
        contract = event_contracts[operation_name]
        lines.append(f"  {json.dumps(operation_name)}: {{")
        for key in (
            "dataSchema",
            "eventTypes",
            "fields",
            "mediaType",
            "responseStatus",
            "schemaVersion",
            "statusValues",
        ):
            if key not in contract:
                continue
            value = json.dumps(
                contract[key],
                ensure_ascii=False,
                separators=(", ", ": "),
            )
            lines.append(f"    {json.dumps(key)}: {value},")
        terminal = cast("Mapping[str, object]", contract["terminal"])
        lines.append('    "terminal": {')
        lines.append(
            '      "field": ' + json.dumps(terminal["field"], ensure_ascii=False) + ","
        )
        lines.append(
            '      "values": '
            + json.dumps(
                terminal["values"],
                ensure_ascii=False,
                separators=(", ", ": "),
            )
            + ","
        )
        lines.append("    },")
        lines.append("  },")
    lines.extend(("} as const;", ""))
    return "\n".join(lines).encode()


def generate_operation_contracts_bytes(*, snapshot_path: Path) -> bytes:
    """Project the canonical schema into deterministic runtime operation metadata."""
    schema, schema_payload = load_local_schema(snapshot_path)
    return _operation_contracts_bytes(
        schema=schema,
        schema_payload=schema_payload,
    )


def local_generator() -> tuple[str, Generator]:
    """Resolve the exact installed generator without package-manager fallback."""
    if not _GENERATOR_PACKAGE.is_file() or not _GENERATOR_CLI.is_file():
        raise CodegenError(
            "".join(
                (
                    "openapi-typescript is not installed locally. ",
                    "Run the repository's ",
                    "frozen/offline bootstrap; this pipeline never invokes bunx or ",
                    "downloads tools.",
                )
            )
        )
    package = json.loads(_GENERATOR_PACKAGE.read_text(encoding="utf-8"))
    version = package.get("version")
    if version != EXPECTED_GENERATOR_VERSION:
        raise CodegenError(
            "openapi-typescript version mismatch: "
            + f"expected {EXPECTED_GENERATOR_VERSION}, found {version!r}"
        )
    node = node_executable(_REPO_ROOT)

    def run(source: Path, output: Path) -> None:
        environment = os.environ.copy()
        environment.update({"CI": "1", "NO_COLOR": "1"})
        subprocess.run(  # noqa: S603 -- exact Node and local pinned CLI paths
            [node, str(_GENERATOR_CLI), str(source), "--output", str(output)],
            # Keep openapi-typescript from auto-discovering the lint-only
            # multi-API Redocly config. The absolute schema is the sole input.
            cwd=output.parent,
            env=environment,
            check=True,
        )

    return EXPECTED_GENERATOR_VERSION, run


def _generate_type_candidate_bytes(
    *,
    schema_payload: bytes,
    generator_version: str,
    run_generator: Generator,
) -> bytes:
    schema_sha256 = hashlib.sha256(schema_payload).hexdigest()
    with tempfile.TemporaryDirectory(prefix="ditto-openapi-types-") as directory:
        temporary_root = Path(directory)
        immutable_snapshot = temporary_root / "openapi.snapshot.json"
        immutable_snapshot.write_bytes(schema_payload)
        immutable_snapshot.chmod(0o444)
        raw_output = temporary_root / "schema.raw.d.ts"
        run_generator(immutable_snapshot, raw_output)
        if not raw_output.is_file():
            raise CodegenError("openapi-typescript did not create its requested output")
        generated = raw_output.read_bytes()
    header = generated_header(
        schema_sha256=schema_sha256,
        generator_version=generator_version,
    ).encode()
    return header + generated


def generate_candidate_bytes(
    *,
    snapshot_path: Path,
    generator_version: str,
    run_generator: Generator,
) -> bytes:
    """Generate one type candidate from an isolated immutable snapshot."""
    _, schema_payload = load_local_schema(snapshot_path)
    return _generate_type_candidate_bytes(
        schema_payload=schema_payload,
        generator_version=generator_version,
        run_generator=run_generator,
    )


def generate_candidates_bytes(
    *,
    snapshot_path: Path,
    generator_version: str,
    run_generator: Generator,
) -> tuple[bytes, bytes]:
    """Generate types and runtime metadata from one in-memory snapshot."""
    schema, schema_payload = load_local_schema(snapshot_path)
    type_candidate = _generate_type_candidate_bytes(
        schema_payload=schema_payload,
        generator_version=generator_version,
        run_generator=run_generator,
    )
    operation_candidate = _operation_contracts_bytes(
        schema=schema,
        schema_payload=schema_payload,
    )
    return type_candidate, operation_candidate


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(payload)
            temporary_file.flush()
            os.fchmod(temporary_file.fileno(), 0o644)
            os.fsync(temporary_file.fileno())
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def check_generated_schema(path: Path, candidate: bytes) -> None:
    """Require byte-for-byte reproducibility without changing the worktree."""
    try:
        committed = path.read_bytes()
    except FileNotFoundError as error:
        raise GeneratedSchemaMismatchError(
            f"generated schema is missing: {path}; run with --write"
        ) from error
    if committed != candidate:
        expected_sha = hashlib.sha256(candidate).hexdigest()
        actual_sha = hashlib.sha256(committed).hexdigest()
        raise GeneratedSchemaMismatchError(
            "".join(
                (
                    "generated schema is not byte-identical to local generation: ",
                    f"{path} (expected SHA-256 {expected_sha}, found {actual_sha}); ",
                    "run with --write",
                )
            )
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="zero-diff check (default)")
    mode.add_argument("--write", action="store_true", help="refresh generated types")
    parser.add_argument("--schema", type=Path, default=_DEFAULT_SNAPSHOT)
    parser.add_argument("--output", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument(
        "--response-output",
        type=Path,
        default=_DEFAULT_RESPONSE_OUTPUT,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Generate through a temporary file and check by default."""
    arguments = _parser().parse_args(argv)
    try:
        version, generator = local_generator()
        candidate, response_candidate = generate_candidates_bytes(
            snapshot_path=arguments.schema,
            generator_version=version,
            run_generator=generator,
        )
        output = arguments.output.resolve()
        response_output = arguments.response_output.resolve()
        if output == response_output:
            raise CodegenError("generated type and response outputs must be distinct")
        if arguments.write:
            _atomic_write(output, candidate)
            _atomic_write(response_output, response_candidate)
            sys.stdout.write(f"Web OpenAPI types updated: {output}\n")
            sys.stdout.write(
                f"Web operation response contracts updated: {response_output}\n"
            )
        else:
            check_generated_schema(output, candidate)
            check_generated_schema(response_output, response_candidate)
            sys.stdout.write(f"Web OpenAPI types are reproducible: {output}\n")
            sys.stdout.write(
                "Web operation response contracts are reproducible: "
                + f"{response_output}\n"
            )
    except (CodegenError, OSError, subprocess.CalledProcessError) as error:
        sys.stderr.write(f"{error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
