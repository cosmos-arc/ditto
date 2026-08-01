"""Build the final redacted, cross-repository Task 18 evidence manifest."""

from __future__ import annotations

import hashlib
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import orjson

__all__ = ["LiveReleaseEvidenceRequest", "build_live_release_evidence"]

_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_R2_GROUPS = (
    "provider_entitlement",
    "performance",
    "recoverability",
    "idempotency",
)


@dataclass(frozen=True, slots=True)
class LiveReleaseEvidenceRequest:
    """Exact live inputs and immutable archive targets for the final bundle."""

    backend_repo: Path
    frontend_repo: Path
    backend_live_evidence_root: Path
    frontend_live_evidence_root: Path
    r2_report: Path
    r2_source_manifest: Path
    r3_report: Path
    openapi_path: Path
    r2_archive_root: Path
    r3_archive_root: Path
    output: Path
    backend_commit: str
    frontend_commit: str
    r2_command: str
    r3_command: str
    frontend_command: str


def _canonical(value: object) -> bytes:
    return (
        orjson.dumps(value, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS) + b"\n"
    )


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _object(path: Path, *, label: str) -> dict[str, object]:
    value = orjson.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return cast("dict[str, object]", value)


def _string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _content_hash(value: object, *, label: str) -> str:
    text = _string(value, label=label)
    if _HASH.fullmatch(text) is None:
        raise ValueError(f"{label} must be a canonical SHA-256")
    return text


def _inside(root: Path, path: Path, *, label: str) -> tuple[Path, str]:
    resolved_root = root.expanduser().resolve(strict=True)
    resolved_path = path.expanduser().resolve(strict=True)
    try:
        relative = resolved_path.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} escapes its approved root") from exc
    return resolved_path, relative


def _inside_future(root: Path, path: Path, *, label: str) -> tuple[Path, str]:
    resolved_root = root.expanduser().resolve(strict=True)
    resolved_path = path.expanduser().resolve(strict=False)
    try:
        relative = resolved_path.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"{label} escapes its approved root") from exc
    return resolved_path, relative


def _entry_path(root: Path, value: object, *, label: str) -> tuple[Path, str, str]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    entry = cast("Mapping[str, object]", value)
    relative = _string(entry.get("relative_path"), label=f"{label}.relative_path")
    expected_hash = _content_hash(entry.get("sha256"), label=f"{label}.sha256")
    path, normalized = _inside(root, root / relative, label=label)
    if _hash_file(path) != expected_hash:
        raise ValueError(f"{label} hash drift")
    return path, normalized, expected_hash


def _artifact_entry(
    *,
    repository: str,
    relative_path: str,
    content_hash: str,
    generated_at: str,
    source_commit: str,
    command: str,
) -> dict[str, str]:
    return {
        "command": command,
        "generated_at": generated_at,
        "mode": "live",
        "relative_path": relative_path,
        "repository": repository,
        "sha256": content_hash,
        "source_commit": source_commit,
    }


def _validated_report(
    path: Path,
    *,
    label: str,
    source_commit: str,
) -> dict[str, object]:
    payload = _object(path, label=label)
    if (
        payload.get("mode") != "real_data"
        or payload.get("passed") is not True
        or payload.get("release_status") != "RELEASE_ACCEPTANCE_PASSED"
        or payload.get("source_commit") != source_commit
    ):
        raise ValueError(f"{label} is not a passing live report for the exact commit")
    return payload


def _r2_sources(request: LiveReleaseEvidenceRequest) -> tuple[tuple[Path, str], ...]:
    manifest_root = request.r2_source_manifest.resolve(strict=True).parent
    payload = _object(request.r2_source_manifest, label="R2 source manifest")
    if payload.get("schema") != "ditto.r2-live-gate-source":
        raise ValueError("R2 source manifest schema is invalid")
    report_path, report_relative, _ = _entry_path(
        manifest_root,
        payload.get("report"),
        label="R2 report",
    )
    if report_path != request.r2_report.resolve(strict=True):
        raise ValueError("R2 source manifest does not bind the requested report")
    report = _object(report_path, label="R2 report")
    if report.get("mode") != "live" or report.get("status") != "ready":
        raise ValueError("R2 report is not ready live evidence")
    groups = payload.get("groups")
    if not isinstance(groups, Mapping):
        raise ValueError("R2 source manifest must bind all four evidence groups")
    typed_groups = cast("Mapping[str, object]", groups)
    if set(typed_groups) != set(_R2_GROUPS):
        raise ValueError("R2 source manifest must bind all four evidence groups")
    sources: dict[Path, str] = {report_path: report_relative}
    for group_name in _R2_GROUPS:
        raw_entries = typed_groups.get(group_name)
        if not isinstance(raw_entries, list) or not raw_entries:
            raise ValueError(f"R2 evidence group is empty: {group_name}")
        for index, raw_entry in enumerate(cast("list[object]", raw_entries)):
            path, relative, _ = _entry_path(
                manifest_root,
                raw_entry,
                label=f"R2 {group_name}[{index}]",
            )
            sources[path] = relative
    return tuple(sorted(sources.items(), key=lambda item: item[1]))


def _frontend_sources(
    request: LiveReleaseEvidenceRequest,
) -> tuple[dict[str, object], tuple[tuple[Path, str, str], ...], Path]:
    manifest_path = request.frontend_live_evidence_root / "manifest.json"
    manifest = _object(manifest_path, label="frontend live manifest")
    if (
        manifest.get("mode") != "real_data"
        or manifest.get("source_commit") != request.frontend_commit
    ):
        raise ValueError("frontend live manifest does not bind the exact commit")
    raw_entries = manifest.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("frontend live manifest has no artifacts")
    sources: list[tuple[Path, str, str]] = []
    for index, value in enumerate(cast("list[object]", raw_entries)):
        try:
            path, relative, expected_hash = _entry_path(
                request.frontend_repo,
                value,
                label=f"frontend evidence[{index}]",
            )
        except ValueError as exc:
            if "hash drift" in str(exc):
                raise ValueError("frontend evidence hash drift") from exc
            raise
        sources.append((path, relative, expected_hash))
    report_path = request.frontend_live_evidence_root / "report.json"
    _validated_report(
        report_path,
        label="frontend live report",
        source_commit=request.frontend_commit,
    )
    if report_path.resolve(strict=True) not in {item[0] for item in sources}:
        raise ValueError("frontend manifest does not bind its live report")
    return manifest, tuple(sources), manifest_path.resolve(strict=True)


def _lane_identity(root: Path, lane: str) -> dict[str, object]:
    index = _object(root / "lanes" / lane / "current.json", label=f"{lane} index")
    result_path, _, expected_hash = _entry_path(
        root,
        index,
        label=f"{lane} result",
    )
    if _hash_file(result_path) != expected_hash:
        raise ValueError(f"{lane} result hash drift")
    result = _object(result_path, label=f"{lane} result")
    if result.get("lane") != lane:
        raise ValueError(f"{lane} result lane drift")
    planning_relative = _string(
        result.get("planning_document_path"),
        label=f"{lane}.planning_document_path",
    )
    planning_path, _ = _inside(
        root,
        root / planning_relative,
        label=f"{lane} planning document",
    )
    planning = _object(planning_path, label=f"{lane} planning document")
    compact_hash = _hash_bytes(orjson.dumps(planning, option=orjson.OPT_SORT_KEYS))
    planning_hash = _content_hash(
        result.get("planning_document_hash"),
        label=f"{lane}.planning_document_hash",
    )
    if compact_hash != planning_hash:
        raise ValueError(f"{lane} planning document hash drift")
    strategy = planning.get("strategy")
    snapshot = planning.get("snapshot")
    cost_model = planning.get("cost_model")
    seed = planning.get("seed")
    if not isinstance(strategy, Mapping) or not isinstance(snapshot, Mapping):
        raise ValueError(f"{lane} planning identity is incomplete")
    if not isinstance(cost_model, Mapping) or type(seed) is not int or seed < 0:
        raise ValueError(f"{lane} cost/seed identity is incomplete")
    typed_strategy = cast("Mapping[str, object]", strategy)
    typed_snapshot = cast("Mapping[str, object]", snapshot)
    typed_cost_model = cast("Mapping[str, object]", cost_model)
    strategy_hash = _content_hash(
        result.get("strategy_spec_hash"),
        label=f"{lane}.strategy_spec_hash",
    )
    snapshot_hash = _content_hash(
        result.get("snapshot_manifest_hash"),
        label=f"{lane}.snapshot_manifest_hash",
    )
    if typed_strategy.get("spec_hash") != strategy_hash:
        raise ValueError(f"{lane} strategy spec hash drift")
    if typed_snapshot.get("manifest_hash") != snapshot_hash:
        raise ValueError(f"{lane} snapshot hash drift")
    return {
        "cost_hash": _hash_bytes(
            orjson.dumps(typed_cost_model, option=orjson.OPT_SORT_KEYS)
        ),
        "packet_bundle_hash": _content_hash(
            result.get("review_bundle_hash"),
            label=f"{lane}.review_bundle_hash",
        ),
        "parameter_hash": _content_hash(
            result.get("parameter_hash"),
            label=f"{lane}.parameter_hash",
        ),
        "planning_document_hash": planning_hash,
        "planning_document_sha256": _hash_file(planning_path),
        "registry_hash": _content_hash(
            result.get("registry_hash"),
            label=f"{lane}.registry_hash",
        ),
        "seed": seed,
        "snapshot_hash": snapshot_hash,
        "strategy_spec_hash": strategy_hash,
    }


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    if _hash_file(source) != _hash_file(target):
        raise ValueError(f"evidence copy hash drift: {source}")


def _repo_relative(repo: Path, path: Path, *, label: str) -> str:
    _, relative = _inside(repo, path, label=label)
    return relative


def _archive_entry(
    *,
    request: LiveReleaseEvidenceRequest,
    target: Path,
    generated_at: str,
    command: str,
) -> dict[str, str]:
    return _artifact_entry(
        repository="backend",
        relative_path=_repo_relative(
            request.backend_repo,
            target,
            label="backend archive",
        ),
        content_hash=_hash_file(target),
        generated_at=generated_at,
        source_commit=request.backend_commit,
        command=command,
    )


def _archive_r2(
    request: LiveReleaseEvidenceRequest,
    sources: tuple[tuple[Path, str], ...],
    *,
    generated_at: str,
) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    archive = request.r2_archive_root.resolve(strict=False)
    for source, relative in sources:
        target = archive / relative
        _copy(source, target)
        artifacts.append(
            _archive_entry(
                request=request,
                target=target,
                generated_at=generated_at,
                command=request.r2_command,
            )
        )
    source_target = archive / "source-manifest.json"
    _copy(request.r2_source_manifest, source_target)
    artifacts.append(
        _archive_entry(
            request=request,
            target=source_target,
            generated_at=generated_at,
            command=request.r2_command,
        )
    )
    bundle_manifest = archive / "manifest.json"
    bundle_manifest.write_bytes(
        _canonical(
            {
                "entries": sorted(artifacts, key=lambda item: item["relative_path"]),
                "generated_at": generated_at,
                "schema": "ditto.r2-live-release-evidence-manifest",
                "version": 1,
            }
        )
    )
    artifacts.append(
        _archive_entry(
            request=request,
            target=bundle_manifest,
            generated_at=generated_at,
            command=request.r2_command,
        )
    )
    return artifacts


def _archive_r3_backend(
    request: LiveReleaseEvidenceRequest,
    *,
    live_root: Path,
    sources: tuple[Path, ...],
    generated_at: str,
) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    archive = request.r3_archive_root.resolve(strict=False)
    for source in sources:
        target = archive / "backend-live" / source.relative_to(live_root)
        _copy(source, target)
        artifacts.append(
            _archive_entry(
                request=request,
                target=target,
                generated_at=generated_at,
                command=request.r3_command,
            )
        )
    for path in (request.r3_report, request.openapi_path):
        resolved, relative = _inside(
            request.backend_repo,
            path,
            label="backend evidence",
        )
        artifacts.append(
            _artifact_entry(
                repository="backend",
                relative_path=relative,
                content_hash=_hash_file(resolved),
                generated_at=generated_at,
                source_commit=request.backend_commit,
                command=request.r3_command,
            )
        )
    return artifacts


def _frontend_artifacts(
    request: LiveReleaseEvidenceRequest,
    *,
    sources: tuple[tuple[Path, str, str], ...],
    manifest_path: Path,
    generated_at: str,
) -> list[dict[str, str]]:
    resolved, relative = _inside(
        request.frontend_repo,
        manifest_path,
        label="frontend live manifest",
    )
    artifacts = [
        _artifact_entry(
            repository="frontend",
            relative_path=relative,
            content_hash=_hash_file(resolved),
            generated_at=generated_at,
            source_commit=request.frontend_commit,
            command=request.frontend_command,
        )
    ]
    artifacts.extend(
        _artifact_entry(
            repository="frontend",
            relative_path=source_relative,
            content_hash=content_hash,
            generated_at=generated_at,
            source_commit=request.frontend_commit,
            command=request.frontend_command,
        )
        for _path, source_relative, content_hash in sources
    )
    return artifacts


def build_live_release_evidence(
    request: LiveReleaseEvidenceRequest,
    *,
    generated_at: datetime | None = None,
) -> dict[str, object]:
    """Validate, safely archive, and bind the final R2/R3 live evidence set."""
    if _COMMIT.fullmatch(request.backend_commit) is None:
        raise ValueError("backend commit must be a full lowercase Git SHA")
    if _COMMIT.fullmatch(request.frontend_commit) is None:
        raise ValueError("frontend commit must be a full lowercase Git SHA")
    backend_repo = request.backend_repo.resolve(strict=True)
    _frontend_repo = request.frontend_repo.resolve(strict=True)
    _inside_future(backend_repo, request.r2_archive_root, label="R2 archive root")
    _inside_future(backend_repo, request.r3_archive_root, label="R3 archive root")
    _inside_future(backend_repo, request.output, label="R3 manifest output")
    if request.r2_archive_root.exists() or request.r3_archive_root.exists():
        raise ValueError("live evidence archive roots must be new")

    r2_sources = _r2_sources(request)
    r3_report = _validated_report(
        request.r3_report,
        label="R3 live report",
        source_commit=request.backend_commit,
    )
    frontend_manifest, frontend_sources, frontend_manifest_path = _frontend_sources(
        request
    )
    live_root = request.backend_live_evidence_root.resolve(strict=True)
    lane_identities = {
        lane: _lane_identity(live_root, lane) for lane in ("stock", "etf")
    }
    live_json = tuple(sorted(live_root.rglob("*.json")))
    if not live_json:
        raise ValueError("backend live evidence root has no JSON artifacts")
    for path in live_json:
        _inside(live_root, path, label="backend live evidence")

    now = generated_at or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")
    generated = now.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    r3_generated = _string(
        r3_report.get("generated_at"),
        label="R3 report generated_at",
    )
    frontend_generated = _string(
        frontend_manifest.get("generated_at"),
        label="frontend manifest generated_at",
    )

    artifacts = _archive_r2(request, r2_sources, generated_at=generated)
    artifacts.extend(
        _archive_r3_backend(
            request,
            live_root=live_root,
            sources=live_json,
            generated_at=r3_generated,
        )
    )
    artifacts.extend(
        _frontend_artifacts(
            request,
            sources=frontend_sources,
            manifest_path=frontend_manifest_path,
            generated_at=frontend_generated,
        )
    )

    unique_artifacts = {
        (item["repository"], item["relative_path"]): item for item in artifacts
    }
    openapi_hash = _hash_file(request.openapi_path.resolve(strict=True))
    lanes = {
        lane: {
            **identity,
            "backend_commit": request.backend_commit,
            "frontend_commit": request.frontend_commit,
            "openapi_hash": openapi_hash,
        }
        for lane, identity in lane_identities.items()
    }
    manifest: dict[str, object] = {
        "artifacts": sorted(
            unique_artifacts.values(),
            key=lambda item: (item["repository"], item["relative_path"]),
        ),
        "backend_commit": request.backend_commit,
        "frontend_commit": request.frontend_commit,
        "generated_at": generated,
        "lanes": lanes,
        "mode": "live",
        "openapi_hash": openapi_hash,
        "r2_manifest_hash": _hash_file(request.r2_source_manifest),
        "r2_report_hash": _hash_file(request.r2_report),
        "schema": "ditto.r3-live-release-evidence-manifest",
        "version": 1,
    }
    request.output.parent.mkdir(parents=True, exist_ok=True)
    request.output.write_bytes(_canonical(manifest))
    return manifest
