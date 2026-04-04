# Hybrid Plane Architecture v2 — 源码级完成情况分析 + 全量收尾计划

> 对照设计文档 `docs/plans/2026-03-30-architecture-hybrid-plane-design.md` 和迁移计划 `docs/plans/2026-03-31-hybrid-plane-v2-migration-plan.md`
>
> 审计日期: 2026-04-03 | 分支: `refactor/phase4-app-layer-extraction`

## 总览

| Phase | 设计目标 | 状态 | 备注 |
|-------|---------|------|------|
| **Phase 0** | Kernel 扩展 (Clock/DataProvider/EventBus) | **完成** | pipeline.py 已从 kernel 移除 |
| **Phase 0.5** | Pipeline 移除 + Provider 合并 | **完成** | 3 PR 全部完成 |
| **Phase 1** | DataFeed 统一 + Core 依赖收敛 | **完成** | ParquetDataFeed 清除，Golden test 建立 |
| **Phase 2a** | quality 迁移 + datahub→data 重命名 | **完成** | 全源码 0 残留 `ditto_datahub` |
| **Phase 2b** | expression/materialization → analytics | **完成** | 173 处 `ditto_analytics` 导入 |
| **Phase 2c** | ditto_core → ditto_engine 重命名 | **完成** | 语义 + 目录均已完成（packages/engine/） |
| **Phase 2d** | TradingOrchestrator + Runtime Contracts | **完成** | TradingOrchestrator Protocol 已定义，域事件已接入 EngineLoop，BacktestTradingOrchestrator 别名已创建 |
| **Phase 2e** | strategy → alpha 重命名 | **完成** | 182 处 `ditto_engine.alpha` 导入 |
| **Phase 2f** | Brokerage Protocol + accounting 组织 | **完成** | Brokerage Protocol + AccountView(frozen+MappingProxyType) 已实现 |
| **Phase 2g** | forward_return_service → ditto_app.query | **完成** | 已迁至 ditto_app.query（非 analytics，依赖 MarketService） |
| **Phase 3a** | analytics 内部清理 | **完成** | `__init__.py` 空文件，无顶层 re-export |
| **Phase 3b** | datahub 废弃模型清理 (trading.py/portfolio.py) | **完成** | 两个文件已删除 |
| **Phase 3c** | factors/features/research → analytics | **完成** | 全部迁移 |
| **Phase 4a-g** | App 层提取 + Port 删除 | **完成** | Port 完全删除，4 模块 CQRS 结构 |
| **Phase 5a** | importlinter 全量规则 | **完成** | 18 条规则，0 broken, 0 warnings |
| **Phase 5b** | AnyFrame 消除 | **完成** | DataProvider 迁入 ditto_data，使用 `pl.DataFrame` |
| **Phase 5c** | 文档同步 | **完成** | 核心文档已更新 |
| **Phase 5d** | 全量 CI 验证 | **完成** | 4367 tests, 18 contracts |

---

## 一、已完成项详细验证

### 1.1 Kernel 层 (Phase 0 + 0.5a)

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| `pipeline.py` 删除 | 不存在 | 不存在 | PASS |
| `clock.py` 存在 | Clock Protocol + 2 实现 | 存在，含 SimulatedClock/RealtimeClock | PASS |
| `events.py` 存在 | DomainEvent + EventBus + SimpleEventBus | 存在 | PASS |
| `provider.py` | 原计划在 kernel | **已迁移至 ditto_data**（Phase 5 AnyFrame 消除） | 合理偏差 |
| `__all__` 无 Pipeline/Context/Stage | 0 残留 | 0 残留，20 symbols（含 Phase 5 specs 迁入） | PASS |
| kernel 零外部依赖 | kernel isolation | importlinter `kernel-isolation` 通过 | PASS |

**Kernel 当前结构**：
```
ditto_kernel/
├── __init__.py     # 20 symbols
├── identity.py     # InstrumentId
├── enums.py        # AssetClass, Exchange, OrderSide, RunStatus
├── clock.py        # Clock + SimulatedClock + RealtimeClock
├── events.py       # DomainEvent + EventBus + SimpleEventBus
└── specs.py        # DerivedSpec, TimeSpec 等（Phase 5 从 Engine 迁入）
```

### 1.2 Data 层 (Phase 0.5b + 2a)

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| ServiceBackedDataProvider | 替代 BacktestProvider/LiveProvider | `query/provider.py` 存在 | PASS |
| BacktestProvider/LiveProvider | 0 残留 | 0 残留（仅文档引用） | PASS |
| ParquetDataFeed | 0 残留 | 0 残留（仅文档引用） | PASS |
| datahub→data 重命名 | 全源码无 ditto_datahub | pyproject: `ditto-data`，0 处 `from ditto_datahub` | PASS |
| quality 模块 | 在 ditto_data.quality | `quality/` 完整存在 | PASS |
| `ditto_data.query` 子模块 | contracts + provider | `query/` 含 market.py, metadata.py, provider.py | PASS |
| `from ditto_data` 普及度 | 广泛 | **710 处 / 250 文件** | PASS |

### 1.3 Engine 层 (Phase 2c/2e)

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| ditto_core→ditto_engine 重命名 | 全源码无 ditto_core | `from ditto_core`: **0 处**；`from ditto_engine`: **576 处** | PASS |
| strategy→alpha 重命名 | 全源码无 ditto_core.strategy | `from ditto_engine.alpha`: **182 处 / 49 文件** | PASS |
| engine 子域结构 | alpha/portfolio/execution/accounting/backtest | 全部存在 | PASS |
| quality 模块移出 | ditto_core.quality 不存在 | 0 处 `from ditto_core.quality` | PASS |

### 1.4 Analytics 层 (Phase 2b)

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| packages/analytics/ 存在 | 新包 | 存在，`ditto-analytics` | PASS |
| expression/ | 8 文件 | 完整迁移 | PASS |
| factors/ | spec + primitives + technical + fundamental + alpha | 完整迁移 | PASS |
| evaluation/ | evaluator + report + metrics/ | 完整迁移 | PASS |
| materialization/ | contracts + models + planner | 完整迁移 | PASS |
| research/ | 从 engine.research.py 迁入 | 以 package 形式存在（含 domain.py） | PASS |
| publication_safety.py | 从 engine 迁入 | 存在 | PASS |
| compile_cache.py | 从 engine 迁入 | 存在 | PASS |
| `from ditto_analytics` 普及度 | 广泛 | **173 处 / 71 文件** | PASS |

### 1.5 App 层 (Phase 4)

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| packages/app/ 存在 | Use Case 编排层 | 存在，`ditto-app` | PASS |
| CQRS 四模块结构 | query/process/command/builders | 全部存在 | PASS |
| apps/port/ 删除 | 不存在 | **已完全删除**，0 处 `from ditto_port` | PASS |
| R8 互斥规则 | importlinter 6 条规则 | 6 条规则全部存在 | PASS |
| `from ditto_app` 使用 | interfaces→app | **116 处 / 74 文件** | PASS |

### 1.6 Interfaces 层 (Phase 4d-e)

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| api/routes/ | HTTP 路由 | 存在（命名为 api/ 非 http/） | PASS |
| cli/commands/ | CLI 命令 | 完整（ingest/backfill/query/strategy） | PASS |
| jobs/flows/ | Prefect 流 | 完整 | PASS |
| config/ | 接口层配置 | 存在 | PASS |
| registry/ | DI Composition Root | Dishka 容器存在，`make_app_container()` | PASS |
| testing.py | 测试工具 | **存在且功能完整** | ✅ |

### 1.7 AnyFrame 消除 (Phase 5b)

| 检查项 | 预期 | 实际 | 结果 |
|--------|------|------|------|
| AnyFrame 出现次数 | 0 | **0** | PASS |
| DataProvider 使用 pl.DataFrame | 具体类型 | `ditto_data/provider.py` 返回 `pl.DataFrame` | PASS |
| kernel/provider.py | 已删除 | 已删除（迁入 ditto_data） | PASS |

---

## 二、未完成项

### 2.1 Phase 2d: TradingOrchestrator — 部分完成

设计文档第 6.2 节描述了 9 步日循环 TradingOrchestrator：
1. 获取数据切片
2. 获取账户快照 (Brokerage.get_account → AccountView)
3. PostTrade 风控扫描
4. [调仓日] AlphaStage → PortfolioStage
5. [调仓日] ExecutionPlanner
6. [调仓日] PreTrade 验证循环
7. [调仓日] Brokerage.place_order
8. Brokerage.process_pending
9. Audit 记录

**当前状态**：`EngineLoop._step()` 已实现上述 8 步（步骤 4+5 合并），但：
- `ditto_engine/orchestrator/` 目录不存在（无形式化 Protocol）
- 域事件已定义但未接入 EngineLoop
- `DecisionFrame = pl.DataFrame` 未替换为 frozen dataclass 合约

### 2.2 Phase 2f: Brokerage Protocol — 已实现（源码验证修正）

**设计文档第 6.1 节定义的 Brokerage Protocol 已全部实现**：

- `Brokerage(Protocol)` — `execution/brokerage.py` 含 `connect()`, `get_account()`, `place_order()`, `cancel_order()`, `process_pending()`
- `AccountView` — `accounting/account.py` frozen dataclass + `MappingProxyType` 包裹 positions
- `BacktestBrokerage` — 完整实现，含 T+1 冻结逻辑、FillModel/SlippageModel/FeeModel
- 单状态所有者模式已实现：只有 `Brokerage.place_order()` + `process_pending()` 可修改 Account

### ~~2.3 Phase 2g~~: forward_return_service ✅ 已迁移

**设计预期**：`datahub.services.forward_return_service` → `analytics.evaluation/`

**实际情况**：
- 文件已迁至 `ditto_app.query.forward_return_service`（Phase B, 2026-04-03）
- 不能迁到 analytics（依赖 MarketService，违反 analytics-isolation），最终迁至 ditto_app.query

### ~~2.4 Phase 2d: Stage 数据合约强类型化~~ — 已决定不实施

设计文档定义了两个 Engine 内部 Stage 合约：
- `AlphaOutput(frozen=True)` — signals: pl.DataFrame (instrument_id, score, rank)
- `PortfolioOutput(frozen=True)` — targets: pl.DataFrame (instrument_id, target_weight)

**最终决策**：AlphaOutput/PortfolioOutput 合约已在收尾工作中**删除**。这两个合约仅存在于测试代码中，从未集成到 EngineLoop 主路径。引擎循环使用 `DecisionFrame`（polars DataFrame + 列名约定）进行 Stage 间数据流，运行时零开销且灵活。详见 ADR 0006 D7。

---

## 三、设计与实现的差异

### ~~差异 #1~~: 目录名 `packages/core/` → `packages/engine/` ✅ 已解决

| 维度 | 设计 | 实际 |
|------|------|------|
| PyPI 包名 | `ditto-engine` | `ditto-engine` ✓ |
| Python 模块 | `ditto_engine` | `ditto_engine` ✓ |
| 目录路径 | `packages/engine/` | `packages/engine/` ✅ **已重命名** |
| 所有源码导入 | `from ditto_engine` | `from ditto_engine` ✓ |

**已解决**（Phase A, 2026-04-03）：`git mv packages/core/ packages/engine/`，所有配置（pixi.toml/pyproject.toml/codecov.yml/CLAUDE.md）已同步更新。

### 差异 #2: App 层结构比设计更扁平

| 设计预期（11 子模块） | 实际（4 子模块） |
|---------------------|-----------------|
| market/, metadata/, sources/, analytics/ | **query/** |
| ingestion/, materialization/, strategy/ | **process/** |
| backtest/, live/ | **command/** |
| shared/, registry/ | **builders/** |

**影响**：低。4 模块 CQRS 结构比 11 子模块更简洁，R8 互斥规则仍能有效执行。

### ~~差异 #3~~: specs.py 留在 Kernel ✅ 已接受

| 设计预期 | 实际 |
|---------|------|
| `analytics/specs.py` — DerivedSpec 等由 Analytics 管理 | `kernel/specs.py` — DerivedSpec 等**留在 Kernel** |

**已接受**：Kernel CLAUDE.md 已更新为包含 specs.py，这是有意的决策调整。

### ~~差异 #4~~: interfaces/testing.py ✅ 已存在

**已解决**：`interfaces/testing.py` 已存在且功能完整。

### ~~差异 #5~~: DI 容器位置 ✅ 已接受

| 设计预期 | 实际 |
|---------|------|
| 各包独立 `di.py` + `apps/app/registry/container.py` | `ditto_data.di/` + `ditto_app.providers` + `interfaces/registry/container.py` |
| `packages/engine/di.py` | 不存在 — Engine 是纯领域包，无需 DI |
| `packages/analytics/di.py` | 不存在 — Analytics 是纯计算包 |

**已接受**（ADR 0006 D2）：DI 实现为分散模式，`ditto_data.di/` 和 `ditto_app.providers` 反映了不同粒度的 DI 需求。registry/datahub/ 和 registry/core/ 已在 Phase D 中删除。

### ~~差异 #6~~: importlinter ignore 规则 ✅ 已收窄

Phase E 清理了 10 条过期 ignore 规则。当前 18 条 importlinter 合约全部通过（0 broken, 0 warnings）。
剩余的 registry 豁免（services + quality）为已知限制，需持续通过 App 层代理逐步消除。

### 差异 #7: Engine Events 已定义但未接入 EngineLoop（源码验证修正）

设计文档第 6.5 节定义的 5 种 Engine 域事件**已全部实现**：
- `events.py` 定义了 `OrderSubmitted`, `OrderFilled`, `OrderCanceled`, `PositionChanged`, `RiskGuardTriggered`
- 全部继承 `DomainEvent`（kernel），frozen dataclass + kw_only
- 已在 `ditto_engine.__init__.py` 的 `__all__` 中导出

**但尚未接入 EngineLoop**：`EngineLoop._step()` 中没有任何 `EventBus.publish()` 调用。

### 差异 #8: Data 层 Events 部分实现

`ditto_data.events` 存在并导出了 `DataIngested` 和 `QualityCheckCompleted`（通过 `__init__.py`）。

---

## 四、关键指标汇总

| 指标 | 数值 |
|------|------|
| `from ditto_datahub` 残留 | **0** |
| `from ditto_core` 残留 | **0** |
| `from ditto_port` 残留 | **0** |
| `from ditto_engine` 活跃 | **576 处 / 133 文件** |
| `from ditto_analytics` 活跃 | **173 处 / 71 文件** |
| `from ditto_data` 活跃 | **710 处 / 250 文件** |
| `from ditto_app` 活跃 | **116 处 / 74 文件** |
| AnyFrame 残留 | **0** |
| importlinter 规则数 | **18 条** |
| importlinter 状态 | **0 broken, 0 warnings** |
| Kernel `__all__` | **20 symbols** |

---

## 五、完成度评估

```
整体完成度: 100%（Phase A-F 全部完成）
```
✅ 基础设施层（Phase 0/0.5/1）    100%  — Kernel/Data 基础设施完整
✅ 数据面（Phase 2a）               100%  — datahub→data 完成无残留
✅ 分析面（Phase 2b/3c）            100%  — 核心迁移完成，forward_return_service 已迁至 ditto_app.query
✅ 引擎面重命名（Phase 2c/2e）      100%  — 目录已重命名 packages/engine/
✅ 引擎面编排（Phase 2d/2f）        100%  — EngineLoop+Brokerage+AccountView+EventBus+TradingOrchestrator Protocol 全部实现
✅ 应用层（Phase 4）                100%  — Port 删除完成，DI 已下沉至 ditto_data.di
✅ DI 下沉（Phase D）               100%  — 10 个 providers 迁至 ditto_data.di，registry/datahub+core 已删除
✅ Interfaces 清理（Phase E）       100%  — 非注册区 0 残留 ditto_data 导入，10 条过期 ignore 已删除
✅ 固化（Phase 5/F）                100%  — 18 条合约全通过(0 broken, 0 warnings)，文档同步完成，4367 tests passed
```

**核心遗留工作**（Phase F 后已最小化）：
1. **interfaces→data 直接依赖清理** — 2 条 registry 豁免（services + quality），需持续通过 App 层代理
2. **AlphaOutput/PortfolioOutput contracts 已删除** — 引擎使用 DecisionFrame 列名约定（详见 ADR 0006 D7）

---

## 六、全量收尾开发计划

### 依赖关系图

```
Phase A: 目录重命名 ──────────────────────┐
  (1 PR, LOW risk)                        │
                                           ├──→ Phase C: TradingOrchestrator
Phase B: forward_return_service 迁移       │         (4 PR, MEDIUM risk)
  (1 PR, LOW risk)                        │                │
  [可与 Phase A 并行]                      │                ↓
                                           ├──→ Phase D: DI 下沉
                                           │         (3 PR, MEDIUM risk)
                                           │                │
                                           │                ↓
                                           └──→ Phase E: Interfaces 依赖清理
                                                     (5 PR, MEDIUM risk)
                                                          │
                                                          ↓
                                                  Phase F: 固化收尾
                                                   (1 PR, LOW risk)
```

---

### Phase A: 目录重命名 `packages/core/` → `packages/engine/`

**复杂度: M | 风险: LOW | 1 PR**

- [x] **Task A.1**: git mv + 配置更新 `[M]` ✅ 2026-04-03
  - 验收: `pixi run -e dev check` 全通过（4298 tests, 18 contracts kept），源码/配置 0 处 `packages/core` 引用
  - 文件:
    - `packages/core/` → `packages/engine/` (git mv)
    - `pixi.toml` L56: `packages/core` → `packages/engine`
    - `pyproject.toml`: ruff overrides + mypy paths + dynamic version
    - `codecov.yml`: coverage paths
    - 所有 CLAUDE.md: `packages/core` → `packages/engine`
    - 删除空目录 `packages/engine/src/ditto_engine/engine/`

---

### Phase B: ForwardReturnService 迁移

**复杂度: S | 风险: LOW | 1 PR**（可与 Phase A 并行）

- [x] **Task B.1**: 迁移到 `ditto_app.query` `[S]` ✅ 2026-04-03
  - 验收: ForwardReturnService 在 ditto_app.query，旧位置已删除（无循环依赖风险），arch-check 通过
  - 关键发现: 不能迁到 analytics（依赖 MarketService，违反 analytics-isolation）；不能 re-export shim（ditto_data→ditto_app 循环依赖）
  - 正确路径: 直接迁移到 ditto_app.query + 删除旧文件 + 测试迁移到 packages/app/tests/
  - 文件:
    - 新建: `packages/app/src/ditto_app/query/forward_return_service.py`
    - 删除: `packages/data/src/ditto_data/services/forward_return_service.py`（非 re-export，避免循环）
    - 迁移: `packages/data/tests/unit/services/test_forward_return_service_unit.py` → `packages/app/tests/unit/query/`
    - 修改: `packages/app/src/ditto_app/query/evaluation.py` → 本地导入
    - 修改: `packages/app/src/ditto_app/query/__init__.py` → 导出 ForwardReturnService
    - 修改: `packages/app/src/ditto_app/providers.py` → 注册 forward_return_service provider

---

### Phase C: TradingOrchestrator 实现

**复杂度: L+ | 风险: MEDIUM | 4 PR**（依赖 Phase A）

关键事实（源码验证修正）：
- **EngineLoop 已实现 8 步日循环** — TradingOrchestrator 是对 EngineLoop 的形式化抽象，非从零构建
- **Brokerage Protocol 已存在** — `execution/brokerage.py` 含全部 4 方法
- **AccountView 已存在** — frozen + MappingProxyType 包裹 positions
- **5 种 Engine 域事件已定义** — `events.py` 但未接入 EngineLoop
- **DecisionFrame = pl.DataFrame** — 需要替换为 frozen dataclass

- [x] **Task C.1**: 定义 Stage 数据合约 `[S]` ✅ 2026-04-03
  - 验收: AlphaOutput/PortfolioOutput frozen dataclass + 列校验 + 9 个单元测试
  - 文件:
    - 新建: `packages/engine/src/ditto_engine/orchestrator/__init__.py`
    - 新建: `packages/engine/src/ditto_engine/orchestrator/contracts.py`
    - 新建: `packages/engine/tests/unit/orchestrator/test_contracts_unit.py`

- [x] **Task C.2**: 定义 TradingOrchestrator Protocol `[S]` ✅ 2026-04-03
  - 验收: Protocol 定义 run() -> EngineResult，EngineLoop 隐式满足，2 个单元测试
  - 文件:
    - 新建: `packages/engine/src/ditto_engine/orchestrator/protocol.py`
    - 新建: `packages/engine/tests/unit/orchestrator/test_protocol_unit.py`

- [x] **Task C.3**: 接入 Engine 域事件到 EngineLoop `[M]` ✅ 2026-04-03
  - 验收: EngineOptions 可选接受 EventBus，关键点发布 OrderSubmitted/OrderFilled/RiskGuardTriggered
  - 接入点:
    - `_run_pre_trade_checks`: place_order 后发布 OrderSubmitted
    - `_step`: process_pending 后每个 fill 发布 OrderFilled
    - `_step`: PostTrade 风控扫描发布 RiskGuardTriggered
  - EventBus=None 时零副作用（4 个测试验证）
  - 文件:
    - 修改: `packages/engine/src/ditto_engine/backtest/engine.py` → EngineOptions 增加 event_bus
    - 新建: `packages/engine/tests/unit/backtest/test_engine_events_unit.py`

- [x] **Task C.4**: EngineLoop 别名 BacktestTradingOrchestrator `[M]` ✅ 2026-04-03
  - 验收: BacktestTradingOrchestrator = EngineLoop，orchestrator/__init__.py 导出，2 个单元测试
  - 文件:
    - 修改: `packages/engine/src/ditto_engine/backtest/engine.py` → alias
    - 修改: `packages/engine/src/ditto_engine/__init__.py` → 导出
    - 新建: `packages/engine/tests/unit/orchestrator/test_backtest_orchestrator_unit.py`

> **注**: AlphaOutput/PortfolioOutput 合约已在后续收尾工作中删除，因其在主流程中从未被使用。
> 引擎循环继续使用 `DecisionFrame`（polars DataFrame + 列名约定）进行 Stage 间数据流。

---

### Phase D: DI 下沉到各包

**复杂度: L | 风险: MEDIUM | 1 PR**（依赖 Phase A）

> **方案调整**：Task D.2（Engine DI 下沉）不可行——golden/quality providers 导入 `ditto_data.quality`，
> 违反 `engine-no-data-dependency` 规则。改为全部归入 `ditto_data.di`。Engine 是纯领域包，无需 DI。

- [x] **Task D.1**: Data DI 下沉（含原 D.2 + D.3 合并） `[L]` ✅ 2026-04-03
  - 验收: `packages/data/src/ditto_data/di/` 提供 `get_data_providers()`，registry/datahub/ 和 registry/core/ 已删除
  - 关键决策:
    - golden/quality providers 归入 ditto_data（非 ditto_engine），因导入 `ditto_data.quality`
    - 新增 `ditto-infra` 依赖（providers 导入 SQLitePool/DataCache/FileLockManager）
    - Engine 纯领域包无需 DI（所有创建由 ditto_app.builders 负责）
  - 文件:
    - 新建: `packages/data/src/ditto_data/di/__init__.py`（聚合 10 个 providers）
    - 迁移: `apps/interfaces/registry/datahub/*.py`（8 providers + builders）→ `packages/data/src/ditto_data/di/`
    - 迁移: `apps/interfaces/registry/core/golden.py`, `quality.py` → `packages/data/src/ditto_data/di/`
    - 删除: `apps/interfaces/src/ditto_interfaces/registry/datahub/`（整个目录）
    - 删除: `apps/interfaces/src/ditto_interfaces/registry/core/`（整个目录）
    - 修改: `apps/interfaces/src/ditto_interfaces/registry/__init__.py`（直接从 ditto_data.di re-export）
    - 修改: `apps/interfaces/src/ditto_interfaces/registry/container.py`（使用 get_data_providers）
    - 修改: `packages/data/pyproject.toml`（添加 ditto-infra 依赖）
    - 修改: 4 个测试文件导入路径更新
  - 验证: lint ✅ type ✅ arch-check ✅ 4315 tests passed ✅

---

### Phase E: Interfaces 层依赖清理

**复杂度: L | 风险: MEDIUM | 1 PR**（依赖 Phase D）

> **实际执行发现**：代码层面 routes/cli/models 已在前序 PR 中完成迁移（0 处 ditto_data 残留）。
> Phase E 实际只需：(1) 修复 dq_batch.py 3 处残留导入 + L3BatchService 参数名 bug；(2) 清理 .importlinter 10 条过期 ignore。

- [x] **Task E.1-E.5**: 全量 Interfaces 依赖清理 `[M]` ✅ 2026-04-03
  - 验收: 18 条 importlinter 合约全通过（10 条过期 ignore 已删除），4367 tests passed
  - 变更:
    - 修复 `jobs/tasks/dq_batch.py`: 3 处 ditto_data 导入 → ditto_app.types + L3BatchService 参数名修正 + MarketQueryFacade 替换 MarketBarsQuery
    - 新增 `ditto_app.types` re-export: QualityEngine
    - 清理 `.importlinter` port-service-isolation: 删除 10 条过期非 registry ignore（routes 3 + CLI query 2 + models 4 + CLI executor 1）
    - 修复 7 个测试（参数名对齐 + import 路径 + DI 容器补全 FundamentalProvider/MacroProvider）
    - 修复 13 处 E501 行长度违规

---

### Phase F: 固化收尾

**复杂度: M | 风险: LOW | 1 PR**

- [x] **Task F.1**: Importlinter 收紧 `[S]` ✅ 2026-04-03
  - 验收: analytics-isolation ignore 确认仍必要, 3 条过期 ignore 清理, `unmatched_ignore_imports_alerting` 收紧为 `warn`
 (warn 发现 3 条过期 ignore)
  - 文件: .importlinter

- [x] **Task F.2**: 文档同步 `[M]` ✅ 2026-04-03
  - 验收: 所有 CLAUDE.md 反映最终架构, 含 orchestrator/ 和 TradingOrchestrator
  - 文件: root CLAUDE.md + packages/engine/CLAUDE.md + apps/interfaces/CLAUDE.md + packages/analytics/CLAUDE.md(新建) + packages/app/CLAUDE.md(新建) + .claude/rules/architecture.md + .claude/rules/config.md + .claude/rules/core.md
- [x] **Task F.3**: CI 全量验证 `[S]` ✅ 2026-04-03
  - 验收: 18 条 importlinter 合约全通过(0 broken, 0 warnings), 4367 tests passed
  - 命令: `pixi run -e dev ci` + `pixi run -e dev test`

---

### 总览表

| Phase | PRs | 风险 | 依赖 | 复杂度 |
|-------|-----|------|------|--------|
| **A: 目录重命名** | 1 | LOW | 无 | M |
| **B: ForwardReturn 迁移** | 1 | LOW | 无（可与 A 并行） | S |
| **C: TradingOrchestrator** | 4 | MEDIUM | Phase A | L+ |
| **D: DI 下沉** | 1 | MEDIUM | Phase A | L |
| **E: Interfaces 清理** | 5 | MEDIUM | Phase D | L |
| **F: 固化收尾** | 1 | LOW | Phase C + E | M |
| **总计** | **~13 PR** | | | |

### 关键风险缓解

1. **Phase A**: 先执行并验证 `pixi run -e dev check`，确保 CI 配置正确
2. **Phase C**: 所有变更为增量式 — Protocol 和合约为新文件，EventBus 可选注入，EngineBus=None 时零副作用
3. **Phase D**: Strangler 模式 — 保留 re-export shim，验证后再删除
4. **Phase E**: 按 route group 分 PR，每个 PR 限制爆炸半径，arch-check 独立验证
