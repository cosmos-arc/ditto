# Wave 1 Final Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver the first genuinely usable Ditto daily quant workflow by narrowing Wave 1 to a staged V1a/V1b/V1c path instead of attempting every high-value capability at once.

**Architecture:** Wave 1 is now organized around the V1 Daily ETF Decision Cockpit boundary from `docs/reviews/2026-06-24-ditto-system-positioning-assessment.md`. V1a creates the smallest daily usable loop: readiness -> signal package -> current positions/deviation -> frontend read-only review. V1b adds write-path ergonomics and portfolio optimizer credibility. V1c expands into full stock-selection promotion, volume-constrained fills, attribution, and supervised AI assistance.

**Tech Stack:** Python 3.13, polars, FastAPI, Prefect, pytest, ruff, basedpyright, import-linter, pixi; ditto-app React 19, TanStack Query/Router, Vite, Biome, Vitest, bun; optional future cvxpy only after explicit approval.

---

## 0. Source Plans Consolidated

This final plan consolidates the following documents:

- `docs/reviews/2026-06-24-ditto-system-positioning-assessment.md`
- `docs/plans/2026-06-24-strategic-positioning-and-functional-gap-analysis.md`
- `docs/plans/2026-06-24-wave1-implementation-plan.md`
- `docs/plans/2026-06-24-wave1-a0-frontend-backend-wiring.md`
- `docs/plans/2026-06-24-wave1-a1-eod-publish-signals.md`
- `docs/plans/2026-06-24-wave1-b0-portfolio-optimizer.md`
- `docs/plans/2026-06-24-wave1-b1-volume-constrained-fills.md`
- `docs/plans/2026-06-24-wave1-b3-real-data-promotion.md`

The 2026-06-24 child plans remain valid as detailed implementation references. This final plan changes the order and acceptance boundary.

## 1. Final Product Boundary

### 1.1 V1 Target

Wave 1 should target:

> A daily ETF decision cockpit with governed data readiness, deterministic signals, current positions, target-vs-actual deviation, manual execution tracking, and a frontend that consumes the real backend.

This is deliberately smaller than "full stock-selection product with optimizer, volume-constrained fills, full RC1 promotion, and attribution." Those capabilities remain important, but they should not block first daily use.

### 1.2 What V1a Must Prove

On one trading date, a user can:

1. Run or inspect the daily pipeline.
2. See whether launch data is ready or blocked.
3. See latest real backend signals from `/trade/signals/latest`.
4. See positions and deviation from `/trade/positions` and `/trade/deviation`.
5. Open ditto-app with mocks disabled and review those backend artifacts.

### 1.3 What V1a Must Not Claim

V1a must not claim:

- Production stock-selection readiness.
- Full RC1 promotion across all 14 datasets.
- Optimizer-driven portfolio construction.
- Volume-realistic backtest capacity.
- Attribution-grade learning loop.
- Paper-trading or live-trading completeness.
- AI-native operation.

## 2. Final Wave Breakdown

| Wave | Name | Objective | Included Work | Explicitly Deferred |
|---|---|---|---|---|
| Wave 1a | First Real Use | Make the system visible and useful on real backend data for ETF daily decisions | Branch baseline, A1 EOD publish, B3a launch dataset readiness, new Daily Decision Cockpit backend contract, A0a read-only frontend wiring | cvxpy optimizer, volume fill rewrite, full RC1, write-path UX |
| Wave 1b | Trust and Action | Make the daily workflow actionable and decision-quality better | A0b record-fill/update-intent write paths, target-vs-actual review polish, B0 optimizer v1 after approval | full stock beta, attribution, paper-account lifecycle |
| Wave 1c | Research Credibility | Make research conclusions and beta expansion trustworthy | B1 volume-constrained fills, B3b full RC1 promotion, stock-selection beta, attribution v1 | live broker adapters, autonomous agents |
| Wave 2 | Daily Learning Loop | Add deeper review and assisted operation | paper operating loop, read-only AI copilot, factor/portfolio attribution UX | autonomous trading |

## 3. Execution Gate Before Any Code

### Task 0: Resolve Branch Baseline

**Files:**
- Read: `git log --oneline --decorate --graph --all -80`
- Read: `docs/plans/2026-06-24-wave1-implementation-plan.md`

**Step 1: Verify current branch and divergence**

Run:

```bash
git branch --show-current
git status --short
git rev-list --left-right --count main...dev/architecture-remediation-batch2-6
git ls-tree -r main -- packages/application/src/ditto_application/processes/execution/signal_package.py
git ls-tree -r dev/architecture-remediation-batch2-6 -- packages/application/src/ditto_application/processes/execution/signal_package.py
```

Expected:

- Current work branch is known.
- `signal_package.py` exists on the chosen Wave baseline.
- Any uncommitted plan edits are either committed or intentionally excluded from implementation branches.

**Step 2: Choose the implementation baseline**

Recommended choice:

1. Merge or PR `dev/architecture-remediation-batch2-6` into `main`.
2. Create Wave branches from updated `main`.

Allowed fallback:

1. Create Wave branches from `dev/architecture-remediation-batch2-6`.
2. Target PRs back to the same dev integration branch.
3. Do not mix some Wave branches from `main` and some from `dev`.

**Step 3: Record the decision**

Update this section with:

```markdown
Baseline decision: main-after-dev-merge
Decision date: 2026-07-01
Reason: `main` is up to date with `origin/main` and contains PR #66 (`refactor: V2 架构整改 Batch 2-6 — 全模块治理`). The Wave 1 dependency `packages/application/src/ditto_application/processes/execution/signal_package.py` exists on both `main` and `dev/architecture-remediation-batch2-6` with the same blob, so Wave 1 backend implementation will branch directly from current `main`.
```

Commit:

```bash
git add docs/plans/2026-06-30-wave1-final-implementation-plan.md
git commit -m "docs: record wave1 baseline decision"
```

## 4. Wave 1a: First Real Use

Wave 1a is the new first milestone. It should be completed before B0/B1 unless the user explicitly chooses to prioritize backend credibility over first usage.

### Task 1: A1 EOD Publish Signals

**Detailed Reference:** `docs/plans/2026-06-24-wave1-a1-eod-publish-signals.md`

**Files:**
- Modify: `packages/apps/src/ditto_apps/jobs/flows/eod.py`
- Read: `packages/apps/src/ditto_apps/cli/commands/strategy.py`
- Read: `packages/application/src/ditto_application/processes/execution/signal_package.py`
- Test: existing or new EOD tests under `packages/apps/tests/integration/`

**Steps:**

1. Read existing EOD flow tests with `rg -n "eod_flow|_run_strategies" packages/apps/tests`.
2. Write a failing integration test proving EOD persists `TradeIntent` records for a published strategy.
3. Run `pixi run -e dev pytest packages/apps/tests/integration -k eod -q`; expected failure is no persisted intents.
4. Change `_run_strategies` from `StrategyRunMode.RESEARCH` to `StrategyRunMode.RECOMMENDATION`.
5. Call `bundle.signal_package_publisher.publish(target=run_result.target, ...)` after successful strategy runs.
6. Record `intent_count` and `checksum` in the EOD strategy result payload.
7. Add a test that one publish failure does not block other strategy results.
8. Run the targeted EOD tests.
9. Run `pixi run -e dev check` and `pixi run -e dev arch-check`.
10. Commit `feat(eod): publish trade signal packages in daily pipeline`.

**Acceptance:**

- `/trade/signals/latest` can return EOD-produced intents for a strategy.
- Publisher missing or one strategy publish failure degrades to warning/partial status.

### Task 2: B3a Launch Dataset Readiness

**Detailed Reference:** narrowed subset of `docs/plans/2026-06-24-wave1-b3-real-data-promotion.md`

**Files:**
- Read: `scripts/acceptance/rc1_real_data_acceptance.py`
- Read: `scripts/acceptance/rc1_requirements.py`
- Read: `docs/architecture/capability-maturity.md`
- Read: `packages/apps/src/ditto_apps/cli/commands/ops.py`

**Step 1: Define V1a launch dataset set**

Create a short table in this plan before execution with the exact V1a dataset list. Recommended initial set:

- `calendar`
- ETF daily market dataset(s) required by the selected ETF strategy
- index/benchmark dataset(s) required by the selected ETF strategy
- factor/materialized outputs required by the selected ETF strategy
- trade intent and position stores used by the manual loop

Do not use the full 14-dataset RC1 list as a V1a blocker unless the selected ETF workflow genuinely needs all 14.

**V1a launch dataset decision (recorded 2026-07-01):**

| Dataset / Store | Why V1a Needs It | V1a Blocking? | Notes |
|---|---|---|---|
| `calendar` | trading-day and T+1/manual-loop date semantics | yes | Dataset maturity is `initial-focus`; catalog evidence still required. |
| `etf_basic` | ETF instrument metadata for the selected ETF workflow | yes | Dataset maturity is `initial-focus`; catalog evidence still required. |
| `etf_daily` | selected ETF strategy daily market inputs | yes | Dataset maturity is `initial-focus`; catalog evidence still required. |
| `index_basic` | benchmark/index metadata | yes | Dataset maturity is `initial-focus`; catalog evidence still required. |
| `index_daily` | benchmark/index daily market inputs | yes | Dataset maturity is `initial-focus`; catalog evidence still required. |
| `fund_adj` | ETF/fund adjustment factors for adjusted ETF signals | yes | Dataset maturity is `initial-focus`; catalog evidence still required. |
| `adj_factor` | stock/index-adj compatibility for shared market paths | review | Included as conservative shared-market dependency; can be demoted if the chosen ETF workflow proves it is unused. |
| trade intent / fill / position runtime stores | manual execution loop state | yes | Not catalog datasets; readiness is verified through trade APIs and execution store tests rather than promotion review. |

Full stock/fundamental/macro launch datasets from `scripts/acceptance/rc1_requirements.py` remain Wave 1c RC1 blockers, not V1a blockers.

**Step 2: Collect readiness evidence**

Run real-environment status commands:

```bash
ditto ops status --json
ditto ops maturity-governance --json
```

If command names differ, inspect `packages/apps/src/ditto_apps/cli/commands/ops.py` and use the actual CLI names.

**Step 3: Produce a readiness matrix**

Record for each dataset:

- current maturity
- promotion status
- freshness status
- schema/storage evidence
- missing criteria
- whether it blocks V1a

**Step 4: Promote only what V1a needs**

For each blocking launch dataset:

```bash
ditto ops promotion-collect <dataset> --start <date> --end <date>
ditto ops promotion-review <dataset>
```

Do not self-manufacture evidence. If evidence fails, mark the dataset blocked and fix ingestion first.

**Acceptance:**

- V1a launch datasets are ready/promoted or explicitly not blocking.
- Blocked datasets have exact missing evidence and owner/action.
- Full RC1 remains Wave 1c unless required for V1a.

### Task 3: Daily Decision Cockpit Backend Contract

This is the missing plan from the 2026-06-24 set. It should be implemented before broad frontend wiring so the frontend does not assemble a cockpit from many scattered endpoint semantics.

**Files:**
- Create: `packages/application/src/ditto_application/queries/daily_decision.py`
- Create or modify tests: `packages/application/tests/unit/query/test_daily_decision_query_unit.py`
- Modify: `packages/apps/src/ditto_apps/models/trade.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/trade_query_routes.py`
- Modify registry/provider wiring as needed under `packages/apps/src/ditto_apps/registry/`
- Test: `packages/apps/tests/integration/api/test_trade_api_integration.py`

**Step 1: Write application DTO tests**

Create failing tests for:

- latest signal date is inferred from `SignalQueryFacade`
- readiness status aggregates `ready`, `blocked`, `review`
- response contains latest intents, positions, deviation report, P&L when available
- missing optional sections return empty/null structured fields instead of raising

Expected command:

```bash
pixi run -e dev pytest packages/application/tests/unit/query/test_daily_decision_query_unit.py -q
```

Expected: FAIL because `daily_decision.py` does not exist.

**Step 2: Implement application read model**

Add dataclasses similar to:

```python
@dataclass(frozen=True)
class DailyDecisionReport:
    strategy_id: str
    trade_date: str
    readiness_status: Literal["ready", "blocked", "review"]
    readiness_reasons: tuple[str, ...]
    signal_intents: tuple[TradeIntent, ...]
    deviation: SignalDeviationReport | None
    positions: tuple[ActualPositionSnapshot, ...]
    pnl: PnlSummary | None
```

Use existing facades/ports:

- `SignalQueryFacade`
- `SignalDeviationQueryFacade`
- `PortfolioActualQueryFacade`
- maturity/source-health facades where already wired

Do not duplicate data maturity policy in this new facade.

**Step 3: Add API response model**

In `packages/apps/src/ditto_apps/models/trade.py`, add:

- `DailyDecisionReadinessResponse`
- `DailyDecisionReportResponse`

Keep these as transport DTOs only.

**Step 4: Add API route**

In `packages/apps/src/ditto_apps/api/routes/trade_query_routes.py`, add:

```text
GET /trade/daily-decision?strategy_id=...&trade_date=...
```

If `trade_date` is omitted, use latest signal date.

**Step 5: Add integration tests**

Extend `packages/apps/tests/integration/api/test_trade_api_integration.py` with:

- returns daily decision report
- returns empty but structured report when no signals exist
- requires strategy_id
- includes maturity/readiness reasons when available

**Step 6: Verify and commit**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/query/test_daily_decision_query_unit.py packages/apps/tests/integration/api/test_trade_api_integration.py -q
pixi run -e dev check
pixi run -e dev arch-check
```

Commit:

```bash
git add packages/application/src/ditto_application/queries/daily_decision.py \
  packages/application/tests/unit/query/test_daily_decision_query_unit.py \
  packages/apps/src/ditto_apps/models/trade.py \
  packages/apps/src/ditto_apps/api/routes/trade_query_routes.py \
  packages/apps/tests/integration/api/test_trade_api_integration.py
git commit -m "feat(trade): add daily decision report query"
```

**Acceptance:**

- One backend endpoint can drive the first cockpit screen.
- Frontend does not need to infer readiness or stitch together core daily semantics.

### Task 4: A0a Frontend Read-Only Real Backend Wiring

**Detailed Reference:** first half of `docs/plans/2026-06-24-wave1-a0-frontend-backend-wiring.md`

**Repository:** `/home/chevy/projects/ditto-app`

**Files:**
- Modify: `/home/chevy/projects/ditto-app/.env.development`
- Modify: `/home/chevy/projects/ditto-app/vite.config.ts`
- Modify: `/home/chevy/projects/ditto-app/src/main.tsx`
- Modify or create hooks under `/home/chevy/projects/ditto-app/src/features/trading/`
- Test: corresponding Vitest/RTL tests

**Steps:**

1. Add `.env.development` with `VITE_API_BASE_URL=/api` and `VITE_USE_MOCK=false`.
2. Add Vite proxy for `/api` to the local Ditto backend port.
3. Gate MSW startup behind `VITE_USE_MOCK === "true"`.
4. Add tests that dev default does not start MSW and mock mode still can.
5. Add or update query hook for `GET /trade/daily-decision`.
6. Wire signals inbox / trading overview to the daily decision report.
7. Wire positions and deviation read-only views to backend data from the same report.
8. Keep write buttons disabled or hidden until A0b; do not fake writes in frontend state.
9. Run `bun run check`.
10. Commit `feat(app): wire read-only trading cockpit to live backend`.

**Acceptance:**

- ditto-app dev default talks to the real backend.
- MSW remains available only by explicit opt-in.
- User can see latest signals, positions, and deviation from live backend.

### Task 5: Wave 1a End-to-End Smoke

**Files:**
- Create: `docs/acceptance/wave1a-first-real-use.md`
- Optionally create script under `scripts/acceptance/` only if repeated automation is needed

**Steps:**

1. Start Ditto backend.
2. Run EOD or publish-signals for a selected ETF strategy.
3. Confirm `/api/v1/trade/daily-decision?strategy_id=<id>` returns non-empty signals or explicit readiness blockers.
4. Start ditto-app with `VITE_USE_MOCK=false`.
5. Capture the visible frontend state: latest signal date, signal count, positions/deviation state.
6. Document any missing real-data blockers.
7. Run backend `pixi run -e dev check`.
8. Run frontend `bun run check`.
9. Commit acceptance evidence:

```bash
git add docs/acceptance/wave1a-first-real-use.md
git commit -m "docs: add wave1a first real use evidence"
```

**Acceptance:**

- There is a human-readable evidence file proving the first real-use path.
- If blocked, the file names exact blockers rather than pretending success.

## 5. Wave 1b: Trust and Action

Wave 1b begins only after Wave 1a has acceptance evidence.

### Task 6: A0b Frontend Write Paths

**Detailed Reference:** A0.2 in `docs/plans/2026-06-24-wave1-a0-frontend-backend-wiring.md`

**Scope:**

- `POST /trade/fills`
- `PUT /trade/intents/{id}/status`
- query invalidation for daily decision report, positions, deviation, P&L

**Acceptance:**

- User can record a manual fill from the UI.
- Deviation updates from backend state after refetch.
- `bun run check` passes.

### Task 7: B0 Portfolio Optimizer V1

**Detailed Reference:** `docs/plans/2026-06-24-wave1-b0-portfolio-optimizer.md`

**Scope Adjustment:**

Implement optimizer v1 in this order:

1. `DiagonalVolCovariance`
2. `MeanVarianceAllocator` long-only min-vol with max weight and cash target
3. fallback to `InverseVolAllocator`
4. application template wiring for one selected ETF workflow

Defer risk parity, Black-Litterman, and broad industry constraints unless V1b requires them.

**Dependency Decision:**

`cvxpy` must be explicitly approved before implementation. If not approved, implement a no-new-dependency min-vol/inverse-vol hybrid and keep cvxpy for Wave 1c.

**Acceptance:**

- Optimizer implements existing `WeightAllocator`.
- Portfolio package keeps zero data dependency.
- Selected workflow can produce target weights with explanation/fallback metadata.

## 6. Wave 1c: Research Credibility

### Task 8: B1 Volume-Constrained Fills

**Detailed Reference:** `docs/plans/2026-06-24-wave1-b1-volume-constrained-fills.md`

**Scope:**

- allow partial fills in brokerage
- add participation-rate cap to continuous auction fill path
- keep `fill_mode` compatibility switch
- re-record golden only after reviewing metric deltas

**Acceptance:**

- Backtest no longer assumes unlimited volume for large orders.
- Reproducibility tests remain stable.
- Golden updates include before/after evidence.

**Implementation Evidence (2026-07-01):**

- Added partial-fill support in `BacktestBrokerage._build_fill_event`; fill events now use the fill model's actual `filled_quantity` and reject only non-positive/over-leaves quantities.
- Added continuous-auction participation cap in `AShareFillModel`; `participation_rate=0` remains the unlimited-volume compatibility path.
- Wired `BacktestServiceConfig.participation_rate` and `fill_mode` through the backtest flow and published-runtime builder; `fill_mode="all_or_nothing"` injects `participation_rate=0`.
- RED observed:
  - `pixi run -e dev pytest packages/backtest/tests/unit/simulation/test_brokerage_unit.py -k partial -q --no-cov` failed on the old all-or-nothing guard.
  - `pixi run -e dev pytest packages/backtest/tests/unit/simulation/test_fill_model_unit.py -k 'participation_rate or participation_cap or zero_volume or auction_volume_cap' -q --no-cov` failed because `AShareFillModel` had no participation-rate parameter.
  - Config/runtime/flow tests failed on missing config fields and SimpleFillModel runtime injection.
- GREEN verification:
  - `pixi run -e dev pytest packages/backtest/tests/unit/simulation/test_fill_model_unit.py packages/backtest/tests/unit/simulation/test_brokerage_unit.py packages/application/tests/unit/process/strategy/test_backtest_service_unit.py packages/application/tests/unit/process/strategy/test_backtest_runtime_builder_unit.py packages/apps/tests/unit/jobs/flows/test_backtest_flow_unit.py -q --no-cov` -> 159 passed.
  - `pixi run -e dev type packages/backtest/src packages/application/src packages/apps/src` -> 0 errors.
  - `pixi run -e dev pytest packages/backtest/tests/integration/test_golden_baseline.py packages/backtest/tests/integration/test_reproducibility.py -q --no-cov` -> 17 passed after snapshot review.
- Golden deltas reviewed before re-record:
  - 3-day ETF rotation final NAV `999954.2841199999 -> 998136.3701199999`; annualized return `3.2494 -> -15.8138`; aggregated trades `3 -> 2`.
  - 5-day ETF rotation final NAV `1001160.0580472726 -> 1040636.1681199998`; annualized return `9.6266 -> 1169.0820`; aggregated trades `8 -> 5`.
  - 3-day trend swing final NAV unchanged at `992355.3246009998`; annualized return `-60.5127 -> -59.5067`; max drawdown `-0.7347 -> -1.6824`.

### Task 9: B3b Full RC1 Promotion

**Detailed Reference:** full `docs/plans/2026-06-24-wave1-b3-real-data-promotion.md`

**Scope:**

- promote full required dataset set
- run `rc1_real_data_acceptance.py --real-data --require-promoted`
- record governance evidence

**Acceptance:**

- Full RC1 hard gate returns 0 in the real environment.
- No evidence is fabricated.

### Task 10: Attribution V1

**Files:**
- Modify: `packages/features/src/ditto_features/evaluation/metrics/attribution.py`
- Add tests under `packages/features/tests/unit/evaluation/`
- Optionally expose through daily decision report only after backend contract is stable

**Scope:**

- Replace placeholder-like interaction/timing semantics with a conservative factor contribution report.
- Keep Brinson/Barra depth for later if data is not ready.

**Acceptance:**

- User can answer at least "which positions/factors drove the result" without relying on hard-coded residual attribution.

**Implementation Evidence (2026-07-01):**

- Replaced residual-style timing attribution with conservative semantics: `timing_return=0.0` and `interaction_return=0.0` unless a dedicated model is implemented.
- Added `AttributionContribution` and `PerformanceAttributionResult.contributions` for quantile/factor-sleeve contribution reporting. Contributions are annualized, observation-weighted, sorted by absolute impact, and sum back to `total_return`.
- RED observed: `pixi run -e dev pytest packages/features/tests/unit/evaluation/test_evaluation_attribution_unit.py -q --no-cov` failed on missing `contributions` and old residual `timing_return`.
- GREEN verification:
  - `pixi run -e dev pytest packages/features/tests/unit/evaluation/test_evaluation_attribution_unit.py packages/features/tests/unit/evaluation/test_report_builder_unit.py packages/features/tests/unit/evaluation/test_derived_types_and_fama_boundary_unit.py -q --no-cov` -> 76 passed.
  - `pixi run -e dev type packages/features/src` -> 0 errors.
- Scope note: v1 explains factor/quantile sleeves in the existing factor evaluation pipeline. Position-level Brinson/Barra-style attribution remains deferred.

## 7. Wave 2: AI and Paper Operating Loop

Wave 2 is not part of first real use.

### Candidate Work

- Read-only AI copilot over daily decision artifacts.
- Paper account lifecycle view.
- Reconciliation repair approval UX.
- Research agent for supervised hypothesis -> expression -> evaluation -> report.

### AI Boundary

AI agents may read, explain, compare, and draft. They may not submit live orders or write directly to stores. Any write must pass existing command handlers and approval paths.

## 8. Global Quality Gates

### Backend Gates

Run before each backend PR:

```bash
pixi run -e dev check
pixi run -e dev arch-check
```

Expected:

- ruff passes
- format clean
- basedpyright has 0 errors and 0 warnings
- fast tests pass
- import-linter contracts kept
- architecture smell check passes

### Frontend Gates

Run before each ditto-app PR:

```bash
bun run check
```

Expected:

- Biome passes
- TypeScript passes
- Vitest passes
- no `any`, `@ts-ignore`, or inline style regressions

### PR Size Gate

Each PR should target one task or one small vertical slice. Avoid combining B0/B1/A0 in one PR.

## 9. Final Definition of Done

### Wave 1a DoD

- EOD can publish signal packages.
- Launch dataset readiness is explicit.
- `/trade/daily-decision` or equivalent backend contract exists.
- ditto-app can show the daily decision cockpit from real backend data with MSW disabled.
- Acceptance evidence exists in `docs/acceptance/wave1a-first-real-use.md`.

### Wave 1b DoD

- User can record a manual fill from the frontend.
- Deviation updates from backend state.
- One optimizer-backed target portfolio path exists or a documented fallback is in place.

### Wave 1c DoD

- Volume-constrained fills are in the backtest path.
- Full RC1 promotion evidence is recorded.
- Basic attribution can support daily review.

## 10. Work Not In Wave 1

- Real broker live trading.
- Autonomous trading agents.
- Multi-asset global expansion.
- Full OpenBB-style workspace clone.
- Intraday data/signals unless explicitly promoted to Wave 2.
- Deep RL or broad AutoML.
- Large new execution/reconciliation matrices unrelated to daily cockpit use.
