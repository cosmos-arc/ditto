# Post Architecture Clarity Follow-up Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the completed architecture-clarity pass into an executable T0 baseline, then prepare the next capability-boundary discussion.

**Architecture:** Keep dependency direction unchanged: `interfaces -> app -> {data, analytics, engine} -> kernel`, with infra wired only through composition roots. First repair objective gates and truthfulness of observability/config docs; only then start capability-boundary and platformization design.

**Tech Stack:** Python 3.13, pixi, import-linter, basedpyright, pytest, ruff, OpenTelemetry via `ditto_infra.foundation`.

---

## Review Baseline

Verified on 2026-04-28:

- `pixi run -e dev lint-imports`: 34 contracts kept, 0 broken.
- `pixi run -e dev type`: 0 errors, 0 warnings, 0 notes.
- Targeted pytest with `-p no:cov -o addopts=''`: 353 passed.
- Targeted ruff check/format on changed architecture files: passed.

Known blockers:

- `pixi run -e dev arch-check` fails because `arch-smells` is now wired into `arch-check` while the baseline still has 5 issues.
- Default `pytest` fails before collection because `pytest-cov` imports an incomplete `coverage` namespace package with no `coverage.data`.
- Kernel `traced` markers in engine/analytics are no-op and should not be documented as real performance observability until a runtime bridge exists.
- `DQSettings.config_root` exists, but the composition provider does not inject a stable project/config root.

---

## Task 1: Make `arch-check` Executable

**Files:**
- Modify: `packages/data/src/ditto_data/storage/runtime/__init__.py`
- Modify: `packages/data/src/ditto_data/services/market_service.py`
- Modify: `packages/data/src/ditto_data/services/metadata/instrument.py`
- Modify: `packages/data/src/ditto_data/sources/tushare/tushare_source.py`
- Modify: `packages/engine/src/ditto_engine/backtest/statistics.py`
- Test: `scripts/architecture/check_architecture_smells.py`

**Step 1: Add the missing package marker**

Create an empty `packages/data/src/ditto_data/storage/runtime/__init__.py`.

**Step 2: Split only enough to get below the current gate**

Move cohesive helper groups out of the four oversized files without changing public APIs:

- `market_service.py`: move ETF/stock status convenience query helpers to a private leaf module.
- `metadata/instrument.py`: move source ticker/name-history helper methods to a private leaf module.
- `tushare_source.py`: move provider construction or grouped endpoint facade methods to private leaf modules.
- `backtest/statistics.py`: move math helpers to `statistics_helpers.py` or a private metrics leaf.

Keep the original public imports and class names stable.

**Step 3: Verify**

Run:

```bash
python scripts/architecture/check_architecture_smells.py
pixi run -e dev arch-check
pixi run -e dev type
```

Expected: smell check passes, import-linter still has 34 kept contracts, type has 0 errors.

---

## Task 2: Fix `pytest-cov` Environment Breakage

**Files:**
- Modify: `pixi.toml`
- Test: `pyproject.toml`

**Step 1: Reproduce the environment failure**

Run:

```bash
pixi run -e dev python -c "import coverage; import coverage.data"
pixi run -e dev pytest packages/data/tests/unit/quality/test_dq_settings_unit.py -q
```

Expected before fix: `ModuleNotFoundError: No module named 'coverage.data'`.

**Step 2: Add explicit coverage dependency**

Add an explicit dev dependency:

```toml
coverage = ">=7.6,<8"
```

**Step 3: Verify default pytest path**

Run:

```bash
pixi run -e dev python -c "import coverage; import coverage.data; print(coverage.__version__)"
pixi run -e dev pytest packages/data/tests/unit/quality/test_dq_settings_unit.py -q
```

Expected: pytest reaches collection and test execution without disabling cov.

---

## Task 3: Make Engine/Analytics Tracing Semantics Honest

**Files:**
- Modify: `packages/kernel/src/ditto_kernel/tracing.py`
- Modify: an app/interfaces composition root that can legally import both `ditto_kernel` and `ditto_infra.foundation`
- Modify: `docs/reviews/audit/2026-04-28-comprehensive-architecture-evaluation.md`
- Modify: `docs/reviews/audit/2026-04-28-t0-architecture-clarity-scorecard.md`
- Test: `packages/kernel/tests/unit/test_tracing_unit.py` or nearest existing kernel test location
- Test: an app/interfaces integration test for the runtime bridge

**Step 1: Decide the contract**

Use this rule:

- Kernel decorator default behavior may be no-op.
- Once a composition root installs a trace handler, `@traced` must produce real spans.
- Docs must distinguish "trace marker present" from "runtime span emitted".

**Step 2: Add a dependency-free kernel hook**

In `ditto_kernel.tracing`, add a small handler protocol and install/reset functions. The wrapper should call the installed handler if present; otherwise it keeps the current no-op behavior.

**Step 3: Wire the bridge from composition root**

In a layer allowed to import both kernel and infra, install a handler that delegates to `ditto_infra.foundation.span`.

Do not make `engine` or `analytics` import `ditto_infra`.

**Step 4: Verify**

Run:

```bash
pixi run -e dev lint-imports
pixi run -e dev pytest packages/kernel/tests packages/infra/tests/unit/observability -q
pixi run -e dev type
```

Expected: import-linter remains kept; kernel tests prove no-op default and installed-handler behavior.

---

## Task 4: Stabilize `DQSettings.config_root`

**Files:**
- Modify: `packages/infra/src/ditto_infra/foundation/config/loader.py`
- Modify: `interfaces/src/ditto_interfaces/registry/infra/config.py`
- Modify: `packages/data/src/ditto_data/quality/config.py` only if model semantics need tightening
- Test: `packages/data/tests/unit/quality/test_dq_settings_unit.py`
- Test: add provider test under `interfaces/tests` or nearest registry test location

**Step 1: Give `ConfigLoader` a stable root**

Add `config_root` to `ConfigLoader`, defaulting to `find_project_root()`, and derive `config_dir` from it.

**Step 2: Inject root into `DQSettings`**

Update `ConfigProvider.dq_settings` to pass `config_root=config_loader.config_root`.

**Step 3: Verify CWD independence**

Add a provider-level test that changes CWD to a temp directory while `ConfigLoader` points at the project/config root.

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/quality/test_dq_settings_unit.py interfaces/tests -q
pixi run -e dev type
```

Expected: DQ rules path resolution no longer depends on process CWD.

---

## Task 5: Finish Expression Contract Ownership Cleanup

**Files:**
- Modify: tests and app call sites that import expression-owned types from `ditto_analytics.materialization.contracts`
- Keep: `packages/analytics/src/ditto_analytics/materialization/contracts.py` compatibility re-export unless a breaking API change is explicitly accepted
- Test: expression/materialization/app process tests

**Step 1: Update internal imports**

Move internal app/tests imports of these types to `ditto_analytics.expression.contracts`:

- `Analysis`
- `AnalysisWarning`
- `CompileIdentity`
- `CompiledDerivedExpression`

**Step 2: Keep public compatibility explicit**

If the re-export remains, document it as a compatibility shim. Do not let new internal code import expression-owned contracts through materialization.

**Step 3: Verify**

Run:

```bash
rg -n "materialization\.contracts import \(Analysis|AnalysisWarning|CompileIdentity|CompiledDerivedExpression\)|from ditto_analytics\.materialization import \(Analysis|CompileIdentity|CompiledDerivedExpression\)" packages interfaces
pixi run -e dev pytest packages/analytics/tests/unit packages/app/tests/unit/process -q
pixi run -e dev lint-imports
```

Expected: no new internal imports from the old owner path; public shim still works where intentionally tested.

---

## Task 6: Update Architecture Truth Documents

**Files:**
- Modify: `docs/reviews/audit/2026-04-28-comprehensive-architecture-evaluation.md`
- Modify: `docs/reviews/audit/2026-04-28-t0-architecture-clarity-scorecard.md`
- Modify: `docs/architecture/boundaries-and-abstraction-standards.md`
- Modify: `docs/architecture/agent-context-pack.md`

**Step 1: Record actual gate state**

Update docs to state:

- import boundaries pass;
- `arch-check` only passes after Task 1;
- tracing is either a real runtime bridge or a semantic marker, depending on Task 3 outcome;
- DQ path handling is CWD-independent only after Task 4.

**Step 2: Add a T0 acceptance checklist**

Use command-based acceptance criteria, not subjective prose.

**Step 3: Verify docs against commands**

Run every command listed in the checklist and update any stale line.

---

## Task 7: Prepare Capability-Boundary and Platformization Review

**Files:**
- Create: `docs/plans/2026-04-28-capability-boundary-and-platformization-review-plan.md`

**Step 1: Start only after Tasks 1-6 pass**

Do not begin capability-boundary design while `arch-check`, pytest environment, DQ root, or tracing semantics are still ambiguous.

**Step 2: Scope the next review**

Cover these candidates:

- command/query separation in app process surfaces;
- plugin extension points and registry ownership;
- data source/provider capability boundaries;
- strategy runtime contracts;
- materialization/platform services;
- agent coding context and guardrails.

**Step 3: Produce candidate decisions**

For each candidate, classify it as:

- keep as-is;
- rename only;
- extract protocol;
- extract plugin interface;
- defer.

Expected output: a decision table with owner package, boundary rule, migration cost, test strategy, and first implementation slice.
