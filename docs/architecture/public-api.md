# Public API Manifest

> Status: backend architecture fitness source for root package surfaces.
> Scope: root `ditto_*.__all__` exports only; leaf-module public APIs remain owned by package-local modules and package `CLAUDE.md` guidance.

This manifest makes root package imports reviewer-visible. A symbol listed here is a stable root convenience API. Symbols not listed here must be imported from their owning leaf module or treated as internal/reserved unless another package-level manifest explicitly promotes them.

### Root Package API Surface

| Package | Stable Root Exports | Root Policy | Leaf-Only / Internal API |
|---|---|---|---|
| `ditto_agent` | `[]` | No stable root exports. | Runtime contracts, tools, models, storage and eval stay leaf-only so consumers import from the defining module. |
| `ditto_analysis` | `AnalysisError`<br>`ResearchDatasetError`<br>`ResearchDatasetSpec` | Narrow research control-plane root. | Snapshots, reports, diagnostics, screeners and experiments stay leaf/reserved until promoted. |
| `ditto_application` | `[]` | No stable root exports. | Commands, queries, builders and process ports stay leaf-only to preserve CQRS boundaries. |
| `ditto_apps` | `[]` | No stable root exports. | FastAPI app, CLI, jobs and registry composition stay explicit leaf imports. |
| `ditto_backtest` | `[]` | No stable root exports. | Engine, reports, replay and checkpoint APIs stay leaf-only while contracts mature. |
| `ditto_data` | `BarQuery`<br>`DataIngested`<br>`DataProvider`<br>`InstrumentQuery`<br>`QualityCheckCompleted` | Stable data-facing protocol/event convenience root. | Storage, source runtimes, catalog implementations and domain services stay leaf-only. |
| `ditto_execution` | `[]` | No stable root exports. | OMS, broker protocols, reconciliation and storage surfaces stay leaf-only until protocol matrices are broader. |
| `ditto_features` | `CompiledDerivedExpression`<br>`DerivedExecutionPlan`<br>`DerivedMaterializationRequest`<br>`DerivedMaterializationResult`<br>`ExpressionCompiler`<br>`FactorContext`<br>`FactorSpec`<br>`validate_derived_spec` | Stable features convenience root for expression/materialization entry points. | Derived storage, artifact readers/writers and publication runtime internals stay leaf-only. |
| `ditto_kernel` | `DEFAULT_COMMISSION_RATE`<br>`DEFAULT_LOT_SIZE`<br>`DEFAULT_MIN_COMMISSION`<br>`DEFAULT_PIT_TIME_COLUMN`<br>`PIT_POLICY_FAIL_CLOSED`<br>`AmbiguousTickerError`<br>`AssetClass`<br>`Clock`<br>`DittoError`<br>`DomainEvent`<br>`EventBus`<br>`EventName`<br>`Exchange`<br>`ExecutionPolicy`<br>`IdentifierError`<br>`ImpactModel`<br>`InstrumentId`<br>`InstrumentIngestParams`<br>`MacroCategory`<br>`MacroFrequency`<br>`NoIdentifierProvidedError`<br>`OrderSide`<br>`OrderType`<br>`RealtimeClock`<br>`RiskScope`<br>`SimpleEventBus`<br>`SimulatedClock`<br>`Synchronizer`<br>`TimeContext`<br>`TimeSlice`<br>`TimeSpec`<br>`traced` | Stable shared language root; near the public surface budget ceiling. | New low-frequency primitives should start leaf-only unless two or more packages need a shared root import. |
| `ditto_platform` | `foundation`<br>`services` | Namespace-only infrastructure root. | Concrete infra implementations stay under `foundation` or `services`; business facts must not be added here. |
| `ditto_portfolio` | `[]` | No stable root exports. | Position/account/value objects stay leaf-only until product-facing portfolio projections mature. |
| `ditto_risk` | `BenchmarkActiveWeight`<br>`BuyingPowerCheck`<br>`CompositePostTradeGuard`<br>`CompositePreTradeCheck`<br>`ConcentrationLimitRule`<br>`ConcentrationMetrics`<br>`ConcentrationPreCheck`<br>`DailyTurnoverPreCheck`<br>`Decision`<br>`DrawdownMetrics`<br>`LaunchRiskReport`<br>`LotSizeCheck`<br>`MarketAnomalyRule`<br>`MaxDrawdownRule`<br>`NoShortSellCheck`<br>`OrderCheckResult`<br>`PostTradeRiskGuard`<br>`PreTradeContext`<br>`PreTradeRiskCheck`<br>`PriceValidityCheck`<br>`RiskAction`<br>`RiskActionType`<br>`RiskPosition`<br>`RiskSeverity`<br>`SingleLossLimitRule`<br>`StressScenario`<br>`TailRiskMetrics`<br>`build_launch_risk_report` | Stable risk guard convenience root. | Stateful recovery, audit payloads and continuous risk state remain leaf-only until promoted. |
| `ditto_strategy` | `[]` | No stable root exports. | Alpha models, templates and storage stay leaf-only while broader template maturity remains experimental. |

### Change Rules

- Adding, removing or reordering root `__all__` entries must update this manifest in the same change.
- Empty-root packages must stay empty unless a module review explicitly promotes a stable root convenience symbol.
- Root exports should be stable, low-churn, and safe for downstream package imports.
- Candidate or experimental APIs should stay in owning leaf modules until their maturity evidence is documented.
