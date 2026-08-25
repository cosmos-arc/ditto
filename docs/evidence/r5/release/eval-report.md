# R5.5 formal eval evidence

Status: PASS. The frozen Fake suite, OrbStack A3 physical sandbox, GLM 5.3 Coding Plan balanced/quality online evaluations, operational exercises, interface checks, and release preflight all pass. This closes the R5 implementation plan; Coding Plan remains acceptance-only and is not a standalone/production credential.

## Frozen identity

- Seed: `20260816`; dataset manifest: `6cd838cc190354e70c31aa6af94786578073beb1c17f8d98bea7f0ec55335114`.
- Grader manifest: `ce6856a7d764bfbe7b6bf344efe653382bddf2901d19473eba955c9ff544d37d`.
- Prompt/tool manifest: `6f0829b47d9ed24e54c4f0427f1829613327b220f8e95fb4e35e6c48e64d6c93`.
- A4 scope hash: `0a3244486e365a275f3e99d6a5bbcef84d567b947c2b01db810b1709377cb219`.
- Provider/model/revision: `glm-coding-plan-responses-v1` / `glm-5.3` / `glm-5.3-coding-plan-2026-08-17`.
- Per-profile total-token cap: `500000`; monetary cost fields use the `usage_cap` basis and mean “not evaluated”, never “free”.

The schema-v2 reports carry all 120 `{case_id, schema_version, input_hash, case_hash}` entries, 120 authenticated observations with request/input/output token usage and model-output hashes, every grader verdict, aggregate manifest hashes, and a final report hash. Raw model output and credentials are not persisted.

## Online acceptance

| Profile | Reasoning | Cases | Requests | Input / output / total tokens | Read P50 / P95 | Complex P50 / P95 | Result |
|---|---|---:|---:|---:|---:|---:|---|
| balanced | `high` | 120/120 | 202 | 180,373 / 62,089 / 242,462 | 12.846 s / 20.058 s | 12.592 s / 22.729 s | PASS |
| quality | `max` | 120/120 | 202 | 182,685 / 67,959 / 250,644 | 13.257 s / 22.877 s | 12.476 s / 21.935 s | PASS |

Both profiles pass all six suites: 30 grounded, 20 author, 30 campaign/PIT/holdout, 20 permission, 10 sandbox, and 10 shadow. Every configured metric passes; forbidden action, approval bypass, PIT safety, holdout isolation, sandbox escape, required abstention, replay, shadow isolation, feedback immutability, and memory non-promotion are 100%. Tool choice and evidence coverage are 100% against a 95% threshold, factual correctness and author compile/validate are 100% against a 90% threshold.

The read P95 limit is 30 seconds and complex P95 limit is 60 seconds. Both reports remain below the 500,000-token cap. Campaign cases are governed by their authorization budget and excluded from the per-interaction latency cohort. Actual currency usage is reviewed in the BigModel console; no zero-cost claim is made.

Canonical live reports:

- [eval-report-balanced.json](eval-report-balanced.json): report hash `9120574701e0bc123e7a26944efe3ab78b52b51da0de364142190d71e033bf72`; run identity `b5f784f683d1946e31c15e17b473e4a4d9adc30a1ea06adec1f119466350a91e`.
- [eval-report-quality.json](eval-report-quality.json): report hash `3d41ef0e00b3bfde168effd18f631f5a222a1d9de7e6c93557d07a6a156fa412`; run identity `d755008d54f778da7b048e47c075e34a5acd43d69e30f6f1c4ed2d12cce4a0f7`.

## Deterministic and physical gates

- [eval-report-fake.json](eval-report-fake.json): Fake 120/120 PASS; report hash `5321bcbe665ad7d7e2ad29fa76ae0f345cc2a1c24759f72c3d11d1bd6ae1e300`.
- [sandbox-live-status.json](sandbox-live-status.json): exact OrbStack A3 scope PASS, including 11 attacks, fresh-container isolation, concurrency, `fit→score`, manifest attestations, and zero residual containers; report hash `65cfdc7f854b374c08e8b358617fa77374b903b1e579101d4c39f5caa4f0765f`.
- [release-exercises.json](release-exercises.json): backup/restore, crash resume, retention dry-run, provider outage, sandbox outage, and feature rollback all pass on isolated fixtures.
- [glm-validation-smoke.json](glm-validation-smoke.json): earlier two-request composition smoke PASS with `production_eligible=false`; it is not substituted for either 120-case report.

## Acceptance boundary

The model received only the frozen synthetic case identity/objective/host status and the closed function-tool allowlist. Expected answers were absent from model input. The deterministic host owned temporal/PIT facts, authorization, tool execution and reconciliation, evidence refs, fact tokens, replay, grading, and the authoritative answer/abstain decision. The provider had no publish, trade, order, broker, arbitrary network-data, real-user-data, market-data, portfolio-data, or research-data capability.

The user explicitly accepted Coding Plan as the R5 online acceptance credential if all online checks passed. A4 rev4 records that scope. It does not authorize Coding Plan for a standalone Ditto process or deployed product. Production activation must use the separately implemented GLM standard-API composition (or a separately approved OpenAI credential), recheck provider data controls and model identity, and rerun affected evals if any accepted identity changes. All Agent feature flags remain off by default.

## Release evidence index

- [release-preflight.json](release-preflight.json): all six checks PASS, no blockers/failures; report hash `6c895276bf694f44e815e8a78dcc84502e0f80a394271b5d808e04a769400a17`.
- [A4 approvals](../preflight/approvals.md), [A4 scope](../preflight/glm-coding-plan-a4-scope.json), and [A4 materials](../preflight/glm-coding-plan-a4-materials.json).
- [R5 Agent operations runbook](../../../operations/r5-agent-runbook.md) and [security boundary](../../../security/r5-agent-security-boundary.md).
