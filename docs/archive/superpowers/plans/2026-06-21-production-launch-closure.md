# Production Launch Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close backend launch gaps for daily A-share stocks, ETFs, macro data, stock selection, research analysis, and manual signal workflows without expanding scope to frontend or live broker execution.

**Architecture:** Keep the existing 12-package boundaries. Acceptance orchestration lives in `scripts/acceptance`, CLI/API entry points stay in `packages/apps`, promotion decisions continue through application command handlers and data-owned promotion stores, and strategy/research quality controls remain in `strategy`, `features`, `application`, and `analysis` without production packages importing `analysis`.

**Tech Stack:** Python 3.13, pixi, pytest, Polars, orjson, SQLite stores, Typer CLI, FastAPI routes, Tushare source adapters, FRED source adapter, existing catalog/promotion/maturity infrastructure.

---

## Launch Scope

This plan covers backend launch readiness only:

- A-share stocks, ETFs, indexes, and macro indicators at daily frequency.
- Research/backtest production readiness.
- Stock selection, factor evaluation, portfolio target generation, and manual trading signal package flow.
- Real-data acceptance with Tushare and FRED where credentials are available.
- Dataset promotion governance and fail-closed production gates.

This plan excludes:

- Frontend implementation.
- Real broker automated execution.
- Intraday data.
- Multi-asset expansion outside stock, ETF, index, and macro launch scope.

## Required Launch Dataset Set

The release gate must treat these datasets as required:

- `stock_basic`
- `stock_daily`
- `stock_status`
- `balance_sheet`
- `income_statement`
- `cash_flow`
- `valuation_metrics`
- `etf_basic`
- `etf_daily`
- `index_basic`
- `index_daily`
- `adj_factor`
- `fund_adj`
- `macro_indicators`

Industry mapping must be validated through the existing metadata/industry read path used by stock selection, even if the exact storage identifier differs from the market/fundamental dataset names above.

## Success Criteria

Release is accepted only when all conditions hold:

- `pixi run -e dev check` exits 0.
- Targeted golden tests pass:
  `packages/apps/tests/integration/test_golden_e2e.py`,
  `packages/apps/tests/integration/test_stock_selection_golden_e2e.py`,
  `packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py`.
- RC acceptance exits 0 only when every launch dataset is promoted or otherwise admitted by persisted maturity override.
- RC acceptance fails when a required launch dataset is `experimental`, `blocked`, missing catalog storage URI, missing schema hash, missing row count, or stale against its freshness SLA.
- Real-data E2E exercises both FRED macro PIT behavior and Tushare stock/ETF/fundamental/valuation/industry ingestion where credentials are configured.
- Stock selection runs from catalog-backed data and emits ranked candidates, target weights, reasons, backtest metrics, and a persisted signal package readable through the existing trade signal read path.
- Manual fill recording recomputes positions and deviation report in the same acceptance lane.
- Production stock-selection factors are either verified as safe for current expression codegen or blocked from production use.

## File Map

- Modify `scripts/acceptance/rc1_real_data_acceptance.py`: add business-level validation of maturity status, promotion status, catalog asset evidence, freshness, targeted real-data coverage, and signal/fill evidence.
- Create `scripts/acceptance/rc1_requirements.py`: define launch dataset list and reusable validation result helpers for the acceptance script.
- Create `scripts/acceptance/test_rc1_requirements.py`: unit tests for acceptance validators.
- Modify `packages/apps/tests/e2e/test_real_data_pipeline.py`: expand from FRED-only checks to full real-data pipeline checks, while preserving skip behavior when credentials are unavailable.
- Create `packages/apps/tests/e2e/test_real_data_stock_selection_pipeline.py`: catalog-backed Tushare-to-stock-selection-to-signal test with a small configured universe.
- Modify `packages/apps/src/ditto_apps/cli/commands/ops.py`: expose any missing JSON/readable operations needed by acceptance without duplicating promotion policy.
- Modify `packages/application/src/ditto_application/queries/promotion_evidence.py`: add evidence fields only when a field is missing from existing read models; do not decide promotion readiness here.
- Modify `packages/application/tests/unit/queries/test_promotion_evidence_unit.py`: cover evidence rows used by acceptance.
- Modify `packages/application/tests/unit/process/strategy/test_backtest_runtime_builder_unit.py`: assert launch-scope stock datasets run without research opt-in only after persisted maturity promotion.
- Modify `packages/application/tests/unit/process/strategy/test_strategy_slice_builder_unit.py`: mirror maturity behavior for strategy slice construction.
- Create `packages/features/tests/unit/test_production_factor_guard_unit.py`: production factor guard tests for unsafe cross-sectional/time-series nesting.
- Create or modify the production factor registry location discovered during implementation under `packages/features` or `packages/strategy`; keep registry ownership with the package that already owns factor definitions.
- Modify `packages/strategy/src/ditto_strategy/alpha/templates/stock_selection_trend.py`: emit reason details only if existing strategy contracts support this locally; otherwise add the reason DTO in application mapping instead.
- Modify `packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py`: extend persisted signal assertions to include reason payload, target weight, and latest-readable contract.
- Create `packages/application/tests/integration/test_manual_signal_fill_deviation_e2e.py`: signal package -> fill -> position -> deviation integration lane.
- Modify `docs/acceptance/rc1-release-checklist.md`: align checklist with the new hard gates.
- Modify `docs/operations/dataset-promotion.md`: add exact launch dataset evidence procedure.

---

## Phase 0: Baseline and Worktree Hygiene

### Task 0.1: Capture Baseline

**Files:**
- Read: `CLAUDE.md`
- Read: `docs/architecture/agent-context-pack.md`
- Read: `docs/architecture/boundaries-and-abstraction-standards.md`
- Read: `docs/acceptance/rc1-release-checklist.md`
- Read: `artifacts/acceptance/rc1-report.json`

- [ ] **Step 1: Confirm working tree state**

Run:

```bash
git status --short
```

Expected: note existing unrelated changes and do not revert them.

- [ ] **Step 2: Run full baseline gate**

Run:

```bash
pixi run -e dev check
```

Expected: exit 0. Record the exact pass count and xfail count in the task notes.

- [ ] **Step 3: Run targeted goldens**

Run:

```bash
pixi run -e dev pytest \
  packages/apps/tests/integration/test_golden_e2e.py \
  packages/apps/tests/integration/test_stock_selection_golden_e2e.py \
  packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py \
  -q --no-cov
```

Expected: exit 0 with 8 passing tests.

- [ ] **Step 4: Record current RC false-positive evidence**

Run:

```bash
pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py \
  --real-data \
  --require-promoted \
  --output artifacts/acceptance/rc1-before-hard-gates.json
```

Expected: current behavior may exit 0 even when maturity status includes blocked datasets. Preserve the output as before-state evidence.

---

## Phase 1: RC Acceptance Must Fail on Business Gaps

### Task 1.1: Add Launch Requirement Definitions

**Files:**
- Create: `scripts/acceptance/rc1_requirements.py`
- Test: `scripts/acceptance/test_rc1_requirements.py`

- [ ] **Step 1: Write failing validator tests**

Create `scripts/acceptance/test_rc1_requirements.py` with tests that cover:

```python
from scripts.acceptance.rc1_requirements import (
    LAUNCH_DATASETS,
    validate_maturity_status,
)


def test_launch_dataset_list_contains_stock_etf_macro_requirements() -> None:
    assert "stock_daily" in LAUNCH_DATASETS
    assert "valuation_metrics" in LAUNCH_DATASETS
    assert "etf_daily" in LAUNCH_DATASETS
    assert "macro_indicators" in LAUNCH_DATASETS


def test_validate_maturity_status_rejects_blocked_dataset() -> None:
    payload = {
        "datasets": [
            {
                "dataset": "stock_daily",
                "dataset_maturity": "experimental",
                "dataset_promotion_status": "blocked",
                "catalog_storage_uri": "sqlite:///market.db",
                "catalog_schema_hash": "abc",
                "catalog_row_count": 10,
                "catalog_freshness_status": "fresh",
            }
        ]
    }

    result = validate_maturity_status(payload, required_datasets=("stock_daily",))

    assert not result.ok
    assert result.failures == (
        "stock_daily promotion status is blocked",
        "stock_daily maturity is experimental",
    )


def test_validate_maturity_status_accepts_promoted_fresh_dataset() -> None:
    payload = {
        "datasets": [
            {
                "dataset": "stock_daily",
                "dataset_maturity": "initial-focus",
                "dataset_promotion_status": "ready",
                "catalog_storage_uri": "sqlite:///market.db",
                "catalog_schema_hash": "abc",
                "catalog_row_count": 10,
                "catalog_freshness_status": "fresh",
            }
        ]
    }

    result = validate_maturity_status(payload, required_datasets=("stock_daily",))

    assert result.ok
    assert result.failures == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pixi run -e dev pytest scripts/acceptance/test_rc1_requirements.py -q
```

Expected: fail because `scripts.acceptance.rc1_requirements` does not exist.

- [ ] **Step 3: Implement `rc1_requirements.py`**

Create a small module with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


LAUNCH_DATASETS: tuple[str, ...] = (
    "stock_basic",
    "stock_daily",
    "stock_status",
    "balance_sheet",
    "income_statement",
    "cash_flow",
    "valuation_metrics",
    "etf_basic",
    "etf_daily",
    "index_basic",
    "index_daily",
    "adj_factor",
    "fund_adj",
    "macro_indicators",
)


ACCEPTED_PROMOTION_STATUSES: frozenset[str] = frozenset({"ready", "promoted"})
ACCEPTED_MATURITIES: frozenset[str] = frozenset({"initial-focus", "stable"})
ACCEPTED_FRESHNESS: frozenset[str] = frozenset({"fresh", "not_applicable"})


@dataclass(frozen=True)
class RequirementValidation:
    ok: bool
    failures: tuple[str, ...]


def _dataset_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("datasets")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    rows = payload.get("ingestion_status")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def validate_maturity_status(
    payload: dict[str, Any],
    *,
    required_datasets: tuple[str, ...] = LAUNCH_DATASETS,
) -> RequirementValidation:
    rows_by_dataset = {
        str(row.get("dataset")): row
        for row in _dataset_rows(payload)
        if row.get("dataset") is not None
    }
    failures: list[str] = []
    for dataset in required_datasets:
        row = rows_by_dataset.get(dataset)
        if row is None:
            failures.append(f"{dataset} missing from maturity status")
            continue

        promotion_status = str(row.get("dataset_promotion_status") or "")
        maturity = str(row.get("dataset_maturity") or "")
        freshness = str(row.get("catalog_freshness_status") or "")
        storage_uri = row.get("catalog_storage_uri")
        schema_hash = row.get("catalog_schema_hash")
        row_count = row.get("catalog_row_count")

        if promotion_status not in ACCEPTED_PROMOTION_STATUSES:
            failures.append(f"{dataset} promotion status is {promotion_status or 'missing'}")
        if maturity not in ACCEPTED_MATURITIES:
            failures.append(f"{dataset} maturity is {maturity or 'missing'}")
        if not storage_uri:
            failures.append(f"{dataset} catalog storage uri is missing")
        if not schema_hash:
            failures.append(f"{dataset} catalog schema hash is missing")
        if row_count is None or int(row_count) <= 0:
            failures.append(f"{dataset} catalog row count is missing or zero")
        if freshness not in ACCEPTED_FRESHNESS:
            failures.append(f"{dataset} freshness is {freshness or 'missing'}")

    return RequirementValidation(ok=not failures, failures=tuple(failures))
```

- [ ] **Step 4: Run validator tests**

Run:

```bash
pixi run -e dev pytest scripts/acceptance/test_rc1_requirements.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add scripts/acceptance/rc1_requirements.py scripts/acceptance/test_rc1_requirements.py
git commit -m "test: add rc1 launch requirement validation"
```

### Task 1.2: Wire Requirement Validation into RC Acceptance

**Files:**
- Modify: `scripts/acceptance/rc1_real_data_acceptance.py`
- Test: `scripts/acceptance/test_rc1_requirements.py`

- [ ] **Step 1: Add failing acceptance-result test**

Extend `scripts/acceptance/test_rc1_requirements.py` with a test for the function that will parse maturity status command output:

```python
from scripts.acceptance.rc1_requirements import validate_maturity_status_from_stdout


def test_validate_maturity_status_from_stdout_rejects_truncated_or_invalid_json() -> None:
    result = validate_maturity_status_from_stdout("not json")

    assert not result.ok
    assert result.failures == ("maturity status stdout is not valid JSON",)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pixi run -e dev pytest scripts/acceptance/test_rc1_requirements.py::test_validate_maturity_status_from_stdout_rejects_truncated_or_invalid_json -q
```

Expected: fail because the function does not exist.

- [ ] **Step 3: Implement stdout parsing**

Add to `scripts/acceptance/rc1_requirements.py`:

```python
import orjson


def validate_maturity_status_from_stdout(stdout: str) -> RequirementValidation:
    try:
        payload = orjson.loads(stdout)
    except orjson.JSONDecodeError:
        return RequirementValidation(
            ok=False,
            failures=("maturity status stdout is not valid JSON",),
        )
    if not isinstance(payload, dict):
        return RequirementValidation(
            ok=False,
            failures=("maturity status stdout JSON is not an object",),
        )
    return validate_maturity_status(payload)
```

- [ ] **Step 4: Change acceptance aggregation**

In `scripts/acceptance/rc1_real_data_acceptance.py`, after command execution, inspect the `maturity-status` command result when `--require-promoted` is enabled. Append business validation failures to the report payload and set top-level `passed` to false when validation fails. Use `orjson` if the script already uses it; otherwise import it through `rc1_requirements.py`.

Required behavior:

```python
from scripts.acceptance.rc1_requirements import validate_maturity_status_from_stdout


business_failures: list[str] = []
for result in results:
    if result.name == "maturity-status":
        validation = validate_maturity_status_from_stdout(result.stdout)
        business_failures.extend(validation.failures)

payload["business_failures"] = business_failures
payload["passed"] = all(result.passed for result in results) and not business_failures
```

- [ ] **Step 5: Run unit tests**

Run:

```bash
pixi run -e dev pytest scripts/acceptance/test_rc1_requirements.py -q
```

Expected: pass.

- [ ] **Step 6: Run RC acceptance against current blocked state**

Run:

```bash
pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py \
  --require-promoted \
  --output artifacts/acceptance/rc1-hard-gate-negative.json
```

Expected: exit non-zero or produce `"passed": false` with `business_failures` explaining blocked or missing launch datasets. If the current command exits non-zero, preserve the report and continue.

- [ ] **Step 7: Commit**

Run:

```bash
git add scripts/acceptance/rc1_real_data_acceptance.py scripts/acceptance/rc1_requirements.py scripts/acceptance/test_rc1_requirements.py
git commit -m "fix: fail rc1 acceptance on unmet launch requirements"
```

---

## Phase 2: Real-Data E2E Must Cover Tushare and FRED

### Task 2.1: Split FRED PIT Test from Full Real-Data Pipeline Semantics

**Files:**
- Modify: `packages/apps/tests/e2e/test_real_data_pipeline.py`

- [ ] **Step 1: Rename docstring expectations**

Update the module docstring so it accurately states that existing tests validate FRED realtime PIT only. Keep the current two FRED tests unchanged except for wording.

- [ ] **Step 2: Run existing FRED e2e when credentials are available**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/e2e/test_real_data_pipeline.py -m e2e --no-cov -q
```

Expected: pass if `FRED_API_KEY` or keyring `fred/api_key` is configured; otherwise skip with the existing skip reason.

- [ ] **Step 3: Commit wording correction**

Run:

```bash
git add packages/apps/tests/e2e/test_real_data_pipeline.py
git commit -m "docs: clarify fred-only real data e2e scope"
```

### Task 2.2: Add Catalog-Backed Tushare Pipeline E2E

**Files:**
- Create: `packages/apps/tests/e2e/test_real_data_stock_selection_pipeline.py`
- Modify only if needed: `packages/apps/tests/e2e/conftest.py`

- [ ] **Step 1: Write failing/skipping test skeleton**

Create a test module that:

- Reads Tushare token from keyring `tushare/token` or `TUSHARE_TOKEN`.
- Skips when token is unavailable.
- Uses a small fixed universe such as three liquid A-share instruments.
- Uses a short fixed window such as 2024-01-02 through 2024-03-29.
- Requires catalog-backed write/read rather than in-memory provider.
- Asserts non-empty stock daily bars, valuation rows, and industry mapping.

Test names:

```python
def test_tushare_catalog_backed_market_and_fundamental_fetch() -> None: ...
def test_tushare_catalog_backed_stock_selection_to_signal_package() -> None: ...
```

- [ ] **Step 2: Run skeleton**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/e2e/test_real_data_stock_selection_pipeline.py -m e2e --no-cov -q
```

Expected: skip without Tushare token, or fail on missing catalog-backed pipeline helpers.

- [ ] **Step 3: Implement through existing public CLI/application paths**

Use existing ingestion CLI/API paths. Do not import storage internals into the test. The test may invoke app CLI commands with `CliRunner` if that is the established pattern in apps tests; otherwise use application facades already exposed to apps tests.

The test must validate these facts:

- Ingested market data has at least one row per requested instrument.
- Catalog status exposes storage URI, schema hash, row count, and freshness for `stock_daily`.
- Fundamental/valuation data is readable by the same application-facing path used by stock selection.
- Industry classification snapshot is available for selected instruments.
- Stock selection can run without `allow_experimental_data=True` only after promotion override is present in the test fixture.

- [ ] **Step 4: Add signal package assertion**

Extend the test to publish the latest stock-selection target as a signal package and read it back through the same path used by `/trade/signals/latest`. Assert:

- At least one `BUY` or rebalance intent exists.
- Every intent has instrument ID, target weight, signal date, and source run ID.
- Latest signal response is stable when read twice.

- [ ] **Step 5: Run full new e2e**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/e2e/test_real_data_stock_selection_pipeline.py -m e2e --no-cov -q
```

Expected: pass with Tushare token, skip without token.

- [ ] **Step 6: Commit**

Run:

```bash
git add packages/apps/tests/e2e/test_real_data_stock_selection_pipeline.py
git commit -m "test: add tushare catalog backed stock selection e2e"
```

### Task 2.3: Require Full Real-Data Coverage in RC Acceptance

**Files:**
- Modify: `scripts/acceptance/rc1_real_data_acceptance.py`
- Modify: `scripts/acceptance/test_rc1_requirements.py`

- [ ] **Step 1: Add command manifest assertion test**

Write a test that calls `_commands(real_data=True, require_promoted=True)` and asserts the command list contains:

- FRED PIT e2e file.
- Tushare stock-selection e2e file.
- Maturity status command.

- [ ] **Step 2: Run test to verify current failure**

Run:

```bash
pixi run -e dev pytest scripts/acceptance/test_rc1_requirements.py -q
```

Expected: fail because `_commands` only includes `test_real_data_pipeline.py`.

- [ ] **Step 3: Modify command list**

Add the new e2e file to the `real-data-e2e` command:

```bash
pytest \
  packages/apps/tests/e2e/test_real_data_pipeline.py \
  packages/apps/tests/e2e/test_real_data_stock_selection_pipeline.py \
  -m e2e \
  --no-cov
```

- [ ] **Step 4: Run command manifest test**

Run:

```bash
pixi run -e dev pytest scripts/acceptance/test_rc1_requirements.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add scripts/acceptance/rc1_real_data_acceptance.py scripts/acceptance/test_rc1_requirements.py
git commit -m "test: require full real data e2e in rc1 acceptance"
```

---

## Phase 3: Dataset Promotion Closure

### Task 3.1: Generate Evidence for Every Launch Dataset

**Files:**
- Modify: `docs/operations/dataset-promotion.md`
- Outputs: `artifacts/promotion/<dataset>/*.md` or existing configured data-root promotion evidence path

- [ ] **Step 1: Run promotion collection for each launch dataset**

Run one command per dataset:

```bash
pixi run -e dev python -m ditto_apps.cli.main ops promotion-collect stock_basic
pixi run -e dev python -m ditto_apps.cli.main ops promotion-collect stock_daily
pixi run -e dev python -m ditto_apps.cli.main ops promotion-collect stock_status
pixi run -e dev python -m ditto_apps.cli.main ops promotion-collect balance_sheet
pixi run -e dev python -m ditto_apps.cli.main ops promotion-collect income_statement
pixi run -e dev python -m ditto_apps.cli.main ops promotion-collect cash_flow
pixi run -e dev python -m ditto_apps.cli.main ops promotion-collect valuation_metrics
pixi run -e dev python -m ditto_apps.cli.main ops promotion-collect etf_basic
pixi run -e dev python -m ditto_apps.cli.main ops promotion-collect etf_daily
pixi run -e dev python -m ditto_apps.cli.main ops promotion-collect index_basic
pixi run -e dev python -m ditto_apps.cli.main ops promotion-collect index_daily
pixi run -e dev python -m ditto_apps.cli.main ops promotion-collect adj_factor
pixi run -e dev python -m ditto_apps.cli.main ops promotion-collect fund_adj
pixi run -e dev python -m ditto_apps.cli.main ops promotion-collect macro_indicators
```

Expected: each command exits 0 and writes objective evidence. `needs_review` is acceptable at collection time.

- [ ] **Step 2: Document reviewer inputs**

Update `docs/operations/dataset-promotion.md` with the launch dataset list and the evidence required for each criterion:

- PIT/replay or non-PIT justification.
- Runtime owner.
- Freshness SLA.
- Source failover policy.
- Catalog-backed runtime/read-model test evidence.

- [ ] **Step 3: Commit docs**

Run:

```bash
git add docs/operations/dataset-promotion.md
git commit -m "docs: define launch dataset promotion evidence procedure"
```

### Task 3.2: Submit Promotion Reviews Through Existing Handler

**Files:**
- Use existing CLI/API only.
- Do not modify source unless a missing CLI option blocks submission.

- [ ] **Step 1: Submit passed evidence for one dataset in a test/staging data root**

Run:

```bash
pixi run -e dev python -m ditto_apps.cli.main ops promotion-submit stock_daily --approve
```

Expected: handler records evidence and writes maturity promotion override only when all criteria are passed.

- [ ] **Step 2: Verify status**

Run:

```bash
pixi run -e dev python -m ditto_apps.cli.main ops status --json
```

Expected: `stock_daily` has accepted maturity and promotion status, plus catalog freshness/storage/schema evidence.

- [ ] **Step 3: Repeat for all launch datasets**

Run `promotion-submit <dataset> --approve` for each launch dataset after verifying collected evidence is accurate.

- [ ] **Step 4: Preserve final status report**

Run:

```bash
pixi run -e dev python -m ditto_apps.cli.main ops status --json > artifacts/acceptance/launch-dataset-status.json
```

Expected: JSON includes no blocked launch-scope dataset.

---

## Phase 4: Production Factor Safety and Selection Quality

### Task 4.1: Add Production Guard for Unsafe Nested Factors

**Files:**
- Create: `packages/features/tests/unit/test_production_factor_guard_unit.py`
- Modify: production factor registry location discovered under `packages/features/src` or `packages/strategy/src`

- [ ] **Step 1: Write failing tests**

Create tests asserting:

- A factor expression containing `cs_rank(ts_mean(...))` is rejected for production unless materialized intermediate columns are used.
- A simple cross-sectional factor like `cs_zscore(roe)` is allowed.
- A simple time-series factor materialized before cross-sectional ranking is allowed only when the registry marks the intermediate as materialized.

- [ ] **Step 2: Run tests**

Run:

```bash
pixi run -e dev pytest packages/features/tests/unit/test_production_factor_guard_unit.py -q
```

Expected: fail because guard does not exist.

- [ ] **Step 3: Implement guard in owning package**

Add a small pure function such as:

```python
def validate_production_factor_expression(expression: str) -> None:
    unsafe_patterns = ("cs_rank(ts_", "cs_zscore(ts_", "cs_demean(ts_")
    if any(pattern in expression.replace(" ", "") for pattern in unsafe_patterns):
        raise ValueError(
            "production factor expression nests cross-sectional and time-series "
            "operators without materialized intermediates"
        )
```

Use the codebase's existing error type if one already exists in the owning package.

- [ ] **Step 4: Wire guard into production stock-selection config loading**

When a strategy/factor config is marked production, call the guard before running backtest or signal publishing. Research paths may still run with explicit opt-in.

- [ ] **Step 5: Run guard tests and existing expression tests**

Run:

```bash
pixi run -e dev pytest \
  packages/features/tests/unit/test_production_factor_guard_unit.py \
  packages/features/tests/unit/test_expression_cross_section_crosscheck_unit.py \
  -q
```

Expected: new tests pass; existing known xfail remains xfail.

- [ ] **Step 6: Commit**

Run:

```bash
git add packages/features packages/strategy
git commit -m "fix: guard unsafe production factor expressions"
```

### Task 4.2: Emit Stock Selection Reasons

**Files:**
- Modify: `packages/strategy/src/ditto_strategy/alpha/templates/stock_selection_trend.py`
- Modify: `packages/application/src/ditto_application/processes/execution/signal_package.py`
- Test: `packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py`

- [ ] **Step 1: Add failing signal package assertions**

Extend the existing signal package E2E to assert each selected instrument includes:

- Composite score or rank.
- Main positive factor contributors.
- Main negative factor contributors.
- Industry classification when available.
- Target weight.

- [ ] **Step 2: Run test**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py -q --no-cov
```

Expected: fail because reason payload is missing or incomplete.

- [ ] **Step 3: Add reason payload at the narrowest existing boundary**

Prefer adding reason data to the application signal package mapping if strategy output already contains factor columns. Only change strategy template if the factor contribution data is not present at application mapping time.

- [ ] **Step 4: Run signal package tests**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py -q --no-cov
```

Expected: pass.

- [ ] **Step 5: Run stock-selection golden**

Run:

```bash
pixi run -e dev pytest packages/apps/tests/integration/test_stock_selection_golden_e2e.py -q --no-cov
```

Expected: pass and deterministic result remains stable.

- [ ] **Step 6: Commit**

Run:

```bash
git add packages/strategy packages/application packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py
git commit -m "feat: include stock selection reasons in signal packages"
```

---

## Phase 5: Manual Signal, Fill, Position, and Deviation E2E

### Task 5.1: Add Manual Trading Loop Integration Test

**Files:**
- Create: `packages/application/tests/integration/test_manual_signal_fill_deviation_e2e.py`
- Modify only if necessary: execution/trade application process files already owning signal/fill/deviation flow

- [ ] **Step 1: Write failing integration test**

Test flow:

1. Create a signal package with two target weights.
2. Read latest signals.
3. Record one manual fill.
4. Recompute actual position.
5. Generate deviation report.
6. Assert deviation reflects filled and unfilled targets.

- [ ] **Step 2: Run test**

Run:

```bash
pixi run -e dev pytest packages/application/tests/integration/test_manual_signal_fill_deviation_e2e.py -q
```

Expected: fail if no integration-level orchestration exists.

- [ ] **Step 3: Implement only missing orchestration**

Use existing execution DTOs, trade stores, and application handlers. Do not add broker adapters. Do not call API routes from application tests.

- [ ] **Step 4: Run integration test**

Run:

```bash
pixi run -e dev pytest packages/application/tests/integration/test_manual_signal_fill_deviation_e2e.py -q
```

Expected: pass.

- [ ] **Step 5: Add test to RC acceptance or targeted command**

If this integration test is fast and deterministic, add it to the targeted golden command in `scripts/acceptance/rc1_real_data_acceptance.py`.

- [ ] **Step 6: Commit**

Run:

```bash
git add packages/application/tests/integration/test_manual_signal_fill_deviation_e2e.py scripts/acceptance/rc1_real_data_acceptance.py
git commit -m "test: cover manual signal fill deviation loop"
```

---

## Phase 6: Research Analysis Artifacts

### Task 6.1: Standardize Factor Evaluation Report Contract

**Files:**
- Modify: factor IC CLI/report code under `packages/apps/src/ditto_apps/cli/commands/ops.py`
- Modify: application factor evaluation facade files under `packages/application/src`
- Test: existing or new tests under `packages/application/tests/unit/query` and `packages/apps/tests/unit/cli`

- [ ] **Step 1: Add report contract test**

Assert a factor evaluation report includes:

- Factor ID and version.
- Dataset/catalog identity.
- Sample period.
- Universe.
- IC and ICIR.
- Decay.
- Quantile returns.
- Long-short return.
- Turnover and cost.
- Industry or regime attribution when requested.

- [ ] **Step 2: Run test**

Run the new or modified factor evaluation test with `-q`.

Expected: fail on any missing required field.

- [ ] **Step 3: Fill missing fields using existing evaluation DTOs**

Add fields only in application-owned DTOs or report rendering. Do not import analysis package into production packages.

- [ ] **Step 4: Run factor evaluation tests**

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/query -q
```

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add packages/application packages/apps
git commit -m "feat: standardize factor evaluation report contract"
```

### Task 6.2: Add Strategy Promotion Artifact

**Files:**
- Create or modify application/reporting location discovered from existing backtest report code
- Test: integration test near existing backtest report tests

- [ ] **Step 1: Write artifact test**

Assert every production-candidate strategy report records:

- Strategy ID.
- Code version or git SHA when available.
- Data catalog identities.
- Parameter hash.
- Benchmark.
- Cost model.
- Backtest metrics.
- Factor report references.
- Recommendation status: `research`, `candidate`, `paper`, or `production`.

- [ ] **Step 2: Run test**

Expected: fail until artifact writer/renderer includes all fields.

- [ ] **Step 3: Implement artifact through existing report path**

Use the current report/audit/lineage conventions. Store artifacts under the configured artifacts/data root, not hardcoded local paths.

- [ ] **Step 4: Run report tests and targeted goldens**

Run:

```bash
pixi run -e dev pytest \
  packages/apps/tests/integration/test_stock_selection_golden_e2e.py \
  packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py \
  -q --no-cov
```

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add packages/application packages/apps
git commit -m "feat: persist strategy promotion artifacts"
```

---

## Phase 7: Portfolio and Risk Minimum Launch Controls

### Task 7.1: Enforce Launch Portfolio Constraints

**Files:**
- Modify portfolio or application portfolio construction location discovered from existing allocator code
- Test: `packages/portfolio/tests/unit` or `packages/application/tests/unit` depending on ownership

- [ ] **Step 1: Add failing constraint tests**

Assert target weights obey:

- Single instrument max weight.
- Industry max weight when industry is available.
- Minimum liquidity filter.
- ST/suspended exclusion if status data marks instrument non-tradable.
- Max turnover limit when previous holdings are supplied.

- [ ] **Step 2: Run tests**

Expected: fail on missing constraints.

- [ ] **Step 3: Implement using existing portfolio abstractions**

Keep reusable portfolio math in `portfolio`. Keep data lookups and application orchestration in `application`.

- [ ] **Step 4: Run portfolio and stock-selection tests**

Run:

```bash
pixi run -e dev pytest packages/portfolio/tests/unit packages/apps/tests/integration/test_stock_selection_golden_e2e.py -q --no-cov
```

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add packages/portfolio packages/application packages/apps/tests/integration/test_stock_selection_golden_e2e.py
git commit -m "feat: enforce launch portfolio constraints"
```

### Task 7.2: Add Minimum Risk Report

**Files:**
- Modify risk/application report code discovered from existing risk package
- Test: `packages/risk/tests/unit` and related application report tests

- [ ] **Step 1: Add failing risk report test**

Assert report includes:

- Concentration.
- Industry exposure.
- Benchmark active weight.
- Drawdown.
- VaR or CVaR where existing metrics support it.
- Stress scenario returns for at least market down and sector down scenarios.

- [ ] **Step 2: Run tests**

Expected: fail on missing report fields.

- [ ] **Step 3: Implement available metrics**

Use existing feature/risk evaluation utilities where present. Do not introduce a heavy optimizer dependency in this task.

- [ ] **Step 4: Run risk tests**

Run:

```bash
pixi run -e dev pytest packages/risk/tests/unit packages/application/tests/unit -q
```

Expected: pass.

- [ ] **Step 5: Commit**

Run:

```bash
git add packages/risk packages/application
git commit -m "feat: add minimum launch risk report"
```

---

## Phase 8: Final Release Gate and Documentation

### Task 8.1: Update RC Checklist

**Files:**
- Modify: `docs/acceptance/rc1-release-checklist.md`
- Modify: `docs/plans/2026-06-14-production-launch-roadmap.md`

- [ ] **Step 1: Update checklist with hard gates**

Checklist must state:

- Required launch datasets.
- Real-data E2E files.
- Promotion status requirements.
- Catalog evidence requirements.
- Manual signal/fill/deviation requirement.
- Production factor guard requirement.

- [ ] **Step 2: Update roadmap status**

Mark prior false-positive acceptance as superseded by hard-gate acceptance. Keep historical evidence, but do not describe it as final launch proof.

- [ ] **Step 3: Commit docs**

Run:

```bash
git add docs/acceptance/rc1-release-checklist.md docs/plans/2026-06-14-production-launch-roadmap.md
git commit -m "docs: align launch roadmap with hard gate acceptance"
```

### Task 8.2: Run Final Acceptance

**Files:**
- Output: `artifacts/acceptance/rc1-report.json`

- [ ] **Step 1: Run full check**

Run:

```bash
pixi run -e dev check
```

Expected: exit 0.

- [ ] **Step 2: Run targeted goldens**

Run:

```bash
pixi run -e dev pytest \
  packages/apps/tests/integration/test_golden_e2e.py \
  packages/apps/tests/integration/test_stock_selection_golden_e2e.py \
  packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py \
  -q --no-cov
```

Expected: exit 0.

- [ ] **Step 3: Run real-data acceptance**

Run:

```bash
pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py \
  --real-data \
  --require-promoted \
  --output artifacts/acceptance/rc1-report.json
```

Expected: exit 0 only when all business gates pass. If credentials are unavailable in CI, run in a credentialed release environment and attach the generated report.

- [ ] **Step 4: Inspect report**

Run:

```bash
python - <<'PY'
import orjson
from pathlib import Path

payload = orjson.loads(Path("artifacts/acceptance/rc1-report.json").read_bytes())
print(payload["passed"])
print(payload.get("business_failures", []))
PY
```

Expected:

```text
True
[]
```

- [ ] **Step 5: Commit final acceptance evidence if repository policy allows artifacts**

Run:

```bash
git add artifacts/acceptance/rc1-report.json
git commit -m "docs: record hard gate rc1 acceptance evidence"
```

If artifacts are intentionally untracked, do not commit them; link the generated report in release notes instead.

---

## Execution Order

1. Phase 0 baseline.
2. Phase 1 hard-gate RC acceptance.
3. Phase 2 full real-data E2E.
4. Phase 3 dataset promotion closure.
5. Phase 5 manual signal/fill/deviation loop.
6. Phase 4 production factor safety and selection reasons.
7. Phase 6 research artifacts.
8. Phase 7 portfolio/risk minimum controls.
9. Phase 8 final release gate and documentation.

Phase 4 and Phase 5 can run in parallel after Phase 1. Phase 6 and Phase 7 can run in parallel after Phase 2 if dataset promotion evidence is already moving.

## Recommended Milestones

- M1, day 2: RC acceptance correctly fails on current blocked/missing launch data.
- M2, day 5: Tushare + FRED real-data E2E exists and is included in RC acceptance.
- M3, day 8: Launch datasets have promotion evidence and status report.
- M4, day 12: Signal package, manual fill, positions, and deviation loop covered.
- M5, day 16: Production factor guard and stock-selection reason payload shipped.
- M6, day 20: Research artifacts and minimum risk report shipped.
- M7, day 22: Final hard-gate RC acceptance report generated.

## Self-Review

- Spec coverage: The plan covers RC false-positive hardening, real-data E2E expansion, dataset promotion, stock-selection quality, manual trading signal loop, research artifacts, portfolio/risk controls, and final release evidence.
- Placeholder scan: No task uses placeholder-only language. Where implementation ownership depends on existing code discovery, the task states the exact package boundary and the discovery rule to prevent architecture drift.
- Type consistency: The proposed acceptance validator uses one `RequirementValidation` dataclass and one `validate_maturity_status` function throughout. Dataset names match the launch dataset list.
