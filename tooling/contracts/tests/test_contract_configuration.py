"""Static policy tests for checked-in contract configuration."""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_redocly_uses_recommended_strict_without_rule_overrides() -> None:
    config = yaml.safe_load((_REPO_ROOT / ".redocly.yaml").read_text(encoding="utf-8"))

    assert config["extends"] == ["recommended-strict"]
    assert config["apis"]["ditto@v1"]["root"] == "./contracts/openapi/v1.json"
    assert "rules" not in config


def test_generated_contract_artifacts_are_marked_for_review_tools() -> None:
    attributes = (_REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "contracts/openapi/v1.json text eol=lf linguist-generated=true" in attributes
    generated_attribute = (
        "apps/web/src/api/generated/schema.d.ts text eol=lf linguist-generated=true"
    )
    assert generated_attribute in attributes


def test_web_codegen_entrypoint_has_no_server_or_package_manager_fallback() -> None:
    script = (_REPO_ROOT / "apps/web/scripts/gen-api.sh").read_text(encoding="utf-8")

    assert "pixi run -e dev python -m tooling.contracts.generate_web_schema" in script
    assert "curl" not in script
    assert "bunx" not in script
