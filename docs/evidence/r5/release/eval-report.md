# R5.5 formal eval evidence

Status: PASS. The frozen Fake suite, OrbStack A3 physical sandbox, GLM 5.3 Coding Plan balanced/quality online evaluations, operational exercises, interface checks, and release preflight all pass. This closes the R5 implementation plan; Coding Plan remains acceptance-only and is not a standalone/production credential.

## Frozen identity

- Seed: `20260816`; dataset manifest: `55d4dac9d9b36b6c818decca06ff3d0aadfd39a43b0908fcdfab001ca679f941`.
- Grader manifest: `ce6856a7d764bfbe7b6bf344efe653382bddf2901d19473eba955c9ff544d37d`.
- Prompt/tool manifest: `37f34f6270be28c6d045458d33cbdea6051ff797c10edd026994f4b222a6e167`.
- A4 scope hash: `50386ed59b9710e043bdcc75d2a646a4c7d6b84659d8af0a13e0a1f3c9a781c8`.
- Provider/model/revision: `glm-coding-plan-responses-v1` / `glm-5.3` / `glm-5.3-coding-plan-2026-09-01`.
- Per-profile total-token cap: `500000`; monetary cost fields use the `usage_cap` basis and mean “not evaluated”, never “free”.

The schema-v2 reports carry all 131 `{case_id, schema_version, input_hash, case_hash}` entries, 131 authenticated observations with request/input/output token usage and model-output hashes, every grader verdict, aggregate manifest hashes, and a final report hash. Raw model output and credentials are not persisted.

## Online acceptance

| Profile | Reasoning | Cases | Requests | Input / output / total tokens | Read P50 / P95 | Complex P50 / P95 | Result |
|---|---|---:|---:|---:|---:|---:|---|
| balanced | `high` | 131/131 | 224 | 202,734 / 68,307 / 271,041 | 15.799 s / 23.829 s | 14.889 s / 32.386 s | PASS |
| quality | `max` | 131/131 | 224 | 202,753 / 72,399 / 275,152 | 12.469 s / 17.509 s | 12.407 s / 25.886 s | PASS |

Both profiles pass all six suites: 41 grounded, 20 author, 30 campaign/PIT/holdout, 20 permission, 10 sandbox, and 10 shadow. Every configured metric passes; forbidden action, approval bypass, PIT safety, holdout isolation, sandbox escape, required abstention, replay, shadow isolation, feedback immutability, and memory non-promotion are 100%. Tool choice and evidence coverage are 100% against a 95% threshold, factual correctness and author compile/validate are 100% against a 90% threshold.

The read P95 limit is 30 seconds and complex P95 limit is 60 seconds. Both reports remain below the 500,000-token cap. Campaign cases are governed by their authorization budget and excluded from the per-interaction latency cohort. Actual currency usage is reviewed in the BigModel console; no zero-cost claim is made.

Canonical live reports:

- [eval-report-balanced.json](eval-report-balanced.json): report hash `71cb922068dbbfbf630cd51dffc92b7d51fcff23c7707a7cf2ae9e3290f87f9d`; run identity `b7ade07345b967b4ebf32002330300d854a7e3b14050bdc41703f2836d791399`.
- [eval-report-quality.json](eval-report-quality.json): report hash `35fd760ed24ff3986222571d8adbcaff00c0d7275810416140ac3521ca081760`; run identity `fe3e6c4b0be951e205bfc7ec474be353e3652898ce6b55fd7052084f2f75ddf9`.

## Deterministic and physical gates

- [eval-report-fake.json](eval-report-fake.json): Fake 131/131 PASS; report hash `e7134abb3159e27bf9bed49ad27b9c042cef268f7aa8ab6ece3945830b70b05f`.
- [sandbox-live-status.json](sandbox-live-status.json): exact OrbStack A3 scope PASS, including 11 attacks, fresh-container isolation, concurrency, `fit→score`, manifest attestations, and zero residual containers; report hash `65cfdc7f854b374c08e8b358617fa77374b903b1e579101d4c39f5caa4f0765f`.
- [release-exercises.json](release-exercises.json): backup/restore, crash resume, retention dry-run, provider outage, sandbox outage, and feature rollback all pass on isolated fixtures.
- [glm-validation-smoke.json](glm-validation-smoke.json): earlier two-request composition smoke PASS with `production_eligible=false`; it is not substituted for either 131-case report.

## Acceptance boundary

The model received only the frozen synthetic case identity/objective/host status and the closed function-tool allowlist. Expected answers were absent from model input. The deterministic host owned temporal/PIT facts, authorization, tool execution and reconciliation, evidence refs, fact tokens, replay, grading, and the authoritative answer/abstain decision. The provider had no publish, trade, order, broker, arbitrary network-data, real-user-data, market-data, portfolio-data, or research-data capability.

The user explicitly accepted Coding Plan as the R5 online acceptance credential if all online checks passed. A4 rev4 records that scope. It does not authorize Coding Plan for a standalone Ditto process or deployed product. Production activation must use the separately implemented GLM standard-API composition (or a separately approved OpenAI credential), recheck provider data controls and model identity, and rerun affected evals if any accepted identity changes. All Agent feature flags remain off by default.

## Release evidence index

- [release-preflight.json](release-preflight.json): all six checks PASS, no blockers/failures; report hash `f9d9d1e18f60a0681e5d1b5e3e0c9ed1056f39f734fee39592cd38ea20c0c7c9`.
- [A4 approvals](../preflight/approvals.md), [A4 scope](../preflight/glm-coding-plan-a4-scope.json), and [A4 materials](../preflight/glm-coding-plan-a4-materials.json).
- [R5 Agent operations runbook](../../../operations/r5-agent-runbook.md) and [security boundary](../../../security/r5-agent-security-boundary.md).
