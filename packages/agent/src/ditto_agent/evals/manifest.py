"""Canonical dataset identity for aggregate R5 release evaluation."""

from __future__ import annotations

from collections.abc import Mapping

from ditto_agent._canonical import canonical_sha256
from ditto_agent.evals.cases import EvalCase


def release_dataset_manifest(
    cases: Mapping[str, tuple[EvalCase, ...]],
) -> tuple[Mapping[str, object], ...]:
    """Build the provider-independent release dataset manifest."""
    return tuple(
        {
            "suite": suite,
            "cases": tuple(
                {
                    "case_id": case.case_id,
                    "schema_version": case.schema_version,
                    "input_hash": case.input_hash,
                    "case_hash": case.case_hash,
                }
                for case in sorted(cases[suite], key=lambda item: item.case_id)
            ),
        }
        for suite in sorted(cases)
    )


def release_dataset_manifest_hash(
    cases: Mapping[str, tuple[EvalCase, ...]],
) -> str:
    """Hash the exact cases that a release provider would receive."""
    return canonical_sha256(release_dataset_manifest(cases))


__all__ = ["release_dataset_manifest", "release_dataset_manifest_hash"]
