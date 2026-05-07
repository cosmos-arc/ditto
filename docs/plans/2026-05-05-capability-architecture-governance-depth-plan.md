# Capability Architecture Governance Depth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在当前 capability package 架构门禁已经全绿的基础上，收口仍然存在的治理深度问题：错误边界、外部依赖元数据、占位模块诚实度、数据治理契约、观测一致性、文档漂移和可持续门禁。

**Architecture:** 不改变 12 包能力架构，不新增产品能力，不把 analysis 报告、真实 broker gateway、OMS 或完整数据治理 UI 放进本轮。所有修改都服务于“源码事实、包元数据、自动化检查和设计意图一致”：能力包保持自治，`application` 负责编排，`apps` 负责 composition root，`platform` 只承载通用技术能力，`kernel` 只承载纯共享协议和值类型。

**Tech Stack:** Python 3.13, pixi, ruff, basedpyright, pytest, import-linter, custom architecture smell checker, AST/tomllib package metadata checks.

---

## Scope

本计划解决架构治理和遗漏，不解决产品路线：

- In scope: 错误 taxonomy、public boundary exception mapping、package metadata direct dependency parity、占位模块诚实化、最小 data catalog/lineage contracts、直接第三方 logging 收口、stale trace/doc cleanup、guardrail 测试。
- Out of scope: analysis 报告渲染、诊断工具实现、实验系统、screeners 业务能力、真实交易网关、OMS、完整数据目录存储/API、notebook 工作流。

## Current Source Evidence

Baseline already passes:

```bash
pixi run -e dev check
```

Expected current result:

```text
ruff check . -> All checks passed
basedpyright --warnings -> 0 errors, 0 warnings
pytest --fast -> 6166 passed, 25 skipped
import-linter -> 36 kept, 0 broken
Architecture smell check passed.
```

Remaining governance gaps visible in source:

- `application` public commands/queries/builders/processes still raise many built-in `ValueError`/`RuntimeError`/`KeyError` instead of `AppError` subclasses.
- `features` still has `FactorValidationError(FeaturesError, ValueError)` and `FeatureStorageError(FeaturesError, ValueError)`.
- `analysis.research` raises built-in `ValueError` for research-domain failures.
- `analysis/reports`, `analysis/diagnostics`, `analysis/experiments`, and `analysis/screeners` are honest placeholders only by comment, not by enforceable rule.
- `data` has no minimal catalog/lineage contracts for data governance ownership.
- Several non-platform packages import `loguru` directly.
- Package `pyproject.toml` files only guard internal dependencies; direct external runtime dependencies are not checked.
- `strategy` still has stale trace label `engine.alpha.pipeline.process`.
- Existing untracked May 4 plan/review drafts are partly stale and should be marked superseded, archived, or intentionally kept.

## Execution Rules

1. Use TDD: write the narrow failing test or checker first, then implement.
2. One task, one commit.
3. Do not weaken `.importlinter`, `check_architecture_smells.py`, ruff, basedpyright, or tests.
4. Do not introduce long-term compatibility re-export shims.
5. Do not use `TYPE_CHECKING` or lazy imports to hide dependency problems.
6. Preserve built-in exceptions for local Python precondition errors only; public command/query/process/builder failures should cross boundaries as `DittoError` subclasses.
7. Do not turn product-roadmap placeholders into fake implementations.

---

## Task 0: Baseline and Plan Hygiene

**Files:**
- Read: `git status --short`
- Read: `docs/plans/2026-05-04-architecture-polish.md`
- Read: `docs/plans/2026-05-04-capability-architecture-100-point-remediation-plan.md`
- Read: `docs/plans/2026-05-04-capability-architecture-semantic-polish-plan.md`
- Read: `docs/reviews/2026-05-04-capability-package-architecture-audit.md`
- Modify or archive only with user approval: stale May 4 plan/review files

**Step 1: Confirm working tree**

Run:

```bash
git status --short
```

Expected: identify untracked plan/review drafts and do not delete them without explicit approval.

**Step 2: Reproduce current green gate**

Run:

```bash
pixi run -e dev check
```

Expected: exits 0.

**Step 3: Inventory current remaining smells**

Run:

```bash
rg -n "raise ValueError|raise TypeError|raise RuntimeError|raise KeyError" \
  packages/{application,backtest,strategy,features,risk,execution,analysis}/src -g "*.py"
rg -n "from loguru|import loguru" packages/*/src -g "*.py"
rg -n "engine\.alpha|analytics spec|此模块为占位符" packages docs/architecture CLAUDE.md README.md -g "*.py" -g "*.md"
```

Expected: use this as the before-state inventory for Tasks 1-6.

**Step 4: Commit**

No commit unless plan-file hygiene is intentionally changed.

---

## Task 1: Make Application Boundary Errors Typed

**Intent:** `application` is the use-case boundary. Errors crossing commands, queries, builders, and processes should be typed `AppError` subclasses so API/CLI/middleware can map them consistently.

**Files:**
- Modify: `packages/application/src/ditto_application/exceptions.py`
- Modify: `packages/application/src/ditto_application/commands/backtest.py`
- Modify: `packages/application/src/ditto_application/commands/trade.py`
- Modify: `packages/application/src/ditto_application/commands/universe.py`
- Modify: `packages/application/src/ditto_application/commands/strategy.py`
- Modify: `packages/application/src/ditto_application/queries/derived.py`
- Modify: `packages/application/src/ditto_application/queries/market.py`
- Modify: `packages/application/src/ditto_application/queries/research.py`
- Modify: `packages/application/src/ditto_application/queries/source.py`
- Modify: `packages/application/src/ditto_application/builders/runtime_builder.py`
- Modify: `packages/application/src/ditto_application/builders/_spec_deserializer.py`
- Modify: `packages/application/src/ditto_application/processes/execution/factor_bridge.py`
- Modify as classified: other `packages/application/src/ditto_application/**` raise sites from Task 0
- Create: `packages/application/tests/unit/test_application_errors_unit.py`
- Create: `packages/apps/tests/unit/architecture/test_application_boundary_errors_unit.py`

**Step 1: RED - Add error taxonomy tests**

Create tests asserting these subclasses exist and preserve `details`:

```python
from ditto_application.exceptions import (
    AppBuilderError,
    AppCommandError,
    AppConfigurationError,
    AppError,
    AppProcessError,
    AppQueryError,
)


def test_application_errors_preserve_details() -> None:
    err = AppCommandError("bad command", command="trade")
    assert isinstance(err, AppError)
    assert err.details == {"command": "trade"}
```

Run:

```bash
pixi run -e dev pytest packages/application/tests/unit/test_application_errors_unit.py -q --no-cov
```

Expected: FAIL because subclasses do not exist yet.

**Step 2: GREEN - Add subclasses**

Add these classes to `ditto_application.exceptions`:

- `AppConfigurationError`
- `AppCommandError`
- `AppQueryError`
- `AppProcessError`
- `AppBuilderError`

Each should inherit `AppError` and rely on `DittoError.details`.

**Step 3: RED - Add boundary raise scanner**

Create `packages/apps/tests/unit/architecture/test_application_boundary_errors_unit.py`.

The scanner should parse AST under:

- `packages/application/src/ditto_application/commands`
- `packages/application/src/ditto_application/queries`
- `packages/application/src/ditto_application/builders`
- selected orchestration modules under `processes`

It should fail on `raise ValueError`, `raise RuntimeError`, and `raise KeyError` unless the file is explicitly allowlisted as a private local parser/precondition helper.

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_application_boundary_errors_unit.py -q --no-cov
```

Expected: FAIL with current offenders.

**Step 4: Migrate command/query/builder/process boundary raises**

Replace boundary failures with the most specific `AppError` subclass.

Examples:

- command validation -> `AppCommandError`
- query filter/format validation -> `AppQueryError`
- runtime assembly/config failure -> `AppBuilderError`
- process orchestration missing dependency/state -> `AppProcessError`
- user/project settings failure -> `AppConfigurationError`

Keep private helper `TypeError`/`ValueError` only when the exception is local and never crosses a public use-case boundary.

**Step 5: Update callers and tests**

Run affected tests first:

```bash
pixi run -e dev pytest packages/application/tests/unit/commands packages/application/tests/unit/queries packages/application/tests/unit/builders -q --no-cov
pixi run -e dev pytest packages/apps/tests/unit/api packages/apps/tests/unit/cli -q --no-cov
```

Expected: tests pass after expectations use `AppError` subclasses where needed.

**Step 6: Verify**

```bash
pixi run -e dev type
pixi run -e dev arch-check
```

**Step 7: Commit**

```bash
git add packages/application packages/apps/tests/unit/architecture
git commit -m "refactor: type application boundary errors"
```

---

## Task 2: Complete Capability Error Taxonomy

**Intent:** Capability packages should distinguish domain failures from local Python preconditions without compatibility-style multiple inheritance.

**Files:**
- Modify: `packages/features/src/ditto_features/errors.py`
- Modify: `packages/features/src/ditto_features/expression/compiler.py`
- Modify as classified: `packages/features/src/ditto_features/evaluation/metrics/*.py`
- Modify: `packages/strategy/src/ditto_strategy/alpha/frame.py`
- Modify: `packages/analysis/src/ditto_analysis/research/domain.py`
- Modify: `packages/analysis/src/ditto_analysis/research/artifact_service.py`
- Modify tests expecting built-in exceptions
- Create: `packages/apps/tests/unit/architecture/test_capability_error_taxonomy_unit.py`

**Step 1: RED - Add multiple-inheritance guard**

Create an AST test that fails when a capability error class inherits both a `DittoError` subclass and a built-in exception such as `ValueError`.

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_capability_error_taxonomy_unit.py -q --no-cov
```

Expected: FAIL on `FactorValidationError` and `FeatureStorageError`.

**Step 2: Remove compatibility inheritance**

Change:

```python
class FactorValidationError(FeaturesError, ValueError):
```

to:

```python
class FactorValidationError(FeaturesError):
```

Do the same for `FeatureStorageError`.

**Step 3: Migrate feature semantic errors**

Use `FactorValidationError` for expression compiler semantic failures:

- unsupported expression node
- dependency cycle

Use `EvaluationError` for public evaluation metric semantic failures. Preserve local numeric precondition `ValueError` only in private helpers if tests confirm they are not package boundary errors.

**Step 4: Migrate strategy semantic errors**

Replace `DecisionFrame` missing required columns in `packages/strategy/src/ditto_strategy/alpha/frame.py` with `StrategySpecError` or `PipelineExecutionError`, depending on whether the failure is static frame shape or runtime pipeline state.

**Step 5: Migrate analysis research semantic errors**

Replace research-domain `ValueError` in:

- `packages/analysis/src/ditto_analysis/research/domain.py`
- `packages/analysis/src/ditto_analysis/research/artifact_service.py`

with `ResearchDatasetError`, including `details` such as policy, relative path, or dataset id.

**Step 6: Verify**

```bash
pixi run -e dev pytest packages/features/tests packages/strategy/tests packages/analysis/tests -q --no-cov
pixi run -e dev type
pixi run -e dev arch-check
```

**Step 7: Commit**

```bash
git add packages/features packages/strategy packages/analysis packages/apps/tests/unit/architecture
git commit -m "refactor: complete capability error taxonomy"
```

---

## Task 3: Add External Runtime Dependency Metadata Guard

**Intent:** Package `pyproject.toml` files should declare direct runtime dependencies. Current checks cover internal `ditto-*` dependencies but not third-party imports.

**Files:**
- Modify: `scripts/architecture/check_architecture_smells.py`
- Modify: relevant `packages/*/pyproject.toml`
- Create: `packages/apps/tests/unit/architecture/test_external_package_metadata_unit.py`

**Step 1: RED - Add external dependency checker test**

Add a test that calls a new checker:

```python
from pathlib import Path

from scripts.architecture.check_architecture_smells import (
    check_external_package_metadata,
)


def test_external_runtime_dependencies_are_declared() -> None:
    assert check_external_package_metadata(Path.cwd()) == []
```

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_external_package_metadata_unit.py -q --no-cov
```

Expected: FAIL because the checker does not exist.

**Step 2: Implement precise external import scanner**

In `check_architecture_smells.py`, implement an AST scanner that:

- scans `packages/*/src/**/*.py`
- ignores stdlib, relative imports, `ditto_*` packages, and package-local modules
- maps import names to distribution names with a small explicit mapping, for example `yaml -> PyYAML`, `opentelemetry -> opentelemetry-api`
- ignores test/dev-only imports
- reports missing direct dependencies with exact package pyproject paths

Do not use a broad string grep; resolve package-local top-level modules first to avoid false positives such as `storage`, `models`, or `config`.

**Step 3: Update package pyprojects**

Run the new checker, then add only true runtime dependencies to each package `pyproject.toml`.

Expected categories:

- `platform`: logging, config, observability, cache, serialization, and HTTP dependencies it imports directly.
- `data`: data frame, serialization, HTTP/source, schema, retry, and hashing dependencies it imports directly.
- `features`: numerical/data frame/model dependencies it imports directly.
- `application` and `apps`: framework and orchestration dependencies they import directly.
- `backtest`: after Task 5, should not need `loguru` as a direct dependency.

**Step 4: Wire checker into arch-smells main**

Add `check_external_package_metadata(ROOT)` to `main()` so `pixi run -e dev arch-check` fails on future drift.

**Step 5: Verify**

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_external_package_metadata_unit.py -q --no-cov
pixi run -e dev arch-check
pixi run -e dev type
```

**Step 6: Commit**

```bash
git add scripts/architecture/check_architecture_smells.py packages/*/pyproject.toml packages/apps/tests/unit/architecture
git commit -m "test: guard external runtime dependency metadata"
```

---

## Task 4: Make Analysis Placeholders Honest and Enforced

**Intent:** Placeholder namespaces should not imply implemented capabilities. If a module exports nothing, docs and tests should say it is reserved, not available.

**Files:**
- Modify: `packages/analysis/src/ditto_analysis/reports/__init__.py`
- Modify: `packages/analysis/src/ditto_analysis/diagnostics/__init__.py`
- Modify: `packages/analysis/src/ditto_analysis/experiments/__init__.py`
- Modify: `packages/analysis/src/ditto_analysis/screeners/__init__.py`
- Create: `packages/analysis/tests/unit/test_placeholder_honesty_unit.py`
- Modify: `scripts/architecture/check_architecture_smells.py`

**Step 1: RED - Add placeholder honesty tests**

Create tests that assert placeholder modules:

- define `__all__: list[str] = []`
- contain `Reserved namespace` or equivalent wording
- do not claim current support for reports/diagnostics/experiments/screeners

Run:

```bash
pixi run -e dev pytest packages/analysis/tests/unit/test_placeholder_honesty_unit.py -q --no-cov
```

Expected: FAIL because current docstrings describe future capabilities as if provided.

**Step 2: Update placeholder modules**

Rewrite each placeholder docstring to say:

- this namespace is reserved for future analysis product work
- no public runtime API is exported yet
- production code must not import this namespace for behavior

Add:

```python
__all__: list[str] = []
```

**Step 3: Add smell checker guard**

Add a check that placeholder modules cannot contain phrases like "提供" or "支持" unless they export at least one tested public contract.

**Step 4: Verify**

```bash
pixi run -e dev pytest packages/analysis/tests/unit/test_placeholder_honesty_unit.py -q --no-cov
pixi run -e dev arch-check
```

**Step 5: Commit**

```bash
git add packages/analysis scripts/architecture/check_architecture_smells.py
git commit -m "docs: make analysis placeholders explicit"
```

---

## Task 5: Add Minimal Data Catalog and Lineage Contracts

**Intent:** Data governance ownership should exist as contracts even before productized catalog storage/API. This prevents lineage/catalog concerns from leaking into `application`, `analysis`, or ad-hoc docs later.

**Files:**
- Create: `packages/data/src/ditto_data/catalog/__init__.py`
- Create: `packages/data/src/ditto_data/catalog/contracts.py`
- Create: `packages/data/src/ditto_data/lineage/__init__.py`
- Create: `packages/data/src/ditto_data/lineage/contracts.py`
- Modify: `packages/data/src/ditto_data/__init__.py` only if this package already exposes similar top-level contracts
- Create: `packages/data/tests/unit/catalog/test_catalog_contracts_unit.py`
- Create: `packages/data/tests/unit/lineage/test_lineage_contracts_unit.py`
- Create: `packages/apps/tests/unit/architecture/test_data_governance_contracts_unit.py`

**Step 1: RED - Add contract existence tests**

Test that `ditto_data.catalog.contracts` and `ditto_data.lineage.contracts` exist and export only data-owned, non-product protocols/DTOs.

Run:

```bash
pixi run -e dev pytest packages/data/tests/unit/catalog/test_catalog_contracts_unit.py packages/data/tests/unit/lineage/test_lineage_contracts_unit.py -q --no-cov
```

Expected: FAIL because modules do not exist.

**Step 2: Create catalog contracts**

Add frozen dataclasses and protocols:

- `DataAssetRef`: dataset id, namespace, optional partition keys
- `DataSchemaFingerprint`: schema hash, row count optional, created_at optional
- `DataCatalogEntry`: asset ref, storage uri, schema fingerprint, source, freshness timestamp
- `DataCatalogReader`: `get_asset`, `list_assets`
- `DataCatalogWriter`: `upsert_asset`

Keep this storage-free. Do not import `features`, `strategy`, `analysis`, `application`, or `apps`.

**Step 3: Create lineage contracts**

Add frozen dataclasses and protocols:

- `LineageInputRef`
- `LineageOutputRef`
- `LineageEvent`: run id, operation, inputs, outputs, timestamp
- `DataLineageRecorder`: `record_event`
- `DataLineageReader`: `list_events_for_asset`

Keep this data-owned and product-neutral. No UI/API/report behavior.

**Step 4: Add architecture guard**

Create `packages/apps/tests/unit/architecture/test_data_governance_contracts_unit.py` to assert:

- data governance contracts exist
- they do not import production orchestration packages
- they do not contain feature/factor/publication semantics

**Step 5: Verify**

```bash
pixi run -e dev pytest packages/data/tests/unit/catalog packages/data/tests/unit/lineage packages/apps/tests/unit/architecture/test_data_governance_contracts_unit.py -q --no-cov
pixi run -e dev type
pixi run -e dev arch-check
```

**Step 6: Commit**

```bash
git add packages/data packages/apps/tests/unit/architecture
git commit -m "feat: add data governance contracts"
```

---

## Task 6: Route Direct Logging Through Owned Boundaries

**Intent:** Non-platform packages should not import `loguru` directly. Platform owns concrete logging; packages that cannot depend on platform should use a kernel protocol or injected sink.

**Files:**
- Create or modify: `packages/kernel/src/ditto_kernel/observability.py`
- Modify: `packages/backtest/src/ditto_backtest/engine.py`
- Modify: `packages/backtest/src/ditto_backtest/manifest.py`
- Modify: `packages/features/src/ditto_features/factors/validate.py`
- Modify: `packages/data/src/ditto_data/config/data_source_validation.py`
- Modify: `packages/application/src/ditto_application/processes/execution/delivery.py`
- Modify: `packages/application/src/ditto_application/queries/comparison.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/backtest.py`
- Modify: `scripts/architecture/check_architecture_smells.py`
- Create: `packages/apps/tests/unit/architecture/test_logging_boundary_unit.py`

**Step 1: RED - Add logging boundary test**

Add a scanner that fails on `from loguru import logger` outside:

- `packages/platform/src/ditto_platform/**`
- possibly tests

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_logging_boundary_unit.py -q --no-cov
```

Expected: FAIL on current direct imports.

**Step 2: Add kernel logging protocol for packages that cannot use platform**

Create a minimal `LogSink` protocol and `NoopLogSink` in `ditto_kernel.observability`.

It should expose only the methods actually needed by backtest, for example:

- `debug(message: str, *args: object, **kwargs: object) -> None`
- `warning(...)`
- `exception(...)`

No concrete third-party logging dependency belongs in kernel.

**Step 3: Refactor backtest**

Backtest currently cannot depend on `ditto_platform`. Add an optional log sink to `EngineOptions` and use `NoopLogSink` or the injected sink inside `engine.py`.

For `manifest.py`, either:

- pass a `LogSink` into the manifest builder where logging is needed, or
- remove debug logging if it is not behaviorally important.

Do not add `ditto-platform` to `ditto-backtest` unless the architecture rules are intentionally changed.

**Step 4: Refactor packages allowed to use platform**

Replace direct `loguru` imports in `data`, `features`, `application`, and `apps` with the existing platform logger import path used elsewhere:

```python
from ditto_platform.foundation import logger
```

Ensure each affected package already declares `ditto-platform`.

**Step 5: Add smell checker guard**

Wire the logging boundary check into `check_architecture_smells.py`.

**Step 6: Verify**

```bash
pixi run -e dev pytest packages/backtest/tests packages/features/tests packages/data/tests/unit packages/application/tests/unit packages/apps/tests/unit -q --no-cov
pixi run -e dev type
pixi run -e dev arch-check
```

**Step 7: Commit**

```bash
git add packages/kernel packages/backtest packages/features packages/data packages/application packages/apps scripts/architecture/check_architecture_smells.py
git commit -m "refactor: route logging through owned boundaries"
```

---

## Task 7: Clean Stale Architecture Terminology and Docs

**Intent:** Active docs, trace labels, and plan artifacts should not contradict the final architecture.

**Files:**
- Modify: `packages/strategy/src/ditto_strategy/alpha/pipeline.py`
- Modify: docs that are active and not archived
- Modify or archive with approval: stale May 4 plan/review files
- Update: `packages/apps/tests/unit/architecture/test_ai_rule_references_unit.py` if needed

**Step 1: RED - Add stale trace check**

Extend existing AI/stale reference tests or smell checker to catch active source trace names containing old architecture terms such as:

- `engine.alpha`
- `analytics spec`
- `ditto_app`
- `packages/infra`
- `interfaces` as a package/layer name

Run:

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_ai_rule_references_unit.py -q --no-cov
```

Expected: FAIL on `engine.alpha.pipeline.process` until renamed.

**Step 2: Rename trace label**

Change:

```python
@traced("engine.alpha.pipeline.process")
```

to a current capability name, for example:

```python
@traced("strategy.alpha.pipeline.process")
```

**Step 3: Handle stale plan/review drafts**

For each untracked May 4 document, choose one:

- mark as superseded by this May 5 plan
- move to an archive location
- keep as historical review and add a current-status note

Do not delete without explicit approval.

**Step 4: Verify**

```bash
pixi run -e dev pytest packages/apps/tests/unit/architecture/test_ai_rule_references_unit.py -q --no-cov
pixi run -e dev arch-check
```

**Step 5: Commit**

```bash
git add packages/strategy docs packages/apps/tests/unit/architecture scripts/architecture/check_architecture_smells.py
git commit -m "docs: remove stale architecture terminology"
```

---

## Task 8: Final Architecture Gate and Review

**Files:**
- Create: `docs/reviews/2026-05-05-capability-architecture-governance-depth-review.md`

**Step 1: Run targeted verification**

```bash
pixi run -e dev pytest \
  packages/apps/tests/unit/architecture \
  packages/application/tests/unit \
  packages/features/tests \
  packages/strategy/tests \
  packages/analysis/tests \
  packages/data/tests/unit/catalog \
  packages/data/tests/unit/lineage \
  packages/backtest/tests \
  -q --no-cov
```

Expected: all pass, except documented skips outside this targeted set.

**Step 2: Run global verification**

```bash
pixi run -e dev lint
pixi run -e dev fmt
pixi run -e dev type
pixi run -e dev test --fast
pixi run -e dev arch-check
pixi run -e dev check
```

Expected: all commands exit 0.

**Step 3: Write final review**

Create `docs/reviews/2026-05-05-capability-architecture-governance-depth-review.md` with:

- before/after source inventory
- tasks completed
- gate outputs
- any intentionally retained allowlist with rationale
- explicit product items deferred out of this governance pass

**Step 4: Commit**

```bash
git add docs/reviews/2026-05-05-capability-architecture-governance-depth-review.md
git commit -m "docs: review capability architecture governance depth"
```

---

## Completion Criteria

This plan is complete only when:

- `pixi run -e dev check` exits 0.
- `pixi run -e dev arch-check` exits 0.
- Public application boundary failures use `AppError` subclasses.
- Capability semantic failures use capability errors, not built-in compatibility inheritance.
- External direct runtime imports are represented in package metadata or routed through the owning package.
- Placeholder analysis modules are explicitly reserved and export no fake API.
- Data owns minimal catalog/lineage contracts.
- Direct `loguru` imports outside platform are gone or justified by a precise, tested exception.
- Active docs and trace labels no longer use stale architecture terms.
- Stale May 4 plan/review drafts are intentionally kept, superseded, or archived.
