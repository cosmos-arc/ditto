# PR #62 Code Review 修复计划

## 概述
- Sprint: V1 Sprint | Phase: Code Review Fixes
- 创建: 2026-04-26
- 来源: PR #62 自动化 Code Review（5 Agent 并行审查 + 置信度评分）

## 修复总览

共 11 个问题（置信度 25-90），按影响分组为 5 个 Phase：

| Phase | 问题数 | 置信度范围 | 影响级别 |
|-------|--------|-----------|---------|
| A: Engine 核心修复 | 2 | 85-90 | 功能缺陷 |
| B: CLAUDE.md 合规 | 3 | 90 | 规范违规 |
| C: Barrel 拆分 | 3 | 65 | 架构规范 |
| D: 数据层正确性 | 3 | 50-75 | 正确性 |
| E: 次要改进 | 3 | 25-35 | 代码质量 |

## 技术方案

### Phase A: Engine 核心修复（功能缺陷）

**A1: `execution_delay > 0` 导致调仓日被 skip（置信度 90）**

根因：`_step()` 中 StrategyStep 生成 `target_portfolio` 后入队并置 `None`，PlanningStep 收到 `None` 返回 `fail()`，整日被 skip。

修复：在 `_step()` 的 step chain 循环中，当 `delay > 0 && deferred_signal is None && step is PlanningStep` 时跳过 PlanningStep。这确保信号入队后 PlanningStep 不会因空 target 而失败。

```python
# engine.py _step() - 在 step chain 循环内添加跳过逻辑
if delay > 0 and deferred_signal is None and isinstance(step, PlanningStep):
    continue
```

**A2: `_execute_delayed_signal()` 跳过 AuditStep（置信度 85）**

根因：flush 尾部信号时显式跳过 AuditStep，导致 fills 无审计记录。

修复：从 `_execute_delayed_signal()` 的 skip list 中移除 `AuditStep`，让它正常执行。AuditStep 只读取 ctx 中的数据（account_view, step_fills），不依赖被跳过的 DataFetchStep/RiskScanStep/StrategyStep 的输出。

```python
# engine.py _execute_delayed_signal() - 从跳过列表移除 AuditStep
if isinstance(step, (DataFetchStep, RiskScanStep, StrategyStep)):
    continue  # 不再跳过 AuditStep
```

### Phase B: CLAUDE.md 合规（规范违规，3 个 PR 反复出现）

**B1: 移除 8 个文件中不必要的 TYPE_CHECKING（置信度 90）**

8 个文件无实际循环依赖，直接改为常规 import：

| 文件 | 导入目标 |
|------|---------|
| `data/services/market_service.py` | `MarketReaders` |
| `data/services/capital_service.py` | `CapitalReaders, CapitalWriters` |
| `data/services/fundamental_service.py` | `FundamentalReaders, FundamentalWriters` |
| `data/services/source_service.py` | `FredSource, DataSources, TushareSource` |
| `app/process/ingestion/commodity_fetcher.py` | `CommodityFetcher, MacroFetcher` |
| `app/process/ingestion/list_date_inference.py` | `MarketFetcher` |
| `app/query/source.py` | `FredSource, TushareSource` |
| `interfaces/api/routes/source.py` | `TushareSource` |

**B2: 重构 `fetch_handlers.py` 循环依赖（置信度 90）**

`fetch_handlers.py` ↔ `coordinator.py` 存在真实循环依赖（`coordinator` 导入 `fetch_handlers` 的 builder 函数，`fetch_handlers` TYPE_CHECKING 导入 `coordinator` 的 `SourceFetchers`）。

修复：将 `SourceFetchers` NamedTuple 提取到 `app/process/ingestion/types.py`。

**B3: 修复 `main.py` noqa E402（置信度 90）**

将 lines 319/321 的 `DataError, DittoError, data_error_handler, ditto_error_handler` 导入移至文件顶部。这些符号不依赖任何模块级局部变量。

### Phase C: Barrel 符号数拆分（架构规范）

**C1: `data/sources/__init__.py`（23 符号 → ≤15）**

当前混合了 7 个子模块的 re-export。按职责拆分为子域入口：

- `data/sources/__init__.py` — 保留仅 error classes（5 个）+ 核心抽象（DataSources, SourceRegistry）
- 消费者直接从叶模块导入：`from ditto_data.sources.protocols import MarketFetcher`

**C2: `analytics/factors/__init__.py`（17 符号 → ≤15）**

当前 re-export 12 个因子分类常量 + 3 个核心类型。拆分：

- `__init__.py` — 保留 `FactorSpec, FactorContext, validate_factor_specs, ALL_FACTOR_SPECS`（4 个核心符号）
- 消费者直接从分类模块导入：`from ditto_analytics.factors.value import VALUES`

**C3: `kernel/__init__.py`（39 符号 → ≤30）**

这是最大的 barrel。注意 Kernel CLAUDE.md 同时认可两种导入模式，存在规则冲突。策略：

- `__init__.py` — 保留每个子域的最常用 2-3 个符号（约 25-28 个）
- 低频使用的次要符号移除出 barrel，消费者从子模块导入
- 更新 Kernel CLAUDE.md 统一规范

### Phase D: 数据层正确性

**D1: 修复 `_build_actual_navs` fallback（置信度 75）**

当前 fallback 路径只减 `fee` 不跟踪交易现金流，NAV 完全不准确。虽然 DI 总是注入 `market_facade`（fallback 不可达），但作为防御性编程：

修复：将 `price_query` 改为必需参数（构造函数中 `market_facade: MarketQueryFacade`，去掉 `| None`）。移除 fallback 路径。

**D2: 修复 `sqlite_store.py` falsy date 检查（置信度 50）**

`if start_date:` → `if start_date is not None:`，涉及 `read()` 和 `delete()` 两个方法共 5 处。

**D3: 修复 `signal_writer.py` TOCTOU 竞态（置信度 50）**

`expected_current=None` 时 SQL 无状态前置条件。修复：当 `expected_current is None` 时抛出 `ValueError`，强制调用者始终提供状态前置条件。同步更新 `UpdateIntentStatusHandler` 确保 `expected_current` 始终非 None。

### Phase E: 次要改进

**E1: ManualTracker 延迟加载交易日历（置信度 25）**

将 10 年交易日历改为按需加载。在 `ManualTracker` 中注入 `MetadataService` 引用，首次使用时加载。

**E2: `as_of_date` 验证增强（置信度 35）**

`list_corporate_actions` 路由中 `as_of_date` 传播已正确。增加防御性验证：若 `as_of_date` 为未来日期则返回 400。

**E3: `TushareSource` 耦合 → Protocol（置信度 25）**

当前 `interfaces/api/routes/source.py` 直接依赖具体类型 `TushareSource`。定义 `DataSourceProtocol` 并让 `TushareSource` 实现，route 层依赖 Protocol 而非具体类。

---

## 任务清单

### Phase A: Engine 核心修复（优先级 P0）

- [x] **A1**: 修复 `execution_delay` 导致调仓日 skip `[M]`
  - 验收: `execution_delay=1` 回测，前 N 个调仓日不再被 skip；`execution_delay=0` 行为不变
  - 文件: `packages/engine/src/ditto_engine/backtest/engine.py`
  - 测试: 新增 `test_delay_1_no_skipped_dates` + `test_delay_1_flush_runs_audit_step`
  - 实现: `_step()` 循环中 `delay > 0 and deferred_signal is None and isinstance(step, PlanningStep)` 时 `continue`

- [x] **A2**: 修复 `_execute_delayed_signal` 审计记录缺失 `[M]`
  - 验收: `execution_delay > 0` 回测，尾部 flush 的 fills 出现在 audit collector 中
  - 文件: `packages/engine/src/ditto_engine/backtest/engine.py`
  - 测试: 新增 `test_delay_1_flush_runs_audit_step` 验证 4 次 record_account_view 调用
  - 实现: 从 skip list 移除 `AuditStep`，仅跳过 `DataFetchStep/RiskScanStep/StrategyStep`

### Phase B: CLAUDE.md 合规（优先级 P1）

- [x] **B1**: 移除 8 个文件中不必要的 TYPE_CHECKING `[S]`
  - 文件: 8 个文件全部改为常规顶层导入
  - 验收: basedpyright 0 errors, 5851 tests passed

- [x] **B2**: 重构 `fetch_handlers.py` 循环依赖 `[M]`
  - 新增: `packages/app/src/ditto_app/process/ingestion/types.py`（SourceFetchers NamedTuple）
  - 修改: coordinator.py / fetch_handlers.py 消除 TYPE_CHECKING 循环
  - 验收: 196 ingestion tests passed

- [x] **B3**: 修复 `main.py` noqa E402 `[S]`
  - 实现: 将 DataError/DittoError/data_error_handler/ditto_error_handler 导入移至文件顶部
  - 验收: `noqa: E402` 全部移除

### Phase C: Barrel 拆分（优先级 P2）

- [x] **C1**: 拆分 `data/sources/__init__.py`（21 → 8）`[M]`
  - 仅保留 6 error classes + SourceRegistry + DataSources
  - 13 符号移除，25 个消费者文件更新
  - 验收: 5848 tests passed, 0 broken

- [x] **C2**: 跳过 — 实际 `__all__` 已为 15 符号（≤15 阈值）

- [x] **C3**: 拆分 `kernel/__init__.py`（38 → 30）`[L]`
  - 移除 quality (4) + research (4) 子模块符号（0 barrel 消费者）
  - 更新 Kernel CLAUDE.md 导入规范
  - 验收: 33 arch contracts KEPT, 0 broken

### Phase D: 数据层正确性（优先级 P2）

- [x] **D1**: 修复 `_build_actual_navs` fallback `[S]`
  - `market_facade` 改为必需参数，移除 fallback 路径
  - `_build_actual_navs_full` 内联到 `_build_actual_navs`
  - 删除 3 个 dead-code 测试

- [x] **D2**: 修复 `sqlite_store.py` falsy date 检查 `[S]`
  - `if start_date:` → `if start_date is not None:` (5 处)

- [x] **D3**: 修复 `signal_writer.py` TOCTOU 竞态 `[S]`
  - `expected_current` 改为必需参数（移除 `= None`）
  - `UpdateIntentStatusHandler` 终态场景 fallback 到 `(intent.status,)` 前置条件

### Phase E: 次要改进（优先级 P3）

- [x] **E1**: 跳过 — ManualTracker 已是纯 DI 注入模式，改为延迟加载会引入 I/O 依赖

- [x] **E2**: `as_of_date` 验证增强 `[S]`
  - 新增 `FutureDateError` + `_reject_future_date()` helper
  - 3 个路由均添加未来日期验证
  - 新增 4 个测试覆盖

- [x] **E3**: `TushareSource` 耦合 → DataSourceProtocol `[M]`
  - 复用已有 `MarketFetcher` Protocol，无需新建
  - route 层 `TushareSource` → `MarketFetcher`

---

## 执行顺序

```
Phase A (P0) ─── 功能缺陷，优先修复
  A1, A2 可并行

Phase B (P1) ─── 规范违规，3 个 PR 反复出现
  B1, B2, B3 可并行

Phase D (P2) ─── 数据层正确性
  D1, D2, D3 可并行

Phase C (P2) ─── 架构规范（影响面广）
  C1, C2 可并行 → C3（在 C1/C2 之后）

Phase E (P3) ─── 次要改进
  E1, E2, E3 可并行
```

## 统计

| 维度 | 数量 |
|------|------|
| 总任务数 | 14 |
| 复杂度 S | 7 |
| 复杂度 M | 5 |
| 复杂度 L | 1（C3 kernel barrel） |
| 新增文件 | 2（types.py, DataSourceProtocol 在 protocols.py 中） |
| 修改文件 | ~30+ |
| Kill Switch 风险 | 2（A1, A2 engine 回测核心） |
