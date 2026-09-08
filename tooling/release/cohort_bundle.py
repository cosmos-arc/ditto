"""Stage the offline verifier and build a deterministic release envelope."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import stat
import tarfile
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

from tooling.release.cohort_verify import verify_cohort_manifest

__all__ = [
    "CohortBundleError",
    "create_release_bundle",
    "main",
    "stage_offline_verifier",
]

_FILE_MODE = 0o644
_COPY_CHUNK_SIZE = 1024 * 1024
_OFFLINE_VERIFIER_FILES = (
    ("tooling/__init__.py", "release-tools/tooling/__init__.py"),
    (
        "tooling/release/__init__.py",
        "release-tools/tooling/release/__init__.py",
    ),
    (
        "tooling/release/cohort_manifest.py",
        "release-tools/tooling/release/cohort_manifest.py",
    ),
    (
        "tooling/release/cohort_verify.py",
        "release-tools/tooling/release/cohort_verify.py",
    ),
    (
        "tooling/release/environment_identity.py",
        "release-tools/tooling/release/environment_identity.py",
    ),
    ("tooling/release/offline_verify.py", "release-tools/verify-cohort.py"),
)


class CohortBundleError(ValueError):
    """Raised when the release envelope cannot be proven deterministic and safe."""


def stage_offline_verifier(
    *,
    source_root: Path,
    workspace_root: Path,
) -> tuple[Path, ...]:
    """Copy the exact stdlib-only verifier runtime into a release workspace."""
    source = _directory_root(source_root, label="source root")
    workspace = _directory_root(workspace_root, label="cohort workspace")
    staged: list[Path] = []
    for source_relative, destination_relative in _OFFLINE_VERIFIER_FILES:
        source_path, _ = _contained_regular_file(
            source,
            source / source_relative,
            label=f"offline verifier source {source_relative}",
        )
        destination = workspace.joinpath(*PurePosixPath(destination_relative).parts)
        _atomic_copy(source_path, destination, root=workspace)
        staged.append(destination)
    return tuple(staged)


def create_release_bundle(
    *,
    workspace_root: Path,
    manifest_path: Path,
    output_path: Path,
    source_date_epoch: int,
    additional_paths: Sequence[Path] = (),
) -> Path:
    """Create and re-open a deterministic tar envelope around a verified cohort."""
    if type(source_date_epoch) is not int or source_date_epoch < 0:
        raise CohortBundleError("source date epoch must be a non-negative integer")
    workspace = _directory_root(workspace_root, label="cohort workspace")
    manifest_candidate = _workspace_path(workspace, manifest_path)
    verified = verify_cohort_manifest(
        workspace_root=workspace,
        manifest_path=manifest_candidate,
    )

    expected_sha256 = {
        record["path"]: record["sha256"] for record in verified["artifacts"]
    }
    manifest_file, manifest_relative = _contained_regular_file(
        workspace,
        manifest_candidate,
        label="release manifest",
    )
    expected_sha256[manifest_relative] = _sha256(manifest_file)
    paths_by_name = {
        record["path"]: workspace.joinpath(*PurePosixPath(record["path"]).parts)
        for record in verified["artifacts"]
    }
    paths_by_name[manifest_relative] = manifest_file

    for additional in additional_paths:
        additional_file, relative = _contained_regular_file(
            workspace,
            _workspace_path(workspace, additional),
            label=f"additional bundle file {additional}",
        )
        if relative in paths_by_name:
            raise CohortBundleError(f"duplicate bundle path: {relative}")
        paths_by_name[relative] = additional_file
        expected_sha256[relative] = _sha256(additional_file)

    destination = _bundle_destination(workspace, output_path)
    destination_relative = destination.relative_to(workspace).as_posix()
    if destination_relative in paths_by_name:
        raise CohortBundleError("bundle output cannot recursively include itself")

    ordered_names = sorted(paths_by_name)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
        with tarfile.open(temporary, mode="w", format=tarfile.GNU_FORMAT) as archive:
            for name in ordered_names:
                source_file, _ = _contained_regular_file(
                    workspace,
                    paths_by_name[name],
                    label=f"bundle member {name}",
                )
                info = tarfile.TarInfo(name=name)
                info.size = source_file.stat().st_size
                info.mode = _FILE_MODE
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.mtime = source_date_epoch
                info.type = tarfile.REGTYPE
                with source_file.open("rb") as payload:
                    archive.addfile(info, fileobj=payload)
        temporary.chmod(_FILE_MODE)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

    _verify_bundle(
        destination,
        expected_sha256=expected_sha256,
        source_date_epoch=source_date_epoch,
    )
    return destination


def _verify_bundle(
    bundle_path: Path,
    *,
    expected_sha256: Mapping[str, str],
    source_date_epoch: int,
) -> None:
    if bundle_path.is_symlink():
        raise CohortBundleError("bundle output cannot be a symlink")
    try:
        with tarfile.open(bundle_path, mode="r:") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            if names != sorted(expected_sha256):
                raise CohortBundleError(
                    "bundle members are missing, extra, or unsorted"
                )
            for member in members:
                _verify_member_metadata(member, source_date_epoch=source_date_epoch)
                stream = archive.extractfile(member)
                if stream is None:
                    raise CohortBundleError(
                        f"could not read bundle member: {member.name}"
                    )
                digest = hashlib.sha256()
                with stream:
                    while chunk := stream.read(_COPY_CHUNK_SIZE):
                        digest.update(chunk)
                if digest.hexdigest() != expected_sha256[member.name]:
                    raise CohortBundleError(
                        f"bundle member SHA-256 is invalid: {member.name}"
                    )
    except (OSError, tarfile.TarError) as error:
        raise CohortBundleError(
            "release bundle is not a readable tar archive"
        ) from error


def _verify_member_metadata(member: tarfile.TarInfo, *, source_date_epoch: int) -> None:
    _validate_portable_path(member.name)
    if not member.isfile() or member.issym() or member.islnk():
        raise CohortBundleError(f"bundle member must be a regular file: {member.name}")
    if (
        member.uid != 0
        or member.gid != 0
        or member.uname != ""
        or member.gname != ""
        or member.mode != _FILE_MODE
        or member.mtime != source_date_epoch
    ):
        raise CohortBundleError(
            f"bundle member metadata is not deterministic: {member.name}"
        )


def _directory_root(path: Path, *, label: str) -> Path:
    candidate = path.expanduser()
    if candidate.is_symlink():
        raise CohortBundleError(f"{label} cannot be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise CohortBundleError(f"{label} is unavailable") from error
    if not resolved.is_dir():
        raise CohortBundleError(f"{label} must be a directory")
    return resolved


def _workspace_path(workspace: Path, path: Path) -> Path:
    return path.expanduser() if path.is_absolute() else workspace / path.expanduser()


def _contained_regular_file(root: Path, path: Path, *, label: str) -> tuple[Path, str]:
    candidate = _workspace_path(root, path)
    try:
        lexical = candidate.absolute().relative_to(root)
    except ValueError as error:
        raise CohortBundleError(f"{label} escapes cohort workspace") from error
    if any(part in {".", ".."} for part in lexical.parts):
        raise CohortBundleError(f"{label} escapes cohort workspace")
    current = root
    metadata = root.lstat()
    for part in lexical.parts:
        current /= part
        try:
            metadata = current.lstat()
        except OSError as error:
            raise CohortBundleError(f"{label} is unavailable") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise CohortBundleError(f"{label} cannot contain a symlink")
    if not stat.S_ISREG(metadata.st_mode):
        raise CohortBundleError(f"{label} must be a regular file")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise CohortBundleError(f"{label} is unavailable") from error
    if not resolved.is_relative_to(root):
        raise CohortBundleError(f"{label} escapes cohort workspace")
    relative = resolved.relative_to(root).as_posix()
    _validate_portable_path(relative)
    return resolved, relative


def _validate_portable_path(value: str) -> None:
    path = PurePosixPath(value)
    parts = value.split("/")
    if (
        not value
        or "\\" in value
        or ":" in value
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise CohortBundleError(f"bundle path is unsafe: {value!r}")


def _safe_parent(root: Path, destination: Path) -> None:
    relative_parent = destination.parent.relative_to(root)
    current = root
    for part in relative_parent.parts:
        current /= part
        if current.is_symlink():
            raise CohortBundleError(
                f"bundle destination cannot contain a symlink: {destination}"
            )
        if current.exists():
            if not current.is_dir():
                raise CohortBundleError(
                    f"bundle destination parent is not a directory: {current}"
                )
        else:
            current.mkdir(mode=0o755)


def _bundle_destination(root: Path, output_path: Path) -> Path:
    candidate = _workspace_path(root, output_path)
    try:
        lexical = candidate.absolute().relative_to(root)
    except ValueError as error:
        raise CohortBundleError("bundle output escapes cohort workspace") from error
    if any(part in {".", ".."} for part in lexical.parts) or not lexical.parts:
        raise CohortBundleError("bundle output escapes cohort workspace")
    destination = root.joinpath(*lexical.parts)
    _safe_parent(root, destination)
    if destination.is_symlink():
        raise CohortBundleError("bundle output cannot be a symlink")
    if destination.exists() and not destination.is_file():
        raise CohortBundleError("bundle output must be a regular file")
    return destination


def _atomic_copy(source: Path, destination: Path, *, root: Path) -> None:
    _safe_parent(root, destination)
    if destination.is_symlink():
        raise CohortBundleError("offline verifier destination cannot be a symlink")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
        shutil.copyfile(source, temporary)
        temporary.chmod(_FILE_MODE)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(_COPY_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _parser() -> argparse.ArgumentParser:
    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    stage = subparsers.add_parser("stage-tools")
    stage.add_argument("--source-root", type=Path, default=repository_root)
    stage.add_argument("--workspace-root", type=Path, required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--workspace-root", type=Path, required=True)
    create.add_argument("--manifest", type=Path, default=Path("release-cohort.json"))
    create.add_argument("--include", type=Path, action="append", default=[])
    create.add_argument("--output", type=Path, default=Path("ditto-release-cohort.tar"))
    create.add_argument("--source-date-epoch", type=int, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Stage the verifier runtime or create a deterministic delivery envelope."""
    arguments = _parser().parse_args(argv)
    if arguments.command == "stage-tools":
        stage_offline_verifier(
            source_root=arguments.source_root,
            workspace_root=arguments.workspace_root,
        )
        return 0
    if arguments.command == "create":
        create_release_bundle(
            workspace_root=arguments.workspace_root,
            manifest_path=arguments.manifest,
            output_path=arguments.output,
            additional_paths=arguments.include,
            source_date_epoch=arguments.source_date_epoch,
        )
        return 0
    raise CohortBundleError(f"unsupported command: {arguments.command}")


if __name__ == "__main__":
    raise SystemExit(main())
