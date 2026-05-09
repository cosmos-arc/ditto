"""Manifest building — compatibility manifest records for publication safety."""

from __future__ import annotations

import platform
from dataclasses import asdict, replace
from hashlib import sha256
from typing import cast

import orjson
from ditto_features.expression.contracts import CompileIdentity
from ditto_features.publication_safety import CompatibilityManifest
from ditto_features.publication_safety_records import CompatibilityManifestRecord
from ditto_features.services import DerivedCatalogService
from ditto_kernel.json_types import JsonDict
from ditto_kernel.strategy import DerivedSpec

from ditto_application.config import now_iso

__all__ = ["build_manifest_record", "resolve_shadow_baseline"]


# ---------------------------------------------------------------------------
# Manifest record
# ---------------------------------------------------------------------------


def build_manifest_record(
    *,
    spec: DerivedSpec,
    version: int,
    compile_identity: CompileIdentity,
) -> CompatibilityManifestRecord:
    """Build a persisted manifest record for publication safety."""
    manifest = _build_manifest(spec=spec, compile_identity=compile_identity)
    manifest_hash = _manifest_hash(_manifest_payload(manifest))
    manifest = replace(manifest, manifest_hash=manifest_hash)
    payload = asdict(manifest)
    return CompatibilityManifestRecord(
        derived_id=spec.id,
        version=version,
        manifest_hash=manifest_hash,
        payload=cast(JsonDict, payload),
        created_at=now_iso(),
    )


def _build_manifest(
    *,
    spec: DerivedSpec,
    compile_identity: CompileIdentity,
) -> CompatibilityManifest:
    return CompatibilityManifest(
        engine_codegen_version=compile_identity.engine_codegen_version,
        analysis_version=compile_identity.analysis_version,
        polars_version=compile_identity.polars_version,
        expr_serialization_format=compile_identity.expr_serialization_format,
        operator_fingerprint=compile_identity.operator_fingerprint,
        global_compile_flags=_compile_flags_dict(compile_identity.global_compile_flags),
        calendar_id=spec.calendar,
        timezone="Asia/Shanghai",
        time_semantics_version="time-v1",
        python_version=platform.python_version(),
        platform=platform.platform(),
        builder_version="unified-derived-v1",
    )


def _manifest_payload(manifest: CompatibilityManifest) -> JsonDict:
    payload = cast(JsonDict, asdict(manifest))
    payload.pop("manifest_hash", None)
    return payload


def _compile_flags_dict(flags: tuple[str, ...]) -> dict[str, str | int | float | bool]:
    parsed: dict[str, str | int | float | bool] = {}
    for flag in flags:
        if "=" not in flag:
            parsed[flag] = True
            continue
        key, value = flag.split("=", 1)
        parsed[key] = value
    return parsed


def _manifest_hash(payload: JsonDict) -> str:
    serialized = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return sha256(serialized).hexdigest()


# ---------------------------------------------------------------------------
# Shadow baseline
# ---------------------------------------------------------------------------


def resolve_shadow_baseline(
    *,
    catalog_service: DerivedCatalogService,
    derived_id: str,
    candidate_version: int,
) -> int | None:
    """Find the primary online version to use as shadow comparison baseline."""
    primary_online = next(
        (
            record.version
            for record in catalog_service.list_versions(derived_id)
            if (
                record.is_primary
                and record.is_online
                and record.version != candidate_version
            )
        ),
        None,
    )
    if primary_online is not None:
        return primary_online
    return next(
        (
            record.version
            for record in catalog_service.list_versions(derived_id)
            if record.is_primary and record.version != candidate_version
        ),
        None,
    )
