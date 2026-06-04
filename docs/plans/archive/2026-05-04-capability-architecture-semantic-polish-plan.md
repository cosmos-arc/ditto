# Capability Architecture Semantic Polish Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** 在 12 包能力架构、import-linter、architecture-smell 和全量 `pixi run -e dev check` 已通过的基础上，收口剩余的“语义归属”和“工程质感”问题：契约归位、错误层级真正使用、backtest/execution 责任边界、apps 普通代码边界、legacy storage 命名债和文档漂移。

**Architecture:** 不再重做包拆分。当前最终依赖图保持不变：`kernel` 无依赖，`platform -> kernel`，能力包只依赖下层/横向允许的明确能力，`application` 编排能力，`apps` 作为 composition root 和外部接口层。修补原则是“让源码语义匹配设计意图”，而不是为了清零表面 smell 盲目替换。

**Tech Stack:** Python 3.13, pixi, ruff, basedpyright, pytest, import-linter, custom architecture smell checker.

---

## Current Evidence

- `pixi run -e dev arch-check`: pass, 36 contracts kept, smell check pass.
- `pixi run -e dev check`: pass, 6075 passed, 25 skipped.
- Active packages are already the final 12 package set: `kernel/platform/data/features/strategy/portfolio/risk/execution/backtest/analysis/application/apps`.
- Old package names (`infra/interfaces/app/analytics/engine`) are gone from active source; remaining mentions are mostly guardrails or stale docs.
- `docs/plans/2026-05-04-architecture-polish.md` is useful, but several items need correction before execution.

## Review of `2026-05-04-architecture-polish.md`

Adopt these ideas:

- Move duplicated `details` handling from `StrategyError`, `ExecutionError`, and similar package roots into `ditto_kernel.exceptions.DittoError`.
- Add `ditto_backtest.errors` and a canonical `ditto_backtest.contracts`.
- Add canonical `ditto_analysis.contracts`.
- Replace strategy/backtest domain semantic failures with package domain errors.
- Keep risk rule violations as return values, not exceptions; use risk errors only for configuration/contract failures.

Modify these ideas before executing:

- Do not blindly delete all `__version__`. Version policy is low-priority architecture polish. Either standardize one canonical public version source or remove runtime versions intentionally. It should not block semantic boundary repair.
- Do not replace `execution/storage/sqlite/legacy/_sql.py` whitelist `ValueError`s with `OrderSubmitError` or `FillProcessingError`. Source lines 87-95 are query/input validation, not order or fill domain failures.
- Do not create `analysis/contracts.py` as a re-export barrel. Move Protocol definitions to the canonical contracts module and import them from there.
- Avoid `TYPE_CHECKING` as a cycle-hiding mechanism. If a contract currently imports an implementation for a return type, move the shared result DTO to a small owner module or make the contract generic.
- `StrategySpecError(StrategyError, ValueError)` should not be preserved indefinitely. This repo explicitly avoids long-term compatibility shims; either remove `ValueError` inheritance now or mark it as a short migration with a deletion task.

---

## Execution Rules

1. Keep one task per commit.
2. Use RED -> GREEN -> REFACTOR for source changes.
3. Do not weaken import-linter, smell checks, ruff, basedpyright, or tests.
4. Do not add long-term compatibility re-export shims.
5. Do not use `TYPE_CHECKING` to hide import cycles or architecture violations.
6. Preserve ordinary Python precondition exceptions (`ValueError`, `TypeError`, `KeyError`) where the failure is local input validation rather than a domain/business failure.
7. Before moving imports, run `rg` for all consumers and update them in the same task.

## Global Verification

Run after every task that touches imports or public APIs:

```bash
pixi run -e dev type
pixi run -e dev test --fast
pixi run -e dev arch-check
```

Run at the end:

```bash
pixi run -e dev check
```

---

## Task 0: Baseline Snapshot

**Files:**
- Read: `git status --short`
- Read: `docs/plans/2026-04-29-capability-package-architecture-design.md`
- Read: `docs/plans/2026-04-29-capability-package-architecture-implementation-plan.md`
- Read: `docs/plans/2026-05-04-architecture-polish.md`

**Steps:**

1. Confirm only intentional plan files are untracked.
2. Run `pixi run -e dev check`.
3. Capture current internal import graph for comparison.

Expected: full gate passes before semantic polish begins.

---

## Task 1: Unify Domain Error Base Behavior

**Intent:** Make custom domain errors real infrastructure, not copy-pasted shells.

**Files:**
- Modify: `packages/kernel/src/ditto_kernel/exceptions.py`
- Modify: `packages/strategy/src/ditto_strategy/errors.py`
- Modify: `packages/execution/src/ditto_execution/errors.py`
- Modify: `packages/features/src/ditto_features/errors.py`
- Modify as needed: `packages/portfolio/src/ditto_portfolio/errors.py`
- Modify as needed: `packages/risk/src/ditto_risk/errors.py`
- Modify as needed: `packages/analysis/src/ditto_analysis/errors.py`
- Add/update focused error tests in affected packages.

**Implementation:**

1. Add `DittoError.__init__(message: str, *, details: dict[str, object] | None = None, **kwargs: object)` and store merged `self.details`.
2. Keep child-specific attributes where they add domain value, for example `DerivedError.derived_id`, `AmbiguousTickerError.matches`.
3. Remove duplicated `details` merge logic from package roots.
4. Confirm existing middleware still maps `DittoError` correctly.
5. Add tests for `DittoError.details`, merged keyword details, and one domain subclass per affected package.

**Verification:**

```bash
pixi run -e dev pytest packages/kernel/tests packages/strategy/tests/unit packages/execution/tests/unit -q --no-cov
pixi run -e dev type
pixi run -e dev arch-check
```

---

## Task 2: Make Backtest Contracts and Errors First-Class

**Intent:** Backtest is a top-level capability; it should not have weaker public contracts than strategy/execution/risk.

**Files:**
- Create: `packages/backtest/src/ditto_backtest/errors.py`
- Create: `packages/backtest/src/ditto_backtest/contracts.py`
- Create if needed: `packages/backtest/src/ditto_backtest/result.py`
- Modify: `packages/backtest/src/ditto_backtest/engine.py`
- Modify: `packages/backtest/src/ditto_backtest/protocol.py`
- Modify: `packages/backtest/tests/unit/test_trading_loop_protocol_unit.py`
- Add: `packages/backtest/tests/unit/test_backtest_errors_unit.py`

**Implementation:**

1. Create `BacktestError`, `EngineConfigError`, `ReplayError`, and `SimulationError`.
2. Move `EngineResult` out of `engine.py` into a small result owner module if that is the cleanest way to avoid `contracts.py -> engine.py`.
3. Move `TradingLoop` to `contracts.py`; keep `protocol.py` only as a short-term compatibility module if removing it would be too disruptive, and add an explicit follow-up to delete it.
4. Replace backtest semantic failures:
   - missing runtime slice in `engine.py`
   - invalid step context in strategy/planning/pre-trade steps
   - replay manifest/config semantic mismatch in `replay.py`
5. Keep local type/precondition errors as built-ins when they are not domain failures.

**Verification:**

```bash
pixi run -e dev pytest packages/backtest/tests -q --no-cov
pixi run -e dev type
pixi run -e dev arch-check
```

---

## Task 3: Make Analysis Contracts Canonical

**Intent:** `analysis` owns research-facing contracts at package top level, not hidden inside one service implementation module.

**Files:**
- Create: `packages/analysis/src/ditto_analysis/contracts.py`
- Modify: `packages/analysis/src/ditto_analysis/research/catalog_service.py`
- Modify consumers of `ResearchCatalogReaderProtocol` and `ResearchCatalogWriterProtocol`.
- Add/update: analysis contract import tests.

**Implementation:**

1. Move `ResearchCatalogReaderProtocol` and `ResearchCatalogWriterProtocol` definitions into `ditto_analysis.contracts`.
2. Make `catalog_service.py` import the protocols from the contracts module.
3. Update all consumers to import from `ditto_analysis.contracts`.
4. Do not implement this as a re-export alias.

**Verification:**

```bash
rg -n "ResearchCatalog.*Protocol" packages -g "*.py"
pixi run -e dev pytest packages/analysis/tests packages/apps/tests/unit/registry -q --no-cov
pixi run -e dev type
pixi run -e dev arch-check
```

---

## Task 4: Replace Strategy Semantic ValueErrors

**Intent:** Strategy spec/template failures are strategy domain failures, not anonymous `ValueError`s.

**Files:**
- Modify: `packages/strategy/src/ditto_strategy/errors.py`
- Modify: `packages/strategy/src/ditto_strategy/alpha/specs.py`
- Modify: `packages/strategy/src/ditto_strategy/alpha/templates/stock_sector_rotation.py`
- Modify: `packages/strategy/src/ditto_strategy/alpha/templates/stock_selection_trend.py`
- Consider: `packages/strategy/src/ditto_strategy/alpha/frame.py`
- Update tests expecting `ValueError`.

**Implementation:**

1. Decide whether `StrategySpecError` immediately drops `ValueError` inheritance. Preferred final state: `class StrategySpecError(StrategyError)`.
2. Replace spec/template validation raises with `StrategySpecError`, including structured details for field/template name where useful.
3. Update catches/tests to use `StrategySpecError`.
4. Keep truly local input precondition failures as built-ins if they are not strategy semantics.

**Verification:**

```bash
pixi run -e dev pytest packages/strategy/tests -q --no-cov
pixi run -e dev type
pixi run -e dev arch-check
```

---

## Task 5: Clarify Risk Error Usage

**Intent:** Risk check outcomes should stay as explicit decisions/actions; risk exceptions should represent invalid risk configuration or contract misuse.

**Files:**
- Modify: `packages/risk/src/ditto_risk/errors.py`
- Modify if needed: risk validation modules.
- Add/update: risk error tests.
- Update docs: `packages/risk/CLAUDE.md`.

**Implementation:**

1. Do not convert normal `RiskAction`/constraint violations into exceptions.
2. Either remove unused `ConstraintViolationError`/`ExposureLimitError`/`DrawdownThresholdError`, or use them only for invalid configuration that cannot produce a meaningful decision.
3. Keep threshold range checks as `ValueError` unless a public risk config constructor needs domain error mapping.
4. Document the distinction: “risk finding = return value; risk configuration failure = exception.”

**Verification:**

```bash
pixi run -e dev pytest packages/risk/tests -q --no-cov
pixi run -e dev type
pixi run -e dev arch-check
```

---

## Task 6: Split Backtest Simulation Semantics Out of Execution

**Intent:** `execution` should own execution ports and order/fill vocabulary; `backtest` should own simulated brokerage, fill/slippage/settlement assumptions used only by simulation.

**Files to inspect first:**
- `packages/execution/src/ditto_execution/brokerage.py`
- `packages/execution/src/ditto_execution/reality/brokerage.py`
- `packages/execution/src/ditto_execution/reality/fill.py`
- `packages/execution/src/ditto_execution/reality/slippage.py`
- `packages/execution/src/ditto_execution/reality/settlement.py`
- `packages/backtest/src/ditto_backtest/engine.py`
- backtest/execution tests importing `BacktestBrokerage` or reality models.

**Implementation:**

1. Keep stable execution-side ports such as `Brokerage` / `BrokerGateway` where they represent live execution abstraction.
2. Move simulation-specific implementation (`BacktestBrokerage`, simulated fill model, simulated slippage/settlement wiring) into `ditto_backtest`.
3. Adjust `EngineLoop` and backtest builders to depend on the execution port but instantiate simulation adapters from backtest.
4. Add import-linter or smell guard preventing `ditto_execution` docs/classes from naming backtest simulation concepts.
5. Preserve behavior with characterization tests before moving code.

**Verification:**

```bash
pixi run -e dev pytest packages/backtest/tests packages/execution/tests/unit -q --no-cov
pixi run -e dev type
pixi run -e dev arch-check
```

---

## Task 7: Normalize Execution Legacy Storage Ownership

**Intent:** `execution.storage.sqlite.legacy` should not stay as a permanent junk drawer, and table names should express capability ownership.

**Files to inspect first:**
- `packages/execution/src/ditto_execution/storage/deps.py`
- `packages/execution/src/ditto_execution/storage/sqlite/legacy/signal_writer.py`
- `packages/execution/src/ditto_execution/storage/sqlite/legacy/fill_writer.py`
- `packages/execution/src/ditto_execution/storage/sqlite/legacy/position_writer.py`
- consumers in application/apps/tests.

**Implementation:**

1. Do not follow the polish doc's suggested `_sql.py` error replacement as written. Those whitelist `ValueError`s are acceptable input validation.
2. Rename or move legacy storage modules into owned concepts: orders/intents, fills, positions, reconciliation.
3. Decide whether `actual_positions` belongs in `portfolio` rather than `execution`; if yes, move persistence behind a portfolio-owned port.
4. Table rename requires an explicit migration path or a compatibility reader/writer test. If schema migration is too large for this pass, keep table names and only normalize module ownership, then open a migration follow-up.
5. Add smell check preventing new permanent modules under `storage/sqlite/legacy`.

**Verification:**

```bash
pixi run -e dev pytest packages/execution/tests packages/application/tests/unit/process/execution -q --no-cov
pixi run -e dev type
pixi run -e dev arch-check
```

---

## Task 8: Tighten Apps Boundary Outside Registry

**Intent:** `apps` may compose concrete providers in registry/container code, but ordinary routes/jobs should not import capability internals directly.

**Files to inspect first:**
- `packages/apps/src/ditto_apps/registry/**`
- `packages/apps/src/ditto_apps/api/routes/source.py`
- `packages/apps/src/ditto_apps/jobs/context.py`
- `.importlinter`
- `scripts/architecture/check_architecture_smells.py`

**Implementation:**

1. Move route-visible protocol types such as source query/fetcher needs behind `application` DTOs or ports.
2. Keep direct capability imports in registry/provider modules only.
3. For jobs, either use application facades or declare a narrow, explicit exception for task host composition code.
4. Add an architecture guard for non-registry `ditto_apps` modules importing `ditto_data`, `ditto_features`, `ditto_strategy`, `ditto_execution`, `ditto_backtest`, `ditto_analysis` internals directly.

**Verification:**

```bash
pixi run -e dev pytest packages/apps/tests -q --no-cov
pixi run -e dev type
pixi run -e dev arch-check
```

---

## Task 9: Fix Documentation Drift

**Intent:** Docs should describe the final stricter architecture, not earlier intermediate designs.

**Files:**
- `docs/architecture/boundaries-and-abstraction-standards.md`
- `packages/platform/CLAUDE.md`
- `packages/risk/CLAUDE.md`
- `packages/strategy/CLAUDE.md`
- any docs found by `rg "infra|interfaces|analytics|engine package|ditto_app|strategy/backtest -> platform|risk.*execution"`.

**Implementation:**

1. Update risk docs: risk no longer depends on execution models.
2. Update platform docs: strategy can depend on platform where current contract allows it.
3. Remove stale strategy portfolio tech-debt notes if source no longer imports portfolio.
4. Replace nonexistent symbol examples with current source-backed examples.
5. Keep guardrail mentions of old names only where they are explicitly smell-check forbidden examples.

**Verification:**

```bash
python scripts/architecture/check_architecture_smells.py --verbose
pixi run -e dev arch-check
```

---

## Task 10: Decide Version Policy

**Intent:** Resolve `__version__` inconsistency intentionally, without mixing it into domain boundary work.

**Preferred options:**

- **Option A:** Keep public `__version__`, but standardize one source of truth across packages, update commitizen config, and test metadata/runtime consistency.
- **Option B:** Remove runtime `__version__` from packages, remove commitizen `version_files`, and update app health/version endpoints to use package metadata or a build/version provider.

**Implementation notes:**

1. Treat this as low priority unless release tooling currently depends on it.
2. If choosing removal, update `packages/apps/src/ditto_apps/main.py` because it imports `ditto_kernel.__version__`.
3. Do not leave mixed `_version.py`, inline `__version__`, and package metadata versions drifting independently.

**Verification:**

```bash
rg -n "__version__|_version|version_files" pyproject.toml packages -g "*.py" -g "*.toml"
pixi run -e dev check
```

---

## Final Acceptance Criteria

- `pixi run -e dev check` exits 0.
- Backtest has canonical `errors.py` and `contracts.py`.
- Analysis contracts are defined at `ditto_analysis.contracts`, not re-exported from service modules.
- Strategy/backtest semantic failures use domain errors.
- Risk errors are either used for config/contract failure or removed; risk decisions stay return-value based.
- Execution no longer owns simulation/backtest-specific implementation names.
- `execution.storage.sqlite.legacy` is not a permanent extension point.
- Non-registry apps code no longer reaches into capability internals directly except documented narrow host-composition exceptions.
- Active architecture docs match the final source import graph.
- Version policy is explicit and consistent.
