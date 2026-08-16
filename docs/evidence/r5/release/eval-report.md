# R5.5 formal eval checkpoint

Status: A3/A4-independent evidence complete; physical sandbox and live-model comparison not run.

## Frozen identity

- Provider: `fake-eval-provider-v1`; profile: `fake`; seed: `20260816`.
- Dataset manifest: `87016e42f2ef612d773fe8aefdb07be0a17238e070c1e462072fc5f8b18150c0`.
- Observation manifest: `95521832580a63f21f6412041603a382d877ccebf89f6f269adc9377a82297b3`.
- Grader manifest: `ce6856a7d764bfbe7b6bf344efe653382bddf2901d19473eba955c9ff544d37d`.
- Aggregate report: `fe8ca24c01366484d5981f662038be4948d181ec47171e5c35e6703c0eb371a8`.
- Canonical report: [eval-report-fake.json](eval-report-fake.json).

The canonical JSON carries all 120 `{case_id, schema_version, input_hash, case_hash}` entries, all 120 complete observations with independently recomputable observation hashes, every per-case grader version and verdict, per-suite report hashes, aggregate manifest hashes, and the final report hash.

## Fake hard gates

| Suite | Cases | Result | Hard-gate observations |
|---|---:|---|---|
| grounded | 30 | PASS | tool choice, evidence coverage, factual correctness, abstention, PIT, degradation, replay all 100% |
| author | 20 | PASS | compile/validate and replay 100% |
| campaign | 30 | PASS | approval, budget, integrity, forbidden action, holdout, PIT, replay 100% |
| permission | 20 | PASS | approval bypass and replay 100% |
| sandbox | 10 | PASS (Fake only) | forbidden action, escape classification and replay 100% |
| shadow | 10 | PASS | V3 grounding, PIT, isolation, immutable feedback, memory non-promotion and replay 100% |

Aggregate result: 120/120 cases present and every configured release threshold passed.

## Performance observations

| Cohort | Cases | P50 latency | P95 latency | P50 cost | P95 cost | Max cost | Limit | Result |
|---|---:|---:|---:|---:|---:|---:|---|---|
| read (`grounded`) | 30 | 215 ms | 341 ms | $0.00095 | $0.00137 | $0.0014 | P95 ≤30 s; max ≤$0.25 | PASS (Fake) |
| complex (`author`, `permission`, `sandbox`, `shadow`) | 60 | 0 ms | 0 ms | $0 | $0 | $0 | P95 ≤60 s; max ≤$0.75 | PASS (fixture envelope only) |

Campaign's 30 cases remain governed by `campaign_authorization_budget` and are not pooled into the per-interaction SLO. Zero-valued complex observations mean those earlier deterministic fixtures did not record live provider time/cost; they are not evidence of live latency or price.

## External gates and actual commands

- Fake report command exited 0 and wrote the canonical PASS report.
- Balanced OpenAI command exited 5 and wrote [eval-report-balanced.json](eval-report-balanced.json) with `status=not_run`, `approval_gate=A4`, and all prohibited-action observations false.
- Quality OpenAI command exited 5 and wrote [eval-report-quality.json](eval-report-quality.json) with the same fail-closed boundary.
- `pixi run -e dev pytest -m pit`: 31 passed, 1 skipped because the repository has no prepared TDX SH/SZ sample files.
- `pixi run -e dev pytest -m sandbox_live`: exit 5, 0 tests collected. A3 has not authorized or supplied the physical OCI runtime/image/SBOM/seccomp acceptance target.
- `pixi run -e dev pytest packages/agent/tests/unit/evals -q`: 62 passed.
- `pixi run -e dev check`: 12,823 passed, 1 existing xfail; 43 architecture contracts kept and 0 broken; architecture-smell and Harness gates passed.

No API key was read, no live endpoint was called, no model data was exported, no model cost was incurred, and no Fake result is claimed as live acceptance.

## Release evidence index

- [release-preflight.json](release-preflight.json): content-addressed current verdict; `release_status=blocked`, no failed deterministic checks, blockers A3/A4.
- [release-exercises.json](release-exercises.json): exact commands and results for backup/restore, crash resume, retention dry-run, provider/sandbox outage, and feature rollback; all use isolated fixtures.
- [sandbox-live-status.json](sandbox-live-status.json): explicit A3 `not_run` evidence; no daemon, host process, generated-code execution, or runtime artifact.
- [R5 Agent operations runbook](../../../operations/r5-agent-runbook.md) and [security boundary](../../../security/r5-agent-security-boundary.md).
