# Integrated Product Roadmap Closure Ledger

**Roadmap:** `docs/plans/2026-08-25-integrated-product-roadmap.md`
**Acceptance date:** 2026-08-30
**Scope:** local single-operator Beta, A-share ETFs, certified or real data,
paper execution only, and GLM only in the approved validation lane.

## Verdict

All P0–P5 implementation scope is **PROVEN in the two current working trees**.
The integrated result is intentionally narrow: one modular backend, one typed HTTP
contract, one frontend application, one synchronous read-only Agent execution seam,
and no worker queue, event bus, BFF, multi-Agent framework, or real broker path.

This is an implementation and local-Beta acceptance verdict, not a production
release or merge claim. Both repositories are on `codex/roadmap-completion` with
uncommitted changes; no commit, merge, push, real order, broker call, production
data write, or deployment was performed.

| Phase | State | Closure evidence |
|---|---|---|
| P0 | PROVEN | The frontend board closes 33/33 routes, 32/32 prototype-backed page contracts and 79/79 overlays. Every contract names its live boundary and states; visual thresholds fail the gate. R5 is replayed into the shared integration branch and the backend architecture/release gates pass. |
| P1 | PROVEN | One App Shell and seven shell presets carry the Decision Spine, status and next action. The current visual matrix passes 32/32 at 1536, 32/32 at 1366, and every declared 1200 contract (22/22), with zero final warnings. Mock/live use the same page components. |
| P2 | PROVEN | Home → Daily Decision V3 → Signals → Portfolio → Risk → Orders/Activity is live and typed, with ready/review/blocked/stale/error semantics and shared snapshot identity. The certified ETF test completes five consecutive paper days with one effective fill and zero remaining quantity per day. |
| P3 | PROVEN | Research/Alpha, Strategy Studio, experiments/backtests, evidence review/governance and Agent Console are continuous UI workflows. The certified R3 acceptance passes 8/8 commands. Persisted Agent execution uses the run's immutable PIT authority and closed read-only tool allowlist; GLM returns cited evidence and a sealed Episode. |
| P4 | PROVEN | Markets, Watchlist, Instrument, Regime and Data Products show as-of, freshness, snapshot, lineage and blocked reasons. Missing/stale data fail closed. The PIT suite and R3 provider/certification gates pass without adding a supplier or minute-data platform. |
| P5 | PROVEN | Current frontend/backend gates, OpenAPI zero-diff, visual/focus checks, five-day paper soak, backup/restore, EOD and Agent interruption recovery, provider-unavailable handling, SSE cursor resume, runbooks and product metrics all pass. |

## Machine-verifiable evidence

| Gate | Result | Evidence |
|---|---|---|
| Backend full gate | PASS: 13,920 passed, 73 skipped, 11 expected xfail, 11 xpass; 92.64% coverage; 43 import contracts kept; architecture and Harness passed | `pixi run -e dev ci` |
| Backend PIT | PASS: 33 passed, 1 skipped because the optional TDX sample is absent | `pixi run -e dev pytest -m pit` |
| R5 release preflight | PASS: 6/6 checks, no blockers/failures; report hash `c08e7fc628ba3c7694cdd3af50c402d4231efbdc41bc1e742a68d43dcb8cc12a`; file SHA-256 `156ac38fa2dd945e51a24f96a554f66233522197d93991d532f51c0d7c558ba0` | [`release-preflight.json`](../evidence/r5/release/release-preflight.json) |
| Certified research flow | PASS: 8/8 commands; report SHA-256 `28a1bd55c7900f89a9afd43ba6063f06ad51d6e838d7b069a0f76f0497e93267`; manifest SHA-256 `b82ca576e1fc0eb5717db2d2defb5b7c0fef27e228d7ea4212a10e5ba107d1d6` | [`r3-certified-research-flow.json`](../evidence/product-beta/20260830/r3-certified-research-flow.json), [`manifest`](../evidence/product-beta/20260830/r3-certified-research-flow.manifest.json) |
| Persisted GLM flow | PASS: completed revision 2, 6 durable events, 1 model attempt, 2 turns, 1 tool call, 0 retries, cited evidence and verified Episode; report hash `8162935dc058790bc288b6634f12711b8aa015a95d9ae051d121a0da7cbea050`; file SHA-256 `fd63b0dcd90a9a24ac6a01c471d26228e8afdfbd83480bbeb53ee528321d2ac4` | [`glm-persisted-run.json`](../evidence/product-beta/20260830/glm-persisted-run.json) |
| Frontend full gate | PASS: check 181 files/1457 tests; coverage 179 files/1433 tests and 85.3% lines; prototype 51 files/710 tests; build passed | [`frontend report`](../../../ditto-app/docs/review/product-beta-20260830/report.md) |
| Frontend page ledger | PASS: 33/33 routes, 32/32 contracts, 79/79 overlays | [`product completion board`](../../../ditto-app/docs/plans/2026-08-29-product-completion-board.md) |
| Frontend visual/a11y | PASS: 32/32 at 1536, 32/32 at 1366, 22/22 declared at 1200; zero warnings; keyboard Escape/focus return and zero browser console errors | [`frontend report`](../../../ditto-app/docs/review/product-beta-20260830/report.md) |
| Current whitespace gates | PASS in both repositories | `git diff --check` |

The current frontend report SHA-256 is
`5cd52d85087c2bbb7c9da4e51e31474f199cf8115bd0db8bb831fdd1402e9f79`.
The frontend R3 workflow report passes 6 files/26 tests and has SHA-256
`b81409f79998c22a36099031403125f826594cc436f0c16da2aab07ede254979`.

## P5 recovery and failure evidence

- Five simulated trading dates (`2026-08-24` through `2026-08-28`) each complete
  EOD, bind one current certified ETF snapshot, persist one paper intent/fill, and
  project a ready decision with a valid package checksum.
- Trading and Research SQLite backups restore into new isolated targets and remain
  queryable. EOD retry recovers the durable package without duplicate orders/fills.
- Agent cancellation, Episode insertion failure and presentation publication failure
  leave the queued run retryable without partial terminal state. A post-commit cursor
  projection failure serves the authoritative event cursor.
- Same-run concurrent execute calls invoke the model once in this single-process
  Beta; the losing caller receives a revision conflict. This is deliberately not a
  distributed exactly-once claim.
- Provider failure seals a failed run and auditable Episode without synthesizing an
  answer. A disabled/unavailable Agent does not break the core research or trading
  paths. SSE resumes from `Last-Event-ID` without replaying side effects.

Operator procedures are fixed in the
[`Product Beta runbook`](../operations/product-beta-runbook.md) and
[`R5 Agent runbook`](../operations/r5-agent-runbook.md).

## Product metrics at acceptance

| Metric | Result |
|---|---:|
| Page workflow closure | 33/33 |
| Overlay closure | 79/79 |
| Certified research command success | 8/8 |
| Consecutive paper-day success | 5/5 |
| GLM retries | 0 |
| GLM tool grounding | 1/1 tool call with cited evidence |
| GLM observed latency | 16,178 ms |
| Recovery drills | backup/restore, EOD interruption, Agent interruption, Episode/presentation failure and SSE resume passed |
| Final visual warnings | 0 |
| Browser console errors in final interaction check | 0 |

## Explicit limits, not unfinished roadmap work

- The deterministic acceptance lane uses a certified fixture. Consequently the R3
  report correctly says `RELEASE_ACCEPTANCE_BLOCKED` and `r2_live_gate=NOT_EVALUATED`:
  it does not prove provider entitlement, fresh certified live data, a 96-month live
  history, or production recovery.
- Tushare and FRED credentials were not found under the documented keyring aliases
  or environment fallbacks, so no fresh-provider claim is made. Their absence does
  not block the roadmap because P5 explicitly permits certified data.
- The GLM credential is Coding Plan validation-only. Its report remains
  `production_eligible=false`; a deployed application requires the formal API lane.
- No real broker connection or real order exists or was exercised. This matches the
  roadmap's explicit non-goals.
- The local per-run execution lock covers this one-process Beta; multi-process or
  distributed execution would require a separately approved architecture change.

These limits prevent an inflated production-release claim while preserving the
roadmap's intended completion boundary.
