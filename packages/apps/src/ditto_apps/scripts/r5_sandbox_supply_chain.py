"""Generate deterministic SPDX and image-manifest evidence for Task 25."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import orjson

_IMAGE = re.compile(r"(?P<repository>[^@]+)@sha256:(?P<digest>[0-9a-f]{64})")


def _id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9-]", "-", value).strip("-")


def _package(
    *, spdx_id: str, name: str, version: str, package_type: str
) -> dict[str, object]:
    return {
        "SPDXID": spdx_id,
        "copyrightText": "NOASSERTION",
        "downloadLocation": "NOASSERTION",
        "externalRefs": [
            {
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceLocator": f"pkg:{package_type}/{name}@{version}",
                "referenceType": "purl",
            }
        ],
        "filesAnalyzed": False,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": "NOASSERTION",
        "name": name,
        "versionInfo": version,
    }


def build_spdx_sbom(
    *,
    image_digest: str,
    base_image_digest: str,
    created_at: str,
    debian_packages: Sequence[tuple[str, str]],
    python_packages: Sequence[tuple[str, str]],
    files: Sequence[tuple[str, str]],
) -> dict[str, object]:
    """Return one stable SPDX 2.3 document from observed image inventory."""
    image = _package(
        spdx_id="SPDXRef-Image",
        name="ditto/r5-research-sandbox",
        version=image_digest,
        package_type="oci",
    )
    base = _package(
        spdx_id="SPDXRef-BaseImage",
        name="python-base-image",
        version=base_image_digest,
        package_type="oci",
    )
    debian = [
        _package(
            spdx_id=f"SPDXRef-Deb-{_id(name)}",
            name=name,
            version=version,
            package_type="deb/debian",
        )
        for name, version in sorted(debian_packages)
    ]
    python = [
        _package(
            spdx_id=f"SPDXRef-PyPI-{_id(name)}",
            name=name,
            version=version,
            package_type="pypi",
        )
        for name, version in sorted(python_packages)
    ]
    spdx_files = [
        {
            "SPDXID": f"SPDXRef-File-{_id(path.replace('_', '-'))}",
            "checksums": [{"algorithm": "SHA256", "checksumValue": digest}],
            "copyrightText": "NOASSERTION",
            "fileName": path,
            "licenseConcluded": "NOASSERTION",
        }
        for path, digest in sorted(files)
    ]
    components = [*debian, *python]
    relationships = [
        {
            "spdxElementId": "SPDXRef-Image",
            "relationshipType": "DESCENDANT_OF",
            "relatedSpdxElement": "SPDXRef-BaseImage",
        },
        *(
            {
                "spdxElementId": "SPDXRef-Image",
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": cast(str, component["SPDXID"]),
            }
            for component in components
        ),
        *(
            {
                "spdxElementId": "SPDXRef-Image",
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": cast(str, file["SPDXID"]),
            }
            for file in spdx_files
        ),
    ]
    return {
        "SPDXID": "SPDXRef-DOCUMENT",
        "creationInfo": {
            "created": created_at,
            "creators": ["Tool: ditto-r5-sbom-generator/1"],
        },
        "dataLicense": "CC0-1.0",
        "documentDescribes": ["SPDXRef-Image"],
        "documentNamespace": (f"https://ditto.local/spdx/r5/{image_digest}"),
        "files": spdx_files,
        "name": "ditto-r5-research-sandbox",
        "packages": [image, base, *components],
        "relationships": relationships,
        "spdxVersion": "SPDX-2.3",
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_image_manifest(
    *, repo_root: Path, approved_dependencies: Sequence[str]
) -> Mapping[str, object]:
    """Authenticate the local image manifest and every bound artifact."""
    image_root = repo_root / "deploy" / "agent-sandbox"
    decoded: object = orjson.loads((image_root / "image-manifest.json").read_bytes())
    if not isinstance(decoded, Mapping):
        raise ValueError("image-manifest.json must contain a JSON object")
    manifest = cast("Mapping[str, object]", decoded)
    if (
        manifest.get("schema_id") != "r5-candidate-image-manifest"
        or manifest.get("schema_version") != 1
        or manifest.get("platform") != "linux/arm64"
        or manifest.get("user") != "65532:65532"
        or manifest.get("entrypoint") != ["/opt/ditto/bin/candidate-runner"]
        or manifest.get("approved_dependencies") != list(approved_dependencies)
    ):
        raise ValueError("sandbox image manifest is outside Approval A3")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("sandbox image artifact manifest is invalid")
    for name, expected in cast("Mapping[str, object]", artifacts).items():
        if type(name) is not str or type(expected) is not str:
            raise ValueError("sandbox image artifact identity is invalid")
        if _sha256(image_root / name) != expected:
            raise ValueError(f"sandbox image artifact drifted: {name}")
    sbom_hash = manifest.get("sbom_hash")
    if (
        type(sbom_hash) is not str
        or _sha256(image_root / "sbom.spdx.json") != sbom_hash
    ):
        raise ValueError("sandbox SBOM drifted outside Approval A3")
    return manifest


def _docker(
    *, docker_binary: Path, context: str, home: Path, arguments: tuple[str, ...]
) -> bytes:
    process = subprocess.run(  # noqa: S603 - fixed trusted Docker binary, no shell.
        (str(docker_binary), f"--context={context}", *arguments),
        capture_output=True,
        env={
            "DOCKER_CONFIG": str(home / ".docker"),
            "HOME": str(home),
            "LANG": "C",
            "LC_ALL": "C",
        },
        timeout=30,
        check=False,
    )
    if process.returncode != 0 or len(process.stdout) > 4 * 1024**2:
        raise RuntimeError("Docker supply-chain inventory command failed")
    return process.stdout


def _pairs(raw: bytes) -> tuple[tuple[str, str], ...]:
    values: list[tuple[str, str]] = []
    for line in raw.decode("utf-8").splitlines():
        name, separator, version = line.partition("\t")
        if not separator or not name or not version:
            raise ValueError("package inventory is invalid")
        values.append((name, version))
    return tuple(values)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--image", required=True)
    parser.add_argument("--base-image-digest", required=True)
    parser.add_argument("--context", default="orbstack")
    parser.add_argument(
        "--docker-binary", default=Path("/usr/local/bin/docker"), type=Path
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Inspect one local immutable image and write authenticated artifacts."""
    args = _parser().parse_args(argv)
    root = args.repo_root.resolve(strict=True)
    image_root = root / "deploy" / "agent-sandbox"
    match = _IMAGE.fullmatch(args.image)
    if match is None:
        raise ValueError("image must be an immutable repository@sha256 reference")
    docker_binary = Path(
        os.path.abspath(args.docker_binary)  # noqa: PTH100 - keep the CLI symlink path.
    )
    if not docker_binary.is_file() or not os.access(docker_binary, os.X_OK):
        raise ValueError("Docker binary must be an executable file")
    home = Path.home().resolve(strict=True)
    inspect_raw = _docker(
        docker_binary=docker_binary,
        context=args.context,
        home=home,
        arguments=("image", "inspect", args.image, "--format", "{{json .}}"),
    )
    decoded: object = orjson.loads(inspect_raw)
    if not isinstance(decoded, Mapping):
        raise ValueError("image inventory is invalid")
    inspect = cast("Mapping[str, object]", decoded)
    repo_digests = inspect.get("RepoDigests")
    config = inspect.get("Config")
    if (
        not isinstance(repo_digests, Sequence)
        or isinstance(repo_digests, str)
        or args.image not in repo_digests
        or not isinstance(config, Mapping)
    ):
        raise ValueError("image digest is not present in the local image store")
    run_prefix = (
        "run",
        "--rm",
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges=true",
        "--entrypoint",
    )
    debian = _pairs(
        _docker(
            docker_binary=docker_binary,
            context=args.context,
            home=home,
            arguments=(
                *run_prefix,
                "/usr/bin/dpkg-query",
                args.image,
                "-W",
                "-f=${Package}\\t${Version}\\n",
            ),
        )
    )
    python_inventory_program = "".join(
        (
            "import importlib.metadata,json;",
            "print(json.dumps(sorted((d.metadata['Name'],d.version) ",
            "for d in importlib.metadata.distributions()),separators=(',',':')))",
        )
    )
    python_raw = _docker(
        docker_binary=docker_binary,
        context=args.context,
        home=home,
        arguments=(
            *run_prefix,
            "/usr/local/bin/python",
            args.image,
            "-c",
            python_inventory_program,
        ),
    )
    python_decoded: object = orjson.loads(python_raw)
    if not isinstance(python_decoded, Sequence):
        raise ValueError("Python package inventory is invalid")
    python_packages = tuple(
        (cast(str, item[0]), cast(str, item[1]))
        for item in cast("Sequence[Sequence[object]]", python_decoded)
    )
    artifact_names = (
        "Containerfile",
        "candidate_runner.py",
        "requirements.lock",
        "runtime-manifest.json",
        "seccomp-provenance.json",
        "seccomp.json",
    )
    files = tuple((name, _sha256(image_root / name)) for name in artifact_names)
    digest = match.group("digest")
    base_digest = args.base_image_digest.removeprefix("sha256:")
    sbom = build_spdx_sbom(
        image_digest=digest,
        base_image_digest=base_digest,
        created_at=cast(str, inspect["Created"]),
        debian_packages=debian,
        python_packages=python_packages,
        files=files,
    )
    sbom_path = image_root / "sbom.spdx.json"
    sbom_path.write_bytes(
        orjson.dumps(sbom, option=orjson.OPT_SORT_KEYS | orjson.OPT_APPEND_NEWLINE)
    )
    manifest = {
        "approved_dependencies": ["numpy==2.3.2", "polars==1.32.2"],
        "artifacts": dict(files),
        "base_image_digest": base_digest,
        "entrypoint": cast("Mapping[str, object]", config).get("Entrypoint"),
        "image_digest": digest,
        "image_repository": match.group("repository"),
        "platform": f"{inspect['Os']}/{inspect['Architecture']}",
        "sbom_hash": _sha256(sbom_path),
        "schema_id": "r5-candidate-image-manifest",
        "schema_version": 1,
        "size_bytes": inspect["Size"],
        "user": cast("Mapping[str, object]", config).get("User"),
    }
    (image_root / "image-manifest.json").write_bytes(
        orjson.dumps(
            manifest,
            option=orjson.OPT_SORT_KEYS | orjson.OPT_APPEND_NEWLINE,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
