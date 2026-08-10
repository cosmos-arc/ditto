# Public API 成熟度登记表

> 范围：`kernel` / `features` / `application` 三包的高频 leaf API，按 `stable` /
> `candidate` / `internal` 三级标注成熟度。本表是**最小可行的人工登记**，无自动
> 守护（fitness function）；用于约束消费者导入路径与变更预期。
>
> 来源：2026-06-13 质量评估整改计划 Phase 5（Task 5.1）。

## 成熟度定义

| 级别 | 含义 | 变更契约 |
|------|------|----------|
| **stable** | 跨 2+ 包稳定消费；接口语义已固化 | 破坏性变更必须走 deprecation 周期 + 迁移指南 |
| **candidate** | 1-2 包消费，或接口仍在演进 | 变更需在 PR 描述通知消费者；尽量 additive |
| **internal** | 私有/演进中/叶模块内部 | 不保证稳定；消费者应改走更稳定的路径 |

> 导入总原则（AGENTS.md）：消费者直接引用**叶模块**，避免跨包 re-export；re-export
> 链深度 ≤ 2。

---

## kernel — 共享内核

barrel `ditto_kernel/__init__.py` 导出 32 个符号。分级依据 `packages/kernel/AGENTS.md`
的 Barrel 公共 API 分级 + 跨包消费者数量。

### stable（核心类型，2+ 跨包消费者，接口稳定）

| 符号 | 叶模块 | 消费者 |
|------|--------|--------|
| `AssetClass`, `Exchange`, `InstrumentIngestParams` | `kernel.instrument` | Data, Apps |
| `OrderSide`, `OrderType` | `kernel.order` | Execution, Risk, Portfolio, Backtest |
| `MacroCategory`, `MacroFrequency`, `TimeSpec` | `kernel.market` | Data, Apps |
| `InstrumentId` | `kernel.identity` | (全包) |
| `Clock`, `RealtimeClock`, `SimulatedClock` | `kernel.clock` | Execution, Backtest, Apps |
| `Synchronizer`, `TimeSlice` | `kernel.synchronizer` | Backtest, Application |
| `TimeContext` | `kernel.time_context` | Backtest, Application |
| `DittoError`, `AmbiguousTickerError`, `IdentifierError`, `NoIdentifierProvidedError` | `kernel.exceptions` | 全包 |
| `DEFAULT_COMMISSION_RATE`, `DEFAULT_LOT_SIZE`, `DEFAULT_MIN_COMMISSION` | `kernel.trading` | Execution, Backtest |

### candidate（1-2 包消费，接口可能演进）

| 符号 | 叶模块 | 备注 |
|------|--------|------|
| `ExecutionPolicy`, `ImpactModel`, `RiskScope` | `kernel.strategy` | 策略域语义，随策略演进可能转叶模块直导 |
| `DomainEvent`, `EventBus`, `EventName`, `SimpleEventBus` | `kernel.events` | 事件层，消费面较窄 |
| `traced` | `kernel.tracing` | 可插拔追踪装饰器，handler 接口演进中 |

### internal（叶模块直导，不在 barrel）

| 符号 | 叶模块 | 说明 |
|------|--------|------|
| `CalendarId`, `GrainId` | `kernel.market` | AGENTS.md 明确要求叶模块直导 |
| `DEFAULT_PIT_TIME_COLUMN`, `PIT_POLICY_FAIL_CLOSED` | `kernel.trading` | 内部 PIT 常量 |
| `pearson_correlation` | `kernel.math` | 纯计算工具，按需叶模块导入 |
| `RuntimeLifecycle`, `BaseRuntimeKernel`, `TradingRuntimeKernel` | `kernel.runtime` | 运行时内核，Backtest/Execution 内部 |

---

## features — 因子/表达式/物化

barrel `ditto_features/__init__.py` 导出 8 个符号。

### stable（编译 + 因子定义核心）

| 符号 | 叶模块 | 说明 |
|------|--------|------|
| `ExpressionCompiler` | `features.expression.compiler` | 表达式编译主入口 |
| `FactorSpec` | `features.factors.spec` | 因子规格基类 |
| `FactorContext` | `features.factors` | 因子运行时上下文 |
| `validate_derived_spec` | `features.validation` | 衍生规格校验 |

### candidate（物化产物，接口演进）

| 符号 | 叶模块 | 说明 |
|------|--------|------|
| `CompiledDerivedExpression` | `features.expression.contracts` | 编译产物契约 |
| `DerivedExecutionPlan` / `DerivedMaterializationRequest` / `DerivedMaterializationResult` | `features.materialization.contracts` | 物化计划/请求/结果，随物化编排演进 |

### internal（叶模块，高频但非 barrel）

| 符号 | 叶模块 | 说明 |
|------|--------|------|
| `compile_expression` | `features.expression.codegen` | codegen 叶模块入口（D7 交叉验证基准） |
| `FactorEvaluator` | `features.evaluation.evaluator` | 因子评估器，按需叶模块导入 |
| `MaterializationPlanner` | `features.materialization.planner` | 物化计划器 |
| `DerivedQueryService` | `features.services.derived.query_service` | 衍生查询服务 |

---

## application — 应用编排（CQRS）

application barrel **不导出**（`__all__ = []`）；消费者从 `queries` / `commands` /
`processes` 子模块直接导入 facade。下表按 CQRS 子模块标注。

### stable（read-model / command facade，跨 apps/API 消费）

| 符号 | 子模块 | 说明 |
|------|--------|------|
| `MarketQueryFacade`, `MetadataQueryFacade`, `UniverseQueryFacade` | `queries` | 行情/元数据/Universe 只读门面 |
| `CatalogQueryFacade`, `IngestionStatusQueryFacade` | `queries` | catalog/摄取状态只读门面 |
| `BacktestQueryFacade`, `RunReadModel`, `LineageQueryFacade` | `queries` | 回测/运行/血统只读门面 |
| `StrategyQueryFacade` | `queries` | 策略只读门面 |
| `IngestDateCommand` / `IngestDateHandler` | `commands.ingestion` | 摄取写命令 |
| `ReviewDatasetPromotionEvidenceHandler` | `commands` | 晋级证据写命令 |
| `IngestionCoordinator` | `processes.ingestion` | 摄取流程编排 |

### candidate（remediation/source-fallback/read-model，演进中）

| 符号 | 子模块 | 说明 |
|------|--------|------|
| `CatalogRemediationQueryFacade` / remediation commands | `queries` / `commands` | catalog 修复，治理流程演进 |
| `DraftCatalogSourceFallbackPolicyHandler` 等生命周期 commands | `commands` | source-fallback policy lifecycle |
| `DerivedMaterializationOrchestrator` | `processes.materialization` | 物化编排 |
| `ReplayProcess`, `FactorBridge` | `processes.execution` | 回放/因子桥接 |
| `ComparisonQueryFacade`, `BacktestTradeQueryFacade` | `queries` | 回测对比/成交查询 |

### internal（`_` 前缀组装辅助 + builders + contracts）

| 符号 | 子模块 | 说明 |
|------|--------|------|
| `_artifact_utils`, `_instrument_code_facade` | `queries` | 查询组装辅助 |
| `StrategyRuntimeBuilder`, `BacktestRuntimeBuilder`, `StrategySliceBuilder` | `builders` | DI 运行时装配 |
| `contracts`, `execution_dto` | 根 | 跨 CQRS 共享契约/DTO |

---

## 维护说明

- **何时升级 candidate → stable**：符号稳定消费 2+ 包、接口无近期破坏性变更，且通过
  一轮质量评估复核。
- **何时降级 → internal**：符号退化为单消费者或被更稳定路径取代。
- **变更本表**：PR 必须同步更新本表 + 受影响包的 `AGENTS.md` barrel 分级。
- **自动守护（未实现）**：当前无 fitness function 校验本表与 `__all__` / 导入模式
  的一致性；如需守护，可扩展 `scripts/architecture/check_architecture_smells.py`
  增加 route_maturity 模块级检查（超出本计划范围）。
