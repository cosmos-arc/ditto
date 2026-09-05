"""Fetch the pinned oasdiff release into a verified immutable tool cache."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from tooling.contracts import oasdiff

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECKSUMS_SHA256 = oasdiff.OASDIFF_CHECKSUMS_SHA256
_RELEASE_ROOT = (
    f"https://github.com/oasdiff/oasdiff/releases/download/v{oasdiff.OASDIFF_VERSION}"
)
_MAX_MANIFEST_BYTES = 1024 * 1024
_MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
_HTTP_OK = 200


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _download(url: str, *, limit: int = _MAX_ARCHIVE_BYTES) -> bytes:
    if not url.startswith(f"{_RELEASE_ROOT}/"):
        raise oasdiff.SupplyChainError("oasdiff download URL is outside pinned release")
    request = urllib.request.Request(  # noqa: S310 -- pinned HTTPS prefix above.
        url,
        headers={"User-Agent": "ditto-oasdiff-bootstrap/1"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 -- request URL was constrained.
            request,
            timeout=60,
        ) as response:
            if response.status != _HTTP_OK:
                raise oasdiff.SupplyChainError(
                    f"oasdiff download returned HTTP {response.status}: {url}"
                )
            payload = response.read(limit + 1)
    except (OSError, urllib.error.URLError) as exc:
        raise oasdiff.SupplyChainError(
            f"could not download pinned oasdiff release material: {url}"
        ) from exc
    if len(payload) > limit:
        raise oasdiff.SupplyChainError(
            f"oasdiff release material exceeds {limit} bytes: {url}"
        )
    return payload


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _verified_manifest(target: Path) -> bytes:
    manifest_path = target / "checksums.txt"
    try:
        payload = manifest_path.read_bytes()
    except OSError:
        payload = b""
    if _sha256(payload) == _CHECKSUMS_SHA256:
        return payload
    payload = _download(
        f"{_RELEASE_ROOT}/checksums.txt",
        limit=_MAX_MANIFEST_BYTES,
    )
    actual = _sha256(payload)
    if actual != _CHECKSUMS_SHA256:
        raise oasdiff.SupplyChainError(
            "downloaded oasdiff checksums.txt SHA-256 mismatch: "
            + f"expected {_CHECKSUMS_SHA256}, found {actual}"
        )
    _atomic_write(manifest_path, payload)
    return payload


def _default_cache_root() -> Path:
    configured = os.environ.get("DITTO_TOOL_CACHE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve() / "oasdiff"
    if sys.platform == "win32":
        base = Path(
            os.environ.get(
                "LOCALAPPDATA",
                Path.home() / "AppData" / "Local",
            )
        )
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "ditto" / "tools" / "oasdiff"


def ensure_distribution(
    *,
    cache_root: Path | None = None,
    system: str | None = None,
    machine: str | None = None,
) -> Path:
    """Return a locally verified distribution, downloading only missing bytes."""
    root = cache_root or _default_cache_root()
    asset_name = oasdiff.release_asset_name(
        system=system or platform.system(),
        machine=machine or platform.machine(),
    )
    target = root / f"v{oasdiff.OASDIFF_VERSION}" / _CHECKSUMS_SHA256
    _verified_manifest(target)
    try:
        oasdiff.verify_release_archive(
            dist_dir=target,
            asset_name=asset_name,
            expected_manifest_sha256=_CHECKSUMS_SHA256,
        )
        return target
    except oasdiff.SupplyChainError:
        pass

    archive_path = target / asset_name
    archive = _download(f"{_RELEASE_ROOT}/{asset_name}")
    _atomic_write(archive_path, archive)
    try:
        oasdiff.verify_release_archive(
            dist_dir=target,
            asset_name=asset_name,
            expected_manifest_sha256=_CHECKSUMS_SHA256,
        )
    except oasdiff.SupplyChainError:
        archive_path.unlink(missing_ok=True)
        raise
    return target


def main() -> int:
    """Materialize and print the verified distribution directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path)
    arguments = parser.parse_args()
    try:
        target = ensure_distribution(cache_root=arguments.cache_root)
    except oasdiff.OasdiffError as error:
        parser.exit(1, f"{error}\n")
    sys.stdout.write(f"{target}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
