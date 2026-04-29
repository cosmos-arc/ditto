# Capability-Boundary and Platformization Review Plan

> **Status:** Draft
> **Date:** 2026-04-28
> **Trigger:** Tasks 1-6 of post-architecture-clarity follow-up complete; T0 baseline solid.
> **Next Step:** Decide which capability boundaries to formalize, which to leave as-is, and which to defer.

---

## 1. Context: What Was Accomplished

Tasks 1-6 of the post-architecture-clarity follow-up established a verified T0 baseline:

| Task | Result |
|------|--------|
| 1. `arch-check` executable | 34 import-linter contracts pass; arch-smell gates fixed |
| 2. `pytest` environment works | 353+ tests pass; coverage infrastructure functional |
| 3. Tracing has real kernel hook + OTel bridge | `ditto_kernel.tracing` provides `traced()`; `ditto_infra.foundation` bridges to OTel |
| 4. DQ config is CWD-independent | `DQSettings` uses injected config root, not `Path.cwd()` |
| 5. Expression contract ownership is clean | `expression/contracts.py` owns `Analysis`, `CompiledDerivedExpression`, etc.; no reverse dependency |
| 6. Architecture docs reflect actual state | `boundaries-and-abstraction-standards.md`, package `CLAUDE.md` files, `.importlinter` all consistent |

The system is now at a point where boundary decisions have teeth: naming is precise, import-linter catches violations, and documentation matches reality.

---

## 2. Scope

### In Scope

This review examines six candidate areas for capability-boundary formalization. For each, it asks:

1. Is the current boundary adequate?
2. Should a Protocol/ABC be extracted to formalize it?
3. Should a plugin extension point be created?
4. Is the naming misleading?
5. Can it be deferred without risk?

The six candidates are:

1. Command/query separation in app process surfaces
2. Plugin extension points and registry ownership
3. Data source/provider capability boundaries
4. Strategy runtime contracts
5. Materialization/platform services
6. Agent coding context and guardrails

### Out of Scope

| Excluded | Reason |
|----------|--------|
| Order aggregate / OMS | No live trading yet; premature |
| DataCatalog replacement | Requires product-level design, not boundary review |
| Dynamic plugin discovery (entry_points / pluggy) | Infrastructure decision, not boundary design |
| Unified backtest/live TradingLoop | Engine-level design, separate from boundary review |
| Public API compatibility layer | No external consumers yet |
| Web workspace / UI | Not in T1 scope |

---

## 3. Candidate Analysis

### 3.1 Command/Query Separation in App Process Surfaces

**Current state:**

The CQRS split is well-defined in `.importlinter` (R8 rules):
- `query` is read-only, forbidden from importing `process`, `builders`, `command`
- `command` is write-only, forbidden from importing `query`, `builders`
- `process` can call `query` (allowed for orchestration)
- `process` and `builders` can reference each other bidirectionally
- `command` can delegate to `process`

The `CommandHandler` Protocol in `app/command/protocols.py` provides a unified handler interface. Process surfaces (`process/execution/`, `process/ingestion/`, `process/materialization/`, `process/quality/`) are internally cohesive.

**Observation:**

The `command -> process` delegation pattern is clean (e.g., `BacktestRunHandler` delegates to `BacktestService`). The `process -> command` direction (Process Manager injecting Handlers) is allowed but currently not heavily used. The `process` subdirectories each have their own `ports.py` for dependency inversion.

**Known tension:** The `command/` module contains files like `backtest.py`, `strategy.py`, `quality_check.py`, `quality_reconciliation.py` that are not pure Command DTOs -- they contain handler logic that coordinates services. This is by design (CQRS Command side), but the naming could mislead agents into thinking they are only DTO definitions.

**Risk:** Low. The R8 import-linter rules enforce separation mechanically. The main risk is conceptual drift as more commands are added.

### 3.2 Plugin Extension Points and Registry Ownership

**Current state:**

DI is through dishka providers:
- `interfaces/registry/container.py` assembles the composition root
- Provider aggregation: `get_infra_providers()` + `get_data_providers()` + `get_app_providers()`
- `interfaces/registry/contexts/` provides bundles (IngestionBundle, MaterializationBundle, StrategyBundle)
- `interfaces/registry/infra/` handles config, notification, observability

The registry has a permanent exemption in `.importlinter` to directly import Data services/quality/config (Composition Root privilege).

**Observation:**

The `SourceRegistry` in `data/sources/registry.py` is a typed in-memory registry that maps `(name, Protocol)` to implementation. It is used at the data-source level but not generalized as a cross-system plugin point.

`DataSources` in `data/sources/source.py` is a concrete accessor with hardcoded source types (tushare, fred). Adding a new source requires modifying this class.

**Known tension:** No plugin discovery mechanism exists. Every new data source or service requires code changes to the composition root. This is appropriate for T0 but will need re-evaluation for platformization.

**Risk:** Medium. The current approach is correct for the current scale. Premature pluginization would add complexity without benefit. But the `DataSources` accessor should not accumulate more hardcoded source references.

### 3.3 Data Source/Provider Capability Boundaries

**Current state:**

ISP-compliant fetcher Protocols exist in `data/sources/protocols.py`:
- `MetadataFetcher`, `MarketFetcher`, `FundamentalFetcher`, `CapitalFetcher`, `MacroFetcher`
- Each protocol represents a cohesive data domain
- Source implementations (tushare, fred, tdx) implement these protocols through adapter classes
- Cross-source isolation enforced by `.importlinter` (tushare/tdx/fred mutually forbidden)

`DataProvider` Protocol in `data/provider.py` is the unified data access abstraction consumed by engine (`Engine -> DataProvider` is the only allowed engine->data dependency).

Normalization layer (`data/sources/normalization.py`) handles source-to-domain code conversion via `SourceExchangeCode` and `NormalizationConfig`.

**Observation:**

The fetcher Protocols are well-designed. Each data source (tushare, fred, tdx) has adapters that implement the relevant protocols. Adding a new data source requires:
1. Creating a new source directory under `data/sources/`
2. Implementing the relevant fetcher Protocol(s)
3. Registering in `DataSources` accessor
4. Adding DI providers in `data/di/sources.py`

The boundary is clear but the `DataSources` accessor is a bottleneck. The `SourceRegistry` exists but is not used by `DataSources`.

**Known tension:** `DataSources` is a concrete class with hardcoded source knowledge. `SourceRegistry` provides the right abstraction but is not wired into the main flow. This gap will widen as more sources are added.

**Risk:** Medium. The ISP Protocols are correct. The registration path needs unification before the next source is added.

### 3.4 Strategy Runtime Contracts

**Current state:**

Strategy lifecycle is well-structured:
- Engine: `alpha/` subdomain (pipeline, protocols, specs, templates, builtins)
- Engine: `backtest/` subdomain (engine loop, data feed, steps, audit)
- App: `process/execution/` orchestrates strategy runs
- App: `process/execution/strategy_types.py` defines `RunLifecycleService` Protocol and triggers
- App: `process/execution/ports.py` defines `PositionReader`, `SignalDeliveryProtocol`
- Kernel: `strategy.py` holds `DerivedSpec`, `MaterializationProfile`, `ExecutionPolicy`, etc.

The `DecisionStage` Protocol in `engine/alpha/protocols.py` is the extension point for strategy stages. The pipeline composes stages (filtering, scoring, selection, signal, etc.).

**Observation:**

The strategy lifecycle has a clear contract chain: `BacktestTrigger` -> `BacktestService` -> `EngineLoop` -> `StrategyPipeline` -> `DecisionStage` implementations. The `RunLifecycleService` Protocol cleanly separates run state management from execution logic.

The strategy templates in `engine/alpha/templates/` demonstrate the extension pattern. New strategies can be created by composing built-in stages or implementing `DecisionStage`.

**Known tension:** Strategy slice triggers (`StrategySliceTrigger`) and backtest triggers (`BacktestTrigger`) are defined in app process but the actual execution crosses into engine. The boundary is clean (app orchestrates, engine computes), but the trigger DTOs could benefit from being in kernel if they need to be shared more broadly.

**Risk:** Low. The current contracts are well-defined. The main question is whether trigger DTOs should migrate to kernel.

### 3.5 Materialization/Platform Services

**Current state:**

The materialization pipeline spans two packages:
- Analytics: `expression/` (compile) + `materialization/` (plan) -- pure computation
- App: `process/materialization/` -- orchestration with I/O

Contracts are in `analytics/materialization/contracts.py`:
- `DerivedExecutionPlan`, `DerivedMaterializationRequest`, `DerivedMaterializationResult`, `DerivedInvalidationEvent`
- These are clean dataclass DTOs

The planner (`analytics/materialization/planner.py`) is a pure function that resolves compute windows. The orchestrator (`app/process/materialization/orchestrator.py`) coordinates the actual materialization with storage I/O.

The cascade orchestrator handles invalidation fan-out. Publication facade handles safety checks.

**Observation:**

The split between analytics (plan) and app (execute) is architecturally correct. The contracts in `analytics/materialization/contracts.py` are stable DTOs that neither side depends on the wrong way. Expression -> contracts <- materialization is the correct dependency direction.

**Known tension:** The app-side materialization process has 14 files, some with overlapping concerns (helpers.py, publication_helpers.py, dependency_refs.py). The "platform service" boundary is clear at the package level but the internal cohesion within `app/process/materialization/` could be tighter.

**Risk:** Low-Medium. The inter-package boundary is solid. Internal refactoring of the app materialization module is a code-quality issue, not an architectural one.

### 3.6 Agent Coding Context and Guardrails

**Current state:**

Multi-layered guardrail system:
- `CLAUDE.md`: Project-level instructions, north-star principles, execution flow
- `.claude/rules/`: 10 rule files (architecture, config, dependencies, doc, noqa, pit, polars, python, python-test, workflow)
- `.claude/checklists/`: 2 checklists (code-change, debug)
- `.importlinter`: 34 contracts enforcing layer boundaries mechanically
- Package-level `CLAUDE.md`: 7 files (app, analytics, data, engine, infra, interfaces, kernel)
- `docs/architecture/boundaries-and-abstraction-standards.md`: Naming dictionary, abstraction rules

Import-linter provides the mechanical enforcement layer. The rule files provide coding guidance. The package CLAUDE.md files provide context for each layer.

**Observation:**

The guardrail system is comprehensive. The three layers (mechanical enforcement, coding rules, architectural context) cover most failure modes. The naming dictionary in `boundaries-and-abstraction-standards.md` is particularly effective at preventing naming drift.

**Known tension:** Agent instructions are spread across many files. A new agent session must read and synthesize 10+ rule files plus the project CLAUDE.md plus package CLAUDE.md. This is correct (each file serves a specific purpose) but the cognitive load is high. The `CLAUDE.md` execution decision flow and skill-first approach helps prioritize.

**Risk:** Low. The guardrails are strong. The main risk is guardrail fatigue (too many rules leading to selective compliance).

---

## 4. Decision Table

| Candidate | Classification | Owner Package | Boundary Rule | Migration Cost | Test Strategy | First Implementation Slice |
|-----------|---------------|---------------|---------------|----------------|---------------|---------------------------|
| **CQRS process surface separation** | **keep as-is** | ditto_app | R8 import-linter rules enforce mechanically | None | Verify R8 contracts pass; add test for any new command->process delegation | No action needed; monitor as new commands/processes are added |
| **DI registry ownership** | **keep as-is** | ditto_interfaces | Registry exemption in import-linter is explicit and bounded | None | Verify composition root still wires correctly | No action needed; document that new providers follow the existing pattern |
| **SourceRegistry vs DataSources gap** | **extract protocol** | ditto_data | `DataSources` should delegate to `SourceRegistry` instead of hardcoded fields | Low (1-2 files) | Unit test: registering a mock source via `SourceRegistry` works end-to-end | Refactor `DataSources.get()` to use `SourceRegistry` internally |
| **DataProvider consumer boundary** | **keep as-is** | ditto_data | Engine -> DataProvider is the single allowed engine->data dependency | None | Existing import-linter contract `engine-no-data-dependency` with explicit ignore | No action needed; the Protocol is stable |
| **Fetcher Protocol ISP compliance** | **keep as-is** | ditto_data | 5 domain Protocols + cross-source isolation enforced | None | Verify tushare/tdx/fred isolation contracts pass | No action needed; pattern is established |
| **Strategy trigger DTOs** | **rename only** | ditto_app -> ditto_kernel | Triggers are cross-consumer DTOs; kernel is the right home if shared | Low (2 DTOs, move to kernel/strategy.py) | Verify all imports resolve after move | Move `BacktestTrigger` and `StrategySliceTrigger` to `ditto_kernel.strategy` |
| **RunLifecycleService Protocol** | **keep as-is** | ditto_app | Already a Protocol; clean dependency direction | None | Existing tests cover lifecycle state transitions | No action needed |
| **DecisionStage extension point** | **keep as-is** | ditto_engine | Protocol in engine/alpha/protocols.py; templates demonstrate extension | None | Template tests cover stage composition | No action needed; new stages follow the template pattern |
| **Materialization internal cohesion** | **defer** | ditto_app | Internal file organization is a code-quality concern, not a boundary issue | Low (reorganize helpers) | Covered by existing materialization tests | Revisit when adding new materialization features |
| **Materialization cross-package boundary** | **keep as-is** | ditto_analytics + ditto_app | contracts.py is the seam; expression -> contracts <- materialization | None | Verify `analytics-expression-no-materialization` contract passes | No action needed; dependency direction is correct |
| **Plugin discovery mechanism** | **defer** | ditto_data (sources), ditto_engine (stages) | No external consumers yet; hardcoded registration is appropriate | N/A | N/A | Revisit when third-party data sources or custom stages are needed |
| **Agent guardrail comprehensiveness** | **keep as-is** | .claude/ | Three-layer system (mechanical, rules, context) is effective | None | Verify new agent sessions produce compliant code | No action needed; monitor for guardrail fatigue |

---

## 5. Risk Assessment

### Low Risk (No Action Needed)

| Candidate | Reason |
|-----------|--------|
| CQRS process separation | R8 import-linter rules are mechanical and comprehensive |
| DI registry ownership | Composition root exemption is bounded and documented |
| DataProvider boundary | Single authorized dependency, enforced by import-linter |
| Fetcher Protocol ISP | 5 focused protocols + cross-source isolation |
| RunLifecycleService | Clean Protocol with clear state machine |
| DecisionStage extension | Templates demonstrate the pattern |
| Materialization cross-package | Correct dependency direction, enforced by import-linter |
| Agent guardrails | Three-layer system is effective |

### Medium Risk (Targeted Action)

| Candidate | Risk | Mitigation |
|-----------|------|------------|
| SourceRegistry vs DataSources | Adding new sources requires modifying `DataSources` class | Refactor `DataSources` to delegate to `SourceRegistry`; this unblocks clean source registration without modifying the accessor |
| Strategy trigger DTOs in app | If kernel or interfaces needs these DTOs, the dependency direction reverses | Move `BacktestTrigger` and `StrategySliceTrigger` to `ditto_kernel.strategy` preemptively; they are value objects with no business behavior |

### Deferred (Revisit Later)

| Candidate | Defer Reason | Revisit Trigger |
|-----------|-------------|-----------------|
| Plugin discovery | No third-party consumers | When external data sources or custom strategy stages are needed |
| Materialization internal cohesion | Code quality, not architecture | When adding new materialization features causes file bloat |

---

## 6. Implementation Priority

### First Slice (Do Now)

Two targeted actions that reduce risk without broad refactoring:

1. **Unify SourceRegistry into DataSources flow** (ditto_data)
   - Refactor `DataSources.__init__` and `DataSources.get()` to use `SourceRegistry` internally
   - Remove hardcoded `_tushare` / `_fred` fields
   - Register sources via `SourceRegistry.register()` during DI setup
   - Estimated scope: 2-3 files, ~50 lines changed
   - Test: existing DataSources tests + new SourceRegistry integration test

2. **Move strategy trigger DTOs to kernel** (ditto_kernel)
   - Move `BacktestTrigger` and `StrategySliceTrigger` from `app/process/execution/strategy_types.py` to `kernel/strategy.py`
   - Update all imports (app process execution files)
   - Estimated scope: 3-4 files, ~20 lines changed
   - Test: existing trigger tests pass after move

### Second Slice (Monitor, No Action)

All other candidates are classified as "keep as-is". Monitor for drift during regular development. If any of the following signals appear, escalate to the next review:

- A new data source requires changes to `DataSources` class (resolved by first slice)
- A new CQRS sub-directory is proposed (verify it fits the R8 matrix)
- A new Protocol is needed in app/process (verify it follows the ports.py pattern)
- Agent sessions produce non-compliant code despite guardrails (update rule files)

---

## 7. Review Completion Criteria

This review is complete when:

- [ ] Decision table is agreed upon by the developer
- [ ] First slice items are implemented and pass `pixi run -e dev check`
- [ ] All "keep as-is" items are documented as intentional decisions (this document serves that purpose)
- [ ] Deferred items have explicit revisit triggers documented
- [ ] No new architecture-smell issues introduced

---

## 8. References

| Document | Relevance |
|----------|-----------|
| `.importlinter` | 34 contracts enforcing layer boundaries |
| `docs/architecture/boundaries-and-abstraction-standards.md` | Naming dictionary and abstraction rules |
| `docs/plans/2026-04-28-t0-architecture-clarity-improvement-plan.md` | Prior architecture clarity work |
| `docs/plans/2026-04-28-post-architecture-clarity-followup-plan.md` | Tasks 1-6 that established the T0 baseline |
| Package-level `CLAUDE.md` files (7) | Per-layer context and rules |
| `.claude/rules/` (10 files) | Coding rules and guardrails |
