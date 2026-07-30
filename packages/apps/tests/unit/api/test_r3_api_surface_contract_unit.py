"""Contract tests for the approval-gated R3 v1 HTTP surface inventory."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from ditto_apps.main import app

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SURFACE_PATH = _REPO_ROOT / "docs/contracts/r3-v1-api-surface.json"
_SURFACE_MARKDOWN_PATH = _REPO_ROOT / "docs/contracts/r3-v1-api-surface.md"
_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
_DISPOSITIONS = frozenset({"IMPLEMENT", "EQUIVALENT", "DEFER"})
_STATES = frozenset({"PLANNED", "IMPLEMENTED"})
_CLASSIFICATION_APPROVAL_STATES = frozenset({"PENDING", "APPROVED"})
_BUNDLE_PROPOSAL_STATES = frozenset({"PENDING", "APPROVED", "NOT_REQUIRED"})
_PATH_PATTERN = re.compile(r"^/api/v1/(?:research|strategies)(?:/.*)?$")

_DESIGN_12_2_OPERATIONS = frozenset(
    {
        ("GET", "/api/v1/research/node-descriptors"),
        ("GET", "/api/v1/research/factors"),
        ("GET", "/api/v1/research/factors/{factor_id}/diagnostics"),
        ("POST", "/api/v1/strategies"),
        ("POST", "/api/v1/strategies/{strategy_id}/versions"),
        ("GET", "/api/v1/strategies/{strategy_id}/versions"),
        ("GET", "/api/v1/strategies/{strategy_id}/versions/{version}"),
        ("GET", "/api/v1/strategies/{strategy_id}/versions/{version}/diff"),
        ("POST", "/api/v1/strategies/{strategy_id}/versions/{version}/validate"),
        (
            "POST",
            "/api/v1/strategies/{strategy_id}/versions/{version}/submit-review",
        ),
        (
            "POST",
            "/api/v1/strategies/{strategy_id}/versions/{version}/review-decisions",
        ),
        ("POST", "/api/v1/strategies/{strategy_id}/versions/{version}/publish"),
        ("POST", "/api/v1/strategies/{strategy_id}/versions/{version}/deprecate"),
        ("GET", "/api/v1/strategies/{strategy_id}/active"),
        ("POST", "/api/v1/strategies/{strategy_id}/reactivate"),
        ("GET", "/api/v1/strategies/{strategy_id}/events"),
        ("POST", "/api/v1/research/experiments"),
        ("GET", "/api/v1/research/experiments"),
        ("GET", "/api/v1/research/experiments/{experiment_id}"),
        ("POST", "/api/v1/research/experiments/{experiment_id}/preflight"),
        ("POST", "/api/v1/research/experiments/{experiment_id}/launch"),
        ("POST", "/api/v1/research/experiments/{experiment_id}/pause"),
        ("POST", "/api/v1/research/experiments/{experiment_id}/resume"),
        ("POST", "/api/v1/research/experiments/{experiment_id}/cancel"),
        ("GET", "/api/v1/research/experiments/{experiment_id}/candidates"),
        ("GET", "/api/v1/research/experiments/{experiment_id}/comparison"),
        ("GET", "/api/v1/research/experiments/{experiment_id}/gates"),
        ("GET", "/api/v1/research/experiments/{experiment_id}/report"),
        ("GET", "/api/v1/research/experiments/{experiment_id}/artifacts"),
        (
            "POST",
            "/api/v1/research/experiments/{experiment_id}/folds/{fold_id}/retry",
        ),
        (
            "POST",
            "/api/v1/research/experiments/{experiment_id}/candidate-selection",
        ),
        (
            "POST",
            "/api/v1/research/experiments/{experiment_id}/holdout-evaluations",
        ),
        ("GET", "/api/v1/research/candidates/{candidate_id}/selections"),
        ("GET", "/api/v1/research/candidates/{candidate_id}/exclusions"),
        (
            "GET",
            "/api/v1/research/candidates/{candidate_id}/factor-contributions",
        ),
        ("GET", "/api/v1/research/reviews"),
        ("GET", "/api/v1/research/reviews/{review_id}"),
    }
)

_W5_REQUIRED_OPERATION_IDS = frozenset(
    {
        "research_list_research_node_descriptors",
        "research_list_research_factors",
        "strategies_create_strategy",
        "strategies_list_strategies",
        "strategies_get_strategy",
        "strategies_update_strategy",
        "strategies_list_strategy_versions",
        "strategies_diff_strategy_version",
        "strategies_validate_strategy_version",
        "strategies_get_active_strategy",
        "strategies_submit_strategy_review",
        "strategies_approve_strategy_review",
        "strategies_reject_strategy_review",
        "strategies_deprecate_strategy_version",
        "strategies_publish_strategy_version",
        "strategies_reactivate_strategy_version",
        "research_list_research_experiments",
        "research_get_experiment",
        "research_list_experiment_candidates",
        "research_get_experiment_comparison",
        "research_list_experiment_gates",
        "research_list_experiment_artifacts",
        "research_get_experiment_selection_evidence",
        "research_pause_experiment",
        "research_cancel_experiment",
        "research_resume_experiment",
        "research_retry_fold_experiment",
        "research_list_research_reviews",
        "research_get_research_experiment_review_packet",
    }
)

_CONTROVERSIAL_TOPICS = frozenset(
    {
        "experiment-preflight-create-launch",
        "strategy-update-vs-version-create",
        "review-decisions-vs-approve-reject",
        "factor-diagnostics",
        "strategy-version-detail-events",
        "experiment-report",
        "candidate-selection",
        "holdout-evaluations",
        "candidate-selection-ledger-reads",
        "aggregate-selection-evidence",
        "review-detail-vs-review-packet",
        "failed-fold-retry",
        "candidate-pin-max-four",
    }
)
_FULL_SCOPE_PLANNED_OPERATIONS = {
    "design_research_factor_diagnostics": ([9], 9),
    "design_strategy_version_detail": ([8], 8),
    "design_strategy_events": ([8], 8),
    "design_research_candidate_selection": ([7, 9], 9),
    "design_research_holdout_evaluations": ([7, 9], 9),
    "design_research_candidate_selections": ([9], 9),
    "design_research_candidate_exclusions": ([9], 9),
    "design_research_candidate_factor_contributions": ([9], 9),
}
_CANDIDATE_EVIDENCE_PAGE_DTOS = {
    "design_research_candidate_selections": (
        "CandidateSelectionPageResponse",
        "CandidateSelectionEventResponse",
    ),
    "design_research_candidate_exclusions": (
        "CandidateExclusionPageResponse",
        "CandidateExclusionEventResponse",
    ),
    "design_research_candidate_factor_contributions": (
        "CandidateFactorContributionPageResponse",
        "CandidateFactorContributionResponse",
    ),
}


@pytest.fixture(scope="module")
def surface() -> dict[str, Any]:
    """Load the checked-in approval inventory."""
    return json.loads(_SURFACE_PATH.read_text(encoding="utf-8"))


def _runtime_operations() -> dict[tuple[str, str], str]:
    schema = app.openapi()
    operations: dict[tuple[str, str], str] = {}
    for path, path_item in schema["paths"].items():
        if not (
            path.startswith("/api/v1/research") or path.startswith("/api/v1/strategies")
        ):
            continue
        for method, operation in path_item.items():
            normalized_method = method.upper()
            if normalized_method not in _HTTP_METHODS:
                continue
            operations[(normalized_method, path)] = operation["operationId"]
    return operations


def _schema_projection(schema: dict[str, Any] | None) -> dict[str, Any] | None:
    if schema is None:
        return None
    return schema


def _runtime_contracts() -> list[dict[str, Any]]:
    """Project every current R3 OpenAPI operation into a stable audit shape."""
    schema = app.openapi()
    contracts: list[dict[str, Any]] = []
    for path, path_item in schema["paths"].items():
        if not (
            path.startswith("/api/v1/research") or path.startswith("/api/v1/strategies")
        ):
            continue
        for method, operation in path_item.items():
            normalized_method = method.upper()
            if normalized_method not in _HTTP_METHODS:
                continue
            request_body = operation.get("requestBody")
            request_schema = None
            if request_body is not None:
                request_schema = (
                    request_body.get("content", {})
                    .get("application/json", {})
                    .get("schema")
                )
            parameters = [
                {
                    "name": parameter["name"],
                    "in": parameter["in"],
                    "required": parameter.get("required", False),
                    "schema": parameter["schema"],
                }
                for parameter in operation.get("parameters", [])
            ]
            contracts.append(
                {
                    "operation_id": operation["operationId"],
                    "method": normalized_method,
                    "path": path,
                    "request_body_schema": _schema_projection(request_schema),
                    "responses": {
                        status: _schema_projection(
                            response.get("content", {})
                            .get("application/json", {})
                            .get("schema")
                        )
                        for status, response in operation["responses"].items()
                    },
                    "parameters": parameters,
                    "maturity": operation["x-ditto-maturity"],
                }
            )
    return sorted(contracts, key=lambda item: (item["path"], item["method"]))


def _resolved_runtime_operations(entry: dict[str, Any]) -> set[tuple[str, str]]:
    resolved: set[tuple[str, str]] = set()
    if entry["runtime_method"] is not None:
        resolved.add((entry["runtime_method"], entry["runtime_path"]))
    for replacement in entry.get("equivalence", {}).get("runtime_operations", []):
        resolved.add((replacement["method"], replacement["path"]))
    return resolved


def _assert_nonempty_audit_text(value: Any) -> None:
    assert isinstance(value, str)
    assert value.strip()


def _assert_approval_state_machine(surface: dict[str, Any]) -> None:
    classification_state = surface["approval_state"]
    assert classification_state in _CLASSIFICATION_APPROVAL_STATES
    approval = surface["approval_required"]
    assert approval["status"] == classification_state

    if classification_state == "PENDING":
        assert approval["decision"] is None
        assert approval["reference"] is None
    else:
        _assert_nonempty_audit_text(approval["decision"])
        _assert_nonempty_audit_text(approval["reference"])

    for entry in surface["operations"]:
        if entry["disposition"] not in {"DEFER", "EQUIVALENT"}:
            continue
        entry_approval = entry["user_approval"]
        assert entry_approval["status"] == classification_state
        if classification_state == "PENDING":
            assert entry_approval["decision"] is None
            assert entry_approval["reference"] is None
        else:
            _assert_nonempty_audit_text(entry_approval["decision"])
            _assert_nonempty_audit_text(entry_approval["reference"])

    proposal = surface["candidate_evidence_bundle_proposal"]
    proposal_state = proposal["approval_state"]
    assert proposal_state in _BUNDLE_PROPOSAL_STATES
    if proposal_state == "PENDING":
        assert proposal["decision"] is None
        assert proposal["reference"] is None
    elif proposal_state == "APPROVED":
        assert classification_state == "APPROVED"
        _assert_nonempty_audit_text(proposal["decision"])
        _assert_nonempty_audit_text(proposal["reference"])
    else:
        assert classification_state == "APPROVED"
        _assert_nonempty_audit_text(proposal["decision"])
        decision = proposal["decision"].lower()
        assert "schema unchanged" in decision
        assert "generic" in decision
        _assert_nonempty_audit_text(proposal["reference"])


def test_surface_schema_and_design_inventory_are_complete(
    surface: dict[str, Any],
) -> None:
    """Every design operation has one structurally complete audit record."""
    assert surface["schema_version"] == 1
    assert surface["approval_state"] in _CLASSIFICATION_APPROVAL_STATES
    entries = surface["operations"]
    operation_ids = [entry["operation_id"] for entry in entries]
    assert len(operation_ids) == len(set(operation_ids))

    design_entries = [
        (entry["design_method"], entry["design_path"])
        for entry in entries
        if "DESIGN_12_2" in entry["origins"]
    ]
    assert len(design_entries) == len(set(design_entries))
    assert set(design_entries) == _DESIGN_12_2_OPERATIONS

    required_fields = {
        "operation_id",
        "design_method",
        "design_path",
        "disposition",
        "runtime_method",
        "runtime_path",
        "equivalent_operation_id",
        "implementation_state",
        "closing_task",
        "dod",
        "reason",
        "origins",
        "contracts",
        "page_consumers",
        "controversy_topic",
    }
    required_contracts = {
        "request_identity",
        "response_dto",
        "error_codes",
        "idempotency",
        "revision_etag",
        "maturity",
    }
    for entry in entries:
        assert required_fields <= entry.keys(), entry["operation_id"]
        assert entry["design_method"] in _HTTP_METHODS
        assert _PATH_PATTERN.fullmatch(entry["design_path"])
        assert entry["disposition"] in _DISPOSITIONS
        assert entry["implementation_state"] in _STATES
        assert required_contracts == entry["contracts"].keys()
        for contract_name, contract_value in entry["contracts"].items():
            assert isinstance(contract_value, str), (
                entry["operation_id"],
                contract_name,
            )
            assert contract_value.strip(), (entry["operation_id"], contract_name)
            assert not re.search(
                r"\b(?:TBD|TODO|not frozen|placeholder)\b|尚未冻结",
                contract_value,
                re.IGNORECASE,
            ), (entry["operation_id"], contract_name)
        assert isinstance(entry["dod"], list)
        assert all(isinstance(item, int) and 1 <= item <= 23 for item in entry["dod"])
        assert entry["reason"].strip()
        assert entry["page_consumers"]
        if entry["runtime_method"] is None:
            assert entry["runtime_path"] is None
        else:
            assert entry["runtime_method"] in _HTTP_METHODS
            assert _PATH_PATTERN.fullmatch(entry["runtime_path"])


def test_planned_equivalent_and_deferred_records_are_auditable(
    surface: dict[str, Any],
) -> None:
    """Closure ownership, equivalence proof, and deferred approval are explicit."""
    for entry in surface["operations"]:
        if (
            entry["disposition"] == "IMPLEMENT"
            and entry["implementation_state"] == "PLANNED"
        ):
            assert isinstance(entry["closing_task"], int)
            assert 5 <= entry["closing_task"] <= 16
        else:
            assert entry["closing_task"] is None

        if entry["disposition"] == "EQUIVALENT":
            assert entry["implementation_state"] == "IMPLEMENTED"
            assert entry["equivalent_operation_id"]
            equivalence = entry["equivalence"]
            assert equivalence["replacement"]
            assert equivalence["runtime_operations"]
            assert set(equivalence["proof"]) == {
                "request_identity",
                "response_dto",
                "error_codes",
                "idempotency",
                "revision_etag",
                "maturity",
                "audit_evidence",
            }
            assert all(value.strip() for value in equivalence["proof"].values())
            runtime_operations = equivalence["runtime_operations"]
            runtime_tuples = [
                (item["method"], item["path"], item["operation_id"])
                for item in runtime_operations
            ]
            assert len(runtime_tuples) == len(set(runtime_tuples))
            primary = (
                entry["runtime_method"],
                entry["runtime_path"],
                entry["equivalent_operation_id"],
            )
            assert runtime_tuples.count(primary) == 1

        if entry["disposition"] == "DEFER":
            assert entry["closing_task"] is None
            approval = entry["user_approval"]
            assert approval["affected_dod"]
            assert entry["runtime_method"] is None
            assert entry["runtime_path"] is None


def test_approval_state_machines_are_auditable_and_independent(
    surface: dict[str, Any],
) -> None:
    """Current and future approval phases obey explicit transition invariants."""
    _assert_approval_state_machine(surface)

    approved = deepcopy(surface)
    approved["approval_state"] = "APPROVED"
    approved["approval_required"].update(
        {
            "status": "APPROVED",
            "decision": "Approved the R3 classification as recorded.",
            "reference": "user-approval:classification-example",
        }
    )
    for entry in approved["operations"]:
        if entry["disposition"] in {"DEFER", "EQUIVALENT"}:
            entry["user_approval"].update(
                {
                    "status": "APPROVED",
                    "decision": f"Approved {entry['operation_id']}.",
                    "reference": "user-approval:classification-example",
                }
            )

    _assert_approval_state_machine(approved)
    for proposal_state, decision in (
        ("APPROVED", "Approved the candidate bundle artifact contract."),
        (
            "NOT_REQUIRED",
            "schema unchanged: reuse the existing generic content-addressed envelope.",
        ),
    ):
        transitioned = deepcopy(approved)
        transitioned["candidate_evidence_bundle_proposal"].update(
            {
                "approval_state": proposal_state,
                "decision": decision,
                "reference": "user-approval:task-9-artifact-checkpoint-example",
            }
        )
        _assert_approval_state_machine(transitioned)

    invalid = deepcopy(surface)
    invalid["approval_state"] = "PENDING"
    invalid["approval_required"].update(
        {"status": "PENDING", "decision": None, "reference": None}
    )
    for entry in invalid["operations"]:
        if entry["disposition"] in {"DEFER", "EQUIVALENT"}:
            entry["user_approval"].update(
                {"status": "PENDING", "decision": None, "reference": None}
            )
    invalid["candidate_evidence_bundle_proposal"].update(
        {
            "approval_state": "APPROVED",
            "decision": "Approved too early.",
            "reference": "invalid:classification-still-pending",
        }
    )
    with pytest.raises(AssertionError):
        _assert_approval_state_machine(invalid)


def test_approval_projection_is_exact_and_unique(surface: dict[str, Any]) -> None:
    """Approval lists are exact projections, not a second hand-maintained truth."""
    approval = surface["approval_required"]
    for disposition, field in (
        ("DEFER", "defer_operation_ids"),
        ("EQUIVALENT", "equivalent_operation_ids"),
    ):
        stored = approval[field]
        assert len(stored) == len(set(stored))
        derived = {
            entry["operation_id"]
            for entry in surface["operations"]
            if entry["disposition"] == disposition
        }
        assert set(stored) == derived

    if "counts" in surface:
        assert surface["counts"] == _derived_counts(surface)

    implement_scope = approval["implement_scope_operation_ids"]
    assert len(implement_scope) == len(set(implement_scope))
    assert set(implement_scope) == set(_FULL_SCOPE_PLANNED_OPERATIONS)


def test_full_scope_completion_target_has_one_defer(surface: dict[str, Any]) -> None:
    """Planned routes can roll into runtime before Task 16 marks them complete."""
    entries = {entry["operation_id"]: entry for entry in surface["operations"]}
    runtime = _runtime_operations()
    for operation_id, (
        implementation_tasks,
        closing_task,
    ) in _FULL_SCOPE_PLANNED_OPERATIONS.items():
        entry = entries[operation_id]
        assert entry["disposition"] == "IMPLEMENT"
        assert entry["implementation_state"] == "PLANNED"
        assert entry["implementation_tasks"] == implementation_tasks
        assert entry["closing_task"] == closing_task
        design_key = (entry["design_method"], entry["design_path"])
        if entry["runtime_method"] is None:
            assert entry["runtime_path"] is None
            assert design_key not in runtime
        else:
            runtime_key = (entry["runtime_method"], entry["runtime_path"])
            assert runtime_key == design_key
            assert runtime[runtime_key] == operation_id

    deferred = {
        entry["operation_id"]
        for entry in surface["operations"]
        if entry["disposition"] == "DEFER"
    }
    assert deferred == {"design_research_experiment_launch_alias"}


def test_candidate_evidence_drilldowns_freeze_typed_cursor_pages(
    surface: dict[str, Any],
) -> None:
    """All candidate ledgers use artifact-bound opaque cursor pagination."""
    entries = {entry["operation_id"]: entry for entry in surface["operations"]}
    for operation_id, (
        page_dto,
        item_dto,
    ) in _CANDIDATE_EVIDENCE_PAGE_DTOS.items():
        entry = entries[operation_id]
        contracts = entry["contracts"]
        request_identity = contracts["request_identity"]
        response_dto = contracts["response_dto"]
        errors = contracts["error_codes"]
        revision = contracts["revision_etag"]

        for required_term in (
            "experiment_id required",
            "cursor optional",
            "limit bounded",
        ):
            assert required_term in request_identity
        assert f"APIResponse[{page_dto}]" in response_dto
        assert item_dto in response_dto
        for required_field in (
            "candidate_id",
            "experiment_id",
            "artifact_id",
            "content_hash",
            "items",
            "next_cursor",
        ):
            assert required_field in response_dto
        assert "INVALID_CANDIDATE_EVIDENCE_CURSOR" in errors
        assert "EVIDENCE_STALE" in errors
        for required_term in ("opaque", "content_hash", "offset"):
            assert required_term in revision


def test_strategy_events_freeze_only_existing_append_only_fields(
    surface: dict[str, Any],
) -> None:
    """The planned event projection must not imply an unapproved schema."""
    entry = next(
        item
        for item in surface["operations"]
        if item["operation_id"] == "design_strategy_events"
    )
    contract_text = json.dumps(entry["contracts"], ensure_ascii=False).lower()
    for required_field in (
        "event_id",
        "strategy_id",
        "event_type",
        "target_version",
        "decision_or_activation_kind",
        "actor",
        "reason",
        "occurred_at",
    ):
        assert required_field in contract_text
    for unsupported_field in (
        "bundle_hash",
        "evidence_hash",
        "previous_version",
        "pointer_revision",
    ):
        assert unsupported_field not in contract_text


def test_candidate_pages_bind_one_approved_immutable_bundle(
    surface: dict[str, Any],
) -> None:
    """Candidate paging identity comes from the comparison-selected bundle."""
    proposal = surface["candidate_evidence_bundle_proposal"]
    assert proposal["approval_state"] in _BUNDLE_PROPOSAL_STATES
    assert surface["approval_required"]["artifact_approval_proposal_ids"] == [
        "candidate_evidence_bundle_proposal"
    ]
    assert proposal["manifest_identity"] == [
        "experiment_id",
        "candidate_id",
        "comparison_payload_hash",
        "comparison_revision",
    ]
    assert proposal["fold_sources_order"] == [
        "validation_fold_ordinal",
        "fold_id",
    ]
    proposal_text = json.dumps(proposal, ensure_ascii=False).lower()
    for required_term in (
        "terminal successful committed",
        "attempt_id",
        "run_id",
        "never latest/max",
        "failed",
        "old retry",
        "selection_artifact_id",
        "exclusion_artifact_id",
        "contribution_artifact_id",
        "artifact_hash",
        "artifact_kind",
        "artifact_version",
        "candidate_bundle_artifact_id",
        "content_hash",
        "resource_kind",
        "offset",
        "new comparison revision",
        "old bundle",
        "evidence_stale",
        "cross-kind",
        "restart parity",
    ):
        assert required_term in proposal_text
    assert proposal["item_sort"] == {
        "selections": [
            "validation_fold_ordinal",
            "fold_id",
            "trade_date",
            "rank",
            "instrument_id",
        ],
        "exclusions": [
            "validation_fold_ordinal",
            "fold_id",
            "trade_date",
            "instrument_id",
            "stage",
            "reason_code",
        ],
        "factor_contributions": [
            "validation_fold_ordinal",
            "fold_id",
            "trade_date",
            "instrument_id",
            "factor_id",
        ],
    }

    entries = {entry["operation_id"]: entry for entry in surface["operations"]}
    for operation_id in _CANDIDATE_EVIDENCE_PAGE_DTOS:
        contract_text = json.dumps(entries[operation_id]["contracts"]).lower()
        assert "candidate_bundle_artifact_id" in contract_text
        assert "candidate bundle content_hash" in contract_text
        assert "resource_kind" in contract_text


def test_runtime_openapi_and_w5_operations_are_reconciled(
    surface: dict[str, Any],
) -> None:
    """No live R3 route or W5-consumed operation can escape the inventory."""
    runtime = _runtime_operations()
    runtime_contracts = {
        (contract["method"], contract["path"]): contract
        for contract in surface["runtime_contracts"]
    }
    entries = surface["operations"]
    inventoried_runtime: set[tuple[str, str]] = set()
    for entry in entries:
        inventoried_runtime.update(_resolved_runtime_operations(entry))

        if entry["runtime_method"] is not None:
            primary_key = (entry["runtime_method"], entry["runtime_path"])
            assert primary_key in runtime, entry["operation_id"]
            if entry["disposition"] == "IMPLEMENT":
                assert runtime[primary_key] == entry["operation_id"]
            elif entry["disposition"] == "EQUIVALENT":
                assert runtime[primary_key] == entry["equivalent_operation_id"]
            assert (
                runtime_contracts[primary_key]["maturity"]
                == entry["contracts"]["maturity"]
            )

        must_resolve = entry["disposition"] != "DEFER" and (
            entry["implementation_state"] == "IMPLEMENTED"
            or entry["disposition"] == "EQUIVALENT"
        )
        if must_resolve:
            resolved_operations = _resolved_runtime_operations(entry)
            assert resolved_operations, entry["operation_id"]
            for operation_key in resolved_operations:
                assert operation_key in runtime, entry["operation_id"]
            if entry["disposition"] == "IMPLEMENT":
                exact_key = (entry["runtime_method"], entry["runtime_path"])
                assert runtime[exact_key] == entry["operation_id"]
            for replacement in entry.get("equivalence", {}).get(
                "runtime_operations", []
            ):
                replacement_key = (replacement["method"], replacement["path"])
                assert runtime[replacement_key] == replacement["operation_id"]

    assert set(runtime) == inventoried_runtime
    assert set(runtime.values()) >= _W5_REQUIRED_OPERATION_IDS


def _derived_counts(surface: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in surface["operations"]:
        key = f"{entry['disposition']}/{entry['implementation_state']}"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def test_runtime_contract_projection_is_exact_and_hash_binds_markdown(
    surface: dict[str, Any],
) -> None:
    """Stored runtime DTO/status/header/maturity truth equals current OpenAPI."""
    stored_contracts = surface["runtime_contracts"]
    assert stored_contracts == _runtime_contracts()
    operation_ids = [contract["operation_id"] for contract in stored_contracts]
    assert len(operation_ids) == len(set(operation_ids))

    canonical = json.dumps(
        surface,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    expected_hash = sha256(canonical).hexdigest()
    markdown = _SURFACE_MARKDOWN_PATH.read_text(encoding="utf-8")
    match = re.search(r"JSON canonical SHA-256: `([0-9a-f]{64})`", markdown)
    assert match is not None
    assert match.group(1) == expected_hash


def test_markdown_machine_summary_is_exact(surface: dict[str, Any]) -> None:
    """Human review summary is machine-derived from the normative JSON."""
    markdown = _SURFACE_MARKDOWN_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"<!-- BEGIN MACHINE-DERIVED APPROVAL SUMMARY -->\s*"
        r"```json\s*(\{.*?\})\s*```\s*"
        r"<!-- END MACHINE-DERIVED APPROVAL SUMMARY -->",
        markdown,
        re.DOTALL,
    )
    assert match is not None
    summary = json.loads(match.group(1))
    approval = surface["approval_required"]
    assert summary == {
        "classification_counts": _derived_counts(surface),
        "runtime_contract_count": len(surface["runtime_contracts"]),
        "defer_operation_ids": approval["defer_operation_ids"],
        "equivalent_operation_ids": approval["equivalent_operation_ids"],
        "implement_scope_operation_ids": approval["implement_scope_operation_ids"],
        "local_state_decisions": approval["local_state_decisions"],
        "artifact_approval_proposal_ids": approval["artifact_approval_proposal_ids"],
        "classification_approval_state": surface["approval_state"],
        "candidate_bundle_proposal_state": surface[
            "candidate_evidence_bundle_proposal"
        ]["approval_state"],
    }


def test_review_detail_equivalence_exposes_latest_selection_risk(
    surface: dict[str, Any],
) -> None:
    """The review replacement cannot claim a stable review-to-experiment map."""
    entry = next(
        item
        for item in surface["operations"]
        if item["operation_id"] == "design_research_review_detail"
    )
    audit_text = json.dumps(entry, ensure_ascii=False).lower()
    for required_term in ("one-to-many", "latest", "bundle_hash", "stale"):
        assert required_term in audit_text


def test_launch_closes_only_after_durable_idempotency(
    surface: dict[str, Any],
) -> None:
    """Route introduction is Task 6, semantic closure remains Task 7."""
    entry = next(
        item
        for item in surface["operations"]
        if item["operation_id"] == "research_launch_experiment"
    )
    assert entry["implementation_tasks"] == [6, 7]
    assert entry["closing_task"] == 7


def test_all_controversial_topics_have_an_explicit_decision(
    surface: dict[str, Any],
) -> None:
    """The approval checkpoint cannot omit any disputed design/W5 semantic."""
    actual = {
        entry["controversy_topic"]
        for entry in surface["operations"]
        if entry["controversy_topic"] is not None
    }
    assert actual == _CONTROVERSIAL_TOPICS
