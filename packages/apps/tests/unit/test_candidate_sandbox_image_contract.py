"""Repository and runner contracts for the fixed R5 candidate image."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[4]
IMAGE_ROOT = REPO_ROOT / "deploy" / "agent-sandbox"
BASE_DIGEST = "67a1e1f215ccda113cfc024e8639049257e88f273898f595b61476d128d387e8"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _runner_payload(source: str, manifest: dict[str, object]) -> bytes:
    artifact = json.dumps(
        {
            "schema_id": "r5-visible-window",
            "schema_version": 1,
            "rows": [{"entity_id": "510300.SH", "value": 1.0}],
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return json.dumps(
        {
            "schema_id": "r5-oci-sandbox-input",
            "schema_version": 1,
            "phase": "fit",
            "invocation_hash": "1" * 64,
            "security_evidence_hash": "2" * 64,
            "code_artifact": {
                "source_code": source,
                "source_hash": _sha256(source.encode()),
                "canonical_ast_hash": "3" * 64,
                "dependency_lock_hash": manifest["dependency_lock_hash"],
                "dependencies": manifest["approved_dependencies"],
                "image_digest": "4" * 64,
                "input_schema_hash": "5" * 64,
                "output_schema_hash": "6" * 64,
            },
            "window": {
                "artifact": {
                    "serialization": "application/json",
                    "content_hash": _sha256(artifact),
                    "schema_hash": "5" * 64,
                    "row_count": 1,
                    "allow_pickle": False,
                    "payload_base64": base64.b64encode(artifact).decode(),
                },
                "snapshot_id": "snapshot-test",
                "decision_time_epoch_us": 1,
                "knowledge_cutoff_epoch_us": 1,
                "publication_cutoff_epoch_us": 1,
                "score_keys": [],
            },
            "seed": 41,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def test_containerfile_is_digest_pinned_non_root_and_has_no_runtime_installer() -> None:
    containerfile = (IMAGE_ROOT / "Containerfile").read_text(encoding="utf-8")

    assert f"python@sha256:{BASE_DIGEST}" in containerfile
    assert "USER 65532:65532" in containerfile
    assert 'ENTRYPOINT ["/opt/ditto/bin/candidate-runner"]' in containerfile
    assert "--require-hashes" in containerfile
    assert "latest" not in containerfile
    assert "apk add" not in containerfile
    assert "apt-get" not in containerfile


def test_dependency_lock_is_exact_and_hash_authenticated() -> None:
    lock = (IMAGE_ROOT / "requirements.lock").read_text(encoding="utf-8")
    runtime_manifest = json.loads(
        (IMAGE_ROOT / "runtime-manifest.json").read_text(encoding="utf-8")
    )

    assert "==" in lock
    assert "--hash=sha256:" in lock
    assert runtime_manifest["dependency_lock_hash"] == _sha256(lock.encode())
    assert runtime_manifest["approved_dependencies"] == [
        "numpy==2.3.2",
        "polars==1.32.2",
    ]


def test_candidate_runner_executes_the_fixed_fit_contract(tmp_path: Path) -> None:
    runtime_manifest = json.loads(
        (IMAGE_ROOT / "runtime-manifest.json").read_text(encoding="utf-8")
    )
    source = (
        "def fit(training_stream):\n"
        "    return {'schema_id': 'r5-model-state', 'mean': 0.0}\n"
        "def score(visible_window, immutable_model_state):\n"
        "    return []\n"
    )

    process = subprocess.run(  # noqa: S603 - fixed current Python and repository script.
        (sys.executable, str(IMAGE_ROOT / "candidate_runner.py"), "fit"),
        input=_runner_payload(source, runtime_manifest),
        capture_output=True,
        env={
            "DITTO_SANDBOX_RUNTIME_MANIFEST": str(IMAGE_ROOT / "runtime-manifest.json")
        },
        timeout=3,
        check=False,
    )

    assert process.returncode == 0, process.stderr
    envelope = json.loads(process.stdout)
    assert set(envelope) == {
        "payload_base64",
        "row_count",
        "schema_hash",
        "schema_id",
        "schema_version",
        "serialization",
    }
    assert envelope["schema_id"] == "r5-oci-sandbox-output"
    state = json.loads(base64.b64decode(envelope["payload_base64"], validate=True))
    assert state == {"mean": 0.0, "schema_id": "r5-model-state"}


def test_candidate_runner_rejects_source_tampering_without_output() -> None:
    runtime_manifest = json.loads(
        (IMAGE_ROOT / "runtime-manifest.json").read_text(encoding="utf-8")
    )
    source = (
        "def fit(training_stream):\n    return {}\n"
        "def score(visible_window, immutable_model_state):\n    return []\n"
    )
    payload = json.loads(_runner_payload(source, runtime_manifest))
    payload["code_artifact"]["source_hash"] = "0" * 64

    process = subprocess.run(  # noqa: S603 - fixed current Python and repository script.
        (sys.executable, str(IMAGE_ROOT / "candidate_runner.py"), "fit"),
        input=json.dumps(payload).encode(),
        capture_output=True,
        env={
            "DITTO_SANDBOX_RUNTIME_MANIFEST": str(IMAGE_ROOT / "runtime-manifest.json")
        },
        timeout=3,
        check=False,
    )

    assert process.returncode == 125
    assert process.stdout == b""
    assert b"source_hash_mismatch" in process.stderr


def test_candidate_runner_accepts_host_validated_helper_functions() -> None:
    runtime_manifest = json.loads(
        (IMAGE_ROOT / "runtime-manifest.json").read_text(encoding="utf-8")
    )
    source = (
        "def _mean(rows):\n"
        "    return sum(row['value'] for row in rows) / len(rows)\n"
        "def fit(training_stream):\n"
        "    return {'schema_id': 'r5-model-state', 'mean': _mean(training_stream)}\n"
        "def score(visible_window, immutable_model_state):\n"
        "    return []\n"
    )

    process = subprocess.run(  # noqa: S603 - fixed current Python and repository script.
        (sys.executable, str(IMAGE_ROOT / "candidate_runner.py"), "fit"),
        input=_runner_payload(source, runtime_manifest),
        capture_output=True,
        env={
            "DITTO_SANDBOX_RUNTIME_MANIFEST": str(IMAGE_ROOT / "runtime-manifest.json")
        },
        timeout=3,
        check=False,
    )

    assert process.returncode == 0, process.stderr
