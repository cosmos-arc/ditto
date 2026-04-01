"""
Compatibility manifest and dependency tracking for derived materialization.

Builds ``CompatibilityManifestRecord`` instances for publication safety and
provides helpers for shadow baseline resolution and dependency reference
classification.
"""

from __future__ import annotations

import platform
from dataclasses import asdict, replace
from hashlib import sha256
from typing import cast

import orjson
from ditto_analytics.materialization import CompileIdentity
from ditto_datahub.models.publication_safety import (
    CompatibilityManifestRecord,
    JsonDict,
)
from ditto_datahub.services.derived_catalog_service import DerivedCatalogService
from ditto_engine.engine.publication_safety import CompatibilityManifest
from ditto_engine.engine.specs import DerivedSpec

from ._utils import now_iso

__all__ = [
    "build_manifest_record",
    "dependency_refs",
    "resolve_shadow_baseline",
]


# ---------------------------------------------------------------------------
# Manifest building
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


# ---------------------------------------------------------------------------
# Dependency reference classification
# ---------------------------------------------------------------------------


def dependency_refs(
    dependencies: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    """Classify each dependency into (kind, ref) pairs for persistence."""
    refs: list[tuple[str, str]] = []
    for dependency in dependencies:
        if dependency.startswith("market."):
            refs.append(("dataset", _market_dependency_ref(dependency)))
            continue
        if dependency.startswith("etf."):
            refs.append(("dataset", _etf_dependency_ref(dependency)))
            continue
        if "." not in dependency:
            continue
        refs.append(("derived", dependency))
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in refs:
        if item in seen:
            continue
        deduped.append(item)
        seen.add(item)
    return tuple(deduped)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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


def _market_dependency_ref(dependency: str) -> str:
    column_name = dependency.removeprefix("market.")
    if column_name in {"open", "high", "low", "close", "pre_close", "volume", "amount"}:
        return "market.stock_daily"
    if column_name == "adj_factor":
        return "market.adj_factor"
    if column_name in {
        "is_suspended",
        "suspend_timing",
        "is_st",
        "st_type",
        "list_status",
    }:
        return "market.stock_status"
    raise NotImplementedError(
        "Unsupported market dependency for durable persistence: "
        + f"dependency={dependency}"
    )


_ETF_DAILY_COLUMNS = frozenset(
    {"open", "high", "low", "close", "pre_close", "volume", "amount", "pct_change"}
)


def _etf_dependency_ref(dependency: str) -> str:
    column_name = dependency.removeprefix("etf.")
    if column_name in _ETF_DAILY_COLUMNS:
        return "etf.daily"
    raise NotImplementedError(
        "Unsupported ETF dependency for durable persistence: "
        + f"dependency={dependency}"
    )
