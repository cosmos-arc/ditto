"""
Governed factor spec registration into the derived catalog.

#418 切片①的生产端入口：把治理目录中的 FactorSpec 物化为
``DerivedSpecRecord``＋``DerivedVersionRecord``（draft），使物化编排器可以
按 DerivedSpec 计算。注册是幂等的：同 (derived_id, version) 同 spec_hash
直接复用；spec_hash 漂移即身份漂移，拒绝且提示修订走新版本号。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256

import orjson

from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)
from ditto_features.errors import MaterializationError
from ditto_features.factors.factor_registry import ALL_FACTOR_SPECS
from ditto_features.factors.spec import FactorSpec
from ditto_features.models.derived import DerivedSpecRecord, DerivedVersionRecord
from ditto_features.services.derived_catalog_service import DerivedCatalogService

__all__ = [
    "DEFAULT_MATERIALIZABLE_FACTOR_IDS",
    "FactorSpecRegistration",
    "build_factor_derived_spec",
    "factor_spec_hash",
    "register_governed_factor",
]


# 切片①治理集合：依赖全部由 RuntimeDerivedInputProvider 供数（market.*）。
# 扩集合的条件：该因子的依赖闭包已在 dependency_registry＋运行时供数两侧就绪。
DEFAULT_MATERIALIZABLE_FACTOR_IDS: tuple[str, ...] = ("momentum_1m",)

_REGISTRATION_ENGINE_VERSION = "unified-derived-v1"


@dataclass(frozen=True)
class FactorSpecRegistration:
    """Outcome of one governed factor registration attempt."""

    derived_id: str
    version: int
    action: str
    spec_hash: str


def build_factor_derived_spec(factor_id: str, *, version: int = 1) -> DerivedSpec:
    """Build the durable SERIES DerivedSpec for one governed factor."""
    factor = _require_governed_factor(factor_id)
    return DerivedSpec(
        id=factor.id,
        version=version,
        role=DerivedRole.FACTOR,
        materialization_profile=MaterializationProfile.SERIES,
        expression=factor.expression,
        description=factor.description,
    )


def factor_spec_hash(spec: DerivedSpec) -> str:
    """Content-address the canonical spec payload（身份维度：定义/参数集）."""
    encoded = orjson.dumps(asdict(spec), option=orjson.OPT_SORT_KEYS)
    return sha256(encoded).hexdigest()


def register_governed_factor(
    catalog_service: DerivedCatalogService,
    factor_id: str,
    *,
    version: int = 1,
) -> FactorSpecRegistration:
    """
    Idempotently register one governed factor as a derived spec.

    Raises:
        MaterializationError: 同 (derived_id, version) 已存在但 spec_hash 不同
            （身份漂移，修订必须走新版本号）；或 factor_id 不在治理集合内。

    """
    spec = build_factor_derived_spec(factor_id, version=version)
    spec_hash = factor_spec_hash(spec)
    existing = catalog_service.get_spec(spec.id, spec.version)
    created_at = datetime.now(UTC).isoformat()
    version_record = _draft_version_record(spec, created_at)
    if existing is not None:
        if existing.spec_hash != spec_hash:
            raise MaterializationError(
                "spec identity drift refused: "
                + f"derived_id={spec.id} version={spec.version} "
                + f"existing_spec_hash={existing.spec_hash} "
                + f"new_spec_hash={spec_hash}; revisions must use a new version",
                details={
                    "derived_id": spec.id,
                    "version": spec.version,
                    "reason": "spec_identity_drift",
                    "existing_spec_hash": existing.spec_hash,
                    "new_spec_hash": spec_hash,
                },
            )
        # 自愈注册半程崩溃：spec 行在而 version 行缺时补写 draft（#418）。
        if catalog_service.get_version(spec.id, spec.version) is None:
            catalog_service.save_version(version_record)
        return FactorSpecRegistration(
            derived_id=spec.id,
            version=spec.version,
            action="already_registered",
            spec_hash=spec_hash,
        )
    catalog_service.save_spec(
        DerivedSpecRecord(
            derived_id=spec.id,
            version=spec.version,
            role=spec.role.value,
            materialization_profile=spec.materialization_profile.value,
            spec_hash=spec_hash,
            spec_json=asdict(spec),
            created_at=created_at,
        )
    )
    catalog_service.save_version(version_record)
    return FactorSpecRegistration(
        derived_id=spec.id,
        version=spec.version,
        action="registered",
        spec_hash=spec_hash,
    )


def _draft_version_record(spec: DerivedSpec, created_at: str) -> DerivedVersionRecord:
    return DerivedVersionRecord(
        derived_id=spec.id,
        version=spec.version,
        status="draft",
        engine_version=_REGISTRATION_ENGINE_VERSION,
        is_online=False,
        is_primary=False,
        created_at=created_at,
        updated_at=None,
    )


def _require_governed_factor(factor_id: str) -> FactorSpec:
    if factor_id not in DEFAULT_MATERIALIZABLE_FACTOR_IDS:
        raise MaterializationError(
            f"factor not in governed materializable set: {factor_id} "
            + f"(allowed={list(DEFAULT_MATERIALIZABLE_FACTOR_IDS)})",
            details={
                "factor_id": factor_id,
                "reason": "factor_not_governed",
                "allowed": list(DEFAULT_MATERIALIZABLE_FACTOR_IDS),
            },
        )
    factor = ALL_FACTOR_SPECS.get(factor_id)
    if factor is None:
        raise MaterializationError(
            f"governed factor missing from registry: {factor_id}",
            details={"factor_id": factor_id, "reason": "factor_not_in_registry"},
        )
    return factor
