#!/usr/local/bin/python
"""Fixed stdin/stdout contract for untrusted R5 research candidates."""

from __future__ import annotations

import ast
import base64
import hashlib
import io
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np
import polars as pl

_INPUT_FIELDS = {
    "schema_id",
    "schema_version",
    "phase",
    "invocation_hash",
    "security_evidence_hash",
    "code_artifact",
    "window",
    "seed",
}
_SCORE_INPUT_FIELDS = _INPUT_FIELDS | {"immutable_model_state"}
_CODE_FIELDS = {
    "source_code",
    "source_hash",
    "canonical_ast_hash",
    "dependency_lock_hash",
    "dependencies",
    "image_digest",
    "input_schema_hash",
    "output_schema_hash",
}
_ARTIFACT_FIELDS = {
    "serialization",
    "content_hash",
    "schema_hash",
    "row_count",
    "allow_pickle",
    "payload_base64",
}
_HASH_LENGTH = 64
_ENTRYPOINT_ARG_COUNT = 2


class ContractError(Exception):
    """Non-sensitive fixed-contract rejection."""


def _reject(reason: str) -> ContractError:
    return ContractError(reason)


def _mapping(value: object, *, reason: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _reject(reason)
    return value


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_text(value: object, *, reason: str) -> str:
    if (
        type(value) is not str
        or len(value) != _HASH_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise _reject(reason)
    return value


def _runtime_manifest() -> Mapping[str, object]:
    path = Path(
        os.environ.get(
            "DITTO_SANDBOX_RUNTIME_MANIFEST",
            "/opt/ditto/runtime-manifest.json",
        )
    )
    decoded = json.loads(path.read_bytes())
    manifest = _mapping(decoded, reason="runtime_manifest_invalid")
    if (
        set(manifest)
        != {
            "approved_dependencies",
            "dependency_lock_hash",
            "schema_id",
            "schema_version",
        }
        or manifest.get("schema_id") != "r5-candidate-runtime-manifest"
    ):
        raise _reject("runtime_manifest_invalid")
    return manifest


def _artifact_payload(artifact: Mapping[str, object]) -> bytes:
    raw_payload = artifact.get("payload_base64")
    if type(raw_payload) is not str:
        raise _reject("artifact_payload_invalid")
    try:
        payload = base64.b64decode(raw_payload, validate=True)
    except (ValueError, TypeError) as exc:
        raise _reject("artifact_payload_invalid") from exc
    if artifact.get("content_hash") != _hash(payload):
        raise _reject("artifact_hash_mismatch")
    return payload


def _deserialize_artifact(
    payload: bytes,
    *,
    serialization: object,
    row_count: int,
) -> object:
    if serialization == "application/json":
        decoded: object = json.loads(payload)
        if isinstance(decoded, Mapping) and "rows" in decoded:
            return decoded["rows"]
        return decoded
    if serialization == "application/vnd.apache.arrow.file":
        return pl.read_ipc(io.BytesIO(payload), n_rows=row_count + 1).to_dicts()
    if serialization == "application/x-npy":
        loaded = np.load(io.BytesIO(payload), allow_pickle=False)
        if loaded.dtype.hasobject:
            raise _reject("artifact_pickle_forbidden")
        return loaded.tolist()
    raise _reject("artifact_serialization_invalid")


def _validate_artifact_rows(decoded: object, *, row_count: int) -> None:
    if isinstance(decoded, Sequence) and not isinstance(decoded, (str, bytes)):
        if len(decoded) != row_count:
            raise _reject("artifact_row_count_mismatch")
    elif row_count != 1:
        raise _reject("artifact_row_count_mismatch")


def _artifact(value: object, *, expected_schema_hash: str) -> tuple[object, int]:
    artifact = _mapping(value, reason="artifact_invalid")
    if set(artifact) != _ARTIFACT_FIELDS:
        raise _reject("artifact_invalid")
    if artifact.get("allow_pickle") is not False:
        raise _reject("artifact_pickle_forbidden")
    if artifact.get("schema_hash") != expected_schema_hash:
        raise _reject("artifact_schema_mismatch")
    row_count = artifact.get("row_count")
    if type(row_count) is not int or row_count < 0:
        raise _reject("artifact_row_count_invalid")
    decoded = _deserialize_artifact(
        _artifact_payload(artifact),
        serialization=artifact.get("serialization"),
        row_count=row_count,
    )
    _validate_artifact_rows(decoded, row_count=row_count)
    return decoded, row_count


def _validate_source(code: Mapping[str, object]) -> str:
    if set(code) != _CODE_FIELDS:
        raise _reject("code_artifact_invalid")
    source = code.get("source_code")
    if type(source) is not str or not source.strip():
        raise _reject("source_invalid")
    if code.get("source_hash") != _hash(source.encode()):
        raise _reject("source_hash_mismatch")
    tree = ast.parse(source, mode="exec")
    functions = {
        statement.name: statement
        for statement in tree.body
        if isinstance(statement, ast.FunctionDef)
    }
    if not {"fit", "score"}.issubset(functions):
        raise _reject("entrypoint_contract_invalid")
    expected = {
        "fit": ("training_stream",),
        "score": ("visible_window", "immutable_model_state"),
    }
    for name, arguments in expected.items():
        function = functions[name]
        observed = tuple(argument.arg for argument in function.args.args)
        if (
            observed != arguments
            or function.args.posonlyargs
            or function.args.kwonlyargs
            or function.args.vararg is not None
            or function.args.kwarg is not None
            or function.args.defaults
            or function.args.kw_defaults
        ):
            raise _reject("entrypoint_contract_invalid")
    return source


def _load_input(phase: str) -> tuple[Mapping[str, object], Mapping[str, object]]:
    decoded = json.loads(sys.stdin.buffer.read())
    payload = _mapping(decoded, reason="input_invalid")
    expected_fields = _INPUT_FIELDS if phase == "fit" else _SCORE_INPUT_FIELDS
    if (
        set(payload) != expected_fields
        or payload.get("schema_id") != "r5-oci-sandbox-input"
        or payload.get("schema_version") != 1
        or payload.get("phase") != phase
        or type(payload.get("seed")) is not int
    ):
        raise _reject("input_invalid")
    _hash_text(payload.get("invocation_hash"), reason="invocation_hash_invalid")
    _hash_text(
        payload.get("security_evidence_hash"),
        reason="security_evidence_hash_invalid",
    )
    code = _mapping(payload.get("code_artifact"), reason="code_artifact_invalid")
    _validate_source(code)
    runtime = _runtime_manifest()
    if code.get("dependency_lock_hash") != runtime.get(
        "dependency_lock_hash"
    ) or code.get("dependencies") != runtime.get("approved_dependencies"):
        raise _reject("dependency_identity_mismatch")
    for field in (
        "canonical_ast_hash",
        "image_digest",
        "input_schema_hash",
        "output_schema_hash",
    ):
        _hash_text(code.get(field), reason=f"{field}_invalid")
    return payload, code


def _json_output(value: object, *, phase: str, code: Mapping[str, object]) -> bytes:
    if phase == "score":
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise _reject("score_output_invalid")
        output: object = {
            "schema_id": "r5-candidate-score-frame",
            "schema_version": 1,
            "rows": list(value),
        }
        row_count = len(value)
        schema_hash = code["output_schema_hash"]
    else:
        if not isinstance(value, (Mapping, Sequence)) or isinstance(
            value, (str, bytes)
        ):
            raise _reject("fit_output_invalid")
        output = value
        row_count = len(value) if isinstance(value, Sequence) else 1
        canonical_shape = json.dumps(
            {"phase": "fit", "type": type(value).__name__},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        schema_hash = _hash(canonical_shape)
    artifact = json.dumps(output, separators=(",", ":"), sort_keys=True).encode()
    envelope = {
        "schema_id": "r5-oci-sandbox-output",
        "schema_version": 1,
        "serialization": "application/json",
        "schema_hash": schema_hash,
        "row_count": row_count,
        "payload_base64": base64.b64encode(artifact).decode("ascii"),
    }
    return json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode()


def _run(phase: str) -> bytes:
    payload, code = _load_input(phase)
    window = _mapping(payload["window"], reason="window_invalid")
    visible, _rows = _artifact(
        window.get("artifact"),
        expected_schema_hash=str(code["input_schema_hash"]),
    )
    namespace: dict[str, Any] = {
        "__builtins__": __builtins__,
        "__name__": "ditto_generated_candidate",
    }
    source = str(code["source_code"])
    exec(  # noqa: S102 - execution occurs only inside the hardened OCI boundary.
        compile(source, "<generated-candidate>", "exec"), namespace
    )
    if phase == "fit":
        result = namespace["fit"](visible)
    else:
        state_mapping = _mapping(
            payload["immutable_model_state"], reason="model_state_invalid"
        )
        state, _state_rows = _artifact(
            state_mapping,
            expected_schema_hash=str(state_mapping.get("schema_hash")),
        )
        immutable_state = MappingProxyType(state) if isinstance(state, dict) else state
        result = namespace["score"](visible, immutable_state)
    return _json_output(result, phase=phase, code=code)


def _write_stderr(message: str) -> None:
    sys.stderr.write(f"{message}\n")


def main() -> int:
    """Run one fixed fit or score invocation from stdin to stdout."""
    if len(sys.argv) != _ENTRYPOINT_ARG_COUNT or sys.argv[1] not in {
        "fit",
        "score",
    }:
        _write_stderr("entrypoint_phase_invalid")
        return 125
    try:
        output = _run(sys.argv[1])
    except ContractError as exc:
        _write_stderr(str(exc))
        return 125
    except PermissionError:
        _write_stderr("sandbox_policy_denied")
        return 126
    except Exception as exc:
        _write_stderr(f"candidate_execution_failed:{type(exc).__name__}")
        return 125
    sys.stdout.buffer.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
