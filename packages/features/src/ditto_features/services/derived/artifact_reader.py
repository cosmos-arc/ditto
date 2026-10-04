"""Shared artifact reader for unified derived runtime data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Literal, Protocol, cast, overload

import orjson
import polars as pl

from ditto_features.errors import (
    DerivedIntegrityError,
    DerivedNotFoundError,
    DerivedVersionError,
)
from ditto_features.models.derived import (
    DerivedCheckpointRecord,
    DerivedCheckpointStatus,
    DerivedSpecRecord,
    DerivedStateRecord,
    DerivedVersionRecord,
)
from ditto_features.services.derived._pruning import prune_parquet_paths
from ditto_features.storage.derived_artifact_writer import run_metadata_path

__all__ = [
    "DerivedArtifactFrameRequest",
    "DerivedArtifactReader",
    "VersionResolutionStrategy",
]


class VersionResolutionStrategy(StrEnum):
    """Explicit strategy for version resolution."""

    PRIMARY_ONLINE_ONLY = "primary_online_only"
    FALLBACK_TO_ACTIVE = "fallback_to_active"
    EXPLICIT_VERSION = "explicit_version"


@dataclass(frozen=True)
class DerivedArtifactFrameRequest:
    """Request object for reading one derived artifact frame slice."""

    derived_id: str
    version: int
    instrument_ids: tuple[int, ...] | None = None
    start: str | None = None
    end: str | None = None
    as_of: str | None = None
    streaming: bool = False
    max_rows: int | None = None
    as_lazy: bool = False


class _CatalogReader(Protocol):
    """Minimal catalog read interface consumed by the artifact reader."""

    def get_spec(self, derived_id: str, version: int) -> DerivedSpecRecord | None: ...
    def get_version(
        self, derived_id: str, version: int
    ) -> DerivedVersionRecord | None: ...
    def get_state(self, derived_id: str) -> DerivedStateRecord | None: ...
    def list_versions(self, derived_id: str) -> tuple[DerivedVersionRecord, ...]: ...
    def list_checkpoints(
        self, derived_id: str, version: int
    ) -> tuple[DerivedCheckpointRecord, ...]: ...


class DerivedArtifactReader:
    """Resolve versions and read materialized artifact frames."""

    def __init__(
        self,
        *,
        catalog_service: _CatalogReader,
        artifact_root: Path,
    ) -> None:
        self._catalog_service = catalog_service
        self._artifact_root = Path(artifact_root)

    def resolve_offline_version(
        self,
        derived_id: str,
        requested_version: int | None = None,
    ) -> int:
        """Resolve an offline artifact version."""
        version = requested_version or self._resolve_active_version(derived_id)
        self._require_catalog_entry(derived_id, version)
        return version

    def resolve_serving_version(
        self,
        derived_id: str,
        *,
        strategy: VersionResolutionStrategy = (
            VersionResolutionStrategy.PRIMARY_ONLINE_ONLY
        ),
        explicit_version: int | None = None,
    ) -> int:
        """
        Resolve the currently serving artifact version.

        Args:
            derived_id: The derived artifact identifier.
            strategy: How to resolve the version.
                Defaults to PRIMARY_ONLINE_ONLY.
            explicit_version: Required when strategy is EXPLICIT_VERSION.

        Returns:
            The resolved version number.

        Raises:
            DerivedVersionError: When resolution fails under the requested strategy.
            DerivedNotFoundError: When the resolved version lacks catalog entries.

        """
        if strategy is VersionResolutionStrategy.EXPLICIT_VERSION:
            if explicit_version is None:
                raise DerivedVersionError(
                    derived_id=derived_id,
                    reason=(
                        "explicit_version is required for "
                        + "EXPLICIT_VERSION strategy"
                    ),
                )
            version = explicit_version
        elif strategy is VersionResolutionStrategy.FALLBACK_TO_ACTIVE:
            version = self._resolve_primary_online(derived_id)
            if version is None:
                version = self._resolve_active_version(derived_id)
        else:
            # PRIMARY_ONLINE_ONLY
            version = self._resolve_primary_online(derived_id)
            if version is None:
                raise DerivedVersionError(
                    derived_id=derived_id,
                    reason="no primary online version found",
                )
        self._require_catalog_entry(derived_id, version)
        return version

    def read_run_manifest_hash(
        self,
        derived_id: str,
        version: int,
        run_id: str,
    ) -> str | None:
        """
        Read the publication manifest hash recorded by one run.

        Returns ``None`` when the run metadata file or its publication block
        does not exist (e.g. runs predating the straight-line publication).
        """
        spec_record = self._require_catalog_entry(derived_id, version)
        metadata_path = run_metadata_path(
            self._artifact_root,
            profile=spec_record.materialization_profile,
            derived_id=derived_id,
            version=version,
            run_id=run_id,
        )
        if not metadata_path.exists():
            return None
        decoded: object = orjson.loads(metadata_path.read_bytes())
        if type(decoded) is not dict:
            return None
        payload = cast("dict[str, object]", decoded)
        publication = payload.get("publication")
        if type(publication) is not dict:
            return None
        manifest_hash = cast("dict[str, object]", publication).get("manifest_hash")
        return manifest_hash if type(manifest_hash) is str else None

    # ------------------------------------------------------------------
    # read_frame overloads
    # ------------------------------------------------------------------

    @overload
    def read_frame(
        self,
        request: DerivedArtifactFrameRequest,
        /,
    ) -> pl.DataFrame | pl.LazyFrame: ...

    @overload
    def read_frame(
        self,
        request: None = None,
        /,
        *,
        derived_id: str,
        version: int,
        instrument_ids: tuple[int, ...] | None = None,
        start: str | None = None,
        end: str | None = None,
        as_of: str | None = None,
        streaming: bool = False,
        max_rows: int | None = None,
        as_lazy: Literal[False] = False,
    ) -> pl.DataFrame: ...

    @overload
    def read_frame(
        self,
        request: None = None,
        /,
        *,
        derived_id: str,
        version: int,
        instrument_ids: tuple[int, ...] | None = None,
        start: str | None = None,
        end: str | None = None,
        as_of: str | None = None,
        streaming: bool = False,
        max_rows: int | None = None,
        as_lazy: Literal[True],
    ) -> pl.DataFrame | pl.LazyFrame: ...

    def read_frame(
        self,
        request: DerivedArtifactFrameRequest | None = None,
        /,
        **params: object,
    ) -> pl.DataFrame | pl.LazyFrame:
        """
        Read one artifact slice from parquet partitions.

        Args:
            request: Preferred typed request object.
            params: Legacy keyword parameters used to build the request object.

        Returns:
            A ``pl.DataFrame`` by default, or a ``pl.LazyFrame`` when
            ``as_lazy=True``.

        """
        frame_request = _normalize_frame_request(request, params)
        frame = self._build_filtered_lazy_frame(
            derived_id=frame_request.derived_id,
            version=frame_request.version,
            instrument_ids=frame_request.instrument_ids,
            start=frame_request.start,
            end=frame_request.end,
            as_of=frame_request.as_of,
        )

        if frame is None:
            return pl.DataFrame()

        if frame_request.as_lazy:
            return frame

        if frame_request.max_rows is not None:
            frame = frame.head(frame_request.max_rows)

        time_key = self._time_key(frame_request.derived_id, frame_request.version)

        if frame_request.streaming:
            collected = frame.collect(engine="streaming").sort(
                ["instrument_id", time_key]
            )
        else:
            collected = frame.collect().sort(["instrument_id", time_key])

        if (
            "availability_time" not in collected.columns
            and time_key in collected.columns
        ):
            collected = collected.with_columns(
                pl.col(time_key).alias("availability_time")
            )
        return collected

    def _build_filtered_lazy_frame(
        self,
        *,
        derived_id: str,
        version: int,
        instrument_ids: tuple[int, ...] | None = None,
        start: str | None = None,
        end: str | None = None,
        as_of: str | None = None,
    ) -> pl.LazyFrame | None:
        """
        Build a filtered LazyFrame for the given artifact version.

        Reads fail closed unless the version is published and every parquet
        partition being read carries a COMPLETE checkpoint whose checksum
        matches the file content（#418 完成才可读＋身份漂移拒绝）.

        Returns ``None`` when no parquet files exist for the requested
        date range (convenient for the ``as_lazy=False`` early-return).
        """
        self._require_published_version(derived_id, version)
        spec_record = self._require_catalog_entry(derived_id, version)
        version_root = (
            self._artifact_root
            / "derived"
            / "artifacts"
            / spec_record.materialization_profile.lower()
            / derived_id
            / f"v{version}"
        )
        parquet_paths = prune_parquet_paths(version_root, start=start, end=end)
        if not parquet_paths:
            return None
        self._verify_partition_integrity(derived_id, version, parquet_paths)

        time_key = _effective_time_key(spec_record)
        frame = _scan_with_schema_evolution(parquet_paths)
        if instrument_ids:
            frame = frame.filter(pl.col("instrument_id").is_in(instrument_ids))

        # 时间列可能是 Date 或 ISO 字符串（按 artifact 物化形态）：
        # 按列 dtype 选择可比字面量（ISO 字符串序即时间序）。
        def _bound(value: str) -> pl.Expr:
            schema = frame.collect_schema()
            if schema.get(time_key) == pl.Utf8:
                return pl.lit(value[:10])
            return pl.lit(_coerce_date(value))

        if start is not None:
            frame = frame.filter(pl.col(time_key) >= _bound(start))
        if end is not None:
            frame = frame.filter(pl.col(time_key) <= _bound(end))
        if as_of is not None:
            frame = frame.filter(pl.col(time_key) <= _bound(as_of))
        return frame

    def _time_key(self, derived_id: str, version: int) -> str:
        """Resolve the effective time key for a given derived artifact."""
        spec_record = self._require_catalog_entry(derived_id, version)
        return _effective_time_key(spec_record)

    def _resolve_active_version(self, derived_id: str) -> int:
        state = self._catalog_service.get_state(derived_id)
        if state is None or state.active_version is None:
            raise DerivedNotFoundError(derived_id=derived_id)
        return state.active_version

    def _resolve_primary_online(self, derived_id: str) -> int | None:
        """Return the primary online PUBLISHED version, or ``None``."""
        return next(
            (
                record.version
                for record in self._catalog_service.list_versions(derived_id)
                if record.is_primary
                and record.is_online
                and record.status == "published"
            ),
            None,
        )

    def _require_catalog_entry(
        self,
        derived_id: str,
        version: int,
    ) -> DerivedSpecRecord:
        spec_record = self._catalog_service.get_spec(derived_id, version)
        if spec_record is None:
            raise DerivedNotFoundError(derived_id=derived_id, version=version)
        version_record = self._catalog_service.get_version(derived_id, version)
        if version_record is None:
            raise DerivedNotFoundError(derived_id=derived_id, version=version)
        return spec_record

    def _require_published_version(self, derived_id: str, version: int) -> None:
        """Refuse reads of versions not yet published（完成才可读）."""
        self._require_catalog_entry(derived_id, version)
        version_record = self._catalog_service.get_version(derived_id, version)
        if version_record is None or version_record.status != "published":
            raise DerivedVersionError(
                derived_id=derived_id,
                reason=(
                    "artifact version not published "
                    f"(status={version_record.status if version_record else 'missing'})"
                ),
            )

    def _verify_partition_integrity(
        self,
        derived_id: str,
        version: int,
        parquet_paths: list[Path],
    ) -> None:
        """
        Fail closed on partitions lacking COMPLETE or matching checksums.

        每个被读分区必须有 COMPLETE checkpoint 且文件内容 sha256 与目录记录
        一致；不一致即身份漂移或部分写入，拒绝读取。
        """
        checkpoints = {
            record.partition_key: record
            for record in self._catalog_service.list_checkpoints(derived_id, version)
        }
        for path in parquet_paths:
            partition_key = path.name.removesuffix(".parquet")
            record = checkpoints.get(partition_key)
            if record is None or record.status != DerivedCheckpointStatus.COMPLETE:
                status = record.status if record is not None else "missing"
                raise DerivedIntegrityError(
                    derived_id=derived_id,
                    version=version,
                    partition_key=partition_key,
                    reason=f"partition checkpoint not COMPLETE (status={status})",
                )
            if record.checksum is None:
                raise DerivedIntegrityError(
                    derived_id=derived_id,
                    version=version,
                    partition_key=partition_key,
                    reason="complete partition has no recorded checksum",
                )
            actual = sha256(path.read_bytes()).hexdigest()
            if actual != record.checksum:
                raise DerivedIntegrityError(
                    derived_id=derived_id,
                    version=version,
                    partition_key=partition_key,
                    reason="partition checksum drift (identity mismatch)",
                    expected_checksum=record.checksum,
                    actual_checksum=actual,
                )


def _effective_time_key(spec_record: DerivedSpecRecord) -> str:
    payload = spec_record.spec_json
    time_keys = payload.get("time_keys")
    if isinstance(time_keys, list) and time_keys:
        first = time_keys[0]
        if isinstance(first, str):
            return first
    return "trade_date"


def _normalize_frame_request(
    request: DerivedArtifactFrameRequest | None,
    params: dict[str, object],
) -> DerivedArtifactFrameRequest:
    """Normalize request-object and legacy keyword read inputs."""
    if request is not None:
        if params:
            msg = "DerivedArtifactFrameRequest cannot be combined with keyword params"
            raise ValueError(msg)
        return request

    return DerivedArtifactFrameRequest(
        derived_id=_required_str(params, "derived_id"),
        version=_required_int(params, "version"),
        instrument_ids=_instrument_ids_param(params.get("instrument_ids")),
        start=_optional_str(params.get("start")),
        end=_optional_str(params.get("end")),
        as_of=_optional_str(params.get("as_of")),
        streaming=_bool_param(params.get("streaming")),
        max_rows=_optional_int(params.get("max_rows")),
        as_lazy=_bool_param(params.get("as_lazy")),
    )


def _required_str(params: dict[str, object], key: str) -> str:
    """Read a required string parameter."""
    value = params[key]
    if value is None:
        msg = f"Missing required artifact frame parameter: {key}"
        raise ValueError(msg)
    return str(value)


def _required_int(params: dict[str, object], key: str) -> int:
    """Read a required integer parameter."""
    return _coerce_int(params[key])


def _instrument_ids_param(raw: object) -> tuple[int, ...] | None:
    """Read optional instrument ID filters."""
    if raw is None:
        return None
    if isinstance(raw, list):
        values = cast(list[object], raw)
        return tuple(_coerce_int(value) for value in values)
    if isinstance(raw, tuple):
        values = cast(tuple[object, ...], raw)
        return tuple(_coerce_int(value) for value in values)
    return (_coerce_int(raw),)


def _optional_str(raw: object) -> str | None:
    """Read an optional string parameter."""
    if raw is None:
        return None
    return str(raw)


def _optional_int(raw: object) -> int | None:
    """Read an optional integer parameter."""
    if raw is None:
        return None
    return _coerce_int(raw)


def _bool_param(raw: object) -> bool:
    """Read an optional boolean parameter."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.lower() in {"1", "true", "yes", "y"}
    return False


def _coerce_int(raw: object) -> int:
    """Coerce integer-compatible values."""
    if isinstance(raw, bool):
        return int(raw)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    if isinstance(raw, str):
        return int(raw)
    msg = f"Expected integer-compatible value, got {type(raw).__name__}"
    raise TypeError(msg)


def _coerce_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _scan_with_schema_evolution(parquet_paths: list[Path]) -> pl.LazyFrame:
    """
    Scan parquet files with schema evolution support.

    When multiple files have diverging schemas (new columns or widened
    types), ``pl.concat(how='diagonal_relaxed')`` unions the column sets
    and coerces mismatched types to their common supertype.
    """
    if len(parquet_paths) == 1:
        return pl.scan_parquet(str(parquet_paths[0]))
    lfs = [pl.scan_parquet(str(p)) for p in parquet_paths]
    return pl.concat(lfs, how="diagonal_relaxed")
