# R5 governed Agent operations runbook

Status: R5.5 release is BLOCKED. Deterministic/Fake acceptance is complete; Approval A3 blocks physical OCI sandbox acceptance and Approval A4 blocks balanced/quality live-model comparison.

This runbook is for the local internal operator. It does not authorize production data writes, real retention deletion, a container daemon, model egress, publishing, trading, orders, or broker access.

## Release preflight

Run from the repository root:

```bash
pixi run -e dev python -m ditto_apps.scripts.r5_agent_release_preflight \
  --repo-root "$PWD" \
  --output docs/evidence/r5/release/release-preflight.json
```

Exit codes are closed: `0` means every R5.5 check passed, `1` means evidence is missing/invalid or a gate failed, and `5` means only explicitly named approvals remain blocked. The current expected result is exit `5`, `release_status=blocked`, `blockers=[A3,A4]`. Never translate exit `5` into PASS.

The command is read-only except for the requested report path. It does not read an API key, invoke a model, start a daemon, execute a sandbox, open a user database, or run cleanup.

## Feature flags and rollback

All five flags default to false:

- `DITTO_AGENT_ENABLED`
- `DITTO_AGENT_AUTHOR_ENABLED`
- `DITTO_AGENT_CAMPAIGN_ENABLED`
- `DITTO_AGENT_DECISION_SHADOW_ENABLED`
- `DITTO_AGENT_MODEL_CALLS_ENABLED`

Rollback is to set all five false and restart the local Apps process. With the master flag false, child flags are ineffective and optional Agent dependencies are not probed. Do not delete Agent/Research databases during rollback. Core Ditto remains available when model provider, Agent database, sandbox, or exporter probes fail.

## Deterministic operational exercises

These commands use test-owned temporary directories, Fake providers, and injected failures. They do not use the real data root.

Backup and restore (Agent SQLite plus migrated Research v2 identity and R3 governance/holdout artifacts):

```bash
pixi run -e dev pytest \
  packages/agent/tests/unit/storage/test_database.py::test_agent_database_initializes_reopens_and_restores_exact_schema \
  packages/apps/tests/integration/research/test_r3_backup_restore.py::test_r3_backup_restore_preserves_governance_holdout_and_pinned_packet \
  -q --no-cov -n 0
```

Crash and restart resume (Campaign idempotency plus approval continuation):

```bash
pixi run -e dev pytest \
  packages/apps/tests/integration/test_agent_campaign_api.py::test_pending_create_recovers_after_completion_crash_without_duplicate_event \
  packages/apps/tests/integration/test_agent_approval_resume.py::test_api_decision_resumes_persisted_interruption_after_restart \
  -q --no-cov -n 0
```

Retention dry-run (30-day boundary and CLI preview only):

```bash
pixi run -e dev pytest \
  packages/agent/tests/unit/test_retention.py::test_dry_run_uses_closed_30_day_boundary_and_is_content_addressed \
  packages/apps/tests/unit/test_agent_retention_cli.py::test_retention_cleanup_defaults_to_auditable_dry_run \
  -q --no-cov -n 0
```

Provider and sandbox outages plus feature rollback:

```bash
pixi run -e dev pytest packages/apps/tests/integration/test_agent_degradation.py::test_agent_dependency_outage_is_isolated_from_core_ditto -k model_provider -q --no-cov -n 0
pixi run -e dev pytest packages/apps/tests/integration/test_agent_degradation.py::test_agent_dependency_outage_is_isolated_from_core_ditto -k sandbox -q --no-cov -n 0
pixi run -e dev pytest packages/apps/tests/unit/test_agent_settings.py packages/apps/tests/integration/test_agent_degradation.py::test_disabled_agent_does_not_probe_optional_dependencies -q --no-cov -n 0
```

Real cleanup always requires an exact current plan hash plus external approval ID and is outside this runbook's deterministic exercise. Never reuse a dry-run approval or execute against an unresolved/broad data root.

## CLI surface

The local operator surface is:

- `agent run`
- `agent show`
- `agent events`
- `agent cancel`
- `agent approve`
- `agent reject`
- `agent campaign create`
- `agent campaign approve`
- `agent campaign show`
- `agent campaign cancel`
- `agent retention-cleanup`

Run/show/events are not authority to mutate. Approve/reject bind to the server-issued action hash. Campaign approval binds the immutable manifest and budget. Retention defaults to dry-run.

## HTTP surface

The checked-in OpenAPI contract exposes only the governed session, run, persisted-event, approval-decision, and Campaign lifecycle routes under `/api/v1/agent`. There is no publish, weight, order, trade, or broker route. SSE resumes from persisted event IDs and never replays a side effect.

## Incident sequence

1. Disable all Agent flags; preserve databases, event logs, Episode manifests, approvals, audit hashes, and the failing preflight report.
2. Classify the first failed dependency or evidence check. Do not fall back to an ungrounded Agent answer.
3. For database issues, create a new non-overwriting backup and restore only into a new target; verify schema, integrity, foreign keys, domain identity, and artifact hashes before any cutover.
4. For provider or exporter outage, keep model calls disabled. Core Ditto requires no Agent recovery action.
5. For sandbox outage, pause Campaign execution. Never run generated code on the host.
6. Resume only from durable idempotency/lease/approval state and the same manifest/context hashes.
7. Rerun focused exercises, Fake eval, PIT, physical sandbox acceptance when A3 exists, live comparisons when A4 exists, then the release preflight and full CI.

## Approval completion

A3 must name the exact runtime/profile, immutable image digest, SBOM, dependency lock, seccomp policy, and acceptance target. A4 must name the dedicated OpenAI project, MAM/ZDR posture, credentials boundary, allowed dataset/egress class, profiles, and budget. Evidence created before those grants cannot satisfy them.
