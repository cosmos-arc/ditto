from __future__ import annotations

from pathlib import Path

import orjson
from ditto_apps.scripts.r5_product_beta_glm import main


class _UnreadableEnvironment(dict[str, str]):
    def get(self, key: str, default: str | None = None) -> str | None:
        raise AssertionError(f"credential must not be read before A4 approval: {key}")


def test_product_beta_glm_requires_a4_before_reading_the_credential(
    tmp_path: Path,
) -> None:
    output = tmp_path / "glm-product-beta.json"

    exit_code = main(
        [
            "--model",
            "glm-5.3",
            "--data-root",
            str(tmp_path / "runtime"),
            "--output",
            str(output),
        ],
        environment=_UnreadableEnvironment(),
    )

    payload = orjson.loads(output.read_bytes())
    assert exit_code == 5
    assert payload == {
        "api_key_read": False,
        "credential_kind": "glm_coding_plan_validation",
        "live_endpoint_called": False,
        "model_id": "glm-5.3",
        "production_eligible": False,
        "provider": "glm",
        "reason_code": "a4_approval_required",
        "schema_version": 1,
        "status": "not_run",
    }
