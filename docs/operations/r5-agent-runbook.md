# R5 governed Agent operations runbook

Status: R5.5 implementation, persisted read-only product execution, and online acceptance are COMPLETE. Deterministic/Fake acceptance, OrbStack A3 physical OCI acceptance, GLM 5.3 Coding Plan balanced/quality 120-case runs, one persisted certified-data Product Beta run, and release preflight all pass. Coding Plan is acceptance-only; a deployed product must use a standard API credential.

This runbook is for the local internal operator. The recorded A3 authorizes only its exact OrbStack/image/security scope; this document does not authorize a different daemon/profile. It does not authorize production data writes, real retention deletion, formal model egress, publishing, trading, orders, or broker access.

## Release preflight

Run from the repository root:

```bash
pixi run -e dev python -m ditto_apps.scripts.r5_agent_release_preflight \
  --repo-root "$PWD" \
  --output docs/evidence/r5/release/release-preflight.json
```

Exit codes are closed: `0` means every R5.5 check passed, `1` means evidence is missing/invalid or a gate failed, and `5` means only explicitly named approvals remain blocked. The current expected result is exit `0`, `release_status=passed`, with empty `blockers`/`failures` and all six checks passed. Never translate exit `1` or `5` into PASS.

The command is read-only except for the requested report path. It does not read an API key, invoke a model, start a daemon, execute a sandbox, open a user database, or run cleanup.

## OrbStack physical sandbox acceptance

OrbStack must already be running on the approved `orbstack` context. The command below performs the marked physical suite and writes content-addressed A3 evidence:

```bash
pixi run -e dev python -m ditto_apps.scripts.r5_sandbox_live_acceptance \
  --repo-root "$PWD" \
  --output docs/evidence/r5/release/sandbox-live-status.json
```

The runner requires the exact approved daemon inventory and immutable image digest, uses `--pull=never`, and leaves no container behind. A passing report contains 11 attack results, fresh-container, concurrent-container and `fit→score` checks. Preflight then recomputes every execution attestation and compares the report with `deploy/agent-sandbox/image-manifest.json`, SBOM, dependency lock, seccomp profile and all image-source hashes. Any runtime or artifact drift requires a new build, new evidence and renewed A3 approval; never weaken the expected profile to make a drift pass.

## Validation-only GLM smoke

This lane validates Apps composition, the fixed GLM Responses endpoint, one function-tool round trip, host-result grounding, usage, and latency. It sends only `synthetic-no-user-data-v1`; it is not a production or release acceptance lane. It may be invoked only from an approved Codex developer task: the provider's [Codex guide](https://docs.bigmodel.cn/cn/coding-plan/tool/codex) assigns `/api/v1` to Codex Responses, while its [FAQ](https://docs.bigmodel.cn/cn/coding-plan/faq) requires standalone/self-built application integrations to use the standard API.

```bash
DITTO_AGENT_GLM_VALIDATION_API_KEY="$(security find-generic-password \
  -s codex-zai-api-key -a chevy -w)" \
pixi run -e dev python -m ditto_apps.scripts.r5_glm_validation \
  --model glm-5.3 \
  --approval-a4 \
  --output docs/evidence/r5/release/glm-validation-smoke.json
```

The command must report `status=passed`, exactly 2 provider requests, at most 4096 total tokens, and all five checks true. It deliberately reports `cost_evaluated=false`, `production_eligible=false`, and `release_gate_passed=false`. Omitting `--approval-a4` returns exit 5 before reading the credential. Coding Plan credentials are rejected whenever Apps composition is in production mode. Do not use this command as a standalone Ditto validation service; repeatable tests outside Codex and every deployed environment require a standard `formal_api` credential. The two credential kinds are code-bound to different protocols: validation uses `/api/v1` Responses; GLM production uses `https://open.bigmodel.cn/api/paas/v4` Chat Completions. Never override a base URL to make one credential impersonate the other.

## Persisted Product Beta execution

The local Beta adds one bounded synchronous execution operation:
`POST /api/v1/agent/runs/{run_id}/execute`. It executes only an already queued run,
uses the immutable PIT authority stored with that run, and permits only the run's
closed read-only evidence-tool allowlist. It persists started/provider/tool/outcome
events, the operator projection, and a sealed Episode before returning. There is no
publish, strategy-weight, order, trade, broker, worker-queue, event-bus, or generic
network tool in this path.

The approved Codex-only GLM rehearsal uses an isolated new data root and a certified
ETF research snapshot. The fixture is deterministic certified evidence, not a fresh
Tushare or FRED download and not proof that those provider credentials are present.
The output intentionally remains `production_eligible=false`.

```bash
DITTO_AGENT_GLM_VALIDATION_API_KEY="$(security find-generic-password \
  -s codex-zai-api-key -a chevy -w)" \
pixi run -e dev python -m ditto_apps.scripts.r5_product_beta_glm \
  --model glm-5.3 \
  --approval-a4 \
  --data-root /absolute/new/path/ditto-product-beta-agent \
  --output docs/evidence/product-beta/20260830/glm-persisted-run.json
```

The exact data root must not already contain operator data. A passing report has
`status=passed`, `run_status=completed`, `guardrail_status=passed`,
`episode_verified=true`, one tool call, grounded evidence references, and a
six-event durable lifecycle. Missing A4 approval, credential, model configuration,
PIT authority, cited evidence, or tool grounding fails closed. Do not rerun solely
to refresh its timestamp.

## GLM online release evaluation

The Apps composition is intentionally sized for one local operator. One schema-v2 scope JSON carries the provider, content hashes for the approval record, provider data controls, runnable 120-case manifest and license/egress manifest, model ID/revision label, and one positive `max_total_tokens`. The operator separately supplies the prompt/tool manifest hash. These values and the selected profile/reasoning are part of the report identity.

The accepted provider is GLM Coding Plan at `https://open.bigmodel.cn/api/v1` using Responses, restricted to the user-approved Codex developer task. Balanced applies `high` reasoning and quality applies `max`; both use `glm-5.3` and the operator-attested label `glm-5.3-coding-plan-2026-08-17`. The label binds the reviewed run configuration and does not claim an immutable provider-returned snapshot. OpenAI remains available through the separate runtime adapter when deliberately selected, but it is not part of this GLM acceptance run. Production GLM continues to use the distinct `formal_api` composition at `https://open.bigmodel.cn/api/paas/v4` and must not inherit the Coding Plan credential.

The Apps-owned scenario provider is runnable. For each of the frozen 120 cases it sends only the synthetic case identity, suite/family, objective and host status, exposes the case's closed function-tool allowlist, executes at most one synthetic host tool, reconciles the model and host call IDs/arguments, retains only cited evidence, derives model-dependent assertions from the output, and stores only an output hash. Expected actions are not inserted into model input. Existing replay/PIT/authorization assertions remain deterministic host-owned system evidence rather than being delegated to model self-grading. The provider has no publish, trade, order, broker, network-data or real-user-data capability.

Before credential access, the runner preflights all six suites, compares their actual canonical manifest hash with the A4 runnable-dataset hash, and requires the supplied prompt/tool manifest hash to equal the runnable provider's exact prompt/tool template. It rejects a missing revision label or a rolling model ID used as its own label. Before the first case it requires the provider to bind the complete run identity and echo that A4 revision label; during the run it authenticates request/input/output token usage and stops on the first cumulative token-cap overrun. A grounded case has a 60-second hard observation timeout and every other case 120 seconds so isolated provider outliers are measured; the release SLO remains read P95 ≤30 seconds and complex P95 ≤60 seconds. Each case is limited to two provider requests, three turns, one tool and 1024 output tokens. `DITTO_AGENT_GLM_VALIDATION_API_KEY` is the only Coding Plan credential input and is never serialized.

For this single-user deployment, code does not calculate provider prices, exchange rates or USD budgets. Use the token cap for runaway protection, the existing per-call timeout/request limits for operational safety, and BigModel's console for actual spend and billing alerts. A zero value in shared dollar report fields means cost was not evaluated. It must never be presented as zero-cost evidence.

The frozen runnable dataset manifest is `6cd838cc190354e70c31aa6af94786578073beb1c17f8d98bea7f0ec55335114`. Derive the current prompt/tool manifest from code instead of typing or inventing it:

```bash
DITTO_R5_PROMPT_TOOL_MANIFEST_HASH="$(pixi run -e dev python -c \
  'from ditto_apps.registry.agent.release_eval_provider import formal_prompt_tool_manifest_hash; print(formal_prompt_tool_manifest_hash())')"
export DITTO_R5_PROMPT_TOOL_MANIFEST_HASH
```

The accepted value is `f6095c0c9a6832ff332742c9cfb0612e47080df456038d403c044c19082b2cc9`; a mismatch fails before key access. The reviewed scope is [glm-coding-plan-a4-scope.json](../evidence/r5/preflight/glm-coding-plan-a4-scope.json), backed by [glm-coding-plan-a4-materials.json](../evidence/r5/preflight/glm-coding-plan-a4-materials.json). It fixes `glm-5.3`, the 129-case dataset, provider controls, license/egress manifest, revision label and a 500,000-token cap per profile. Do not fabricate placeholder hashes to obtain a green report.

For a deliberate rerun of the accepted scope, inject `DITTO_AGENT_GLM_VALIDATION_API_KEY` through the local secret mechanism and run both profiles through the Apps-owned entry point. Do not rerun merely to refresh a timestamp; model/profile/prompt/tool/dataset changes require a new approval identity.

```bash
pixi run -e dev python -m ditto_apps.scripts.r5_release_eval \
  --profile balanced --approval-a4 \
  --scope "$DITTO_R5_A4_SCOPE" \
  --prompt-tool-manifest-hash "$DITTO_R5_PROMPT_TOOL_MANIFEST_HASH" \
  --output docs/evidence/r5/release/eval-report-balanced.json

pixi run -e dev python -m ditto_apps.scripts.r5_release_eval \
  --profile quality --approval-a4 \
  --scope "$DITTO_R5_A4_SCOPE" \
  --prompt-tool-manifest-hash "$DITTO_R5_PROMPT_TOOL_MANIFEST_HASH" \
  --output docs/evidence/r5/release/eval-report-quality.json
```

Do not place the API key on the command line or commit a secret. Missing credentials return `formal_eval_credential_missing`; scope, dataset, prompt/tool, provider identity, model-revision or token drift returns its own failed report. The checked-in balanced and quality reports are both authenticated 120/120 PASS, and the subsequent preflight exits `0`; Task 37/38 are complete.

## Feature flags and rollback

All five flags default to false:

- `DITTO_AGENT_ENABLED`
- `DITTO_AGENT_AUTHOR_ENABLED`
- `DITTO_AGENT_CAMPAIGN_ENABLED`
- `DITTO_AGENT_DECISION_SHADOW_ENABLED`
- `DITTO_AGENT_MODEL_CALLS_ENABLED`

Live evidence egress also requires an independent, Apps-owned license grant:

- `DITTO_AGENT_MODEL_APPROVED_LICENSE_CLASSES` is a comma-separated exact allowlist, for example `approved-research,redistribution-reviewed`.
- Its default is empty (deny all). Entries with surrounding whitespace, empty segments, or duplicates are rejected instead of normalized implicitly.
- A run's persisted `license_class` is only a classification request; it never authorizes itself. `cloud_allowed` evidence crosses the provider boundary only when the exact class is present in this allowlist.
- Manual Account evidence is composed through `account_event_evidence`; cloud-bound reads always request `cloud_redacted`, while prohibited egress fails before the Application query runs.

Rollback is to set all five false and restart the local Apps process. With the master flag false, child flags are ineffective and optional Agent dependencies are not probed. Do not delete Agent/Research databases during rollback. Core Ditto remains available when model provider, Agent database, sandbox, or exporter probes fail.

## Deterministic operational exercises

These commands use test-owned temporary directories, Fake providers, and injected failures. They do not use the real data root.

Backup and restore (both Agent SQLite stores plus migrated Research v2 identity and R3 governance/holdout artifacts):

```bash
pixi run -e dev pytest \
  packages/apps/tests/integration/test_agent_database_lifecycle.py::test_agent_bundle_backup_and_restore_preserve_readable_projection \
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

The checked-in OpenAPI contract exposes only the governed session, run, bounded
read-only run execution, persisted-event, approval-decision, and Campaign lifecycle
routes under `/api/v1/agent`. There is no publish, weight, order, trade, or broker
route. SSE resumes from persisted event IDs and never replays a side effect.

## Incident sequence

1. Disable all Agent flags; preserve databases, event logs, Episode manifests, approvals, audit hashes, and the failing preflight report.
2. Classify the first failed dependency or evidence check. Do not fall back to an ungrounded Agent answer.
3. For database issues, create a new non-overwriting backup and restore only into a new target; verify schema, integrity, foreign keys, domain identity, and artifact hashes before any cutover.
4. For provider or exporter outage, keep model calls disabled. Core Ditto requires no Agent recovery action.
5. For sandbox outage, pause Campaign execution. Never run generated code on the host.
6. Resume only from durable idempotency/lease/approval state and the same manifest/context hashes.
7. Rerun focused exercises, Fake eval, PIT, the exact A3 physical sandbox acceptance, live comparisons when A4 exists, then the release preflight and full CI.

## Approval completion

A3 is complete for the exact OrbStack 2.2.1/aarch64 scope recorded in `docs/evidence/r5/preflight/approvals.md`; no Kubernetes is required. A4 rev4 accepts the exact Coding Plan synthetic online-eval scope and both 120-case reports for R5 completion. Actual currency spend is reviewed in the BigModel console. This approval does not authorize Coding Plan in standalone/production execution: deployment must replace the credential with a GLM standard API key and reassess any changed provider/model/config identity before enabling flags.
