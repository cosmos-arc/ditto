"""Deterministic supply-chain evidence for the R5 sandbox image."""

from __future__ import annotations

from ditto_apps.scripts.r5_sandbox_supply_chain import build_spdx_sbom


def test_spdx_sbom_is_sorted_and_binds_every_observed_package() -> None:
    sbom = build_spdx_sbom(
        image_digest="1" * 64,
        base_image_digest="2" * 64,
        created_at="2026-08-17T00:00:00Z",
        debian_packages=(
            ("zlib1g", "1:1.2.13.dfsg-1"),
            ("base-files", "12.4"),
        ),
        python_packages=(("polars", "1.32.2"), ("numpy", "2.3.2")),
        files=(("candidate_runner.py", "3" * 64),),
    )

    assert sbom["spdxVersion"] == "SPDX-2.3"
    packages = sbom["packages"]
    relationships = sbom["relationships"]
    assert isinstance(packages, list)
    assert isinstance(relationships, list)
    assert all(isinstance(package, dict) for package in packages)
    assert all(isinstance(relationship, dict) for relationship in relationships)
    assert [package["name"] for package in packages] == [
        "ditto/r5-research-sandbox",
        "python-base-image",
        "base-files",
        "zlib1g",
        "numpy",
        "polars",
    ]
    contained = {
        relationship["relatedSpdxElement"]
        for relationship in relationships
        if relationship["relationshipType"] == "CONTAINS"
    }
    assert contained == {
        package["SPDXID"]
        for package in packages
        if package["name"] not in {"ditto/r5-research-sandbox", "python-base-image"}
    } | {"SPDXRef-File-candidate-runner-py"}
