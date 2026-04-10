# App 层 CQRS 重构 — 实施计划

> 日期：2026-04-10
> 状态：已完成
> 基于设计文档：`docs/plans/2026-04-10-app-layer-cqrs-redesign.md`（第 1-11 节）

## 概述

将 `packages/app/src/ditto_app/process/` 从 30+ 文件平铺结构，重构为 CQRS 模式：
- **command/** — 原子写操作（DTO + Handler）
- **process/** — 有状态长流程（按能力域分子包：ingestion/materialization/execution）
- **query/** — 不变
- **builders/** — 不变

## 技术方案

### 核心决策（沿用设计文档 §6）

1. **经典 CQRS 风格**：Command Handler 处理原子写，Process Manager 处理长流程
2. **按能力域拆子包**：ingestion / materialization / execution
3. **Milan Jovanovic 风格**：DTO + Handler 放同一文件
4. **质量检查 = Command**（带副作用的写操作）
5. **Process Manager 直接接收 Trigger**（不经 Command Handler 桥接）

### 迁移分 3 阶段

| 阶段 | 目标 | 风险 |
|------|------|------|
| Phase 1 | 结构搬迁（纯文件移动） | 低 — 不改行为 |
| Phase 2 | 职责拆分（行为变更） | 中 — 改变调用链 |
| Phase 3 | 收尾（DI + 文档） | 低 |

---

## Phase 1：结构搬迁（纯文件移动，零行为变更）

### Task 1.1：创建 process/ingestion/ 子包 `[L]`

**目标**：将所有 ingestion 相关文件移入 `process/ingestion/` 子包。

**文件移动映射**（14 个文件）：

| 源文件 | 目标位置 |
|--------|---------|
| `process/ingestion_coordinator.py` | `process/ingestion/coordinator.py` |
| `process/coordinator_factory.py` | `process/ingestion/coordinator_factory.py` |
| `process/ingestion_config.py` | `process/ingestion/config.py` |
| `process/data_writer.py` | `process/ingestion/data_writer.py` |
| `process/result_handler.py` | `process/ingestion/result_handler.py` |
| `process/metadata_manager.py` | `process/ingestion/metadata_manager.py` |
| `process/list_date_inference.py` | `process/ingestion/list_date_inference.py` |
| `process/auto_init.py` | `process/ingestion/auto_init.py` |
| `process/backfill_handler.py` | `process/ingestion/backfill_handler.py` |
| `process/backfill_manager.py` | `process/ingestion/backfill_manager.py` |
| `process/retry_manager.py` | `process/ingestion/retry_manager.py` |
| `process/_commodity_fetcher.py` | `process/ingestion/commodity_fetcher.py`（去掉下划线前缀） |
| `process/_coordinator_constants.py` | `process/ingestion/coordinator_constants.py`（去掉下划线前缀） |
| `process/_fetch_handlers.py` | `process/ingestion/fetch_handlers.py`（去掉下划线前缀） |

**内部导入更新**（文件间交叉引用）：
- `coordinator.py` → 引用同目录文件（去掉 `process.` 前缀）
- `coordinator_factory.py` → `coordinator.py`、`config.py`、`quality`（暂保留）
- `backfill_manager.py` → `coordinator.py`、`result_handler.py`
- `retry_manager.py` → `coordinator.py`、`result_handler.py`
- `config.py` → `quality`（暂保留）

**外部导入更新**（interfaces 层 3 个文件 + providers.py）：
- `interfaces/.../registry/contexts/ingestion.py` — 4 处（BackfillManager, create_coordinator, IngestionCoordinatorConfig, QualityService）
- `interfaces/.../registry/contexts/bundle.py` — 4 处（BackfillManager, IngestionCoordinator, retry_manager, 等）
- `interfaces/.../cli/executor.py` — 2 处（BackfillManager, IngestionCoordinator）
- `interfaces/.../jobs/flows/daily.py` — 1 处（count_results）

**测试导入更新**（~17 个文件）：
- `tests/unit/process/ingestion/` 下 13 个测试文件
- `tests/unit/test_coordinator_factory_unit.py`
- `tests/unit/test_commodity_fetcher_unit.py`
- `tests/unit/test_coordinator_constants_unit.py`
- `interfaces/tests/` 下 4+ 个文件

**验收标准**：
- [ ] 所有文件移入 `process/ingestion/`，原文件删除
- [ ] 所有内部导入更新完毕
- [ ] 所有外部导入更新完毕
- [ ] `pixi run -e dev test --unit` 通过
- [ ] `pixi run -e dev arch-check` 通过

---

### Task 1.2：创建 process/materialization/ 子包 `[L]`

**目标**：将所有 materialization 相关文件移入 `process/materialization/` 子包。

**文件移动映射**（10 个文件）：

| 源文件 | 目标位置 |
|--------|---------|
| `process/materialization_orchestrator.py` | `process/materialization/orchestrator.py` |
| `process/cascade_orchestrator.py` | `process/materialization/cascade_orchestrator.py` |
| `process/publication_facade.py` | `process/materialization/publication_facade.py` |
| `process/_publication_helpers.py` | `process/materialization/publication_helpers.py`（去掉下划线前缀） |
| `process/materialization_dependencies.py` | `process/materialization/dependencies.py` |
| `process/materialization_helpers.py` | `process/materialization/helpers.py` |
| `process/certification_rules.py` | `process/materialization/certification_rules.py` |
| `process/runtime_input_provider.py` | `process/materialization/runtime_input_provider.py` |
| `process/materialization_types.py` | `process/materialization/types.py` |
| `process/factor_orthogonalization.py` | `process/materialization/factor_orthogonalization.py` |

**内部导入更新**：
- `orchestrator.py` → `types.py`、`dependencies.py`、`helpers.py`、`runtime_input_provider.py`、`factor_orthogonalization.py`
- `runtime_input_provider.py` → `types.py`、`dependencies.py`
- `publication_facade.py` → `publication_helpers.py`、`certification_rules.py`
- `cascade_orchestrator.py` → `orchestrator.py`

**外部导入更新**：
- `interfaces/.../registry/contexts/materialization.py` — 3 处
- `interfaces/.../registry/contexts/bundle.py` — 3 处
- `providers.py` — 4 处

**测试导入更新**（~12 个文件）：
- `tests/unit/process/materialization/` 下 10 个测试文件
- `tests/unit/test_materialization_unit.py`
- `tests/unit/test_providers_unit.py`
- `interfaces/tests/` 下 3+ 个文件

**验收标准**：
- [ ] 所有文件移入 `process/materialization/`，原文件删除
- [ ] 所有导入更新完毕
- [ ] `pixi run -e dev test --unit` 通过
- [ ] `pixi run -e dev arch-check` 通过

---

### Task 1.3：创建 process/execution/ 子包 `[M]`

**目标**：将策略执行相关文件移入 `process/execution/` 子包。

**文件移动映射**（4 个文件）：

| 源文件 | 目标位置 |
|--------|---------|
| `process/backtest_service.py` | `process/execution/backtest_process.py` |
| `process/strategy_run_service.py` | `process/execution/strategy_run_process.py` |
| `process/backtest_serialization.py` | `process/execution/backtest_serialization.py` |
| `process/strategy_types.py` | `process/execution/strategy_types.py`（Phase 1 先整体移动，Phase 2 拆分） |

**外部导入更新**：
- `interfaces/.../cli/commands/strategy.py` — 2 处
- `interfaces/.../registry/contexts/bundle.py` — 1 处
- `interfaces/.../registry/contexts/strategy.py` — 1 处
- `providers.py` — 1 处

**测试导入更新**（~13 个文件）：
- `tests/unit/process/strategy/` 下 10 个测试文件
- `tests/unit/test_backtest_serialization_unit.py`
- `tests/unit/test_providers_unit.py`
- `interfaces/tests/` 下 3+ 个文件

**验收标准**：
- [ ] 所有文件移入 `process/execution/`，原文件删除
- [ ] 所有导入更新完毕
- [ ] `pixi run -e dev test --unit` 通过
- [ ] `pixi run -e dev arch-check` 通过

---

### Task 1.4：质量模块归入 process/quality/ 子包（临时） `[M]`

**目标**：将质量相关文件归入 `process/quality/` 子包，为 Phase 2 迁入 command/ 做准备。删除 `quality.py` re-export shim，用 `__init__.py` 替代。

**文件移动映射**（5 个文件 → quality/ 子包）：

| 源文件 | 目标位置 |
|--------|---------|
| `process/quality.py`（re-export shim） | 删除（由 `__init__.py` 替代） |
| `process/quality_check.py` | `process/quality/quality_check.py` |
| `process/quality_l3.py` | `process/quality/l3_batch.py` |
| `process/quality_reconciliation.py` | `process/quality/reconciliation.py` |
| `process/quality_protocols.py` | `process/quality/protocols.py` |
| `process/quality_types.py` | `process/quality/types.py` |

**创建 `process/quality/__init__.py`**（临时向后兼容，Phase 2 迁入 command/ 后删除）：
```python
from ditto_app.process.quality.quality_check import QualityService
from ditto_app.process.quality.l3_batch import L3BatchService
from ditto_app.process.quality.reconciliation import QualityReconciliationService
from ditto_app.process.quality.protocols import QualityEngineProtocol
from ditto_app.process.quality.types import L3CheckResult
```

**外部导入不需要更新**（`from ditto_app.process.quality import X` 保持不变，通过 `__init__.py` re-export）。

**验收标准**：
- [ ] 质量子模块文件移入 `process/quality/`
- [ ] `quality.py` shim 删除，`__init__.py` re-export 替代
- [ ] 所有已有测试不修改、通过
- [ ] `pixi run -e dev test --unit` 通过
- [ ] `pixi run -e dev arch-check` 通过

---

### Task 1.5：清理 process/ 根目录 + 全量验证 `[S]`

**目标**：确认 process/ 根目录只剩子包目录和 `__init__.py`。

**验证清单**：
- `process/` 根目录不再有任何 .py 文件（只有 `__init__.py` + 子包目录 `ingestion/`、`materialization/`、`execution/`、`quality/`）
- `pixi run -e dev check` 全部通过
- `pixi run -e dev arch-check` 全部通过

**验收标准**：
- [ ] process/ 根目录只有 `__init__.py` + 4 个子包目录
- [ ] `pixi run -e dev check` 通过
- [ ] 无遗留的旧路径引用

---

## Phase 2：职责拆分（行为变更）

### Task 2.1：拆分 IngestionCoordinator → Command Handler + Process Manager `[L]`

**目标**：将 `IngestionCoordinator` 的单日摄取逻辑提取为 `IngestDateHandler`（Command），日期范围编排保留为 `IngestRangeProcess`（Process）。

**具体操作**：

1. **创建 `command/ingestion.py` Handler**：
   ```python
   # command/ingestion.py（已有 DTO，新增 Handler）
   class IngestDateHandler:
       """单日入库的原子写操作."""
       def __init__(self, coordinator: IngestionCoordinator) -> None:
           self._coordinator = coordinator

       def handle(self, command: IngestDateCommand) -> IngestionResult:
           return self._coordinator.ingest_date(
               command.dataset, command.trade_date, force=command.force
           )
   ```

2. **创建 `process/ingestion/range_process.py`**：
   ```python
   @dataclass(frozen=True)
   class IngestRangeTrigger:
       dataset: str
       start_date: date
       end_date: date
       force: bool = False
       parallel: int = 4

   class IngestRangeProcess:
       """日期范围摄取 — Process Manager."""
       def __init__(self, handler: IngestDateHandler) -> None:
           self._handler = handler

       def run(self, trigger: IngestRangeTrigger) -> None:
           # 原 BackfillManager.backfill_range() 的范围编排逻辑
   ```

3. **同步拆分 BackfillManager**：
   - `command/backfill.py`：`BackfillGapCommand` + `BackfillGapHandler`（单次 gap 填充）
   - `process/ingestion/backfill_process.py`：`BackfillRangeTrigger` + `BackfillRangeProcess`（范围编排 + 并行）

4. **更新 `command/__init__.py` 导出**

**测试要求**：
- `IngestDateHandler.handle()` 单元测试
- `IngestRangeProcess.run()` 单元测试
- `BackfillGapHandler` 单元测试
- `BackfillRangeProcess` 单元测试

**验收标准**：
- [ ] `IngestDateHandler` 实现并测试
- [ ] `IngestRangeProcess` + `IngestRangeTrigger` 实现并测试
- [ ] `BackfillGapHandler` + `BackfillGapCommand` 实现并测试
- [ ] `BackfillRangeProcess` + `BackfillRangeTrigger` 实现并测试
- [ ] 原 `IngestionCoordinator` 保留为编排核心（Handler 委托它执行）
- [ ] `pixi run -e dev test --unit` 通过

---

### Task 2.2：质量检查 → Command Handler `[L]`

**目标**：将质量检查从共享 Service 提升为显式 Command Handler，文件从 `process/quality/` 迁入 `command/`。

**具体操作**：

1. **创建 `command/quality_check.py`**：
   ```python
   @dataclass(frozen=True)
   class CheckDataQualityCommand:
       df: pl.DataFrame
       dataset: str

   class CheckDataQualityHandler:
       def __init__(self, engine: QualityEngineProtocol,
                    writer: QuarantineWriterProtocol) -> None: ...
       def handle(self, cmd: CheckDataQualityCommand) -> tuple[pl.DataFrame, bool]: ...
   ```

2. **创建 `command/quality_l3.py`**：`L3BatchCheckCommand` + `L3BatchCheckHandler`

3. **创建 `command/quality_reconciliation.py`**：`ReconcileSourcesCommand` + `ReconcileSourcesHandler`

4. **迁入 command/**：
   - `process/quality/quality_check.py` → `command/quality_check.py`（包装为 Handler）
   - `process/quality/l3_batch.py` → `command/quality_l3.py`（包装为 Handler）
   - `process/quality/reconciliation.py` → `command/quality_reconciliation.py`（包装为 Handler）
   - `process/quality/protocols.py` → 各 Handler 内部依赖（QualityEngineProtocol, QuarantineWriterProtocol 等）
   - `process/quality/types.py` → `command/` 或按需归入 kernel

5. **删除 `process/quality/` 目录**

6. **更新所有消费者导入**（从 `process.quality` → `command.*`）：
   - `providers.py` — 1 处
   - `process/ingestion/config.py` — 1 处
   - `process/ingestion/coordinator_factory.py` — 1 处
   - `interfaces/.../ingestion.py` — 1 处
   - `interfaces/.../dq_batch.py` — 1 处
   - `interfaces/.../context.py` — 1 处

**测试要求**：
- 每个 Handler 的 `handle()` 方法单元测试
- 已有质量测试迁移到 `tests/unit/command/` 目录

**验收标准**：
- [ ] 3 个 Command Handler 实现并测试
- [ ] `process/quality/` 目录删除
- [ ] 所有消费者导入更新
- [ ] `pixi run -e dev check` 通过

---

### Task 2.3：策略命令 DTO 重命名 → Trigger DTO `[M]`

**目标**：将 Process Manager 的输入 DTO 从 Command 命名空间移到 Process 子包，命名为 `*Trigger`。

**具体操作**：

1. **在 `process/execution/types.py` 添加**：
   ```python
   @dataclass(frozen=True)
   class BacktestTrigger:
       strategy_id: str
       start_date: date
       end_date: date

   @dataclass(frozen=True)
   class StrategySliceTrigger:
       strategy_id: str
       trade_date: date
   ```

2. **删除 `command/strategy.py`**（`RunBacktestCommand` → `BacktestTrigger`）

3. **更新 `BacktestService` 接口**（渐进，保持内部兼容）

4. **更新 `StrategyFacade` 接口**

5. **更新 `command/__init__.py` 删除 strategy 相关导出**

**测试要求**：
- Trigger DTO 创建测试
- 更新已有 `test_commands.py`

**验收标准**：
- [ ] Trigger DTO 定义在 `process/execution/types.py`
- [ ] `command/strategy.py` 删除
- [ ] Process Manager 接受 Trigger DTO
- [ ] 测试更新并通过

---

### Task 2.4：strategy_types.py 拆分 `[M]`

**目标**：将混合文件拆分为纯类型 + 纯逻辑。

**具体操作**：

1. **`process/execution/types.py`**（纯类型定义）：
   - `RunLifecycleService` Protocol
   - `BacktestProcessConfig` / `StrategyRunProcessConfig`
   - `BacktestTrigger` / `StrategySliceTrigger`（Task 2.3 已添加）

2. **`process/execution/strategy_input.py`**（逻辑实现）：
   - `StrategyInputAssembler`
   - `enrich_record_with_symbol()`
   - `write_backtest_artifacts()`

3. **删除 `process/execution/strategy_types.py`**

**验收标准**：
- [ ] types.py 仅含 Protocol / dataclass / Trigger DTO
- [ ] strategy_input.py 仅含逻辑实现
- [ ] 所有导入更新
- [ ] 测试通过

---

## Phase 3：收尾

### Task 3.1：激活 CommandHandler Protocol + AppCommandProvider `[M]`

**目标**：CommandHandler Protocol 从"未使用"变为生产代码，新增 DI Provider。

**具体操作**：

1. **激活 `command/protocols.py`**：
   - 删除 `.. note:: 当前无生产代码使用此 Protocol` 注释
   - Handler 类通过鸭子类型满足 Protocol

2. **在 `providers.py` 中新增 `AppCommandProvider`**：
   ```python
   class AppCommandProvider(Provider):
       scope = Scope.APP

       @provide
       def ingest_date_handler(self, coordinator: IngestionCoordinator) -> IngestDateHandler:
           return IngestDateHandler(coordinator)

       @provide
       def quality_handler(self, engine: QualityEngineProtocol,
                           writer: QuarantineWriterProtocol) -> CheckDataQualityHandler:
           return CheckDataQualityHandler(engine, writer)
       # ... 其他 Handler
   ```

3. **更新 `get_app_providers()`**：返回 4 个 Provider

4. **更新 `AppProcessProvider`**：Process Manager 通过注入获取 Handler

**验收标准**：
- [ ] `CommandHandler` Protocol 被生产代码使用
- [ ] `AppCommandProvider` 注册所有 Handler
- [ ] Process Manager 通过 DI 获取 Handler
- [ ] `pixi run -e dev check` 通过

---

### Task 3.2：更新 importlinter 规则 `[M]`

**目标**：更新 R8 规则以反映 command/ 新内容和 process/ 子包结构。

**具体操作**：

1. **验证现有 R8 规则**仍然适用：
   - `command → query` 禁止 ✅
   - `command → builders` 禁止 ✅
   - `process → command` 允许（Process Manager 注入 Handler）→ **需确认无 forbidden 规则阻挡**
   - `command → process` → Handler 委托底层协调器（非 Process Manager）→ 不需要

2. **检查依赖方向**：
   - `process → command` ✅ 允许（IngestRangeProcess 依赖 IngestDateHandler）
   - 当前 R8 规则没有 `process → command` 的禁止规则，所以已隐式允许

3. **验证子包内部无违规**

**验收标准**：
- [ ] R8 规则完整覆盖新结构
- [ ] `pixi run -e dev arch-check` 通过
- [ ] 所有 24+ 条 contract 通过

---

### Task 3.3：更新 CLAUDE.md 文档 `[S]`

**目标**：更新 `packages/app/CLAUDE.md` 反映新结构。

**具体操作**：

1. **更新目录结构描述**：
   ```
   ditto_app/
   ├── query/              # 只读查询（零写入）
   ├── command/            # Command DTO + Handler（原子写操作）
   │   ├── ingestion.py    # IngestDateCommand + IngestDateHandler
   │   ├── quality_check.py
   │   ├── quality_l3.py
   │   ├── quality_reconciliation.py
   │   ├── backfill.py
   │   └── protocols.py    # CommandHandler Protocol
   ├── process/            # Process Manager（有状态长流程）
   │   ├── ingestion/      # 数据摄取流程
   │   ├── materialization/# 因子物化流程
   │   ├── execution/      # 策略执行流程
   │   └── [quality/ 已迁入 command/]
   ├── builders/           # 运行时装配（DI 构造）
   ├── providers.py        # 4 个 DI Provider
   └── config.py           # 数据集配置
   ```

2. **更新 DI Provider 描述**：3 个 → 4 个
3. **更新顶层 CLAUDE.md 中的 CQRS 描述**

**验收标准**：
- [ ] CLAUDE.md 反映新结构
- [ ] 文档与代码一致

---

### Task 3.4：全量验证 + 清理废弃代码 `[S]`

**目标**：最终验证 + 清理。

**具体操作**：

1. `pixi run -e dev ci` — 完整 CI 检查
2. 删除所有临时 re-export shim（如有残留）
3. 确认无 `# type: ignore` / `# noqa` 新增
4. 确认测试覆盖率 ≥ 80%
5. `pixi run -e dev arch-check` — 所有 24+ 条 contract 通过

**验收标准**：
- [ ] `pixi run -e dev ci` 通过
- [ ] 无临时兼容代码残留
- [ ] 覆盖率 ≥ 80%

---

## 执行顺序与依赖关系

```
Phase 1（结构搬迁）:
  1.1 process/ingestion/  ──┐
  1.2 process/materialization/ ──┤──→ 1.5 清理根目录
  1.3 process/execution/  ──┤
  1.4 process/quality/    ──┘

Phase 2（职责拆分）:
  2.1 IngestionCoordinator 拆分
  2.2 质量检查 → Command Handler      ──┐
  2.3 Trigger DTO 创建（依赖 2.1）       ├──→ 2.4 strategy_types 拆分（依赖 2.3）
                                          ┘

Phase 3（收尾）:
  3.1 DI Provider 激活（依赖 Phase 2 全部）
  3.2 importlinter 更新（依赖 3.1）
  3.3 文档更新（可与 3.2 并行）
  3.4 全量验证（依赖 3.1-3.3 全部）
```

**关键约束**：
- Phase 1 内 Task 1.1-1.4 **可并行**（互不依赖）
- Phase 2 内 Task 2.1 和 2.2 **可并行**，Task 2.3 依赖 2.1，Task 2.4 依赖 2.3
- Phase 3 全部依赖 Phase 2 完成

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Phase 1 导入更新遗漏 | CI 失败 | `grep -r "from ditto_app.process\." ` 全量扫描 |
| IngestionCoordinator 拆分破坏现有行为 | 回归 | 保留原接口作为薄委托层，渐进替换 |
| quality/ 迁入 command/ 后 R8 规则需更新 | arch-check 失败 | Phase 3 统一更新 |
| Process Manager 依赖 Handler 导致循环 | 编译失败 | Handler 不依赖 Process，单向依赖 |
| `_` 前缀文件改名后私有语义丢失 | 意图不明 | 子包本身就是封装边界，不再需要 `_` 前缀 |

## 测试要求

- **Phase 1**：不需要新测试（纯文件移动），已有测试验证行为不变
- **Phase 2**：每个新 Handler/Process 必须有单元测试
- **Phase 3**：`pixi run -e dev ci` 全量验证

## 不在本次范围

- Event Bus 基础设施引入
- 状态持久化实现（L0-L1 演进）
- 可插拔接口（MarketDataSource、ExecutionHandler 等）
- 回测/实盘统一抽象
- factor_orthogonalization 纯逻辑下沉到 ditto_data
- list_date_inference 纯推断下沉到 ditto_data
